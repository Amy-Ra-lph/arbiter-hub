import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from server.auth.dependencies import get_caller
from server.auth.models import CallerIdentity
from server.config import settings

logger = logging.getLogger(__name__)

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
        "spnego_enabled": settings.spnego_enabled,
    }


class LocalLoginRequest(BaseModel):
    username: str = "admin"
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
    return provider.issue_token(principal=body.username)


_spnego_provider = None


def _get_spnego_provider():
    global _spnego_provider
    if _spnego_provider is None:
        from server.auth.spnego import SPNEGOProvider

        _spnego_provider = SPNEGOProvider(
            keytab_path=settings.spnego_keytab,
            service_principal=settings.spnego_principal or None,
        )
    return _spnego_provider


@router.post("/auth/negotiate")
async def negotiate_login(request: Request):
    """SPNEGO/Kerberos authentication — accepts Negotiate token, returns JWT.

    Clients use: curl --negotiate -u : -X POST https://hub/auth/negotiate
    """
    if not settings.spnego_enabled:
        raise HTTPException(status_code=404, detail="SPNEGO auth not enabled")

    from server.auth.spnego import GSSAPI_AVAILABLE

    if not GSSAPI_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="SPNEGO configured but gssapi package not installed",
        )

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Negotiate "):
        return JSONResponse(
            status_code=401,
            content={"detail": "send Authorization: Negotiate <token>"},
            headers={"WWW-Authenticate": "Negotiate"},
        )

    negotiate_token = auth_header[len("Negotiate "):]

    try:
        provider = _get_spnego_provider()
        principal, response_token = provider.validate_token(negotiate_token)
    except Exception as exc:
        logger.warning("SPNEGO validation failed: %s", exc)
        return JSONResponse(
            status_code=401,
            content={"detail": f"SPNEGO validation failed: {exc}"},
            headers={"WWW-Authenticate": "Negotiate"},
        )

    # Issue a local JWT for the authenticated principal
    from server.auth.dependencies import _get_local_provider

    identity = provider.build_identity(principal)
    local = _get_local_provider()
    token_response = local.issue_token(principal=identity.principal)

    headers = {}
    if response_token:
        headers["WWW-Authenticate"] = f"Negotiate {response_token}"

    return JSONResponse(content=token_response, headers=headers)


@router.get("/auth/whoami")
async def whoami(caller: CallerIdentity = Depends(get_caller)):
    return {
        "principal": caller.principal,
        "roles": caller.roles,
        "actor_type": caller.actor_type,
    }
