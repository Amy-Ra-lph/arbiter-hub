# Phase 2.5: OIDC Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace trust-X-headers auth with real OIDC JWT validation, add CSRF protection, and enforce append-only audit log.

**Architecture:** Three-mode auth (`dev`/`oidc`/`proxy`) selected by `ARBITER_AUTH_MODE`. In OIDC mode, `OIDCValidator` fetches JWKS from the IdP, validates JWT signatures, and maps claims to existing `CallerIdentity`. UI uses `oidc-client-ts` for authorization code + PKCE flow, stores tokens in memory only.

**Tech Stack:** PyJWT + cryptography (backend JWT), oidc-client-ts (frontend OIDC), PostgreSQL triggers (append-only audit)

**Spec:** `docs/superpowers/specs/2026-10-18-phase25-oidc-auth-design.md`

## Global Constraints

- Python ≥ 3.12, FastAPI ≥ 0.115, SQLAlchemy ≥ 2.0 (async)
- `ruff check .` and `ruff format --check .` must pass (rules: E, F, I, UP, W; line-length 100)
- `pytest tests/ -v` must pass (asyncio_mode = "auto")
- CI runs with `ARBITER_AUTH_MODE=dev` and `ARBITER_FERNET_KEY_FILE=""` — dev mode must stay working
- Existing 84 backend + 23 UI tests must not break
- No tokens in localStorage — memory only
- All new config via `ARBITER_` env prefix (pydantic-settings)

## Review Focus

1. **Expired JWKS cache + rotated signing key** — token arrives with unknown `kid` after IdP key rotation. Expect: single JWKS refetch, then validate. Not infinite retry loop.
2. **Empty `roles` list in OIDC mode with misconfigured claim path** — every request returns 403 silently. Expect: startup warning log when `oidc_role_claim` is set but claim path yields nothing from a test decode.
3. **`ARBITER_DEV_MODE=true` with `ARBITER_AUTH_MODE` unset** — backward compat. Expect: auth_mode resolves to `"dev"`, not `"oidc"`.
4. **UI token expiry mid-session** — RTK Query request gets 401. Expect: silent refresh attempt, then redirect to login if refresh fails. Not infinite 401 loop.
5. **POST request with no Origin header in OIDC mode** — CSRF middleware. Expect: 403 rejection, not silent pass-through.

---

### Task 1: Config + Auth Mode Resolution

**Files:**
- Modify: `server/config.py`
- Modify: `server/auth/dependencies.py`
- Test: `tests/unit/test_auth.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `settings.auth_mode: str` (resolved value: `"dev"` | `"oidc"` | `"proxy"`), `settings.oidc_principal_claim: str`, `settings.oidc_role_claim: str`, `settings.oidc_scope_claim: str`, `settings.oidc_role_prefix: str`, `settings.oidc_jwks_cache_ttl: int`, `settings.oidc_actor_type_claim: str`

- [ ] **Step 1: Write failing tests for config and auth mode resolution**

```python
# tests/unit/test_auth.py — append these

def test_auth_mode_defaults_to_dev():
    """auth_mode defaults to 'dev' when neither AUTH_MODE nor DEV_MODE set."""
    from server.auth.dependencies import _resolve_auth_mode
    assert _resolve_auth_mode(auth_mode="dev", dev_mode_legacy=False) == "dev"

def test_dev_mode_legacy_sets_auth_mode_dev():
    """ARBITER_DEV_MODE=true with AUTH_MODE unset → 'dev'."""
    from server.auth.dependencies import _resolve_auth_mode
    assert _resolve_auth_mode(auth_mode="", dev_mode_legacy=True) == "dev"

def test_auth_mode_overrides_dev_mode():
    """AUTH_MODE takes precedence over DEV_MODE."""
    from server.auth.dependencies import _resolve_auth_mode
    assert _resolve_auth_mode(auth_mode="oidc", dev_mode_legacy=True) == "oidc"

def test_proxy_mode_requires_principal_header(client_fixture):
    """proxy mode with no X-Caller-Principal → 401."""
    # Uses existing test client pattern with ARBITER_AUTH_MODE=proxy
    ...

def test_oidc_mode_rejects_no_bearer(client_fixture):
    """oidc mode with no Authorization header → 401."""
    ...
