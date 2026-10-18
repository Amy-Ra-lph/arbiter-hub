from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from server.models.db import AuditLog, get_session
from server.models.schemas import AuditLogRead, PaginatedResponse
from server.auth.dependencies import require_permission

router = APIRouter()


@router.get("/audit")
async def list_audit(
    actor: str | None = None,
    action: str | None = None,
    start_index: int = Query(1, ge=1, alias="startIndex"),
    count: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    caller=require_permission("read_audit"),
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    count_stmt = select(func.count(AuditLog.id))

    # Apply filters
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
        count_stmt = count_stmt.where(AuditLog.actor == actor)
    if action:
        stmt = stmt.where(AuditLog.action == action)
        count_stmt = count_stmt.where(AuditLog.action == action)

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.offset(start_index - 1).limit(count)
    result = await session.execute(stmt)
    items = [AuditLogRead.model_validate(a) for a in result.scalars()]
    return PaginatedResponse[AuditLogRead](
        items=items, total=total, start_index=start_index, count=count
    )
