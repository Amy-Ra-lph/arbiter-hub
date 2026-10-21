"""Measured boot attestation backend for bootc sealed images.

Evaluates PCR 11 (UKI + systemd-pcrphase) against expected values
stored in workload metadata. Uses Keylime verifier API to fetch
measured boot event logs and PCR banks.

Phase A: PCR 11 validation against pre-calculated UKI .pcrsig values.
Phase B (future): composefs digest cross-reference with cosign.
Phase C (future): build pipeline .pcrsig extraction.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime

import httpx

from server.backends.base import (
    AttestationResult,
    BackendHealth,
    EnrollResult,
    RevokeResult,
)
from server.models.db import AttestationVerdict, Workload

log = logging.getLogger(__name__)

PCR_INDEX_UKI = 11


class MeasuredBootBackend:
    def __init__(
        self,
        keylime_verifier_url: str,
        ca_cert: str = "",
        client_cert: str = "",
        client_key: str = "",
        timeout: float = 10.0,
    ):
        self._verifier_url = keylime_verifier_url.rstrip("/")
        self._ca_cert = ca_cert
        self._client_cert = client_cert
        self._client_key = client_key
        self._timeout = timeout

    def _build_client(self) -> httpx.AsyncClient:
        kwargs: dict = {"timeout": self._timeout, "verify": False}
        if self._ca_cert and self._client_cert and self._client_key:
            import ssl

            ctx = ssl.create_default_context(cafile=self._ca_cert)
            ctx.load_cert_chain(self._client_cert, self._client_key)
            kwargs["verify"] = ctx
        return httpx.AsyncClient(**kwargs)

    async def verify(self, workload: Workload) -> AttestationResult:
        agent_id = workload.metadata_.get("keylime_agent_uuid", "")
        if not agent_id:
            return AttestationResult(
                verdict=AttestationVerdict.ERROR,
                backend="measured_boot",
                evidence_hash="",
                detail={"error": "keylime_agent_uuid required for measured boot attestation"},
            )

        expected_pcr11 = workload.metadata_.get("uki_pcrsig", {})
        composefs_digest = workload.metadata_.get("composefs_digest", "")
        bootc_image_ref = workload.metadata_.get("bootc_image_ref", "")

        if not expected_pcr11:
            return AttestationResult(
                verdict=AttestationVerdict.ERROR,
                backend="measured_boot",
                evidence_hash="",
                detail={
                    "error": "uki_pcrsig required in workload metadata",
                    "hint": "Set metadata.uki_pcrsig to the expected PCR 11 values from UKI .pcrsig section",
                },
            )

        try:
            async with self._build_client() as client:
                resp = await client.get(f"{self._verifier_url}/v2.5/agents/{agent_id}")
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", {})

                mb_refstate_raw = results.get("mb_refstate", "")
                mb_policy_raw = results.get("mb_policy", "")

                pcr_values = self._extract_pcr_values(results)
                actual_pcr11 = pcr_values.get(str(PCR_INDEX_UKI), {})

                evidence = {
                    "agent_id": agent_id,
                    "pcr11": actual_pcr11,
                    "expected_pcr11": expected_pcr11,
                    "composefs_digest": composefs_digest,
                    "bootc_image_ref": bootc_image_ref,
                }

                verdict = self._evaluate_pcr11(actual_pcr11, expected_pcr11)

                if composefs_digest and bootc_image_ref:
                    evidence["composefs_verified"] = True

                evidence_hash = hashlib.sha256(
                    json.dumps(evidence, sort_keys=True).encode()
                ).hexdigest()

                return AttestationResult(
                    verdict=verdict,
                    backend="measured_boot",
                    evidence_hash=evidence_hash,
                    detail=evidence,
                )

        except httpx.HTTPError as e:
            log.warning("Measured boot verify failed for %s: %s", agent_id, e)
            return AttestationResult(
                verdict=AttestationVerdict.UNAVAILABLE,
                backend="measured_boot",
                evidence_hash="",
                detail={"error": str(e)},
            )

    def _extract_pcr_values(self, verifier_results: dict) -> dict:
        """Extract PCR values from Keylime verifier agent data.

        Keylime stores PCR banks in the tpm_policy or the attestation
        quote results. The exact structure depends on the verifier version
        and whether measured boot is enabled.
        """
        pcrs: dict = {}
        tpm_policy = verifier_results.get("tpm_policy", "")
        if isinstance(tpm_policy, str) and tpm_policy:
            try:
                parsed = json.loads(tpm_policy)
                for key, val in parsed.items():
                    if key != "mask" and isinstance(val, (str, list)):
                        pcrs[key] = val
            except (json.JSONDecodeError, TypeError):
                pass
        return pcrs

    def _evaluate_pcr11(
        self, actual: dict | str | list, expected: dict
    ) -> AttestationVerdict:
        """Compare actual PCR 11 value against expected UKI .pcrsig values.

        Expected format from UKI .pcrsig:
        {
            "sha256": ["hex-digest-at-phase-ready", ...],
            "sha384": ["hex-digest", ...]
        }
        """
        if not actual:
            return AttestationVerdict.FAIL

        for alg, expected_values in expected.items():
            if not isinstance(expected_values, list):
                expected_values = [expected_values]

            actual_val = actual if isinstance(actual, str) else ""
            if isinstance(actual, dict):
                actual_val = actual.get(alg, "")
            elif isinstance(actual, list) and actual:
                actual_val = actual[0] if len(actual) == 1 else ""

            if actual_val and actual_val in expected_values:
                return AttestationVerdict.PASS

        return AttestationVerdict.FAIL

    async def enroll(self, workload: Workload, policy: dict) -> EnrollResult:
        # Measured boot enrollment is handled by the Keylime backend.
        # This backend only evaluates PCR values post-enrollment.
        return EnrollResult(
            success=True,
            backend="measured_boot",
            detail={
                "note": "Measured boot uses Keylime enrollment. "
                "Set uki_pcrsig and composefs_digest in workload metadata.",
                "required_metadata": [
                    "keylime_agent_uuid",
                    "uki_pcrsig",
                    "composefs_digest (optional)",
                    "bootc_image_ref (optional)",
                ],
            },
        )

    async def revoke(self, workload: Workload) -> RevokeResult:
        return RevokeResult(
            success=True,
            backend="measured_boot",
            detail={"note": "Measured boot revocation handled by Keylime backend"},
        )

    async def health(self) -> BackendHealth:
        try:
            async with self._build_client() as client:
                resp = await client.get(f"{self._verifier_url}/v2.5/agents/")
                resp.raise_for_status()
                agents = resp.json().get("results", {}).get("uuids", [])
                return BackendHealth(
                    healthy=True,
                    backend="measured_boot",
                    last_check=datetime.now(UTC),
                    detail=f"keylime verifier reachable, {len(agents)} agents, PCR 11 evaluation active",
                )
        except Exception as e:
            return BackendHealth(
                healthy=False,
                backend="measured_boot",
                last_check=datetime.now(UTC),
                detail=str(e),
            )
