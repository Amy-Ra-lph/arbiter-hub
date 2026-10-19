import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.db import AuditLog, StateTransition, Workload, WorkloadState


class InvalidTransitionError(Exception):
    def __init__(self, from_state: WorkloadState, to_state: WorkloadState, reason: str):
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        super().__init__(f"{from_state.value} -> {to_state.value}: {reason}")


VALID_TRANSITIONS: dict[WorkloadState, set[WorkloadState]] = {
    WorkloadState.REGISTERED: {WorkloadState.ATTESTING},
    WorkloadState.ATTESTING: {WorkloadState.HEALTHY, WorkloadState.FAILED},
    WorkloadState.HEALTHY: {WorkloadState.ATTESTING, WorkloadState.STALE, WorkloadState.FAILED, WorkloadState.REVOKED},
    WorkloadState.STALE: {WorkloadState.ATTESTING},
    WorkloadState.FAILED: {WorkloadState.UNDER_REMEDIATION, WorkloadState.REVOKED},
    WorkloadState.UNDER_REMEDIATION: {WorkloadState.ATTESTING},
    WorkloadState.REVOKED: set(),
}


def validate_transition(from_state: WorkloadState, to_state: WorkloadState) -> None:
    allowed = VALID_TRANSITIONS.get(from_state, set())
    if to_state not in allowed:
        if from_state == WorkloadState.REVOKED:
            reason = "revoked is terminal — requires new enrollment"
        elif from_state == WorkloadState.FAILED and to_state == WorkloadState.HEALTHY:
            reason = "prohibited — must go through Under Remediation -> Attesting -> Healthy"
        else:
            reason = f"not a valid transition from {from_state.value}"
        raise InvalidTransitionError(from_state, to_state, reason)


async def transition(
    session: AsyncSession,
    workload: Workload,
    to_state: WorkloadState,
    triggered_by: str,
    justification: str | None = None,
) -> StateTransition:
    validate_transition(workload.current_state, to_state)

    from_state = workload.current_state
    workload.current_state = to_state

    record = StateTransition(
        workload_id=workload.id,
        from_state=from_state,
        to_state=to_state,
        triggered_by=triggered_by,
        justification=justification,
    )
    session.add(record)

    audit = AuditLog(
        actor=triggered_by,
        actor_type="system",
        action="state_transition",
        target_type="workload",
        target_id=workload.id,
        detail={"from": from_state.value, "to": to_state.value, "justification": justification},
    )
    session.add(audit)

    return record


async def check_stale_workloads(session: AsyncSession) -> list[uuid.UUID]:
    now = datetime.now(UTC)
    stmt = select(Workload).where(
        Workload.current_state == WorkloadState.HEALTHY,
        Workload.last_attested_at.isnot(None),
    )
    result = await session.execute(stmt)
    stale_ids = []
    for workload in result.scalars():
        elapsed = (now - workload.last_attested_at).total_seconds()
        if elapsed >= workload.stale_ttl_seconds:
            await transition(session, workload, WorkloadState.STALE, "staleness_scheduler")
            stale_ids.append(workload.id)
    await session.commit()
    return stale_ids
