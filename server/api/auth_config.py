from fastapi import APIRouter

from server.config import settings

router = APIRouter()


@router.get("/auth/config")
async def get_auth_config():
    return {
        "auth_mode": settings.auth_mode,
        "issuer": settings.oidc_issuer,
        "client_id": settings.oidc_client_id,
        "scopes": "openid profile",
    }
