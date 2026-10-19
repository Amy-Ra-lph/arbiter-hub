# Arbiter Hub — Security & Threat Model Assessment

**Date:** 2026-10-19 (updated from 2026-10-18 initial assessment)
**Assessor:** Automated audit (backend, frontend, deployment) + manual review
**Scope:** Full stack — API, UI, containers, network, deployment
**Status:** PoC deployed on Beaker lab with OIDC auth + Keylime attestation

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Trust Boundary: External              │
│  Browser ──► nginx :8080 ──► Static SPA (React/PF6)     │
│                  │                                       │
│                  ▼ /api/                                 │
│  ┌──────────── Trust Boundary: Internal ───────────────┐ │
│  │  FastAPI :8400 (stateless, N nodes)                 │ │
│  │    ├── Keylime Verifier (mTLS)                      │ │
│  │    ├── Trustee KBS :8085 (internal)                 │ │
│  │    ├── cosign (subprocess)                          │ │
│  │    ├── Rekor (HTTPS)                                │ │
│  │    └── PostgreSQL :5432 (internal)                  │ │
│  └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## STRIDE Threat Analysis

### Spoofing

| Threat | Current State | Severity |
|--------|--------------|----------|
| API caller identity spoofed via X-Caller-* headers | **FIXED** — X-headers only trusted when `AUTH_MODE=dev`; OIDC mode validates JWT | ~~CRITICAL~~ RESOLVED |
| No OIDC/mTLS enforcement on API | **FIXED** — OIDC JWT validation with JWKS caching, PyJWT, configurable claim mapping. Supports IPA (ahdapa) and Keycloak issuers | ~~HIGH~~ RESOLVED |
| No CSRF protection | **FIXED** — CSRFOriginMiddleware validates Origin header on state-changing methods (POST/PUT/DELETE/PATCH). Skipped in dev/proxy modes | ~~LOW~~ RESOLVED |

### Tampering

| Threat | Current State | Severity |
|--------|--------------|----------|
| Audit log records deletable | No DB-level append-only protection | MEDIUM |
| KBS path traversal via `../` in repo/type/tag | Params unsanitized | MEDIUM |
| cosign `artifact_ref` flag injection | `--key=/etc/shadow` possible | CRITICAL |

### Repudiation

| Threat | Current State | Severity |
|--------|--------------|----------|
| Attestation actions not tied to verified identity | **FIXED** — All actions attributed to JWT-verified principal (sub claim). Audit log records actor from validated token | ~~HIGH~~ RESOLVED |
| Audit log tamperable (see Tampering) | **FIXED** — PostgreSQL BEFORE UPDATE/DELETE triggers on audit_log table prevent modification or deletion of records | ~~MEDIUM~~ RESOLVED |

### Information Disclosure

| Threat | Current State | Severity |
|--------|--------------|----------|
| Health endpoint leaks internal hostname | `node_id = socket.gethostname()` | LOW |
| KBS secrets encrypted with fallback all-zeros key | `b"0" * 32` if keyfile missing | HIGH |
| DB credentials in default config | `arbiter:arbiter` hardcoded default | MEDIUM |
| Default Ansible DB password `changeme` | `defaults/main.yml` | HIGH |

### Denial of Service

| Threat | Current State | Severity |
|--------|--------------|----------|
| No rate limiting on any endpoint | **FIXED** — slowapi rate limiting applied globally via `Limiter(key_func=get_remote_address)` | ~~HIGH~~ RESOLVED |
| No input length validation on WorkloadCreate | String fields unbounded at API level | MEDIUM |

### Elevation of Privilege

| Threat | Current State | Severity |
|--------|--------------|----------|
| All callers get admin by default | **FIXED** — OIDC mode: roles derived from JWT scopes or claims (configurable). Dev mode: X-headers gated behind explicit `AUTH_MODE=dev`. No implicit admin | ~~CRITICAL~~ RESOLVED |
| KBS port exposed externally | `PublishPort=8085:8085` | HIGH |
| MCP port exposed externally | `PublishPort=8401:8401` | HIGH |
| Network not internal | `Internal=false` on pod network | HIGH |

---

## Findings by Severity

### CRITICAL (3) — All Resolved

**C1 — Auth bypass via spoofable headers** ✅ FIXED (Phase 2.5)
`server/auth/dependencies.py` — Three auth modes: `dev` (X-headers, gated behind explicit `AUTH_MODE=dev`), `oidc` (JWT Bearer validation with JWKS), `proxy` (reverse proxy trust). OIDC mode validates JWT signature, issuer, audience, and expiry via PyJWT + JWKS caching with asyncio.Lock.

