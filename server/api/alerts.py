import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.api.webhooks import dispatch_webhooks
from server.auth.dependencies import require_permission
from server.auth.models import CallerIdentity
from server.models.db import (
    AttestationRecord,
    AttestationVerdict,
    BackendType,
    Workload,
    WorkloadState,
    get_session,
)
from server.state.machine import InvalidTransitionError, transition

log = logging.getLogger(__name__)

router = APIRouter()

ACTIONABLE_PRIORITIES = {"Emergency", "Alert", "Critical", "Error", "Warning"}


async def _handle_falco_alert(alert: dict, session: AsyncSession) -> dict:
    container_id = alert.get("output_fields", {}).get("container.id", "")
    priority = alert.get("priority", "")

    if not container_id:
        return {"transitioned": False, "detail": "no container.id in alert"}

    stmt = select(Workload).where(Workload.metadata_["container_id"].astext == container_id)
    result = await session.execute(stmt)
    workloads = result.scalars().all()

    if not workloads:
        log.warning("falco alert for unknown container_id=%s", container_id)
        return {"transitioned": False, "detail": f"no workload for container_id={container_id}"}

    if priority not in ACTIONABLE_PRIORITIES:
        log.info("falco alert priority=%s below threshold, skipping", priority)
        return {"transitioned": False, "detail": f"priority {priority} below threshold"}

    workload = workloads[0]
    if workload.current_state != WorkloadState.HEALTHY:
        return {
            "transitioned": False,
            "detail": f"workload not healthy (state={workload.current_state.value})",
        }

    try:
        await transition(
            session,
            workload,
            WorkloadState.FAILED,
            triggered_by="falco_alert",
            justification=alert.get("output", "")[:500],
        )
    except InvalidTransitionError as e:
        return {"transitioned": False, "detail": str(e)}

    record = AttestationRecord(
        workload_id=workload.id,
        backend=BackendType.FALCO,
        verdict=AttestationVerdict.FAIL,
        evidence_hash="",
        detail={
            "rule": alert.get("rule", ""),
            "priority": priority,
            "output": alert.get("output", "")[:500],
            "container_id": container_id,
        },
    )
    session.add(record)
    await session.commit()

    await dispatch_webhooks(
        session,
        "state_transition",
        workload.id,
        "healthy",
        "failed",
        {"rule": alert.get("rule", ""), "priority": priority},
    )

    return {
        "transitioned": True,
        "workload_id": str(workload.id),
        "from_state": "healthy",
        "to_state": "failed",
        "rule": alert.get("rule", ""),
    }


@router.post("/api/alerts/falco")
async def receive_falco_alert(
    alert: dict,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("trigger_attestation"),
):
    return await _handle_falco_alert(alert, session)
