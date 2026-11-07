"""Tests for MeasuredBootBackend — PCR 11 evaluation for bootc sealed images."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from server.backends.measured_boot import MeasuredBootBackend
from server.models.db import AttestationVerdict, WorkloadState, WorkloadType


def _make_workload(**metadata_overrides):
    wl = MagicMock()
    wl.id = "test-workload-id"
    wl.ipa_principal = "bootc/node1@ARBITER.DEMO"
    wl.workload_type = WorkloadType.BOOTC
    wl.current_state = WorkloadState.ATTESTING
    meta = {
        "keylime_agent_uuid": "test-uuid-123",
        "uki_pcrsig": {
            "sha256": ["abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"]
        },
        "composefs_digest": "sha256:deadbeef",
        "bootc_image_ref": "quay.io/rhel-security/demo-bootc:latest",
    }
    meta.update(metadata_overrides)
    wl.metadata_ = meta
    return wl


@pytest.fixture
def backend():
    return MeasuredBootBackend(
        keylime_verifier_url="https://verifier.test:8881",
    )


@pytest.mark.asyncio
async def test_verify_pass_matching_pcr11(backend):
    expected_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    wl = _make_workload()

    verifier_response = {
        "results": {
            "operational_state": 3,
            "tpm_policy": json.dumps({
                "mask": "0x408",
                "11": expected_hash,
            }),
        }
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = verifier_response

    with patch.object(backend, "_build_client") as mock_client:
        ctx = AsyncMock()
        ctx.get = AsyncMock(return_value=mock_resp)
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.return_value = ctx

        result = await backend.verify(wl)

    assert result.verdict == AttestationVerdict.PASS
    assert result.backend == "measured_boot"
    assert result.detail["pcr11"] == expected_hash


@pytest.mark.asyncio
async def test_verify_fail_mismatched_pcr11(backend):
    wl = _make_workload()

    verifier_response = {
        "results": {
            "operational_state": 3,
            "tpm_policy": json.dumps({
                "mask": "0x408",
                "11": "wrong_hash_value_does_not_match_expected",
            }),
        }
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = verifier_response

    with patch.object(backend, "_build_client") as mock_client:
        ctx = AsyncMock()
        ctx.get = AsyncMock(return_value=mock_resp)
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.return_value = ctx

        result = await backend.verify(wl)

    assert result.verdict == AttestationVerdict.FAIL
    assert result.backend == "measured_boot"


@pytest.mark.asyncio
async def test_verify_error_no_agent_uuid(backend):
    wl = _make_workload(keylime_agent_uuid="")
    result = await backend.verify(wl)
    assert result.verdict == AttestationVerdict.ERROR
    assert "keylime_agent_uuid" in result.detail["error"]


@pytest.mark.asyncio
async def test_verify_error_no_pcrsig(backend):
    wl = _make_workload(uki_pcrsig={})
    result = await backend.verify(wl)
    assert result.verdict == AttestationVerdict.ERROR
    assert "uki_pcrsig" in result.detail["error"]


@pytest.mark.asyncio
async def test_verify_unavailable_on_http_error(backend):
    wl = _make_workload()

    with patch.object(backend, "_build_client") as mock_client:
        ctx = AsyncMock()
        ctx.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.return_value = ctx

        result = await backend.verify(wl)

    assert result.verdict == AttestationVerdict.UNAVAILABLE


@pytest.mark.asyncio
async def test_enroll_returns_metadata_guidance(backend):
    wl = _make_workload()
    result = await backend.enroll(wl, {})
    assert result.success is True
    assert "uki_pcrsig" in str(result.detail)


@pytest.mark.asyncio
async def test_health_ok(backend):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"results": {"uuids": ["agent-1"]}}

    with patch.object(backend, "_build_client") as mock_client:
        ctx = AsyncMock()
        ctx.get = AsyncMock(return_value=mock_resp)
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.return_value = ctx

        result = await backend.health()

    assert result.healthy is True
    assert "PCR 11" in result.detail


@pytest.mark.asyncio
async def test_evaluate_pcr11_multiple_algorithms(backend):
    """PCR 11 evaluation matches on any supported algorithm."""
    sha384_hash = "a" * 96
    actual = {"sha384": sha384_hash}
    expected = {"sha256": ["no-match"], "sha384": [sha384_hash]}
    verdict = backend._evaluate_pcr11(actual, expected)
    assert verdict == AttestationVerdict.PASS


@pytest.mark.asyncio
async def test_evaluate_pcr11_empty_actual(backend):
    verdict = backend._evaluate_pcr11({}, {"sha256": ["abc"]})
    assert verdict == AttestationVerdict.FAIL


def test_bootc_workload_type_exists():
    assert WorkloadType.BOOTC == "bootc"


def test_measured_boot_backend_type_exists():
    from server.models.db import BackendType
    assert BackendType.MEASURED_BOOT == "measured_boot"
