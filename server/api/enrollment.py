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
from server.backends.base import BackendRegistry
from server.models.db import (
    AuditLog,
    Workload,
    WorkloadState,
    get_session,
)
from server.models.schemas import EnrollRequest, EnrollResult
from server.state.machine import InvalidTransitionError, transition

log = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


@router.post(
    "/workloads/{workload_id}/enroll",
    response_model=EnrollResult,
)
@limiter.limit("10/minute")
async def enroll_workload(
    workload_id: UUID,
    body: EnrollRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("enroll_workload"),
):
    """Enroll a workload's agent with the attestation backend (e.g. Keylime verifier).

    Registers the agent with the verifier so subsequent attestation checks
    can reach and quote the agent. Optionally triggers attestation after
    successful enrollment.
    """
    stmt = select(Workload).where(Workload.id == workload_id).with_for_update()
    result = await session.execute(stmt)
    workload = result.scalar_one_or_none()
    if not workload:
        raise HTTPException(status_code=404, detail="workload not found")

    if workload.current_state not in (
        WorkloadState.REGISTERED,
        WorkloadState.FAILED,
        WorkloadState.UNDER_REMEDIATION,
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                f"enrollment requires REGISTERED, FAILED, or UNDER_REMEDIATION state, "
                f"workload is {workload.current_state.value}"
            ),
        )

    registry: BackendRegistry = getattr(request.app.state, "backend_registry", None)
    if not registry:
        raise HTTPException(status_code=500, detail="backend registry not initialized")

    # Enroll with the first keylime-type backend
    keylime_backend = None
    for bt in workload.backend_types:
        if bt == "keylime":
            try:
                keylime_backend = registry.get(bt)
                break
            except KeyError:
                pass

    if not keylime_backend:
        raise HTTPException(
            status_code=400,
            detail="workload has no keylime backend configured",
        )

    policy = {
        "tpm_policy": body.tpm_policy,
        "runtime_policy": body.runtime_policy,
        "runtime_policy_name": body.runtime_policy_name,
    }
    if body.ak_tpm:
        policy["ak_tpm"] = body.ak_tpm
    if body.mtls_cert:
        policy["mtls_cert"] = body.mtls_cert

    enroll_result = await keylime_backend.enroll(workload, policy)

    audit = AuditLog(
        actor=caller.principal,
        actor_type=caller.actor_type,
        action="enroll_workload",
        target_type="workload",
        target_id=workload.id,
        detail={
            "success": enroll_result.success,
            "backend": enroll_result.backend,
            "agent_id": workload.metadata_.get("keylime_agent_uuid", ""),
        },
    )
    session.add(audit)

    attestation_triggered = False

    if enroll_result.success and body.auto_attest:
        try:
            await transition(
                session,
                workload,
                WorkloadState.ATTESTING,
                caller.principal,
                justification="auto-attest after enrollment",
            )
            attestation_triggered = True
        except InvalidTransitionError:
            log.warning("auto-attest transition failed for workload %s", workload_id)

    await session.commit()

    if enroll_result.success:
        await dispatch_webhooks(
            session,
            "enrollment",
            workload.id,
            workload.current_state.value,
            workload.current_state.value,
            {
                "agent_id": workload.metadata_.get("keylime_agent_uuid", ""),
                "auto_attest": attestation_triggered,
            },
        )

    if not enroll_result.success:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "enrollment failed",
                "backend_detail": enroll_result.detail,
            },
        )

    return EnrollResult(
        workload_id=workload.id,
        success=True,
        backend=enroll_result.backend,
        state=workload.current_state,
        attestation_triggered=attestation_triggered,
        detail=enroll_result.detail,
    )
