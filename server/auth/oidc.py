"""OIDC JWT token validation with JWKS caching."""

import asyncio
import logging
import time

import httpx
import jwt

from server.auth.models import CallerIdentity

logger = logging.getLogger(__name__)


def _traverse_claim(claims: dict, dot_path: str):
    """Traverse a dot-separated path into a nested claims dict."""
    parts = dot_path.split(".")
    value = claims
    for part in parts:
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


class OIDCValidator:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        principal_claim: str = "sub",
        role_claim: str = "realm_access.roles",
        scope_claim: str = "scope",
        role_prefix: str = "",
        actor_type_claim: str = "",
        jwks_cache_ttl: int = 3600,
        jwks_override: dict | None = None,
    ):
        self._issuer = issuer
        self._audience = audience
        self._principal_claim = principal_claim
        self._role_claim = role_claim
        self._scope_claim = scope_claim
        self._role_prefix = role_prefix
        self._actor_type_claim = actor_type_claim
        self._jwks_cache_ttl = jwks_cache_ttl
        self._jwks: dict | None = jwks_override
        self._jwks_fetched_at: float = time.time() if jwks_override else 0
        self._http_client: httpx.AsyncClient | None = None
        self._jwks_lock = asyncio.Lock()

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(verify=True, timeout=10)
        return self._http_client

    async def _fetch_jwks(self) -> dict:
        client = await self._get_http_client()
        discovery_url = f"{self._issuer.rstrip('/')}/.well-known/openid-configuration"
        resp = await client.get(discovery_url)
        resp.raise_for_status()
        jwks_uri = resp.json()["jwks_uri"]
        resp = await client.get(jwks_uri)
        resp.raise_for_status()
        self._jwks = resp.json()
        self._jwks_fetched_at = time.time()
        return self._jwks

    def _find_key(self, kid: str) -> dict | None:
        if not self._jwks or "keys" not in self._jwks:
            return None
        for key in self._jwks["keys"]:
            if key.get("kid") == kid:
                return key
        return None

    async def _get_signing_key(self, kid: str) -> jwt.PyJWK:
        key_data = self._find_key(kid)
        if key_data is None:
            async with self._jwks_lock:
                # Re-check after acquiring lock (another coroutine may have fetched)
                key_data = self._find_key(kid)
                if key_data is None:
                    cache_age = time.time() - self._jwks_fetched_at
                    if self._jwks_fetched_at == 0 or cache_age > self._jwks_cache_ttl:
                        try:
                            await self._fetch_jwks()
                            key_data = self._find_key(kid)
                        except Exception:
                            logger.warning("JWKS refetch failed for kid=%s", kid)
        if key_data is None:
            raise jwt.exceptions.InvalidKeyError(f"Signing key not found for kid={kid}")
        return jwt.PyJWK(key_data)

    def _extract_roles(self, claims: dict) -> list[str]:
        if self._role_claim:
            raw = _traverse_claim(claims, self._role_claim)
            if isinstance(raw, list):
                return [f"{self._role_prefix}{r}" for r in raw]
            return []
        scope_str = claims.get(self._scope_claim, "")
        if not scope_str:
            return []
        return [s for s in scope_str.split() if s]

    def _extract_scopes(self, claims: dict) -> list[str]:
        scope_str = claims.get(self._scope_claim, "")
        if not scope_str:
            return []
        return scope_str.split()

    def _extract_actor_type(self, claims: dict) -> str:
        if self._actor_type_claim:
            value = claims.get(self._actor_type_claim)
            if value:
                return str(value)
        if "preferred_username" in claims or "nonce" in claims:
            return "user"
        return "service"

    async def validate_and_extract(self, token: str) -> CallerIdentity:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid", "")
        signing_key = await self._get_signing_key(kid)

        decode_opts: dict = {
            "algorithms": ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"],
            "issuer": self._issuer,
        }
        if self._audience:
            decode_opts["audience"] = self._audience
        else:
            decode_opts["options"] = {"verify_aud": False}
        claims = jwt.decode(token, signing_key.key, **decode_opts)

        principal = _traverse_claim(claims, self._principal_claim)
        if not principal:
            raise ValueError(f"Principal claim '{self._principal_claim}' not found in token")

        return CallerIdentity(
            principal=str(principal),
            actor_type=self._extract_actor_type(claims),
            roles=self._extract_roles(claims),
            scopes=self._extract_scopes(claims),
        )
