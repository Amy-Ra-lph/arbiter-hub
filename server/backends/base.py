from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable
from server.models.db import AttestationVerdict, Workload


@dataclass
class AttestationResult:
    verdict: AttestationVerdict
    backend: str
    evidence_hash: str
    detail: dict = field(default_factory=dict)
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(__import__("datetime").timezone.utc)
    )


@dataclass
class EnrollResult:
    success: bool
    backend: str
    detail: dict = field(default_factory=dict)


@dataclass
class RevokeResult:
    success: bool
    backend: str
    detail: dict = field(default_factory=dict)


@dataclass
class BackendHealth:
    healthy: bool
    backend: str
    last_check: datetime
    detail: str = ""


@runtime_checkable
class AttestationBackend(Protocol):
    async def verify(self, workload: Workload) -> AttestationResult: ...
    async def enroll(self, workload: Workload, policy: dict) -> EnrollResult: ...
    async def revoke(self, workload: Workload) -> RevokeResult: ...
    async def health(self) -> BackendHealth: ...


class BackendRegistry:
    def __init__(self):
        self._backends: dict[str, AttestationBackend] = {}

    def register(self, name: str, backend: AttestationBackend) -> None:
        self._backends[name] = backend

    def get(self, name: str) -> AttestationBackend:
        return self._backends[name]

    async def health_all(self) -> dict[str, BackendHealth]:
        results = {}
        for name, backend in self._backends.items():
            results[name] = await backend.health()
        return results

    def all_names(self) -> list[str]:
        return list(self._backends.keys())
