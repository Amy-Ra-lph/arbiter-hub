import pytest
from server.kbs.store import encrypt_secret, decrypt_secret
from server.kbs.gate import check_kbs_gate
from server.models.db import WorkloadState


def test_encrypt_decrypt_roundtrip():
    key = b"0" * 32  # 256-bit key
    plaintext = "my-secret-password"
    encrypted = encrypt_secret(plaintext, key)
    assert encrypted != plaintext.encode()
    decrypted = decrypt_secret(encrypted, key)
    assert decrypted == plaintext


def test_encrypt_different_key_fails():
    key1 = b"0" * 32
    key2 = b"1" * 32
    encrypted = encrypt_secret("secret", key1)
    with pytest.raises(Exception):
        decrypt_secret(encrypted, key2)


@pytest.mark.asyncio
async def test_gate_allows_healthy_workload():
    result = await check_kbs_gate(
        workload_state=WorkloadState.HEALTHY,
        attestation_age_seconds=100,
        policy_engine=None,
        subject="pipeline",
        resource="secret-1",
    )
    assert result.allowed is True


@pytest.mark.asyncio
async def test_gate_denies_failed_workload():
    result = await check_kbs_gate(
        workload_state=WorkloadState.FAILED,
        attestation_age_seconds=100,
        policy_engine=None,
        subject="pipeline",
        resource="secret-1",
    )
    assert result.allowed is False


@pytest.mark.asyncio
async def test_gate_denies_stale_attestation():
    result = await check_kbs_gate(
        workload_state=WorkloadState.HEALTHY,
        attestation_age_seconds=99999,
        policy_engine=None,
        subject="pipeline",
        resource="secret-1",
        max_attestation_age=3600,
    )
    assert result.allowed is False
