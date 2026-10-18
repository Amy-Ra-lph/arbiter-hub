# Arbiter Hub — Security & Threat Model Assessment

**Date:** 2026-10-18
**Assessor:** Automated audit (backend, frontend, deployment) + manual review
**Scope:** Full stack — API, UI, containers, network, deployment
**Status:** PoC (pre-production)

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
| API caller identity spoofed via X-Caller-* headers | **VULNERABLE** — headers trusted with admin defaults | CRITICAL |
| No OIDC/mTLS enforcement on API | Config exists, not wired | HIGH |
| No CSRF protection | Moot without auth; required when auth added | LOW (now) |

### Tampering

| Threat | Current State | Severity |
|--------|--------------|----------|
| Audit log records deletable | No DB-level append-only protection | MEDIUM |
| KBS path traversal via `../` in repo/type/tag | Params unsanitized | MEDIUM |
| cosign `artifact_ref` flag injection | `--key=/etc/shadow` possible | CRITICAL |

### Repudiation

| Threat | Current State | Severity |
|--------|--------------|----------|
| Attestation actions not tied to verified identity | All actions attributed to header-supplied actor | HIGH |
| Audit log tamperable (see Tampering) | Same | MEDIUM |

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
| No rate limiting on any endpoint | Attest + sign are expensive | HIGH |
| No input length validation on WorkloadCreate | String fields unbounded at API level | MEDIUM |

### Elevation of Privilege

| Threat | Current State | Severity |
|--------|--------------|----------|
| All callers get admin by default | X-Caller-Roles defaults to `attestation-admin` | CRITICAL |
| KBS port exposed externally | `PublishPort=8085:8085` | HIGH |
| MCP port exposed externally | `PublishPort=8401:8401` | HIGH |
| Network not internal | `Internal=false` on pod network | HIGH |

---

## Findings by Severity

### CRITICAL (3)

**C1 — Auth bypass via spoofable headers**
`server/auth/dependencies.py:7-18`
Identity from client-supplied `X-Caller-*` headers, defaults to admin. Any unauthenticated request gets full privileges.
**Fix:** Implement OIDC token validation or mTLS client cert extraction. Gate header-trust behind `ARBITER_DEV_MODE=true`.

**C2 — Command injection in signing endpoint**
`server/api/signing.py:27-29`
`artifact_ref` passed directly to `cosign` subprocess. Malicious refs like `--key=/etc/shadow` abuse cosign flags.
**Fix:** Validate against OCI reference regex. Reject values starting with `--`. Validate `key_ref` against allowed paths.

**C3 — KBS encryption key fallback to all-zeros**
`server/api/kbs.py:24`
If `/etc/arbiter/kbs.key` missing, falls back to `b"0" * 32`. All stored secrets trivially decryptable.
**Fix:** Raise startup error if key file missing. No silent fallback.

### HIGH (6)

**H1 — No CORS middleware** — `server/main.py`
**H2 — No rate limiting** — all endpoints, especially `/attest`, `/sign`, `/verify`
**H3 — Default DB password "changeme"** — `deploy/ansible/roles/arbiter_hub/defaults/main.yml:6`
**H4 — Network not internal** — `deploy/quadlet/arbiter-hub.network` `Internal=false`
**H5 — KBS port published externally** — `deploy/quadlet/arbiter-hub-kbs.container:10`
**H6 — MCP port published externally** — `deploy/quadlet/arbiter-hub-mcp.container:10`

### MEDIUM (4)

**M1 — Audit log not append-only** — `server/models/db.py:142-159`
**M2 — KBS path params unsanitized** — `server/api/kbs.py:48`
**M3 — No input length validation** — `server/models/schemas.py:27-33`
**M4 — No TLS between nginx and API** — acceptable for internal network if H4 fixed

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

| Phase | Auth Method | Scope |
|-------|-------------|-------|
| **Current (PoC)** | None (header-trust) | Demo/lab only |
| **Phase 2.5** | OIDC via IPA/Keycloak | API endpoints gated by JWT claims. RBAC roles: `attestation-admin`, `attestation-reader`, `policy-editor`. CSRF tokens on state-changing operations. |
| **Phase 3** | mTLS for backend-to-backend | API↔Keylime, API↔KBS, API↔Rekor require mutual TLS. Certs issued by IPA CA. |
| **Phase 3** | Kerberos SPNEGO (optional) | For environments with IPA domain — negotiate auth like freeipa-webui. |

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

**Before any shared deployment (fix now):**
1. C1 — Gate header-trust behind `ARBITER_DEV_MODE`
2. C2 — Validate cosign artifact_ref and key_ref
3. C3 — Fail on missing KBS key, no zeros fallback
4. H4 — Set network `Internal=true`
5. H5 — Remove KBS `PublishPort`
6. H6 — Remove MCP `PublishPort` or bind localhost
7. H3 — Remove default DB password

**Before Beaker/lab deployment:**
8. H1 — Add CORS middleware
9. H2 — Add rate limiting (slowapi)
10. M2 — Validate KBS path params
11. M3 — Add max_length to Pydantic models

**Before production (Phase 2.5+):**
12. OIDC auth integration
13. CSRF tokens
14. M1 — Append-only audit log
15. M4 — Internal TLS

**Phase 3:**
16. Falco eBPF integration
17. EDA rulebook + remediation playbooks
18. mTLS for backend-to-backend
