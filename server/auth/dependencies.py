import logging
import os

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request

from server.auth.models import CallerIdentity
from server.auth.rbac import check_permission
from server.config import settings

logger = logging.getLogger(__name__)

_oidc_validator = None


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


def _get_oidc_validator():
    global _oidc_validator
    if _oidc_validator is None:
        from server.auth.oidc import OIDCValidator

        _oidc_validator = OIDCValidator(
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
            principal_claim=settings.oidc_principal_claim,
            role_claim=settings.oidc_role_claim,
            scope_claim=settings.oidc_scope_claim,
            role_prefix=settings.oidc_role_prefix,
            actor_type_claim=settings.oidc_actor_type_claim,
            jwks_cache_ttl=settings.oidc_jwks_cache_ttl,
        )
    return _oidc_validator


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


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

    # oidc mode
    token = _extract_bearer(request)
    if not token:
        raise HTTPException(status_code=401, detail="Bearer token required")
    try:
        validator = _get_oidc_validator()
        return await validator.validate_and_extract(token)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token expired")
    except (pyjwt.InvalidTokenError, ValueError) as exc:
        raise HTTPException(status_code=401, detail=str(exc))


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
