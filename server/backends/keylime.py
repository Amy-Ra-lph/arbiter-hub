import asyncio
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

DEFAULT_TPM_HASH_ALGS = ["sha256", "sha384", "sha512"]
DEFAULT_TPM_ENC_ALGS = ["rsa"]
DEFAULT_TPM_SIGN_ALGS = ["rsassa"]


class KeylimeBackend:
    def __init__(
        self,
        verifier_url: str,
        ca_cert: str,
        client_cert: str,
        client_key: str,
        registrar_url: str = "",
        timeout: float = 10.0,
    ):
        self._verifier_url = verifier_url.rstrip("/")
        self._registrar_url = registrar_url.rstrip("/") if registrar_url else ""
        self._ca_cert = ca_cert
        self._client_cert = client_cert
        self._client_key = client_key
        self._timeout = timeout

    def _build_client(self) -> httpx.AsyncClient:
        kwargs: dict = {"timeout": self._timeout, "verify": False}
        if self._ca_cert and self._client_cert and self._client_key:
            import ssl

            ctx = ssl.create_default_context(cafile=self._ca_cert)
            ctx.check_hostname = False
            ctx.load_cert_chain(self._client_cert, self._client_key)
            kwargs["verify"] = ctx
        return httpx.AsyncClient(**kwargs)

    def _build_registrar_client(self) -> httpx.AsyncClient:
        """Registrar uses a different server cert; disable verification but send mTLS client cert."""
        kwargs: dict = {"timeout": self._timeout, "verify": False}
        if self._client_cert and self._client_key:
            import ssl

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.load_cert_chain(self._client_cert, self._client_key)
            kwargs["verify"] = ctx
        return httpx.AsyncClient(**kwargs)

    async def _fetch_registrar_agent(self, agent_id: str) -> dict | None:
        """Fetch agent registration data (ak_tpm, mtls_cert, ip) from registrar."""
        if not self._registrar_url:
            return None
        try:
            async with self._build_registrar_client() as client:
                resp = await client.get(
                    f"{self._registrar_url}/v2.5/agents/{agent_id}"
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("results", {})
        except httpx.HTTPError as e:
            log.warning("Registrar fetch for %s failed: %s", agent_id, e)
            return None

    async def verify(self, workload: Workload) -> AttestationResult:
        agent_id = workload.metadata_.get("keylime_agent_uuid", "")
        if not agent_id:
            return AttestationResult(
                verdict=AttestationVerdict.ERROR,
                backend="keylime",
                evidence_hash="",
                detail={"error": "no keylime_agent_uuid in workload metadata"},
            )
        try:
            async with self._build_client() as client:
                resp = await client.get(f"{self._verifier_url}/v2.5/agents/{agent_id}")
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", {})
                op_state = results.get("operational_state", -1)
                if isinstance(op_state, str):
                    op_state_str = op_state.lower()
                else:
                    op_state_str = ""
                ima_hash = hashlib.sha256(str(results).encode()).hexdigest()
                if op_state in (3, 4) or op_state_str in ("get quote", "provide v"):
                    verdict = AttestationVerdict.PASS
                else:
                    verdict = AttestationVerdict.FAIL
                return AttestationResult(
                    verdict=verdict,
                    backend="keylime",
                    evidence_hash=ima_hash,
                    detail={"operational_state": op_state, "agent_id": agent_id},
                )
        except httpx.HTTPError as e:
            log.warning("Keylime verify failed for %s: %s", agent_id, e)
            return AttestationResult(
                verdict=AttestationVerdict.UNAVAILABLE,
                backend="keylime",
                evidence_hash="",
                detail={"error": str(e)},
            )

    async def enroll(self, workload: Workload, policy: dict) -> EnrollResult:
        agent_id = workload.metadata_.get("keylime_agent_uuid", "")
        agent_ip = workload.metadata_.get("keylime_agent_ip", "")
        agent_port = workload.metadata_.get("keylime_agent_port", 9002)
        if not agent_id or not agent_ip:
            return EnrollResult(
                success=False,
                backend="keylime",
                detail={"error": "keylime_agent_uuid and keylime_agent_ip required in metadata"},
            )

        reg_data = await self._fetch_registrar_agent(agent_id)

        ak_tpm = policy.get("ak_tpm", "")
        mtls_cert = policy.get("mtls_cert", "")
        if reg_data:
            ak_tpm = ak_tpm or reg_data.get("aik_tpm", "") or reg_data.get("ak_tpm", "")
            mtls_cert = mtls_cert or reg_data.get("mtls_cert", "")
            if not agent_ip and reg_data.get("ip"):
                agent_ip = reg_data["ip"]

        tpm_policy = policy.get("tpm_policy", '{"mask": "0x0"}')
        if isinstance(tpm_policy, dict):
            if "mask" not in tpm_policy:
                tpm_policy["mask"] = "0x0"
            tpm_policy = json.dumps(tpm_policy)

        payload = {
            "v": policy.get("v", ""),
            "agent_id": agent_id,
            "ip": agent_ip,
            "port": agent_port,
            "cloudagent_ip": agent_ip,
            "cloudagent_port": agent_port,
            "tpm_policy": tpm_policy,
            "runtime_policy": policy.get("runtime_policy", ""),
            "runtime_policy_name": policy.get("runtime_policy_name", ""),
            "runtime_policy_key": policy.get("runtime_policy_key", ""),
            "metadata": policy.get("metadata", "{}"),
            "revocation_key": policy.get("revocation_key", ""),
            "accept_tpm_hash_algs": policy.get(
                "accept_tpm_hash_algs", DEFAULT_TPM_HASH_ALGS
            ),
            "accept_tpm_encryption_algs": policy.get(
                "accept_tpm_encryption_algs", DEFAULT_TPM_ENC_ALGS
            ),
            "accept_tpm_signing_algs": policy.get(
                "accept_tpm_signing_algs", DEFAULT_TPM_SIGN_ALGS
            ),
            "ima_sign_verification_keys": policy.get("ima_sign_verification_keys", ""),
            "mb_refstate": policy.get("mb_refstate", ""),
            "mb_policy": policy.get("mb_policy", ""),
            "mb_policy_name": policy.get("mb_policy_name", ""),
            "supported_version": policy.get("supported_version", "2.1"),
            "ak_tpm": ak_tpm,
            "mtls_cert": mtls_cert,
        }

        try:
            async with self._build_client() as client:
                url = f"{self._verifier_url}/v2.5/agents/{agent_id}"
                resp = await client.post(url, json=payload)
                if resp.status_code == 409:
                    # Agent exists (e.g. verifier PULL mode auto-enrolled
                    # with ip=None). Delete and re-add with correct fields.
                    del_resp = await client.delete(url)
                    if del_resp.status_code in (200, 202):
                        await asyncio.sleep(1)
                        resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return EnrollResult(
                    success=True,
                    backend="keylime",
                    detail={
                        "agent_id": agent_id,
                        "ip": agent_ip,
                        "port": agent_port,
                        "registrar_data_used": reg_data is not None,
                        "response": resp.json(),
                    },
                )
        except httpx.HTTPError as e:
            error_detail = str(e)
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_detail = e.response.text
                except Exception:
                    pass
            return EnrollResult(
                success=False,
                backend="keylime",
                detail={"error": error_detail, "agent_id": agent_id},
            )

    async def revoke(self, workload: Workload) -> RevokeResult:
        agent_id = workload.metadata_.get("keylime_agent_uuid", "")
        if not agent_id:
            return RevokeResult(success=False, backend="keylime", detail={"error": "no agent_id"})
        try:
            async with self._build_client() as client:
                resp = await client.delete(f"{self._verifier_url}/v2.5/agents/{agent_id}")
                resp.raise_for_status()
                return RevokeResult(success=True, backend="keylime", detail=resp.json())
        except httpx.HTTPError as e:
            return RevokeResult(success=False, backend="keylime", detail={"error": str(e)})

    async def health(self) -> BackendHealth:
        try:
            async with self._build_client() as client:
                resp = await client.get(f"{self._verifier_url}/v2.5/agents/")
                resp.raise_for_status()
                return BackendHealth(
                    healthy=True,
                    backend="keylime",
                    last_check=datetime.now(UTC),
                    detail=(
                        f"verifier reachable, "
                        f"{len(resp.json().get('results', {}).get('uuids', []))} agents"
                    ),
                )
        except Exception as e:
            return BackendHealth(
                healthy=False,
                backend="keylime",
                last_check=datetime.now(UTC),
                detail=str(e),
            )
