from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from server.auth.dependencies import get_caller
from server.auth.models import CallerIdentity
from server.config import settings

router = APIRouter()


@router.get("/auth/config")
async def get_auth_config():
    return {
        "auth_mode": settings.auth_mode,
        "issuer": settings.oidc_issuer,
        "client_id": settings.oidc_ui_client_id or settings.oidc_client_id,
        "scopes": settings.oidc_ui_scopes or settings.oidc_scopes,
        "local_auth_enabled": settings.local_admin_enabled
        or settings.auth_mode == "local",
    }


class LocalLoginRequest(BaseModel):
    password: str


@router.post("/auth/local")
async def local_login(body: LocalLoginRequest):
    if settings.auth_mode != "local" and not settings.local_admin_enabled:
        raise HTTPException(status_code=404, detail="local auth not enabled")
    if not settings.local_admin_password:
        raise HTTPException(status_code=503, detail="local admin password not configured")

    from server.auth.dependencies import _get_local_provider

    provider = _get_local_provider()
    if not provider.verify_password(body.password):
        raise HTTPException(status_code=401, detail="invalid credentials")
    return provider.issue_token()


@router.get("/auth/whoami")
async def whoami(caller: CallerIdentity = Depends(get_caller)):
    return {
        "principal": caller.principal,
        "roles": caller.roles,
        "actor_type": caller.actor_type,
    }
