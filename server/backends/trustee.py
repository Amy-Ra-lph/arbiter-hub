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


class TrusteeBackend:
    def __init__(self, trustee_url: str, timeout: float = 10.0):
        self._url = trustee_url.rstrip("/")
        self._timeout = timeout

    async def verify(self, workload: Workload) -> AttestationResult:
        tee_type = workload.metadata_.get("tee_type", "sample")
        evidence = workload.metadata_.get("tee_evidence", "")
        if not evidence:
            return AttestationResult(
                verdict=AttestationVerdict.ERROR,
                backend="trustee",
                evidence_hash="",
                detail={"error": "no tee_evidence in workload metadata"},
            )
        try:
            async with httpx.AsyncClient(timeout=self._timeout, verify=False) as client:
                resp = await client.post(
                    f"{self._url}/kbs/v0/attest",
                    json={"tee_type": tee_type, "evidence": evidence},
                )
                resp.raise_for_status()
                data = resp.json()
                import hashlib

                eh = hashlib.sha256(evidence.encode()).hexdigest()
                if data.get("attestation_pass", False):
                    return AttestationResult(
                        verdict=AttestationVerdict.PASS,
                        backend="trustee",
                        evidence_hash=eh,
                        detail=data,
                    )
                else:
                    return AttestationResult(
                        verdict=AttestationVerdict.FAIL,
                        backend="trustee",
                        evidence_hash=eh,
                        detail=data,
                    )
        except httpx.HTTPError as e:
            return AttestationResult(
                verdict=AttestationVerdict.UNAVAILABLE,
                backend="trustee",
                evidence_hash="",
                detail={"error": str(e)},
            )

    async def enroll(self, workload: Workload, policy: dict) -> EnrollResult:
        try:
            async with httpx.AsyncClient(timeout=self._timeout, verify=False) as client:
                resp = await client.post(
                    f"{self._url}/kbs/v0/register",
                    json={
                        "workload_id": str(workload.id),
                        "expected_measurements": policy.get("expected_measurements", {}),
                    },
                )
                resp.raise_for_status()
                return EnrollResult(success=True, backend="trustee", detail=resp.json())
        except httpx.HTTPError as e:
            return EnrollResult(success=False, backend="trustee", detail={"error": str(e)})

    async def revoke(self, workload: Workload) -> RevokeResult:
        return RevokeResult(
            success=True, backend="trustee", detail={"note": "trustee has no revocation API"}
        )

    async def health(self) -> BackendHealth:
        try:
            async with httpx.AsyncClient(timeout=self._timeout, verify=False) as client:
                resp = await client.get(f"{self._url}/kbs/v0/health")
                resp.raise_for_status()
                return BackendHealth(
                    healthy=True,
                    backend="trustee",
                    last_check=datetime.now(UTC),
                    detail="reachable",
                )
        except Exception as e:
            return BackendHealth(
                healthy=False,
                backend="trustee",
                last_check=datetime.now(UTC),
                detail=str(e),
            )
