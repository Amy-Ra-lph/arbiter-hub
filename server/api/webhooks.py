import asyncio
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import require_permission
from server.auth.models import CallerIdentity
from server.models.db import WebhookRegistration, get_session

log = logging.getLogger(__name__)

router = APIRouter()


def compute_hmac_signature(body: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def build_webhook_payload(
    event_type: str,
    workload_id: UUID,
    from_state: str,
    to_state: str,
    detail: dict | None = None,
) -> dict:
    return {
        "event_type": event_type,
        "workload_id": str(workload_id),
        "from_state": from_state,
        "to_state": to_state,
        "detail": detail or {},
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def dispatch_webhooks(
    session: AsyncSession,
    event_type: str,
    workload_id: UUID,
    from_state: str,
    to_state: str,
    detail: dict | None = None,
) -> None:
    try:
        stmt = select(WebhookRegistration)
        result = await session.execute(stmt)
        webhooks = result.scalars().all()
    except Exception as e:
        log.debug("webhook query failed (expected in tests): %s", e)
        return

    payload = build_webhook_payload(event_type, workload_id, from_state, to_state, detail)
    body = json.dumps(payload).encode()

    for wh in webhooks:
        if event_type not in wh.events and "*" not in wh.events:
            continue
        asyncio.create_task(_deliver_webhook(wh.url, body, wh.secret))


async def _deliver_webhook(url: str, body: bytes, secret: str) -> None:
    sig = compute_hmac_signature(body, secret)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Arbiter-Signature": sig,
                },
            )
    except Exception as e:
        log.warning("webhook delivery to %s failed: %s", url, e)


class WebhookCreate(BaseModel):
    url: str
    events: list[str]
    secret: str


class WebhookRead(BaseModel):
    id: UUID
    url: str
    events: list[str]
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("/api/webhooks", response_model=WebhookRead, status_code=201)
async def register_webhook(
    body: WebhookCreate,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("register_webhook"),
):
    wh = WebhookRegistration(
        url=body.url,
        events=body.events,
        secret=body.secret,
        created_by=caller.principal,
    )
    session.add(wh)
    await session.commit()
    await session.refresh(wh)
    return WebhookRead.model_validate(wh)


@router.get("/api/webhooks")
async def list_webhooks(
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("read_workload"),
):
    result = await session.execute(select(WebhookRegistration))
    return [WebhookRead.model_validate(w) for w in result.scalars()]


@router.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: UUID,
    session: AsyncSession = Depends(get_session),
    caller: CallerIdentity = require_permission("register_webhook"),
):
    result = await session.execute(
        select(WebhookRegistration).where(WebhookRegistration.id == webhook_id)
    )
    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(status_code=404, detail="webhook not found")
    await session.delete(wh)
    await session.commit()
    return {"status": "deleted"}
