from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from server.models.db import (
    Workload, AttestationRecord, Policy, WorkloadState, WorkloadType,
    get_session,
)
from server.models.schemas import (
    WorkloadRead, WorkloadList, AttestationRecordRead,
    PolicyRead, PaginatedResponse,
)
from server.auth.dependencies import get_caller, require_permission
from server.auth.models import CallerIdentity
from server.auth.rbac import check_scope

router = APIRouter()


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

    # Scope filtering: agents only see workloads matching their scope
    if "*" not in caller.scopes:
        # Extract principal realm/domain for scoped filtering
        scope_principals = []
        if "@" in caller.principal:
            realm = caller.principal.split('@')[-1]
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
    scope_key = workload.ipa_principal.split("@")[0] if "@" in workload.ipa_principal else workload.ipa_principal
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
    scope_key = workload.ipa_principal.split("@")[0] if "@" in workload.ipa_principal else workload.ipa_principal
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
    att_count = (await session.execute(
        select(func.count(AttestationRecord.id)).where(AttestationRecord.workload_id == workload_id)
    )).scalar_one()
    att_result = await session.execute(att_stmt)
    items = [AttestationRecordRead.model_validate(a) for a in att_result.scalars()]
    return PaginatedResponse[AttestationRecordRead](
        items=items, total=att_count, start_index=start_index, count=count
    )


@router.get("/policies")
async def list_policies(
    start_index: int = Query(1, ge=1, alias="startIndex"),
    count: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("read_workload"),
):
    stmt = select(Policy).where(Policy.active == True).offset(start_index - 1).limit(count)
    total = (await session.execute(
        select(func.count(Policy.id)).where(Policy.active == True)
    )).scalar_one()
    result = await session.execute(stmt)
    items = [PolicyRead.model_validate(p) for p in result.scalars()]
    return PaginatedResponse[PolicyRead](items=items, total=total, start_index=start_index, count=count)
