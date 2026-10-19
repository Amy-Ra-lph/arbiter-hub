from fastapi import APIRouter, Depends

from server.auth.dependencies import get_caller
from server.auth.models import CallerIdentity
from server.config import settings

router = APIRouter()


@router.get("/auth/config")
async def get_auth_config():
    return {
        "auth_mode": settings.auth_mode,
        "issuer": settings.oidc_issuer,
        "client_id": settings.oidc_client_id,
        "scopes": settings.oidc_scopes,
    }


@router.get("/auth/whoami")
async def whoami(caller: CallerIdentity = Depends(get_caller)):
    return {
        "principal": caller.principal,
        "roles": caller.roles,
        "actor_type": caller.actor_type,
    }
