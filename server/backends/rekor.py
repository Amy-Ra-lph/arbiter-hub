import hashlib
import json
import logging
from datetime import datetime, timezone
import httpx
from server.backends.base import (
    AttestationBackend, AttestationResult, EnrollResult, RevokeResult, BackendHealth,
)
from server.models.db import AttestationVerdict, Workload

log = logging.getLogger(__name__)


class RekorBackend:
    def __init__(self, rekor_url: str, timeout: float = 10.0):
        self._url = rekor_url.rstrip("/")
        self._timeout = timeout

    async def verify(self, workload: Workload) -> AttestationResult:
        entry_uuid = workload.metadata_.get("rekor_entry_uuid", "")
        if not entry_uuid:
            return AttestationResult(
                verdict=AttestationVerdict.ERROR,
                backend="rekor",
                evidence_hash="",
                detail={"error": "no rekor_entry_uuid in workload metadata"},
            )
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._url}/api/v1/log/entries/{entry_uuid}")
                resp.raise_for_status()
                data = resp.json()
                eh = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
                return AttestationResult(
                    verdict=AttestationVerdict.PASS,
                    backend="rekor",
                    evidence_hash=eh,
                    detail={"entry_found": True, "uuid": entry_uuid},
                )
        except httpx.HTTPError as e:
            return AttestationResult(
                verdict=AttestationVerdict.UNAVAILABLE,
                backend="rekor",
                evidence_hash="",
                detail={"error": str(e)},
            )

    async def log_entry(self, data: dict) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._url}/api/v1/log/entries", json=data)
                resp.raise_for_status()
                result = resp.json()
                return next(iter(result.keys()), None)
        except httpx.HTTPError as e:
            log.warning("Rekor log_entry failed: %s", e)
            return None

    async def enroll(self, workload: Workload, policy: dict) -> EnrollResult:
        return EnrollResult(success=True, backend="rekor", detail={"note": "rekor is audit-only, no enrollment"})

    async def revoke(self, workload: Workload) -> RevokeResult:
        return RevokeResult(success=True, backend="rekor", detail={"note": "rekor is append-only, no revocation"})

    async def health(self) -> BackendHealth:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._url}/api/v1/log")
                resp.raise_for_status()
                data = resp.json()
                return BackendHealth(
                    healthy=True, backend="rekor",
                    last_check=datetime.now(timezone.utc),
                    detail=f"tree size: {data.get('treeSize', 'unknown')}",
                )
        except Exception as e:
            return BackendHealth(
                healthy=False, backend="rekor",
                last_check=datetime.now(timezone.utc), detail=str(e),
            )
