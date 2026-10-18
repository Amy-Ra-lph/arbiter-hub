from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import get_caller, require_permission
from server.auth.models import CallerIdentity
from server.auth.rbac import check_scope
from server.config import settings
from server.kbs.gate import check_kbs_gate
from server.kbs.store import decrypt_secret, encrypt_secret
from server.models.db import AuditLog, KBSSecret, Workload, get_session
from server.models.schemas import KBSSecretCreate

router = APIRouter(prefix="/kbs/v0")


def _load_encryption_key() -> bytes:
    p = Path(settings.kbs_encryption_key_file)
    if p.exists():
        return p.read_bytes().strip()
    return b"0" * 32  # dev fallback


@router.get("/health")
async def kbs_health():
    return {"status": "ok", "service": "arbiter-hub-kbs"}


@router.post("/resource/{repo}/{secret_type}/{tag}", status_code=201)
async def store_secret(
    repo: str,
    secret_type: str,
    tag: str,
    body: KBSSecretCreate,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("manage_kbs"),
):
    key = _load_encryption_key()
    encrypted = encrypt_secret(body.value, key)
    secret = KBSSecret(
        repo=repo,
        secret_type=secret_type,
        tag=tag,
        encrypted_value=encrypted,
        required_state=body.required_state,
        workload_scope=body.workload_scope,
        created_by=caller.principal,
    )
    session.add(secret)
    audit = AuditLog(
        actor=caller.principal,
        actor_type=caller.actor_type,
        action="kbs_store_secret",
        target_type="kbs_secret",
        detail={"repo": repo, "type": secret_type, "tag": tag},
    )
    session.add(audit)
    await session.commit()
    return {"status": "stored", "repo": repo, "type": secret_type, "tag": tag}


@router.get("/resource/{repo}/{secret_type}/{tag}")
async def retrieve_secret(
    repo: str,
    secret_type: str,
    tag: str,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = Depends(get_caller),
):
    stmt = select(KBSSecret).where(
        KBSSecret.repo == repo,
        KBSSecret.secret_type == secret_type,
        KBSSecret.tag == tag,
    )
    result = await session.execute(stmt)
    secret = result.scalar_one_or_none()
    if not secret:
        raise HTTPException(status_code=404, detail="secret not found")

    if secret.workload_scope and not check_scope(caller, secret.workload_scope):
        raise HTTPException(status_code=404, detail="secret not found")

    # Gate check: lock workload row to prevent concurrent revocation during release
    wl_stmt = select(Workload).where(Workload.ipa_principal == caller.principal).with_for_update()
    wl_result = await session.execute(wl_stmt)
    workload = wl_result.scalar_one_or_none()

    if workload:
        age = 0.0
        if workload.last_attested_at:
            age = (datetime.now(UTC) - workload.last_attested_at).total_seconds()
        else:
            age = float("inf")
        gate = await check_kbs_gate(
            workload_state=workload.current_state,
            attestation_age_seconds=age,
            policy_engine=None,
            subject=caller.principal,
            resource=f"{repo}/{secret_type}/{tag}",
        )
        if not gate.allowed:
            raise HTTPException(status_code=403, detail=gate.reason)

    key = _load_encryption_key()
    plaintext = decrypt_secret(secret.encrypted_value, key)

    audit = AuditLog(
        actor=caller.principal,
        actor_type=caller.actor_type,
        action="kbs_release_secret",
        target_type="kbs_secret",
        target_id=secret.id,
        detail={"repo": repo, "type": secret_type, "tag": tag},
    )
    session.add(audit)
    await session.commit()

    return {"value": plaintext}