**C2 — Command injection in signing endpoint** ✅ FIXED (Phase 2)
`server/api/signing.py` — `artifact_ref` validated against OCI reference regex. Values starting with `--` rejected. `key_ref` validated against allowed path prefix.

**C3 — KBS encryption key fallback to all-zeros** ✅ FIXED (Phase 2)
`server/api/kbs.py` — Startup error raised if key file missing. No silent fallback to zero key.

### HIGH (6) — 3 Resolved, 3 Remaining

**H1 — No CORS middleware** ✅ FIXED (Phase 2.5)
`server/main.py` — CORSMiddleware configured with explicit `allow_origins`, restricted methods and headers.

**H2 — No rate limiting** ✅ FIXED (Phase 2.5)
`server/main.py` — slowapi `Limiter` with `get_remote_address` key function applied globally.

**H3 — Default DB password "changeme"** ✅ FIXED (Beaker deploy)
Beaker deployment uses randomly generated passwords stored in `/root/.arbiter-db-credentials`.

**H4 — Network not internal** — `deploy/quadlet/arbiter-hub.network` `Internal=false` — OPEN
**H5 — KBS port published externally** — `deploy/quadlet/arbiter-hub-kbs.container:10` — OPEN
**H6 — MCP port published externally** — `deploy/quadlet/arbiter-hub-mcp.container:10` — OPEN

### MEDIUM (4) — 2 Resolved, 2 Remaining

**M1 — Audit log not append-only** ✅ FIXED (Phase 2.5)
`server/models/db.py` — PostgreSQL BEFORE UPDATE and BEFORE DELETE triggers raise exceptions on the `audit_log` table, enforcing append-only at the database level.

**M2 — KBS path params unsanitized** ✅ FIXED (Phase 2)
`server/api/kbs.py` — Path components validated against `[a-zA-Z0-9._-]+` regex. Traversal sequences rejected.

**M3 — No input length validation** — `server/models/schemas.py` — OPEN
**M4 — No TLS between nginx and API** — acceptable for internal network if H4 fixed — OPEN

### LOW / INFO (4)

**L1 — Health endpoint leaks hostname** — `server/api/health.py:6`
**L2 — DB URL default contains credentials** — `server/config.py:5`
**I1 — No TLS termination documented**
**I2 — CSP uses `unsafe-inline` for styles** — required by PatternFly

### CLEAN Areas

- **SQL injection**: All queries via SQLAlchemy ORM, parameterized. No raw SQL.
- **XSS**: No `dangerouslySetInnerHTML` or `innerHTML`. React JSX escaping throughout.
- **CSV injection**: Mitigated with `csvEscape()` in AuditLog and History exports.
- **Client storage**: No localStorage/sessionStorage/cookie usage in frontend.
- **Secrets in frontend**: None. No VITE_ env vars, no hardcoded tokens.
- **Container users**: API runs as UID 1001, UI runs as nginx default non-root.
- **Ansible secrets**: `no_log: true` correctly set on secret creation tasks.
- **Volume mounts**: ReadOnly=true on API and UI containers, `:ro,Z` on cert volumes.

---

## Auth Roadmap (freeipa-webui Pattern)

Target: mirror freeipa-webui's Kerberos+session auth pattern adapted for federation context.

| Phase | Auth Method | Scope | Status |
|-------|-------------|-------|--------|
| **Phase 1-2 (PoC)** | Header-trust (dev mode) | Demo/lab only, gated behind `AUTH_MODE=dev` | ✅ DONE |
| **Phase 2.5** | OIDC via IPA/Keycloak | JWT validation, JWKS caching, CSRF, append-only audit, auth code + PKCE for UI | ✅ DONE — deployed on Beaker J:1200313979 with ahdapa IdP |
| **Phase 2.5** | Keylime backend mTLS | API↔Keylime verifier via mTLS (cv_ca certs) | ✅ DONE — attestation PASS verified |
| **Phase 3** | mTLS for all backends | API↔KBS, API↔Rekor require mutual TLS. Certs issued by IPA CA. | PLANNED |
| **Phase 3** | Kerberos SPNEGO (optional) | For environments with IPA domain — negotiate auth like freeipa-webui. | PLANNED |

---

## Phase 3 — Runtime Monitoring & Automated Remediation

