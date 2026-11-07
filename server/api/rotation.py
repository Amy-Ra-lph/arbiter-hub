import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.webhooks import dispatch_webhooks
from server.auth.dependencies import require_permission
from server.auth.models import CallerIdentity
from server.models.db import Workload, WorkloadState, get_session
from server.models.schemas import ImageRotateRequest, ImageRotateResult
from server.state.machine import InvalidTransitionError, transition

log = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


@router.post(
    "/workloads/{workload_id}/rotate",
    response_model=ImageRotateResult,
)
@limiter.limit("10/minute")
async def rotate_image(
    workload_id: UUID,
    body: ImageRotateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("trigger_attestation"),
):
    """Rotate a workload's container image to a new signed version.

    Flow: HEALTHY → ROTATING → ATTESTING (→ cosign verify → HEALTHY or FAILED)
    Preserves workload identity, audit trail, and KBS secret bindings.
    """
    stmt = select(Workload).where(Workload.id == workload_id).with_for_update()
    result = await session.execute(stmt)
    workload = result.scalar_one_or_none()
    if not workload:
        raise HTTPException(status_code=404, detail="workload not found")

    if workload.current_state != WorkloadState.HEALTHY:
        raise HTTPException(
            status_code=409,
            detail=f"image rotation requires HEALTHY state, workload is {workload.current_state.value}",
        )

    if workload.artifact_digest == body.artifact_digest:
        raise HTTPException(
            status_code=409,
            detail="new digest matches current digest — no rotation needed",
        )

    previous_digest = workload.artifact_digest

    try:
        await transition(
            session,
            workload,
            WorkloadState.ROTATING,
            caller.principal,
            justification=f"image rotation: {previous_digest or 'none'} → {body.artifact_digest}",
        )
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))

    workload.previous_artifact_digest = previous_digest
    workload.artifact_ref = body.artifact_ref
    workload.artifact_digest = body.artifact_digest
    workload.metadata_["rotation_history"] = workload.metadata_.get("rotation_history", [])
    workload.metadata_["rotation_history"].append({
        "from_digest": previous_digest,
        "to_digest": body.artifact_digest,
        "to_ref": body.artifact_ref,
        "triggered_by": caller.principal,
    })

    attestation_triggered = False
    if body.auto_attest:
        try:
            await transition(
                session,
                workload,
                WorkloadState.ATTESTING,
                "rotation_auto_attest",
                justification=f"auto-attest after rotation to {body.artifact_digest[:12]}",
            )
            attestation_triggered = True
        except InvalidTransitionError:
            log.warning("auto-attest transition failed for workload %s", workload_id)

    await session.commit()

    await dispatch_webhooks(
        session,
        "image_rotation",
        workload.id,
        WorkloadState.HEALTHY.value,
        workload.current_state.value,
        {
            "previous_digest": previous_digest,
            "new_digest": body.artifact_digest,
            "new_ref": body.artifact_ref,
            "auto_attest": attestation_triggered,
        },
    )

    return ImageRotateResult(
        workload_id=workload.id,
        previous_digest=previous_digest,
        new_digest=body.artifact_digest,
        new_ref=body.artifact_ref,
        state=workload.current_state,
        attestation_triggered=attestation_triggered,
    )


@router.post("/workloads/{workload_id}/rotate-and-verify")
@limiter.limit("5/minute")
async def rotate_and_verify(
    workload_id: UUID,
    body: ImageRotateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("trigger_attestation"),
):
    """Rotate image and immediately run full attestation in one call.

    Combines rotation + attestation trigger for CI pipeline automation.
    Returns the final workload state after cosign verification completes.
    """
    import asyncio
    from datetime import UTC, datetime

    from server.backends.base import BackendRegistry, compute_composite_verdict
    from server.models.db import AttestationRecord, AttestationVerdict

    stmt = select(Workload).where(Workload.id == workload_id).with_for_update()
    result = await session.execute(stmt)
    workload = result.scalar_one_or_none()
    if not workload:
        raise HTTPException(status_code=404, detail="workload not found")

    if workload.current_state != WorkloadState.HEALTHY:
        raise HTTPException(
            status_code=409,
            detail=f"image rotation requires HEALTHY state, workload is {workload.current_state.value}",
        )

    if workload.artifact_digest == body.artifact_digest:
        return {
            "workload_id": str(workload_id),
            "status": "no_change",
            "message": "digest already matches — skipped rotation",
            "state": workload.current_state.value,
        }

    previous_digest = workload.artifact_digest

    await transition(
        session, workload, WorkloadState.ROTATING, caller.principal,
        justification=f"rotate-and-verify: {previous_digest or 'none'} → {body.artifact_digest}",
    )

    workload.previous_artifact_digest = previous_digest
    workload.artifact_ref = body.artifact_ref
    workload.artifact_digest = body.artifact_digest

    await transition(
        session, workload, WorkloadState.ATTESTING, "rotation_auto_attest",
    )

    registry: BackendRegistry = getattr(request.app.state, "backend_registry", None)
    if not registry:
        raise HTTPException(status_code=500, detail="backend registry not initialized")

    backends = []
    for bt in workload.backend_types:
        try:
            backends.append((bt, registry.get(bt)))
        except KeyError:
            log.warning("backend %s not configured, skipped during rotation verify", bt)
    if not backends:
        raise HTTPException(status_code=503, detail="no configured backends")

    raw_results = await asyncio.gather(
        *[b.verify(workload) for _, b in backends], return_exceptions=True
    )

    att_results = []
    for (bt, _), raw in zip(backends, raw_results):
        if isinstance(raw, Exception):
            from server.backends.base import AttestationResult
            att_results.append(AttestationResult(
                verdict=AttestationVerdict.ERROR, backend=bt,
                evidence_hash="", detail={"error": str(raw)},
            ))
        else:
            att_results.append(raw)

    for ar in att_results:
        session.add(AttestationRecord(
            workload_id=workload.id, backend=ar.backend,
            verdict=ar.verdict, evidence_hash=ar.evidence_hash, detail=ar.detail,
        ))

    composite = compute_composite_verdict(att_results)

    if composite == AttestationVerdict.PASS:
        await transition(session, workload, WorkloadState.HEALTHY, "rotation_attestation")
        workload.last_attested_at = datetime.now(UTC)
    elif composite == AttestationVerdict.FAIL:
        await transition(session, workload, WorkloadState.FAILED, "rotation_attestation")

    await session.commit()

    await dispatch_webhooks(
        session, "image_rotation_verified", workload.id,
        WorkloadState.HEALTHY.value, workload.current_state.value,
        {
            "previous_digest": previous_digest,
            "new_digest": body.artifact_digest,
            "verdict": composite.value,
            "per_backend": [{"backend": ar.backend, "verdict": ar.verdict.value} for ar in att_results],
        },
    )

    return {
        "workload_id": str(workload_id),
        "status": "rotated",
        "previous_digest": previous_digest,
        "new_digest": body.artifact_digest,
        "verdict": composite.value,
        "state": workload.current_state.value,
        "per_backend": [{"backend": ar.backend, "verdict": ar.verdict.value} for ar in att_results],
    }
