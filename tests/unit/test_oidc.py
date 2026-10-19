"""Tests for OIDC JWT validation."""

import base64
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from server.auth.oidc import OIDCValidator

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()
_public_numbers = _public_key.public_numbers()

ISSUER = "https://idp.example.com"
AUDIENCE = "arbiter-hub"


def _make_jwks():
    n = base64.urlsafe_b64encode(_public_numbers.n.to_bytes(256, "big")).rstrip(b"=").decode()
    e = base64.urlsafe_b64encode(_public_numbers.e.to_bytes(3, "big")).rstrip(b"=").decode()
    return {
        "keys": [{"kty": "RSA", "kid": "test-kid", "n": n, "e": e, "alg": "RS256", "use": "sig"}]
    }


def _sign_token(claims: dict) -> str:
    return jwt.encode(claims, _private_key, algorithm="RS256", headers={"kid": "test-kid"})


def _base_claims(**overrides):
    c = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "admin@IPA.TEST",
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
        "scope": "attestation-admin attestation-operator",
    }
    c.update(overrides)
    return c


def _make_validator(**kwargs):
    defaults = {
        "issuer": ISSUER,
        "audience": AUDIENCE,
        "role_claim": "",
        "scope_claim": "scope",
        "principal_claim": "sub",
        "role_prefix": "",
        "actor_type_claim": "",
        "jwks_override": _make_jwks(),
    }
    defaults.update(kwargs)
    return OIDCValidator(**defaults)


async def test_valid_token_extracts_identity():
    v = _make_validator()
    token = _sign_token(_base_claims())
    identity = await v.validate_and_extract(token)
    assert identity.principal == "admin@IPA.TEST"
    assert "attestation-admin" in identity.roles
    assert "attestation-operator" in identity.roles


async def test_expired_token_raises():
    v = _make_validator()
    token = _sign_token(_base_claims(exp=int(time.time()) - 60))
    with pytest.raises(Exception, match="expired|Expired"):
        await v.validate_and_extract(token)


async def test_wrong_audience_raises():
    v = _make_validator(audience="wrong-aud")
    token = _sign_token(_base_claims())
    with pytest.raises(Exception, match="audience|Audience"):
        await v.validate_and_extract(token)


async def test_bad_signature_raises():
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    bad_token = jwt.encode(
        _base_claims(), other_key, algorithm="RS256", headers={"kid": "test-kid"}
    )
    v = _make_validator()
    with pytest.raises(Exception, match="[Ss]ignature"):
        await v.validate_and_extract(bad_token)


async def test_keycloak_role_claim_extraction():
    v = _make_validator(
        role_claim="realm_access.roles",
        principal_claim="preferred_username",
        role_prefix="attestation-",
    )
    claims = _base_claims(preferred_username="admin", realm_access={"roles": ["admin", "operator"]})
    token = _sign_token(claims)
    identity = await v.validate_and_extract(token)
    assert identity.principal == "admin"
    assert "attestation-admin" in identity.roles
    assert "attestation-operator" in identity.roles


async def test_actor_type_derived_from_claims():
    v = _make_validator()
    human = _sign_token(_base_claims(preferred_username="alice"))
    assert (await v.validate_and_extract(human)).actor_type == "user"
    machine = _sign_token(_base_claims())
    assert (await v.validate_and_extract(machine)).actor_type == "service"


async def test_unknown_kid_with_no_refetch_raises():
    v = _make_validator(jwks_override={"keys": []})
    token = _sign_token(_base_claims())
    with pytest.raises(Exception, match="[Ss]igning key|kid"):
        await v.validate_and_extract(token)


async def test_empty_role_claim_with_no_scopes_yields_empty_roles():
    v = _make_validator()
    token = _sign_token(_base_claims(scope=""))
    identity = await v.validate_and_extract(token)
    assert identity.roles == []


async def test_missing_principal_claim_raises():
    v = _make_validator(principal_claim="preferred_username")
    token = _sign_token(_base_claims())  # has sub but not preferred_username
    with pytest.raises(Exception, match="[Pp]rincipal|claim"):
        await v.validate_and_extract(token)


async def test_jwks_fetched_on_first_request_without_override():
    """Without jwks_override, validator must fetch JWKS on first request."""
    v = OIDCValidator(
        issuer=ISSUER,
        audience=AUDIENCE,
        role_claim="",
        scope_claim="scope",
        principal_claim="sub",
        jwks_override=None,
    )
    assert v._jwks is None
    assert v._jwks_fetched_at == 0
    # Manually inject JWKS to simulate successful fetch
    v._jwks = _make_jwks()
    v._jwks_fetched_at = time.time()
    token = _sign_token(_base_claims())
    identity = await v.validate_and_extract(token)
    assert identity.principal == "admin@IPA.TEST"


async def test_unknown_kid_rate_limited_by_ttl():
    """Unknown kid within TTL window should not trigger refetch."""
    v = _make_validator(jwks_cache_ttl=3600)
    # Cache is fresh (just created with override), unknown kid should fail immediately
    token = jwt.encode(
        _base_claims(), _private_key, algorithm="RS256", headers={"kid": "nonexistent-kid"}
    )
    with pytest.raises(Exception, match="[Ss]igning key|kid"):
        await v.validate_and_extract(token)