```

- [ ] **Step 2: Run tests — expect ImportError on `_resolve_auth_mode`**

Run: `pytest tests/unit/test_auth.py -v -k "auth_mode"`

- [ ] **Step 3: Add new settings to `server/config.py`**

Add to `Settings` class:
```python
auth_mode: str = "dev"
oidc_principal_claim: str = "sub"
oidc_role_claim: str = "realm_access.roles"
oidc_scope_claim: str = "scope"
oidc_role_prefix: str = ""
oidc_jwks_cache_ttl: int = 3600
oidc_actor_type_claim: str = ""
```

- [ ] **Step 4: Implement `_resolve_auth_mode()` and update `get_caller()` in `server/auth/dependencies.py`**

Extract auth-mode resolution into a pure function `_resolve_auth_mode(auth_mode: str, dev_mode_legacy: bool) -> str`. Refactor `get_caller()` to branch on three modes: `dev` (existing X-header logic), `proxy` (existing non-dev logic requiring X-Caller-Principal), `oidc` (placeholder raising 501 — Task 2 fills this in). Remove the bare `_DEV_MODE` bool; replace with `_auth_mode = _resolve_auth_mode(settings.auth_mode, ...)` reading `ARBITER_DEV_MODE` from env for legacy compat.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: all 84 backend tests pass (dev mode path unchanged)

- [ ] **Step 6: Commit**

```
feat(auth): add auth_mode config with dev/oidc/proxy modes

Three-mode auth resolution with backward compat for ARBITER_DEV_MODE.
OIDC mode placeholder — JWT validation in next commit.
```

---

### Task 2: OIDC JWT Validator

**Files:**
- Create: `server/auth/oidc.py`
- Modify: `pyproject.toml` (add `PyJWT[crypto]`)
- Test: `tests/unit/test_oidc.py`

**Interfaces:**
- Consumes: `CallerIdentity` from `server/auth/models.py`, settings from Task 1
- Produces: `OIDCValidator` class with `async validate_and_extract(token: str) -> CallerIdentity`

- [ ] **Step 1: Add `PyJWT[crypto]` to `pyproject.toml` dependencies**

- [ ] **Step 2: Install updated dependencies**

Run: `pip install -e ".[dev]"`

- [ ] **Step 3: Write failing tests for OIDC validator**

Create `tests/unit/test_oidc.py`:

```python
import time
import jwt
from server.auth.oidc import OIDCValidator
from server.auth.models import CallerIdentity

# Generate test RSA key pair at module level
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()
_public_numbers = _public_key.public_numbers()

def _make_jwks():
    """Build a JWKS dict from test public key."""
    import base64
    n = base64.urlsafe_b64encode(
        _public_numbers.n.to_bytes(256, "big")
    ).rstrip(b"=").decode()
    e = base64.urlsafe_b64encode(
        _public_numbers.e.to_bytes(3, "big")
    ).rstrip(b"=").decode()
    return {"keys": [{"kty": "RSA", "kid": "test-kid", "n": n, "e": e, "alg": "RS256", "use": "sig"}]}

def _sign_token(claims: dict) -> str:
    return jwt.encode(claims, _private_key, algorithm="RS256", headers={"kid": "test-kid"})

ISSUER = "https://idp.example.com"
AUDIENCE = "arbiter-hub"

def _base_claims(**overrides):
    c = {"iss": ISSUER, "aud": AUDIENCE, "sub": "admin@IPA.TEST",
         "exp": int(time.time()) + 300, "iat": int(time.time()),
         "scope": "attestation-admin attestation-operator"}
    c.update(overrides)
    return c

async def test_valid_token_extracts_identity():
    v = OIDCValidator(issuer=ISSUER, audience=AUDIENCE, role_claim="", scope_claim="scope",
                      principal_claim="sub", role_prefix="", actor_type_claim="",
                      jwks_override=_make_jwks())
    token = _sign_token(_base_claims())
    identity = await v.validate_and_extract(token)
    assert identity.principal == "admin@IPA.TEST"
    assert "attestation-admin" in identity.roles  # scopes-as-roles

async def test_expired_token_raises():
    v = OIDCValidator(issuer=ISSUER, audience=AUDIENCE, role_claim="", scope_claim="scope",
                      principal_claim="sub", role_prefix="", actor_type_claim="",
                      jwks_override=_make_jwks())
    token = _sign_token(_base_claims(exp=int(time.time()) - 60))
    with pytest.raises(Exception, match="expired|ExpiredSignature"):
        await v.validate_and_extract(token)

