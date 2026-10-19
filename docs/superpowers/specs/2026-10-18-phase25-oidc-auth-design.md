# Phase 2.5: OIDC Authentication, CSRF Protection, Append-Only Audit

## Intent

Replace the trust-X-headers production auth path with real OIDC JWT validation.
The hub must authenticate both human users (via browser OIDC login) and machine
callers (via `client_credentials` tokens). Test target: ahdapa on IPA (Beaker lab)
and Keycloak as secondary provider.

### Why now

Phase 1+2 shipped with `ARBITER_DEV_MODE` gating auth bypass, but production mode
still trusts reverse-proxy-injected X-headers with no token validation. Before
Beaker E2E deploy or any demo with real IPA, the API needs to verify JWTs directly.

## Goals

1. Validate OIDC JWT Bearer tokens on every API request (except `/health`)
2. Map JWT claims to `CallerIdentity` (principal, roles, scopes) for existing RBAC
3. Support both ahdapa and Keycloak claim shapes via configurable claim paths
4. UI login via authorization code + PKCE flow (redirect to IdP)
5. CSRF protection for browser-origin state-changing requests
6. Append-only guarantee on `audit_log` table (DB-level)
7. Dev mode (`ARBITER_DEV_MODE=true`) unchanged for local development/CI

## Non-Goals

- Session management / server-side sessions (stateless JWT only)
- Token refresh in the API server (UI handles refresh via IdP)
- Multi-tenancy or tenant-scoped OIDC
- User registration or self-service
- Replacing RBAC model (roles/permissions stay as-is)

## Anti-Goals

- Storing tokens in localStorage (XSS vector)
- Accepting tokens from arbitrary issuers without explicit configuration
- Weakening dev-mode behavior (CI tests depend on X-header auth)

## Constraints

- ahdapa token claims differ from Keycloak:
  - **ahdapa**: `sub` = Kerberos principal, scopes in `scope` (space-delimited string),
    no nested role claim — roles derived from IPA groups via HBAC
  - **Keycloak**: `sub` = UUID, `preferred_username` for principal,
    `realm_access.roles` (JSON array), `scope` (space-delimited)
- httpx already in dependencies (for JWKS fetch)
- cryptography already in dependencies (for JWT signature verification)
- UI uses RTK Query with `fetchBaseQuery` — need to inject Bearer header
- nginx reverse proxy fronts both UI and API in production

## Design

### 1. OIDC Token Validation (`server/auth/oidc.py`, new)

```
OIDCValidator
  ├── __init__(issuer, audience, client_id, role_claim, scope_claim)
  ├── _fetch_jwks()          # GET {issuer}/.well-known/openid-configuration → jwks_uri → GET keys
  ├── _get_signing_key(kid)  # Match kid from JWT header, cache with TTL
  ├── validate_token(token)  # Verify sig, exp, iss, aud → decoded claims dict
  └── extract_identity(claims) → CallerIdentity  # Map claims to principal/roles/scopes
```

**JWKS caching**: Fetch on first request, cache for 1 hour. On `kid` miss, refetch
once (key rotation). Use `httpx.AsyncClient` with connection pooling.

**Claim mapping** (configurable via settings):
- `oidc_principal_claim`: default `"sub"` — ahdapa puts Kerberos principal here
- `oidc_role_claim`: default `"realm_access.roles"` — dot-path into claims dict.
  For ahdapa PoC, set to empty string (scopes-as-roles, see below)
- `oidc_scope_claim`: default `"scope"` — space-delimited string, split to list
- `oidc_role_prefix`: default `""` — prepend to each extracted role
  (e.g., `"attestation-"` to map Keycloak role `admin` → `attestation-admin`)

**Role resolution strategy** (phased):

| Phase | Strategy | Config | Notes |
|-------|----------|--------|-------|
| PoC (now) | Scopes-as-roles | `oidc_role_claim=""` | Zero infra. Register ahdapa client with scopes matching role names (`attestation-admin`, etc.). When role_claim is empty, scope values used as roles. |
| Production v1 | IdP groups claim | `oidc_role_claim="groups"` | ahdapa adds IPA group memberships to JWT. Keycloak uses `realm_access.roles`. Config-only change, no code. |
| Production v2 | + LDAP cross-validation | `oidc_ldap_verify=true` | LDAP pool queries IPA to verify claimed roles match current group membership. 60s cache TTL. Catches group removal between token issuance and expiry. |

