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


class FalcoBackend:
    def __init__(self, healthz_url: str, timeout: float = 5.0):
        self._healthz_url = healthz_url
        self._timeout = timeout

    async def verify(self, workload: Workload) -> AttestationResult:
        return AttestationResult(
            verdict=AttestationVerdict.PASS,
            backend="falco",
            evidence_hash="",
            detail={"note": "falco is event-driven; verify returns PASS by default"},
        )

    async def enroll(self, workload: Workload, policy: dict) -> EnrollResult:
        return EnrollResult(
            success=True,
            backend="falco",
            detail={"note": "falco enrollment is a no-op"},
        )

    async def revoke(self, workload: Workload) -> RevokeResult:
        return RevokeResult(
            success=True,
            backend="falco",
            detail={"note": "falco revocation is a no-op"},
        )

    async def health(self) -> BackendHealth:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(self._healthz_url)
                return BackendHealth(
                    healthy=resp.status_code == 200,
                    backend="falco",
                    last_check=datetime.now(UTC),
                    detail=f"status={resp.status_code}",
                )
        except Exception as e:
            return BackendHealth(
                healthy=False,
                backend="falco",
                last_check=datetime.now(UTC),
                detail=str(e),
            )