async def test_wrong_audience_raises():
    v = OIDCValidator(issuer=ISSUER, audience="wrong-aud", role_claim="", scope_claim="scope",
                      principal_claim="sub", role_prefix="", actor_type_claim="",
                      jwks_override=_make_jwks())
    token = _sign_token(_base_claims())
    with pytest.raises(Exception, match="audience|InvalidAudience"):
        await v.validate_and_extract(token)

async def test_bad_signature_raises():
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    bad_token = jwt.encode(_base_claims(), other_key, algorithm="RS256", headers={"kid": "test-kid"})
    v = OIDCValidator(issuer=ISSUER, audience=AUDIENCE, role_claim="", scope_claim="scope",
                      principal_claim="sub", role_prefix="", actor_type_claim="",
                      jwks_override=_make_jwks())
    with pytest.raises(Exception, match="signature|InvalidSignature"):
        await v.validate_and_extract(bad_token)

async def test_keycloak_role_claim_extraction():
    v = OIDCValidator(issuer=ISSUER, audience=AUDIENCE, role_claim="realm_access.roles",
                      scope_claim="scope", principal_claim="preferred_username",
                      role_prefix="attestation-", actor_type_claim="",
                      jwks_override=_make_jwks())
    claims = _base_claims(preferred_username="admin", realm_access={"roles": ["admin", "operator"]})
    token = _sign_token(claims)
    identity = await v.validate_and_extract(token)
    assert identity.principal == "admin"
    assert "attestation-admin" in identity.roles
    assert "attestation-operator" in identity.roles

async def test_actor_type_derived_from_claims():
    """Tokens with preferred_username → 'user', without → 'service'."""
    v = OIDCValidator(issuer=ISSUER, audience=AUDIENCE, role_claim="", scope_claim="scope",
                      principal_claim="sub", role_prefix="", actor_type_claim="",
                      jwks_override=_make_jwks())
    # Human token
    human = _sign_token(_base_claims(preferred_username="alice"))
    assert (await v.validate_and_extract(human)).actor_type == "user"
    # Machine token
    machine = _sign_token(_base_claims())
    assert (await v.validate_and_extract(machine)).actor_type == "service"

async def test_unknown_kid_with_no_refetch_raises():
    """Token with kid not in JWKS and no live endpoint → raises."""
    v = OIDCValidator(issuer=ISSUER, audience=AUDIENCE, role_claim="", scope_claim="scope",
                      principal_claim="sub", role_prefix="", actor_type_claim="",
                      jwks_override={"keys": []})
    token = _sign_token(_base_claims())
    with pytest.raises(Exception, match="kid|signing key"):
        await v.validate_and_extract(token)

async def test_empty_role_claim_with_no_scopes_yields_empty_roles():
    """Token with role_claim='' and no scope claim → empty roles list (all requests 403)."""
    v = OIDCValidator(issuer=ISSUER, audience=AUDIENCE, role_claim="", scope_claim="scope",
                      principal_claim="sub", role_prefix="", actor_type_claim="",
                      jwks_override=_make_jwks())
    token = _sign_token(_base_claims(scope=""))
    identity = await v.validate_and_extract(token)
    assert identity.roles == []

async def test_missing_principal_claim_raises():
    """Token missing configured principal claim → raises."""
    v = OIDCValidator(issuer=ISSUER, audience=AUDIENCE, role_claim="", scope_claim="scope",
                      principal_claim="preferred_username", role_prefix="", actor_type_claim="",
                      jwks_override=_make_jwks())
    token = _sign_token(_base_claims())  # has sub but not preferred_username
    with pytest.raises(Exception, match="principal|claim"):
        await v.validate_and_extract(token)