The scopes-as-roles PoC path is forward-compatible — when ahdapa adds a
groups claim, set `ARBITER_OIDC_ROLE_CLAIM=groups` with no code changes.
Production v2 LDAP verification is the long-term target for high-security
deployments where revocation latency matters.

**actor_type derivation** (builder call): Tokens with `preferred_username`
or `nonce` claim → `"user"`, otherwise → `"service"`. Configurable via
`oidc_actor_type_claim` for deployments that put grant type in a custom claim.

**Auth mode** (`ARBITER_AUTH_MODE` env var):
- `dev` — current X-header behavior (default for CI)
- `oidc` — JWT validation required, X-headers ignored
- `proxy` — trust X-headers from reverse proxy (for deployments behind mod_auth_openidc)

**Backward compat** (builder call): If `ARBITER_DEV_MODE=true` and
`ARBITER_AUTH_MODE` is not set, auth_mode defaults to `"dev"`. Existing CI
and container quadlets that set `DEV_MODE` continue working. `AUTH_MODE`
takes precedence when both are set.

### 2. Updated Dependencies (`server/auth/dependencies.py`)

```python
async def get_caller(request: Request) -> CallerIdentity:
    if _auth_mode == "dev":
        # existing X-header logic, unchanged
        ...
    elif _auth_mode == "proxy":
        # existing production X-header logic (requires X-Caller-Principal)
        ...
    else:  # oidc
        token = _extract_bearer(request)
        if not token:
            raise HTTPException(401, "Bearer token required")
        return await oidc_validator.validate_and_extract(token)
```

The `/health` and `/metrics` endpoints remain unauthenticated.

### 3. Config Additions (`server/config.py`)

```python
auth_mode: str = "dev"  # "dev" | "oidc" | "proxy"
oidc_issuer: str = ""         # existing, now used
oidc_client_id: str = "arbiter-hub"  # existing
oidc_audience: str = "arbiter-hub"   # existing
oidc_principal_claim: str = "sub"
oidc_role_claim: str = "realm_access.roles"
oidc_scope_claim: str = "scope"
oidc_role_prefix: str = ""
oidc_jwks_cache_ttl: int = 3600
```

For ahdapa deployment:
```bash
ARBITER_AUTH_MODE=oidc
ARBITER_OIDC_ISSUER=https://idm.example.com/idp
ARBITER_OIDC_AUDIENCE=arbiter-hub
ARBITER_OIDC_PRINCIPAL_CLAIM=sub
ARBITER_OIDC_ROLE_CLAIM=
ARBITER_OIDC_SCOPE_CLAIM=scope
```

### 4. UI OIDC Login (authorization code + PKCE)

Add `oidc-client-ts` (lightweight, no React wrapper needed — write a thin hook).

**Flow:**
1. App loads → check for existing valid token in memory
2. No token → redirect to `{issuer}/authorize` with PKCE challenge
3. IdP authenticates (SPNEGO for IPA, login form for Keycloak)
4. Redirect back with `code` → exchange for tokens at `{issuer}/token`
5. Store `access_token` and `refresh_token` in memory (not localStorage)
6. RTK Query `fetchBaseQuery` gets `prepareHeaders` that injects `Authorization: Bearer`
7. On 401 → attempt silent refresh → if fail, redirect to login
8. Logout → redirect to `{issuer}/end_session`

**New files:**
- `ui/src/auth/OIDCProvider.tsx` — context provider, wraps `<App />`
- `ui/src/auth/useAuth.ts` — hook: `{ user, token, login, logout, isAuthenticated }`
- `ui/src/auth/ProtectedRoute.tsx` — redirect to login if not authenticated

**Modified files:**
- `ui/src/services/api.ts` — `prepareHeaders` to inject Bearer token
- `ui/src/App.tsx` — wrap in `<OIDCProvider>`
- `ui/src/AppLayout.tsx` — add user indicator + logout button in masthead

**Config:** UI reads OIDC settings from `/api/auth/config` endpoint (new):
```json
{
  "auth_mode": "oidc",
  "issuer": "https://...",
  "client_id": "arbiter-hub",
  "scopes": "openid profile"
}
```

