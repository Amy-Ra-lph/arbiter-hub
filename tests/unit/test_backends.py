from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from server.backends.base import (
    AttestationBackend,
    AttestationResult,
    BackendRegistry,
)
from server.backends.keylime import KeylimeBackend
from server.models.db import AttestationVerdict, BackendType, Workload, WorkloadState, WorkloadType


def _make_workload(**overrides):
    import uuid

    defaults = dict(
        id=uuid.uuid4(),
        ipa_principal="agent-test@EXAMPLE.COM",
        display_name="Test Agent",
        workload_type=WorkloadType.AGENTIC,
        current_state=WorkloadState.ATTESTING,
        backend_types=[BackendType.KEYLIME.value],
        stale_ttl_seconds=3600,
        registered_at=datetime.now(UTC),
        last_attested_at=None,
        metadata_={},
    )
    defaults.update(overrides)
    w = Workload.__new__(Workload)
    for k, v in defaults.items():
        object.__setattr__(w, k, v)
    return w


def test_attestation_result_fields():
    r = AttestationResult(
        verdict=AttestationVerdict.PASS,
        backend="keylime",
        evidence_hash="abc123",
        detail={"ima_count": 5508},
        timestamp=datetime.now(UTC),
    )
    assert r.verdict == AttestationVerdict.PASS
    assert r.backend == "keylime"


def test_backend_registry():
    registry = BackendRegistry()
    mock_backend = AsyncMock(spec=AttestationBackend)
    registry.register("test", mock_backend)
    assert registry.get("test") is mock_backend


def test_backend_registry_unknown_raises():
    registry = BackendRegistry()
    with pytest.raises(KeyError):
        registry.get("nonexistent")


def test_keylime_backend_implements_protocol():
    kb = KeylimeBackend(
        verifier_url="https://localhost:8881",
        ca_cert="",
        client_cert="",
        client_key="",
    )
    assert isinstance(kb, AttestationBackend)


@pytest.mark.asyncio
async def test_keylime_health_unreachable():
    kb = KeylimeBackend(
        verifier_url="https://unreachable:8881",
        ca_cert="",
        client_cert="",
        client_key="",
    )
    health = await kb.health()
    assert health.healthy is False
    assert health.backend == "keylime"
