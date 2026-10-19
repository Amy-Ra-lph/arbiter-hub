import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.webhooks import dispatch_webhooks
from server.auth.dependencies import require_permission
from server.auth.models import CallerIdentity
from server.backends.base import BackendRegistry, compute_composite_verdict
from server.models.db import (
    AttestationRecord,
    AttestationVerdict,
    Workload,
    WorkloadState,
    get_session,
)
from server.state.machine import InvalidTransitionError, transition

log = logging.getLogger(__name__)

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

    # Resolve backends for all declared types, track skipped
    backends = []
    skipped_backends = []
    for bt in workload.backend_types:
        try:
            backends.append((bt, registry.get(bt)))
        except KeyError:
            log.warning("backend %s not configured, skipped", bt)
            skipped_backends.append(bt)
    if not backends:
        raise HTTPException(
            status_code=503,
            detail=f"no configured backends for types {workload.backend_types}",
        )

    # Run all backends in parallel
    raw_results = await asyncio.gather(
        *[b.verify(workload) for _, b in backends], return_exceptions=True
    )

    att_results = []
    for (bt, _), raw in zip(backends, raw_results):
        if isinstance(raw, Exception):
            log.error("backend %s raised %s", bt, raw)
            from server.backends.base import AttestationResult

            att_results.append(
                AttestationResult(
                    verdict=AttestationVerdict.ERROR,
                    backend=bt,
                    evidence_hash="",
                    detail={"error": str(raw)},
                )
            )
        else:
            att_results.append(raw)

    # Create one attestation record per backend
    record_ids = []
    for ar in att_results:
        record = AttestationRecord(
            workload_id=workload.id,
            backend=ar.backend,
            verdict=ar.verdict,
            evidence_hash=ar.evidence_hash,
            detail=ar.detail,
        )
        session.add(record)
        record_ids.append(record.id)

    # Compute composite verdict
    composite = compute_composite_verdict(att_results)

    # Transition based on composite verdict
    pre_transition_state = workload.current_state
    if composite == AttestationVerdict.PASS:
        await transition(session, workload, WorkloadState.HEALTHY, "attestation_result")
        workload.last_attested_at = datetime.now(UTC)
    elif composite == AttestationVerdict.FAIL:
        await transition(session, workload, WorkloadState.FAILED, "attestation_result")

    await session.commit()

    if workload.current_state != pre_transition_state:
        await dispatch_webhooks(
            session,
            "state_transition",
            workload.id,
            pre_transition_state.value,
            workload.current_state.value,
            {"verdict": composite.value},
        )

    response_detail = {
        "workload_id": str(workload_id),
        "verdict": composite.value,
        "state": workload.current_state.value,
        "attestation_id": str(record_ids[0]),
        "per_backend": [{"backend": ar.backend, "verdict": ar.verdict.value} for ar in att_results]
        + [{"backend": sb, "verdict": "skipped"} for sb in skipped_backends],
    }

    if composite == AttestationVerdict.UNAVAILABLE:
        response_detail["message"] = (
            "One or more backends unavailable; workload remains in current state"
        )

    return response_detail
