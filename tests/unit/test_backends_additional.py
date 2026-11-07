from unittest.mock import MagicMock

import pytest

from server.backends.base import AttestationBackend
from server.backends.cosign import CosignBackend
from server.backends.rekor import RekorBackend
from server.backends.trustee import TrusteeBackend
from server.models.db import AttestationVerdict


def test_trustee_implements_protocol():
    tb = TrusteeBackend(trustee_url="https://localhost:8085")
    assert isinstance(tb, AttestationBackend)


def test_cosign_implements_protocol():
    cb = CosignBackend(cosign_binary="cosign", rekor_url="")
    assert isinstance(cb, AttestationBackend)


def test_rekor_implements_protocol():
    rb = RekorBackend(rekor_url="https://localhost:3000")
    assert isinstance(rb, AttestationBackend)


@pytest.mark.asyncio
async def test_trustee_health_unreachable():
    tb = TrusteeBackend(trustee_url="https://unreachable:8085")
    health = await tb.health()
    assert health.healthy is False
    assert health.backend == "trustee"


@pytest.mark.asyncio
async def test_cosign_verify_missing_artifact_ref():
    cb = CosignBackend(cosign_binary="cosign", rekor_url="")
    # Use a simple mock object instead of full ORM workload
    workload = MagicMock()
    workload.artifact_ref = None
    workload.metadata_ = {}
    result = await cb.verify(workload)
    assert result.verdict == AttestationVerdict.ERROR
    assert "artifact_ref" in result.detail.get("error", "")


@pytest.mark.asyncio
async def test_rekor_health_unreachable():
    rb = RekorBackend(rekor_url="https://unreachable:3000")
    health = await rb.health()
    assert health.healthy is False