```

- [ ] **Step 4: Run tests — expect ImportError**

Run: `pytest tests/unit/test_oidc.py -v`

- [ ] **Step 5: Implement `OIDCValidator` in `server/auth/oidc.py`**

Class with:
- `__init__` taking issuer, audience, claim config, and optional `jwks_override` for testing
- `_fetch_jwks()` — async httpx GET to discovery doc → jwks_uri → keys. Cache dict + timestamp. On `kid` miss, refetch once if cache age > 0.
- `_get_signing_key(kid: str) -> jwt.PyJWK` — lookup in cached JWKS, raise if not found after refetch
- `validate_and_extract(token: str) -> CallerIdentity` — decode header for kid, get signing key, `jwt.decode()` with iss/aud verification, then map claims:
  - principal from `principal_claim` (dot-path traversal)
  - roles: if `role_claim` non-empty, traverse dot-path and extract list; else split `scope_claim` value as roles. Apply `role_prefix`.
  - scopes: split `scope_claim` value
  - actor_type: check `actor_type_claim` first; else `"user"` if `preferred_username` or `nonce` in claims, `"service"` otherwise

- [ ] **Step 6: Run tests — all pass**

Run: `pytest tests/unit/test_oidc.py -v`

- [ ] **Step 7: Commit**

```
feat(auth): add OIDC JWT validator with JWKS caching

Validates signature, exp, iss, aud. Configurable claim paths for
principal, roles, scopes. Scopes-as-roles fallback when role_claim empty.
```

---

### Task 3: Wire OIDC Validator into Dependencies + Auth Config Endpoint

**Files:**
- Modify: `server/auth/dependencies.py`
- Create: `server/api/auth_config.py`
- Modify: `server/main.py`
- Test: `tests/unit/test_auth.py` (extend), `tests/unit/test_oidc.py` (extend)

**Interfaces:**
- Consumes: `OIDCValidator` from Task 2, `_resolve_auth_mode` from Task 1
- Produces: `GET /auth/config` endpoint returning `{auth_mode, issuer, client_id, scopes}`, fully working OIDC auth path in `get_caller()`

- [ ] **Step 1: Write failing test for OIDC mode integration**

Add to `tests/unit/test_oidc.py`:

```python
async def test_get_caller_oidc_mode_valid_token():
    """Full integration: request with Bearer token in OIDC mode → CallerIdentity."""
    ...

async def test_get_caller_oidc_mode_no_token():
    """Request without Authorization header in OIDC mode → 401."""
    ...
