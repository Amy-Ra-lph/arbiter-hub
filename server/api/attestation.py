from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import require_permission
from server.auth.models import CallerIdentity
from server.backends.base import BackendRegistry
from server.models.db import (
    AttestationRecord,
    AttestationVerdict,
    Workload,
    WorkloadState,
    get_session,
)
from server.state.machine import InvalidTransitionError, transition

limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


@router.post("/workloads/{workload_id}/attest")
@limiter.limit("10/minute")
async def trigger_attestation(
    workload_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("trigger_attestation"),
):
    # Use SELECT FOR UPDATE to prevent race conditions on concurrent attestations
    stmt = select(Workload).where(Workload.id == workload_id).with_for_update()
    result = await session.execute(stmt)
    workload = result.scalar_one_or_none()
    if not workload:
        raise HTTPException(status_code=404, detail="workload not found")

    # Transition to Attesting if currently in a state that allows it
    if workload.current_state in (
        WorkloadState.REGISTERED,
        WorkloadState.STALE,
        WorkloadState.UNDER_REMEDIATION,
    ):
        try:
            await transition(session, workload, WorkloadState.ATTESTING, caller.principal)
        except InvalidTransitionError as e:
            raise HTTPException(status_code=409, detail=str(e))
    elif workload.current_state != WorkloadState.ATTESTING:
        raise HTTPException(
            status_code=409,
            detail=f"cannot attest workload in state {workload.current_state.value}",
        )

    # Get backend registry and run verification
    registry: BackendRegistry = getattr(request.app.state, "backend_registry", None)
    if not registry:
        raise HTTPException(status_code=500, detail="backend registry not initialized")

    try:
        primary_backend = workload.backend_types[0]
        backend = registry.get(primary_backend)
    except KeyError:
        raise HTTPException(
            status_code=503, detail=f"backend {workload.backend_types[0]} not configured"
        )

    att_result = await backend.verify(workload)

    # Record attestation result
    record = AttestationRecord(
        workload_id=workload.id,
        backend=workload.backend_types[0],
        verdict=att_result.verdict,
        evidence_hash=att_result.evidence_hash,
        detail=att_result.detail,
    )
    session.add(record)

    # Transition based on verdict
    # CRITICAL: UNAVAILABLE does NOT transition to Failed
    if att_result.verdict == AttestationVerdict.PASS:
        await transition(session, workload, WorkloadState.HEALTHY, "attestation_result")
        workload.last_attested_at = datetime.now(UTC)
    elif att_result.verdict == AttestationVerdict.FAIL:
        await transition(session, workload, WorkloadState.FAILED, "attestation_result")
    # For UNAVAILABLE and ERROR: stay in Attesting, do not transition to Failed

    await session.commit()

    # Return detailed response
    response_detail = {
        "workload_id": str(workload_id),
        "verdict": att_result.verdict.value,
        "state": workload.current_state.value,
        "attestation_id": str(record.id),
    }

    # Add message for UNAVAILABLE verdict
    if att_result.verdict == AttestationVerdict.UNAVAILABLE:
        response_detail["message"] = (
            "Backend temporarily unavailable; workload remains in current state"
        )

    return response_detail
