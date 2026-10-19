import pytest
from unittest.mock import MagicMock

from server.backends.cosign import CosignBackend
from server.models.db import AttestationVerdict


@pytest.mark.asyncio
async def test_cosign_verify_uses_key_flag():
    cb = CosignBackend(cosign_binary="echo", public_key="/tmp/test.pub")
    workload = MagicMock()
    workload.metadata_ = {"artifact_ref": "quay.io/test/image:latest"}
    result = await cb.verify(workload)
    assert "--key" in result.detail.get("output", "")
    assert "/tmp/test.pub" in result.detail.get("output", "")


def test_cosign_backend_without_key():
    cb = CosignBackend(cosign_binary="cosign")
    assert cb._public_key == ""


def test_cosign_backend_with_key():
    cb = CosignBackend(cosign_binary="cosign", public_key="/etc/cosign.pub")
    assert cb._public_key == "/etc/cosign.pub"
