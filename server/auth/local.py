"""Local admin authentication for bootstrap and standalone operation.

Issues short-lived JWTs signed with a local HMAC key. Intended for
initial setup before OIDC is configured, and as a break-glass fallback
in production.

Enable via ARBITER_AUTH_MODE=local or ARBITER_LOCAL_ADMIN_ENABLED=true
(the latter allows local auth alongside OIDC).
"""

import hashlib
import hmac
import logging
import secrets
import time

import jwt as pyjwt

from server.auth.models import CallerIdentity, Role

logger = logging.getLogger(__name__)

LOCAL_ISSUER = "arbiter-hub-local"
LOCAL_TOKEN_TTL = 3600
LOCAL_ALGORITHM = "HS256"


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), iterations=600_000
    ).hex()


class LocalAuthProvider:
    def __init__(self, admin_password_hash: str, signing_key: str):
        self._password_hash = admin_password_hash
        self._signing_key = signing_key

    @classmethod
    def from_password(cls, password: str, signing_key: str | None = None) -> "LocalAuthProvider":
        if not password:
            raise ValueError("local admin password must not be empty")
        salt = "arbiter-hub-local-admin"
        pw_hash = _hash_password(password, salt)
        key = signing_key or secrets.token_hex(32)
        return cls(admin_password_hash=pw_hash, signing_key=key)

    def verify_password(self, password: str) -> bool:
        salt = "arbiter-hub-local-admin"
        candidate = _hash_password(password, salt)
        return hmac.compare_digest(candidate, self._password_hash)

    def issue_token(self, principal: str = "local-admin") -> dict:
        now = int(time.time())
        claims = {
            "iss": LOCAL_ISSUER,
            "sub": principal,
            "iat": now,
            "exp": now + LOCAL_TOKEN_TTL,
            "roles": [Role.ADMIN],
            "actor_type": "admin",
            "scope": "openid profile attestation-admin",
        }
        token = pyjwt.encode(claims, self._signing_key, algorithm=LOCAL_ALGORITHM)
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": LOCAL_TOKEN_TTL,
            "scope": claims["scope"],
        }

    def validate_token(self, token: str) -> CallerIdentity:
        claims = pyjwt.decode(
            token,
            self._signing_key,
            algorithms=[LOCAL_ALGORITHM],
            issuer=LOCAL_ISSUER,
        )
        return CallerIdentity(
            principal=claims["sub"],
            actor_type=claims.get("actor_type", "admin"),
            roles=claims.get("roles", [Role.ADMIN]),
            scopes=claims.get("scope", "").split(),
        )
