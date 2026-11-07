import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, StringConstraints
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from server.api.webhooks import dispatch_webhooks
from server.auth.dependencies import require_permission
from server.auth.models import CallerIdentity
from server.backends.base import BackendRegistry
from server.models.db import (
    AttestationRecord,
    AuditLog,
    StateTransition,
    Workload,
    WorkloadState,
    WorkloadType,
    get_session,
)
from server.state.machine import InvalidTransitionError, transition

log = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/ci")


class CIEnrollRequest(BaseModel):
    ipa_principal: Annotated[str, StringConstraints(min_length=1, max_length=512, pattern=r"^[a-zA-Z0-9_./@-]+$")]
    display_name: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    workload_type: WorkloadType
    backend_types: list[str] = Field(min_length=1, max_length=10)
    artifact_ref: Annotated[str, StringConstraints(max_length=1024)] = ""
    image_digest: Annotated[str, StringConstraints(max_length=256)] = ""
    metadata: dict = Field(default_factory=dict)
    auto_attest: bool = True


class CIEnrollResponse(BaseModel):
    workload_id: UUID
    state: WorkloadState
    attestation_triggered: bool
    backends_registered: list[str]
    detail: dict = Field(default_factory=dict)


@router.post("/enroll", response_model=CIEnrollResponse)
@limiter.limit("5/minute")
async def ci_enroll(
    body: CIEnrollRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("ci_enroll"),
):
    existing_result = await session.execute(
        select(Workload).where(Workload.ipa_principal == body.ipa_principal)
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        if existing.current_state in (WorkloadState.HEALTHY, WorkloadState.STALE):
            return CIEnrollResponse(
                workload_id=existing.id,
                state=existing.current_state,
                attestation_triggered=False,
                backends_registered=existing.backend_types,
                detail={"action": "existing_healthy"},
            )
        if existing.current_state in (WorkloadState.REGISTERED, WorkloadState.ATTESTING):
            return CIEnrollResponse(
                workload_id=existing.id,
                state=existing.current_state,
                attestation_triggered=False,
                backends_registered=existing.backend_types,
                detail={"action": "in_progress"},
            )
        if existing.current_state in (WorkloadState.FAILED, WorkloadState.REVOKED):
            for att in (await session.execute(
                select(AttestationRecord).where(AttestationRecord.workload_id == existing.id)
            )).scalars():
                await session.delete(att)
            for trans in (await session.execute(
                select(StateTransition).where(StateTransition.workload_id == existing.id)
            )).scalars():
                await session.delete(trans)
            audit_cleanup = AuditLog(
                actor=caller.principal,
                actor_type=caller.actor_type,
                action="ci_enroll_cleanup",
                target_type="workload",
                target_id=existing.id,
                detail={
                    "previous_state": existing.current_state.value,
                    "principal": body.ipa_principal,
                },
            )
            session.add(audit_cleanup)
            await session.delete(existing)
            await session.flush()

    workload = Workload(
        ipa_principal=body.ipa_principal,
        display_name=body.display_name,
        workload_type=body.workload_type,
        backend_types=body.backend_types,
        artifact_ref=body.artifact_ref or None,
        artifact_digest=body.image_digest or None,
        metadata_=body.metadata,
    )
    session.add(workload)

    audit = AuditLog(
        actor=caller.principal,
        actor_type=caller.actor_type,
        action="ci_enroll",
        target_type="workload",
        target_id=workload.id,
        detail={
            "principal": body.ipa_principal,
            "backend_types": body.backend_types,
            "artifact_ref": body.artifact_ref,
            "image_digest": body.image_digest,
        },
    )
    session.add(audit)

    attestation_triggered = False

    if body.auto_attest and "cosign" in body.backend_types and body.artifact_ref:
        registry: BackendRegistry = getattr(request.app.state, "backend_registry", None)
        if registry:
            try:
                cosign_backend = registry.get("cosign")
                result = await cosign_backend.verify(workload)
                att_record = AttestationRecord(
                    workload_id=workload.id,
                    backend="cosign",
                    verdict=result.verdict,
                    evidence_hash=result.evidence_hash,
                    detail=result.detail,
                )
                session.add(att_record)

                if result.verdict.value == "pass":
                    try:
                        await transition(
                            session,
                            workload,
                            WorkloadState.ATTESTING,
                            caller.principal,
                            justification="ci auto-enrollment",
                        )
                        await transition(
                            session,
                            workload,
                            WorkloadState.HEALTHY,
                            caller.principal,
                            justification="cosign verification passed",
                        )
                    except InvalidTransitionError:
                        log.warning("state transition failed during ci_enroll for %s", body.ipa_principal)
                else:
                    try:
                        await transition(
                            session,
                            workload,
                            WorkloadState.ATTESTING,
                            caller.principal,
                            justification="ci auto-enrollment",
                        )
                        await transition(
                            session,
                            workload,
                            WorkloadState.FAILED,
                            caller.principal,
                            justification=f"cosign verification {result.verdict.value}",
                        )
                    except InvalidTransitionError:
                        log.warning("state transition failed during ci_enroll for %s", body.ipa_principal)
                attestation_triggered = True
            except KeyError:
                log.info("cosign backend not configured, skipping auto-attest")

    await session.commit()
    await session.refresh(workload)

    await dispatch_webhooks(
        session,
        "ci_enrollment",
        workload.id,
        "none",
        workload.current_state.value,
        {
            "principal": body.ipa_principal,
            "backend_types": body.backend_types,
            "auto_attest": attestation_triggered,
        },
    )

    return CIEnrollResponse(
        workload_id=workload.id,
        state=workload.current_state,
        attestation_triggered=attestation_triggered,
        backends_registered=body.backend_types,
        detail={"action": "created"},
    )
