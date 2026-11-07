import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.backends.base import EnrollResult
from server.backends.keylime import DEFAULT_TPM_ENC_ALGS, DEFAULT_TPM_HASH_ALGS, DEFAULT_TPM_SIGN_ALGS, KeylimeBackend


@pytest.fixture
def keylime_backend():
    return KeylimeBackend(
        verifier_url="https://verifier.test:8881",
        ca_cert="",
        client_cert="",
        client_key="",
        registrar_url="https://registrar.test:8891",
    )


@pytest.fixture
def mock_workload():
    w = MagicMock()
    w.metadata_ = {
        "keylime_agent_uuid": "d432fbb3-d2f1-4a97-9ef7-75bd81c00000",
        "keylime_agent_ip": "192.0.2.10",
        "keylime_agent_port": 9002,
    }
    return w


@pytest.mark.asyncio
async def test_enroll_missing_uuid():
    backend = KeylimeBackend(
        verifier_url="https://verifier.test:8881",
        ca_cert="", client_cert="", client_key="",
    )
    workload = MagicMock()
    workload.metadata_ = {}
    result = await backend.enroll(workload, {})
    assert result.success is False
    assert "required" in result.detail["error"]


@pytest.mark.asyncio
async def test_enroll_missing_ip():
    backend = KeylimeBackend(
        verifier_url="https://verifier.test:8881",
        ca_cert="", client_cert="", client_key="",
    )
    workload = MagicMock()
    workload.metadata_ = {"keylime_agent_uuid": "test-uuid"}
    result = await backend.enroll(workload, {})
    assert result.success is False


@pytest.mark.asyncio
async def test_enroll_builds_correct_payload(keylime_backend, mock_workload):
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"results": {}}

    verifier_client = AsyncMock()
    verifier_client.post = AsyncMock(return_value=mock_resp)
    verifier_client.__aenter__ = AsyncMock(return_value=verifier_client)
    verifier_client.__aexit__ = AsyncMock(return_value=False)

    registrar_client = AsyncMock()
    registrar_client.get = AsyncMock(return_value=AsyncMock(
        raise_for_status=MagicMock(),
        json=MagicMock(return_value={
            "results": {
                "aik_tpm": "test-ak-data",
                "mtls_cert": "test-cert-data",
                "ip": "192.0.2.10",
            }
        }),
    ))
    registrar_client.__aenter__ = AsyncMock(return_value=registrar_client)
    registrar_client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(keylime_backend, "_build_client", return_value=verifier_client), \
         patch.object(keylime_backend, "_build_registrar_client", return_value=registrar_client):
        result = await keylime_backend.enroll(mock_workload, {})

    assert result.success is True
    assert result.detail["agent_id"] == "d432fbb3-d2f1-4a97-9ef7-75bd81c00000"
    assert result.detail["registrar_data_used"] is True

    post_call = verifier_client.post.call_args
    payload = post_call.kwargs["json"]
    assert payload["agent_id"] == "d432fbb3-d2f1-4a97-9ef7-75bd81c00000"
    assert payload["ip"] == "192.0.2.10"
    assert payload["port"] == 9002
    assert payload["ak_tpm"] == "test-ak-data"
    assert payload["mtls_cert"] == "test-cert-data"
    tpm_policy = json.loads(payload["tpm_policy"])
    assert tpm_policy["mask"] == "0x0"
    assert payload["accept_tpm_hash_algs"] == DEFAULT_TPM_HASH_ALGS
    assert payload["accept_tpm_encryption_algs"] == DEFAULT_TPM_ENC_ALGS
    assert payload["accept_tpm_signing_algs"] == DEFAULT_TPM_SIGN_ALGS


@pytest.mark.asyncio
async def test_enroll_custom_tpm_policy(keylime_backend, mock_workload):
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"results": {}}

    verifier_client = AsyncMock()
    verifier_client.post = AsyncMock(return_value=mock_resp)
    verifier_client.__aenter__ = AsyncMock(return_value=verifier_client)
    verifier_client.__aexit__ = AsyncMock(return_value=False)

    registrar_client = AsyncMock()
    registrar_client.get = AsyncMock(return_value=AsyncMock(
        raise_for_status=MagicMock(),
        json=MagicMock(return_value={"results": {}}),
    ))
    registrar_client.__aenter__ = AsyncMock(return_value=registrar_client)
    registrar_client.__aexit__ = AsyncMock(return_value=False)

    custom_policy = {
        "tpm_policy": {"mask": "0x408000", "22": ["sha256:abc123"]},
        "ak_tpm": "override-ak",
    }

    with patch.object(keylime_backend, "_build_client", return_value=verifier_client), \
         patch.object(keylime_backend, "_build_registrar_client", return_value=registrar_client):
        result = await keylime_backend.enroll(mock_workload, custom_policy)

    assert result.success is True
    payload = verifier_client.post.call_args.kwargs["json"]
    tpm_policy = json.loads(payload["tpm_policy"])
    assert tpm_policy["mask"] == "0x408000"
    assert "22" in tpm_policy
    assert payload["ak_tpm"] == "override-ak"


