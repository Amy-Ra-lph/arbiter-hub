from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import require_permission
from server.auth.models import CallerIdentity
from server.auth.rbac import check_scope
from server.models.db import (
    AttestationRecord,
    AuditLog,
    Policy,
    StateTransition,
    Workload,
    WorkloadState,
    WorkloadType,
    get_session,
)
from server.models.schemas import (
    AttestationRecordRead,
    ComplianceResult,
    PaginatedResponse,
    PolicyCreate,
    PolicyRead,
    StateTransitionRead,
    WorkloadCreate,
    WorkloadList,
    WorkloadRead,
)
from server.state.machine import InvalidTransitionError, transition

router = APIRouter()


class RevokeRequest(BaseModel):
    justification: str


class RemediateRequest(BaseModel):
    justification: str | None = None


@router.get("/workloads", response_model=WorkloadList)
async def list_workloads(
    state: WorkloadState | None = None,
    workload_type: WorkloadType | None = None,
    start_index: int = Query(1, ge=1, alias="startIndex"),
    count: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("read_workload"),
):
    stmt = select(Workload)
    count_stmt = select(func.count(Workload.id))

    # Apply filters
    if state:
        stmt = stmt.where(Workload.current_state == state)
        count_stmt = count_stmt.where(Workload.current_state == state)
    if workload_type:
        stmt = stmt.where(Workload.workload_type == workload_type)
        count_stmt = count_stmt.where(Workload.workload_type == workload_type)

    # Scope filtering: agents see only their own workloads; admins see all
    from server.auth.models import Role

    is_admin = Role.ADMIN.value in caller.roles
    if not is_admin and "*" not in caller.scopes:
        scope_principals = []
        if "@" in caller.principal:
            realm = caller.principal.split("@")[-1]
            scope_principals = [f"{s}@{realm}" for s in caller.scopes]
        else:
            scope_principals = caller.scopes
        stmt = stmt.where(Workload.ipa_principal.in_(scope_principals))
        count_stmt = count_stmt.where(Workload.ipa_principal.in_(scope_principals))

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.offset(start_index - 1).limit(count)
    result = await session.execute(stmt)
    items = [WorkloadRead.model_validate(w) for w in result.scalars()]
    return WorkloadList(items=items, total=total, start_index=start_index, count=count)


@router.get("/workloads/{workload_id}", response_model=WorkloadRead)
async def get_workload(
    workload_id: UUID,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("read_workload"),
):
    stmt = select(Workload).where(Workload.id == workload_id)
    result = await session.execute(stmt)
    workload = result.scalar_one_or_none()
    if not workload:
        raise HTTPException(status_code=404, detail="workload not found")

    # Scope check: agents can only see workloads in their scope
    scope_key = (
        workload.ipa_principal.split("@")[0]
        if "@" in workload.ipa_principal
        else workload.ipa_principal
    )
    if not check_scope(caller, scope_key):
        raise HTTPException(status_code=404, detail="workload not found")

    return WorkloadRead.model_validate(workload)


@router.get("/workloads/{workload_id}/attestations")
async def get_attestations(
    workload_id: UUID,
    start_index: int = Query(1, ge=1, alias="startIndex"),
    count: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("read_workload"),
):
    # Verify workload exists and caller has access
    stmt = select(Workload).where(Workload.id == workload_id)
    result = await session.execute(stmt)
    workload = result.scalar_one_or_none()
    if not workload:
        raise HTTPException(status_code=404, detail="workload not found")

    # Scope check
    scope_key = (
        workload.ipa_principal.split("@")[0]
        if "@" in workload.ipa_principal
        else workload.ipa_principal
    )
    if not check_scope(caller, scope_key):
        raise HTTPException(status_code=404, detail="workload not found")

    # Get attestation records
    att_stmt = (
        select(AttestationRecord)
        .where(AttestationRecord.workload_id == workload_id)
        .order_by(AttestationRecord.created_at.desc())
        .offset(start_index - 1)
        .limit(count)
    )
    att_count = (
        await session.execute(
            select(func.count(AttestationRecord.id)).where(
                AttestationRecord.workload_id == workload_id
            )
        )
    ).scalar_one()
    att_result = await session.execute(att_stmt)
    items = [AttestationRecordRead.model_validate(a) for a in att_result.scalars()]
    return PaginatedResponse[AttestationRecordRead](
        items=items, total=att_count, start_index=start_index, count=count
    )


