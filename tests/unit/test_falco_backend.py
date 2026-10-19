from unittest.mock import MagicMock

import pytest

from server.backends.base import AttestationBackend
from server.backends.falco import FalcoBackend
from server.models.db import AttestationVerdict


def test_falco_implements_protocol():
    fb = FalcoBackend(healthz_url="http://localhost:8765/healthz")
    assert isinstance(fb, AttestationBackend)


@pytest.mark.asyncio
async def test_falco_verify_returns_pass():
    fb = FalcoBackend(healthz_url="http://localhost:8765/healthz")
    result = await fb.verify(MagicMock())
    assert result.verdict == AttestationVerdict.PASS
    assert result.backend == "falco"


@pytest.mark.asyncio
async def test_falco_health_unreachable():
    fb = FalcoBackend(healthz_url="http://127.0.0.1:1/healthz")
    health = await fb.health()
    assert health.healthy is False
    assert health.backend == "falco"


@pytest.mark.asyncio
async def test_falco_enroll_is_noop():
    fb = FalcoBackend(healthz_url="http://localhost:8765/healthz")
    result = await fb.enroll(MagicMock(), {})
    assert result.success is True


@pytest.mark.asyncio
async def test_falco_revoke_is_noop():
    fb = FalcoBackend(healthz_url="http://localhost:8765/healthz")
    result = await fb.revoke(MagicMock())
    assert result.success is True
