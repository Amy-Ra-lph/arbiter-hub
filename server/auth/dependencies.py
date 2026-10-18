import os

from fastapi import Depends, HTTPException, Request

from server.auth.models import CallerIdentity
from server.auth.rbac import check_permission

_DEV_MODE = os.environ.get("ARBITER_DEV_MODE", "").lower() in ("1", "true", "yes")


async def get_caller(request: Request) -> CallerIdentity:
    if _DEV_MODE:
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

    # Production: no default privileges — caller must authenticate
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