@router.get("/workloads/{workload_id}/compliance", response_model=ComplianceResult)
async def check_compliance(
    workload_id: UUID,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("read_workload"),
):
    stmt = select(Workload).where(Workload.id == workload_id)
    result = await session.execute(stmt)
    workload = result.scalar_one_or_none()
    if not workload:
        raise HTTPException(status_code=404, detail="workload not found")

    scope_key = (
        workload.ipa_principal.split("@")[0]
        if "@" in workload.ipa_principal
        else workload.ipa_principal
    )
    if not check_scope(caller, scope_key):
        raise HTTPException(status_code=404, detail="workload not found")

    checks = []
    checks.append(
        {
            "check": "state_healthy",
            "passed": workload.current_state == WorkloadState.HEALTHY,
            "detail": f"state={workload.current_state.value}",
        }
    )
    attestation_current = False
    if workload.last_attested_at:
        age = (datetime.now(UTC) - workload.last_attested_at).total_seconds()
        attestation_current = age <= workload.stale_ttl_seconds
    checks.append(
        {
            "check": "attestation_current",
            "passed": attestation_current,
            "detail": f"last_attested={workload.last_attested_at}",
        }
    )

    compliant = all(c["passed"] for c in checks)
    return ComplianceResult(
        workload_id=workload.id,
        compliant=compliant,
        checks=checks,
        evaluated_at=datetime.now(UTC),
    )


@router.delete("/workloads/{workload_id}")
async def delete_workload(
    workload_id: UUID,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("register_workload"),
):
    stmt = select(Workload).where(Workload.id == workload_id)
    result = await session.execute(stmt)
    workload = result.scalar_one_or_none()
    if not workload:
        raise HTTPException(status_code=404, detail="workload not found")

    scope_key = (
        workload.ipa_principal.split("@")[0]
        if "@" in workload.ipa_principal
        else workload.ipa_principal
    )
    if not check_scope(caller, scope_key):
        raise HTTPException(status_code=404, detail="workload not found")

    # Delete related records first
    att_stmt = select(AttestationRecord).where(AttestationRecord.workload_id == workload_id)
    att_result = await session.execute(att_stmt)
    for att in att_result.scalars():
        await session.delete(att)

    trans_stmt = select(StateTransition).where(StateTransition.workload_id == workload_id)
    trans_result = await session.execute(trans_stmt)
    for trans in trans_result.scalars():
        await session.delete(trans)

    audit = AuditLog(
        actor=caller.principal,
        actor_type=caller.actor_type,
        action="delete_workload",
        target_type="workload",
        target_id=workload.id,
        detail={"principal": workload.ipa_principal},
    )
    session.add(audit)
    await session.delete(workload)
    await session.commit()
    return {"status": "deleted"}