```

Add to `tests/unit/test_auth.py`:

```python
async def test_auth_config_endpoint(client):
    resp = await client.get("/auth/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "auth_mode" in data
    assert "client_id" in data
```

- [ ] **Step 2: Run tests — expect failures**

- [ ] **Step 3: Update `get_caller()` OIDC branch in `server/auth/dependencies.py`**

Replace the 501 placeholder: extract `Authorization: Bearer <token>` from request, call `oidc_validator.validate_and_extract(token)`, catch `jwt.ExpiredSignatureError` / `jwt.InvalidTokenError` → 401. Initialize `oidc_validator` as module-level singleton from settings (lazy, on first OIDC-mode request). Add `_extract_bearer(request: Request) -> str | None` helper.

- [ ] **Step 4: Create `server/api/auth_config.py`**

Single route `GET /auth/config` returning:
```python
{"auth_mode": settings.auth_mode, "issuer": settings.oidc_issuer,
 "client_id": settings.oidc_client_id, "scopes": "openid profile"}
```
No authentication required on this endpoint.

- [ ] **Step 5: Register auth_config router in `server/main.py`**

Add `from server.api import auth_config` and `app.include_router(auth_config.router, tags=["auth"])`.

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v --tb=short`

- [ ] **Step 7: Commit**

```
feat(auth): wire OIDC validator into request pipeline

Bearer token extraction and validation in OIDC mode. Auth config
endpoint for UI OIDC discovery. Dev and proxy modes unchanged.
```

---

### Task 4: CSRF Origin Validation Middleware

**Files:**
- Create: `server/middleware/csrf.py`
- Modify: `server/main.py`
- Test: `tests/unit/test_csrf.py`

**Interfaces:**
- Consumes: `settings.cors_allowed_origins`, `settings.auth_mode`
- Produces: FastAPI middleware that rejects state-changing requests with missing/bad Origin in non-dev modes

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_csrf.py`:

```python
async def test_post_without_origin_rejected():
    """POST with no Origin header in oidc mode → 403."""
    ...

async def test_post_with_valid_origin_allowed():
    """POST with Origin in cors_allowed_origins → passes through."""
    ...

async def test_get_without_origin_allowed():
    """GET requests bypass CSRF check."""
    ...

async def test_dev_mode_skips_csrf():
    """Dev mode does not enforce CSRF."""
    ...

async def test_post_with_bad_origin_rejected():
    """POST with Origin not in allowlist → 403."""
    ...
```

- [ ] **Step 2: Run tests — expect ImportError**

- [ ] **Step 3: Implement `CSRFOriginMiddleware` in `server/middleware/csrf.py`**

Starlette `BaseHTTPMiddleware`. For non-safe methods (POST, PUT, DELETE, PATCH): check `Origin` header against `allowed_origins` set. Missing or non-matching → 403 JSON response. Skip entirely when `auth_mode == "dev"`. Safe methods (GET, HEAD, OPTIONS) always pass through.

- [ ] **Step 4: Add middleware to `server/main.py`**

Add after CORS middleware: `app.add_middleware(CSRFOriginMiddleware, allowed_origins=settings.cors_allowed_origins, auth_mode=settings.auth_mode)`.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: all pass (test fixtures use dev mode or set appropriate headers)

- [ ] **Step 6: Commit**

```
feat(security): add CSRF origin validation middleware

Rejects state-changing requests with missing or invalid Origin header.
Skipped in dev mode. Defense-in-depth alongside Bearer token auth.
```

---

### Task 5: Append-Only Audit Log Migration

**Files:**
- Create: `alembic/versions/002_audit_immutable.py`
- Test: `tests/integration/test_audit_immutable.py`

**Interfaces:**
- Consumes: `audit_log` table from migration 001
- Produces: DB triggers preventing UPDATE and DELETE on `audit_log`

- [ ] **Step 1: Write failing integration test**

Create `tests/integration/test_audit_immutable.py`:

```python
async def test_audit_insert_succeeds(db_session):
    """Normal INSERT into audit_log works."""
    ...

async def test_audit_update_blocked(db_session):
    """UPDATE on audit_log raises DB error."""
    ...

async def test_audit_delete_blocked(db_session):
    """DELETE on audit_log raises DB error."""
    ...
```

These tests need a real PostgreSQL instance (CI has one). They execute raw SQL after inserting a row. Note: CI conftest uses `Base.metadata.create_all` which doesn't run alembic migrations, so these tests must apply the trigger via raw SQL in a fixture (or run `alembic upgrade head` before the test).

- [ ] **Step 2: Run tests — expect pass on insert, pass on update/delete (no triggers yet)**

Run: `pytest tests/integration/test_audit_immutable.py -v`

- [ ] **Step 3: Create migration `alembic/versions/002_audit_immutable.py`**

```python
revision = "002"
down_revision = "001"

def upgrade():
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only: % not permitted', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();
    """)
    op.execute("""
        CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();
    """)

def downgrade():
    op.execute("DROP TRIGGER IF EXISTS audit_no_delete ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS audit_no_update ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_mutation()")
```

- [ ] **Step 4: Apply migration in test DB and re-run tests**

Run: `ARBITER_DATABASE_URL=... alembic upgrade head && pytest tests/integration/test_audit_immutable.py -v`
Expected: insert passes, update and delete raise `IntegrityError` / `InternalError`

- [ ] **Step 5: Commit**

```
feat(audit): add DB triggers enforcing append-only audit log

Prevents UPDATE and DELETE on audit_log table via PostgreSQL triggers.
Application code already only INSERTs; this adds DB-level enforcement.
```

---

### Task 6: UI OIDC Login Flow

**Files:**
- Create: `ui/src/auth/OIDCProvider.tsx`
- Create: `ui/src/auth/useAuth.ts`
- Create: `ui/src/auth/ProtectedRoute.tsx`
- Modify: `ui/src/services/api.ts`
- Modify: `ui/src/App.tsx`
- Modify: `ui/src/AppLayout.tsx`
- Modify: `ui/src/main.tsx`
- Modify: `ui/package.json` (add `oidc-client-ts`)

**Interfaces:**
- Consumes: `GET /api/auth/config` from Task 3
- Produces: `useAuth()` hook returning `{ user: string | null, isAuthenticated: boolean, isLoading: boolean, login: () => void, logout: () => void }`, Bearer token injection into all API calls

- [ ] **Step 1: Add `oidc-client-ts` dependency**

Run: `cd ui && npm install oidc-client-ts`

- [ ] **Step 2: Create `ui/src/auth/useAuth.ts`**

Custom hook wrapping `oidc-client-ts` `UserManager`:
- Fetches OIDC config from `/api/auth/config` on mount
- If `auth_mode !== "oidc"`, returns `{ isAuthenticated: true, user: "dev", ... }` (dev/proxy passthrough)
- Creates `UserManager` with authority=issuer, client_id, redirect_uri=`window.location.origin + "/"`, response_type=`"code"`, scope=`"openid profile"`, automaticSilentRenew=true
- Handles callback (checks `code` in URL params → `signinCallback()`)
- Exposes `getAccessToken(): string | null` for API layer
- On `accessTokenExpired` event → `signinSilent()`, on failure → `signinRedirect()`

- [ ] **Step 3: Create `ui/src/auth/OIDCProvider.tsx` and `ui/src/auth/ProtectedRoute.tsx`**

`OIDCProvider`: React context provider wrapping `useAuth`. Renders children only when `!isLoading`. Shows loading spinner during OIDC redirect handling.

`ProtectedRoute`: Wrapper component that checks `isAuthenticated` from auth context. If `auth_mode === "oidc"` and not authenticated, calls `login()` (redirect to IdP). Used to wrap `<Outlet />` in AppLayout so all pages are protected.

- [ ] **Step 4: Modify `ui/src/services/api.ts` — inject Bearer token**

```typescript
import { getStoredToken } from "src/auth/useAuth";

export const api = createApi({
  reducerPath: "arbiterApi",
  baseQuery: fetchBaseQuery({
    baseUrl: "/api",
    prepareHeaders: (headers) => {
      const token = getStoredToken();
      if (token) {
        headers.set("Authorization", `Bearer ${token}`);
      }
      return headers;
    },
  }),
  tagTypes: ["Workload", "Policy", "Backend", "Audit", "KBSSecret"],
  endpoints: () => ({}),
});
```

`getStoredToken()` is a module-level function exported from `useAuth.ts` that reads the in-memory token (not localStorage).

- [ ] **Step 5: Modify `ui/src/main.tsx` — wrap in OIDCProvider**

```tsx
<React.StrictMode>
  <Provider store={store}>
    <OIDCProvider>
      <App />
    </OIDCProvider>
  </Provider>
</React.StrictMode>
```

- [ ] **Step 6: Modify `ui/src/AppLayout.tsx` — add user indicator + logout**

Add to masthead `ToolbarContent`, right-aligned: display `user` from `useAuth()`, and a logout button (PatternFly `Button` variant="plain") that calls `logout()`. Only render when `auth_mode === "oidc"` (fetch from auth context).

- [ ] **Step 7: Verify existing UI tests still pass**

Run: `cd ui && npx vitest run`

- [ ] **Step 8: Commit**

```
feat(ui): add OIDC login with authorization code + PKCE

oidc-client-ts handles redirect flow. Tokens stored in memory only.
Bearer header injected on all API calls. Login/logout in masthead.
Dev/proxy mode passthrough — no login required.
```

---

### Task 7: Integration Verification + CI Update

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: all prior tasks
- Produces: CI passes with new tests, env vars documented

- [ ] **Step 1: Update `tests/conftest.py`**

Ensure `ARBITER_AUTH_MODE` defaults to `"dev"` in test env (already does via settings default, but add explicit env var in conftest if needed for clarity). Add a `monkeypatch` fixture that sets auth mode for OIDC-mode tests.

- [ ] **Step 2: Run full backend test suite**

Run: `pytest tests/ -v --tb=short`
Expected: all tests pass (old + new)

- [ ] **Step 3: Run lint + format**

Run: `ruff check . && ruff format --check .`

- [ ] **Step 4: Run UI tests**

Run: `cd ui && npx vitest run`

- [ ] **Step 5: Update CI workflow if needed**

Ensure `ARBITER_AUTH_MODE: "dev"` is in CI env (may already work via default). Add the new test files to the test matrix if they need PostgreSQL (integration tests already have it).

- [ ] **Step 6: Commit any CI fixes**

```
chore(ci): ensure auth_mode=dev for CI test environment
```

- [ ] **Step 7: Create PR**

Branch `phase25-oidc-auth` → `main`. PR title: "Phase 2.5: OIDC authentication, CSRF protection, append-only audit". Include test count delta in description.
