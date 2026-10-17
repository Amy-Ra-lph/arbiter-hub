from fastapi import Request, HTTPException, Depends
from server.auth.models import CallerIdentity
from server.auth.rbac import check_permission


async def get_caller(request: Request) -> CallerIdentity:
    # Phase 1: extract from X-Caller-* headers (dev mode)
    # Production: OIDC token validation or client cert extraction
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


def require_permission(action: str):
    async def _check(caller: CallerIdentity = Depends(get_caller)):
        if not check_permission(caller, action):
            raise HTTPException(
                status_code=403,
                detail={"type": "about:blank", "title": "Forbidden", "status": 403,
                        "detail": f"permission denied for action: {action}"},
            )
        return caller
    return Depends(_check)