@router.get("/workloads/{workload_id}/transitions")
async def get_transitions(
    workload_id: UUID,
    start_index: int = Query(1, ge=1, alias="startIndex"),
    count: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("read_workload"),
):
    stmt = select(Workload).where(Workload.id == workload_id)
    result = await session.execute(stmt)
    workload = result.scalar_one_or_none()
    if not workload:
        raise HTTPException(status_code=404, detail="workload not found")

    scope_key = (
        workload.ipa_principal.split("@")[0]
        if "@" in workload.ipa_principal
        else workload.ipa_principal
    )
    if not check_scope(caller, scope_key):
        raise HTTPException(status_code=404, detail="workload not found")

    trans_stmt = (
        select(StateTransition)
        .where(StateTransition.workload_id == workload_id)
        .order_by(StateTransition.created_at.desc())
        .offset(start_index - 1)
        .limit(count)
    )
    trans_count = (
        await session.execute(
            select(func.count(StateTransition.id)).where(StateTransition.workload_id == workload_id)
        )
    ).scalar_one()
    trans_result = await session.execute(trans_stmt)
    items = [StateTransitionRead.model_validate(t) for t in trans_result.scalars()]
    return PaginatedResponse[StateTransitionRead](
        items=items, total=trans_count, start_index=start_index, count=count
    )


@router.get("/policies")
async def list_policies(
    start_index: int = Query(1, ge=1, alias="startIndex"),
    count: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("read_workload"),
):
    stmt = select(Policy).offset(start_index - 1).limit(count)
    total = (await session.execute(select(func.count(Policy.id)))).scalar_one()
    result = await session.execute(stmt)
    items = [PolicyRead.model_validate(p) for p in result.scalars()]
    return PaginatedResponse[PolicyRead](
        items=items, total=total, start_index=start_index, count=count
    )


@router.post("/workloads", response_model=WorkloadRead, status_code=201)
async def register_workload(
    body: WorkloadCreate,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("register_workload"),
):
    existing = await session.execute(
        select(Workload).where(Workload.ipa_principal == body.ipa_principal)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="workload with this principal already exists")

    workload = Workload(
        ipa_principal=body.ipa_principal,
        display_name=body.display_name,
        workload_type=body.workload_type,
        backend_types=[bt.value for bt in body.backend_types],
        stale_ttl_seconds=body.stale_ttl_seconds,
        metadata_=body.metadata,
    )
    session.add(workload)
    audit = AuditLog(
        actor=caller.principal,
        actor_type=caller.actor_type,
        action="register_workload",
        target_type="workload",
        target_id=workload.id,
        detail={"principal": body.ipa_principal},
    )
    session.add(audit)
    await session.commit()
    await session.refresh(workload)
    return WorkloadRead.model_validate(workload)


@router.post("/workloads/{workload_id}/revoke")
async def revoke_workload(
    workload_id: UUID,
    body: RevokeRequest,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("revoke_workload"),
):
    stmt = select(Workload).where(Workload.id == workload_id)
    result = await session.execute(stmt)
    workload = result.scalar_one_or_none()
    if not workload:
        raise HTTPException(status_code=404, detail="workload not found")
    try:
        record = await transition(
            session,
            workload,
            WorkloadState.REVOKED,
            triggered_by=caller.principal,
            justification=body.justification,
        )
        await session.commit()
        return {"status": "revoked", "transition_id": str(record.id)}
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/workloads/{workload_id}/remediate")
async def remediate_workload(
    workload_id: UUID,
    body: RemediateRequest,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("remediate_workload"),
):
    stmt = select(Workload).where(Workload.id == workload_id)
    result = await session.execute(stmt)
    workload = result.scalar_one_or_none()
    if not workload:
        raise HTTPException(status_code=404, detail="workload not found")
    try:
        record = await transition(
            session,
            workload,
            WorkloadState.UNDER_REMEDIATION,
            triggered_by=caller.principal,
            justification=body.justification,
        )
        await session.commit()
        return {"status": "under_remediation", "transition_id": str(record.id)}
    except InvalidTransitionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/policies", status_code=201)
async def create_policy(
    body: PolicyCreate,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("create_policy"),
):
    policy = Policy(
        name=body.name,
        policy_type=body.policy_type,
        policy_content=body.policy_content,
        scope=body.scope,
        active=body.active,
        created_by=caller.principal,
    )
    session.add(policy)
    await session.commit()
    await session.refresh(policy)
    return PolicyRead.model_validate(policy)