@pytest.mark.asyncio
async def test_enroll_no_registrar():
    backend = KeylimeBackend(
        verifier_url="https://verifier.test:8881",
        ca_cert="", client_cert="", client_key="",
    )
    workload = MagicMock()
    workload.metadata_ = {
        "keylime_agent_uuid": "test-uuid",
        "keylime_agent_ip": "10.0.0.1",
    }

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"results": {}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(backend, "_build_client", return_value=mock_client):
        result = await backend.enroll(workload, {"ak_tpm": "provided-ak"})

    assert result.success is True
    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["ak_tpm"] == "provided-ak"


@pytest.mark.asyncio
async def test_enroll_verifier_error(keylime_backend, mock_workload):
    import httpx

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "400 Bad Request",
            request=MagicMock(),
            response=MagicMock(text='{"error": "missing field"}'),
        )
    )
    mock_client.get = AsyncMock(return_value=AsyncMock(
        raise_for_status=MagicMock(),
        json=MagicMock(return_value={"results": {}}),
    ))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(keylime_backend, "_build_client", return_value=mock_client):
        result = await keylime_backend.enroll(mock_workload, {})

    assert result.success is False
    assert "error" in result.detail


@pytest.mark.asyncio
async def test_enroll_tpm_policy_dict_without_mask(keylime_backend, mock_workload):
    """Dict tpm_policy missing mask field gets mask added automatically."""
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"results": {}}

    verifier_client = AsyncMock()
    verifier_client.post = AsyncMock(return_value=mock_resp)
    verifier_client.__aenter__ = AsyncMock(return_value=verifier_client)
    verifier_client.__aexit__ = AsyncMock(return_value=False)

    registrar_client = AsyncMock()
    registrar_client.get = AsyncMock(return_value=AsyncMock(
        raise_for_status=MagicMock(),
        json=MagicMock(return_value={"results": {}}),
    ))
    registrar_client.__aenter__ = AsyncMock(return_value=registrar_client)
    registrar_client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(keylime_backend, "_build_client", return_value=verifier_client), \
         patch.object(keylime_backend, "_build_registrar_client", return_value=registrar_client):
        result = await keylime_backend.enroll(
            mock_workload, {"tpm_policy": {"22": ["sha256:xyz"]}}
        )

    assert result.success is True
    payload = verifier_client.post.call_args.kwargs["json"]
    tpm_policy = json.loads(payload["tpm_policy"])
    assert tpm_policy["mask"] == "0x0"
    assert "22" in tpm_policy


@pytest.mark.asyncio
async def test_registrar_fetch_failure_continues(keylime_backend, mock_workload):
    """Registrar fetch failure doesn't block enrollment — falls back to policy-provided data."""
    import httpx

    call_count = {"get": 0, "post": 0}

    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"results": {}}

    async def mock_get(*args, **kwargs):
        call_count["get"] += 1
        raise httpx.ConnectError("registrar unreachable")

    async def mock_post(*args, **kwargs):
        call_count["post"] += 1
        return mock_resp

    mock_client = AsyncMock()
    mock_client.get = mock_get
    mock_client.post = mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch.object(keylime_backend, "_build_client", return_value=mock_client):
        result = await keylime_backend.enroll(
            mock_workload, {"ak_tpm": "fallback-ak", "mtls_cert": "fallback-cert"}
        )

    assert result.success is True
    assert result.detail["registrar_data_used"] is False


def test_enroll_workload_permission_in_admin_role():
    from server.auth.rbac import ROLE_PERMISSIONS
    assert "enroll_workload" in ROLE_PERMISSIONS["attestation-admin"]


def test_enroll_workload_permission_in_operator_role():
    from server.auth.rbac import ROLE_PERMISSIONS
    assert "enroll_workload" in ROLE_PERMISSIONS["attestation-operator"]


def test_enroll_workload_permission_not_in_viewer():
    from server.auth.rbac import ROLE_PERMISSIONS
    assert "enroll_workload" not in ROLE_PERMISSIONS["attestation-viewer"]