This avoids hardcoding IdP URL in the frontend build.

### 5. CSRF Protection

For `auth_mode=oidc` with browser clients:

**Approach:** Origin/Referer validation middleware on state-changing methods
(POST, PUT, DELETE, PATCH). This is sufficient because:
- API uses Bearer tokens (not cookies) — CSRF via cookie-riding doesn't apply
- The middleware catches any cross-origin form submission attempts
- SameSite cookie policy isn't relevant (no auth cookies)

Implementation: FastAPI middleware that checks `Origin` header against
`cors_allowed_origins` for non-GET/HEAD/OPTIONS requests. Reject with 403
if Origin is missing or not in allowlist. Skip in dev mode.

**Why not double-submit cookie:** Bearer token auth already prevents
cookie-based CSRF. The Origin check is defense-in-depth for any future
session mechanism.

### 6. Append-Only Audit Log

Alembic migration `002_audit_immutable.py`:

```sql
CREATE OR REPLACE FUNCTION prevent_audit_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_no_update
    BEFORE UPDATE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();

CREATE TRIGGER audit_no_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation();
```

Application code already only INSERTs. This adds DB-level enforcement.

### 7. Auth Config Endpoint

New route in `server/api/health.py` (or new `server/api/auth_config.py`):

```
GET /api/auth/config  (unauthenticated)
→ { auth_mode, issuer, client_id, scopes: "openid profile" }
```

Only exposes public OIDC discovery info the UI needs. No secrets.

## File Summary

| File | Action | Lines |
|------|--------|-------|
| `server/auth/oidc.py` | new | ~120 |
| `server/auth/dependencies.py` | modify | ~30 |
| `server/config.py` | modify | ~15 |
| `server/api/auth_config.py` | new | ~25 |
| `server/main.py` | modify | ~10 |
| `alembic/versions/002_audit_immutable.py` | new | ~40 |
| `ui/src/auth/OIDCProvider.tsx` | new | ~80 |
| `ui/src/auth/useAuth.ts` | new | ~40 |
| `ui/src/auth/ProtectedRoute.tsx` | new | ~15 |
| `ui/src/services/api.ts` | modify | ~10 |
| `ui/src/App.tsx` | modify | ~10 |
| `ui/src/AppLayout.tsx` | modify | ~20 |
| `ui/package.json` | modify | ~1 |
| `pyproject.toml` | modify | ~1 |
| `tests/unit/test_oidc.py` | new | ~180 |
| `tests/unit/test_auth.py` | modify | ~30 |
| **Total** | | ~630 |

## Testing Strategy

**Unit tests (`tests/unit/test_oidc.py`):**
- Valid JWT with correct sig/iss/aud → CallerIdentity extracted
- Expired JWT → 401
- Bad signature → 401
- Wrong audience → 401
- Unknown kid → JWKS refetch → retry
- Ahdapa claim shape (sub=principal, scope=space-delimited) → correct mapping
- Keycloak claim shape (realm_access.roles array) → correct mapping
- Missing principal claim → 401
- Auth mode switching (dev/oidc/proxy)

**Integration tests:**
- Full request with valid mock JWT → 200
- Request without token in OIDC mode → 401
- Request with expired token → 401
- CSRF origin check on POST → 403 for bad origin

**E2E on Beaker lab:**
- Register arbiter-hub as ahdapa client via RFC 7591 `/register`
- `client_credentials` grant → JWT → API call with Bearer → success
- UI login via browser → ahdapa SPNEGO → redirect back → authenticated session
- Audit log mutation attempt → DB trigger rejects

## Deployment Notes (Beaker)

1. Register `arbiter-hub` client in ahdapa:
   ```bash
   curl -X POST https://<server>/register \
     -H 'Authorization: Bearer <reg_token>' \
     -H 'Content-Type: application/json' \
     -d '{"client_name":"arbiter-hub","redirect_uris":["https://<client>:8080/"],...}'
   ```
2. Set env vars in container quadlet
3. Run `alembic upgrade head` for audit trigger migration
4. Nginx config: proxy `/api/auth/config` without auth (already unauthenticated)
