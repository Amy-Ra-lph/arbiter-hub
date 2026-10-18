import os

from fastapi import Depends, HTTPException, Request

from server.auth.models import CallerIdentity
from server.auth.rbac import check_permission
from server.config import settings


def _resolve_auth_mode(auth_mode: str, dev_mode_legacy: bool) -> str:
    if auth_mode:
        return auth_mode
    if dev_mode_legacy:
        return "dev"
    return "dev"


_dev_mode_legacy = os.environ.get("ARBITER_DEV_MODE", "").lower() in (
    "1",
    "true",
    "yes",
)
_auth_mode = _resolve_auth_mode(settings.auth_mode, _dev_mode_legacy)


async def get_caller(request: Request) -> CallerIdentity:
    if _auth_mode == "dev":
        principal = request.headers.get("X-Caller-Principal", "anonymous")
        actor_type = request.headers.get("X-Caller-Type", "admin")
        roles = request.headers.get("X-Caller-Roles", "attestation-admin").split(",")
        scopes = request.headers.get("X-Caller-Scopes", "*").split(",")
        return CallerIdentity(
            principal=principal,
            actor_type=actor_type,
            roles=[r.strip() for r in roles],
            scopes=[s.strip() for s in scopes],
        )

    if _auth_mode == "proxy":
        principal = request.headers.get("X-Caller-Principal")
        if not principal:
            raise HTTPException(status_code=401, detail="authentication required")
        actor_type = request.headers.get("X-Caller-Type", "user")
        roles = request.headers.get("X-Caller-Roles", "").split(",")
        scopes = request.headers.get("X-Caller-Scopes", "").split(",")
        return CallerIdentity(
            principal=principal,
            actor_type=actor_type,
            roles=[r.strip() for r in roles if r.strip()],
            scopes=[s.strip() for s in scopes if s.strip()],
        )

    # oidc mode — placeholder until Task 2 implements OIDCValidator
    raise HTTPException(status_code=501, detail="OIDC auth not yet implemented")


def require_permission(action: str):
    async def _check(caller: CallerIdentity = Depends(get_caller)):
        if not check_permission(caller, action):
            raise HTTPException(
                status_code=403,
                detail={
                    "type": "about:blank",
                    "title": "Forbidden",
                    "status": 403,
                    "detail": f"permission denied for action: {action}",
                },
            )
        return caller

    return Depends(_check)