### Falco eBPF Integration

Runtime behavioral monitoring on attested workloads. Falco watches syscalls via eBPF — no kernel module, no agent in workload container.

```
Workload container
    │ (syscalls)
    ▼
eBPF probes (kernel)
    │
    ▼
Falco engine ──► rules evaluation
    │
    ▼ (alert: unexpected behavior)
Arbiter Hub webhook
    │
    ▼
State transition: HEALTHY → FAILED
    │
    ▼
Audit log entry + EDA event
```

**Detection categories:**
- Unexpected process execution (cryptominer, reverse shell)
- File integrity violations (binary replacement, config tampering)
- Network anomalies (connections to undeclared endpoints, DNS exfiltration)
- Privilege escalation attempts (setuid, capability abuse)
- Container escape indicators (mount namespace changes, /proc writes)

**Implementation:**
- Falco deployed as DaemonSet/systemd unit with eBPF driver
- Custom Falco rules per workload_type (different baselines for web vs DB vs ML)
- Webhook receiver endpoint: `POST /api/workloads/{id}/falco-alert`
- Alert → state machine transition with Falco event as evidence in attestation record

### Event-Driven Ansible (EDA) Integration

Attestation state transitions → EDA rulebook → automated remediation playbooks.

```
Arbiter Hub audit log
    │
    ▼
EDA source plugin (webhook or kafka)
    │
    ▼
Rulebook evaluation
    │
    ▼
Ansible playbook execution
```

**Rulebook triggers:**

| Event | Condition | Action |
|-------|-----------|--------|
| `state_transition` | `to_state == FAILED` | Quarantine: isolate network, revoke certs, alert oncall |
| `state_transition` | `to_state == STALE` | Re-attest: trigger `/attest` via API |
| `attestation` | `verdict == FAIL && backend == keylime` | IMA violation: snapshot filesystem, collect evidence |
| `falco_alert` | `priority >= WARNING` | Behavioral: cordon workload, trigger forensic collection |
| `state_transition` | `to_state == REVOKED` | Decommission: drain connections, remove from LB, archive logs |

**Components to build:**
- `eda/plugins/event_source/arbiter_hub.py` — EDA source plugin polling audit API or receiving webhooks
- `eda/rulebooks/attestation_remediation.yml` — rulebook with conditions above
- `eda/playbooks/quarantine.yml` — network isolation + cert revocation
- `eda/playbooks/re_attest.yml` — API call to trigger re-attestation
- `eda/playbooks/forensic_collect.yml` — snapshot + evidence gathering
- `server/api/webhooks.py` — outbound webhook dispatcher on state transitions
- `server/api/falco.py` — inbound Falco alert receiver endpoint

**Architecture decision:** EDA source plugin (pull) vs webhook (push). Recommend webhook push — lower latency for security events, EDA source plugin as fallback for environments where outbound webhooks aren't allowed.

---

## Recommended Fix Priority

### Completed (Phase 2 + 2.5)

| # | Finding | Fix |
|---|---------|-----|
| C1 | Auth bypass via spoofable headers | OIDC JWT validation, dev mode gated |
| C2 | cosign command injection | OCI ref regex validation |
| C3 | KBS zero-key fallback | Startup error on missing key |
| H1 | No CORS middleware | CORSMiddleware with explicit origins |
| H2 | No rate limiting | slowapi global limiter |
| H3 | Default DB password | Random passwords in Beaker deploy |
| M1 | Audit log not append-only | PostgreSQL triggers |
| M2 | KBS path traversal | Regex validation |

### Remaining — Future Builds

**Next (before any shared/production deployment):**
1. H4 — Set network `Internal=true` in quadlet config
2. H5 — Remove KBS `PublishPort` or bind localhost only
3. H6 — Remove MCP `PublishPort` or bind localhost only
4. M3 — Add `max_length` to Pydantic string fields
5. M4 — Enable TLS between nginx and API (internal)
6. Audience validation — use RFC 8707 resource indicators or configure IdP audience claims properly
7. Scope filtering — admin role should bypass scope filtering on workload list/get queries
8. IPA CA trust — container should mount IPA CA cert or use certmonger-managed trust bundle
9. Keylime mTLS hostname — use IPA-issued certs with proper DNS SANs instead of `check_hostname=False`

**Phase 3:**
10. Falco eBPF integration
11. EDA rulebook + remediation playbooks
12. mTLS for all backend-to-backend connections
