# Arbiter Hub Architecture

## Overview

Arbiter Hub is a federation attestation hub that provides a single control plane for managing workload trust across heterogeneous attestation backends. It answers one question: "should this workload be trusted right now?"

## System Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                         External Boundary                        │
│                                                                  │
│  ┌──────────┐     ┌────────────────┐     ┌──────────────────┐   │
│  │ Browser  │────►│ nginx :8080    │────►│ React SPA        │   │
│  │          │     │ (LB + proxy)   │     │ (PatternFly 6)   │   │
│  └──────────┘     └───────┬────────┘     └──────────────────┘   │
│                           │ /api/                                │
│  ┌────────────────────────▼──────────────────────────────────┐  │
│  │                    Internal Network                        │  │
│  │                                                            │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │            FastAPI API Tier (stateless)              │  │  │
│  │  │                                                     │  │  │
│  │  │  ┌──────────┐  ┌──────────┐  ┌──────────┐         │  │  │
│  │  │  │ Node 1   │  │ Node 2   │  │ Node N   │         │  │  │
│  │  │  │ :8400    │  │ :8400    │  │ :8400    │         │  │  │
│  │  │  └────┬─────┘  └────┬─────┘  └────┬─────┘         │  │  │
│  │  └───────┼─────────────┼─────────────┼────────────────┘  │  │
│  │          │             │             │                    │  │
│  │  ┌───────▼─────────────▼─────────────▼────────────────┐  │  │
│  │  │                PostgreSQL :5432                     │  │  │
│  │  │  (workloads, attestations, transitions, audit,     │  │  │
│  │  │   policies, kbs_secrets)                           │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  │                                                            │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │              Attestation Backends                     │ │  │
│  │  │                                                       │ │  │
│  │  │  ┌───────────┐ ┌───────────┐ ┌────────┐ ┌─────────┐│ │  │
│  │  │  │ Keylime   │ │ Trustee   │ │ cosign │ │  Rekor  ││ │  │
│  │  │  │ (TPM/IMA) │ │ (KBS)     │ │        │ │         ││ │  │
│  │  │  │ mTLS      │ │ internal  │ │ binary │ │  HTTPS  ││ │  │
│  │  │  └───────────┘ └───────────┘ └────────┘ └─────────┘│ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Components

### API Tier (FastAPI)

Stateless Python application. All state lives in PostgreSQL, so nodes can be added or removed freely behind the nginx load balancer.

**Modules:**

| Module | Responsibility |
|--------|----------------|
| `server/api/workloads.py` | CRUD + attest/remediate/revoke lifecycle |
| `server/api/attestation.py` | Backend dispatch and result recording |
| `server/api/audit.py` | Immutable event log queries |
| `server/api/kbs.py` | Key Broker: encrypted secret store + state-gated release |
| `server/api/signing.py` | Container image sign/verify via cosign |
| `server/api/health.py` | Node health with cluster awareness |
| `server/auth/` | Identity extraction and RBAC |
| `server/state/machine.py` | Mubeen 7-state machine with transition validation |
| `server/state/scheduler.py` | Background stale-TTL checker |
| `server/backends/` | Pluggable attestation backend adapters |
| `server/policy/` | Rules engine with OPA-compatible interface |
| `server/plugins/` | Entry-point based plugin loader |
| `server/telemetry/` | OpenTelemetry traces, Prometheus metrics, OCSF events |

### UI Tier (React + PatternFly 6)

Single-page application served by nginx. Communicates exclusively through `/api/` proxy — no direct backend access from the browser.

**Pages:**

| Page | Purpose |
|------|---------|
| Dashboard | State summary, backend health, stale alerts, recent events, cluster status |
| Workloads | Searchable/filterable/sortable table with add/delete modals |
| Workload Detail | 4-tab detail (overview + state diagram, attestation history, transitions, vulnerabilities) with attest/remediate/revoke actions |
| Backends | Gallery view with health polling |
| Policies | Table with expandable JSON, add policy modal |
| KBS Secrets | Secret management with state-gated release |
| Audit Log | Expandable event log with CSV export |
| History | Attestation-specific event log with verdict filter |
| Federation | Force-directed topology graph (backends + workloads) |
| Vulnerabilities | Placeholder for CVE integration |

### Data Model

```
Workload (1) ──── (*) AttestationRecord
    │                      │
    │                      └── verdict, backend, detail (JSON)
    │
    ├──── (*) StateTransition
    │              └── from_state, to_state, triggered_by
    │
    └──── (scope) KBSSecret
                     └── encrypted_value, required_state

Policy ──── type, scope, content (JSON), active
AuditLog ──── actor, action, target, detail (JSON)
```

### State Machine

The Mubeen 7-state machine governs workload lifecycle:

| State | Meaning | Allowed Transitions |
|-------|---------|---------------------|
| `REGISTERED` | Enrolled, never attested | → ATTESTING |
| `ATTESTING` | Attestation in progress | → HEALTHY, FAILED |
| `HEALTHY` | Last attestation passed | → ATTESTING, STALE, REVOKED |
| `STALE` | TTL expired without re-attestation | → ATTESTING, FAILED |
| `FAILED` | Attestation failed | → UNDER_REMEDIATION, REVOKED |
| `UNDER_REMEDIATION` | Active remediation | → ATTESTING |
| `REVOKED` | Trust permanently withdrawn | terminal |

### Attestation Backends

Each backend implements a common interface (`BackendBase`):

```python
class BackendBase:
    async def attest(self, workload) -> AttestationResult
    async def health() -> BackendHealth
```

| Backend | Protocol | Trust Signal |
|---------|----------|--------------|
| **Keylime** | mTLS to Verifier API | TPM quotes, IMA log integrity |
| **Trustee** | HTTP to KBS | Confidential computing evidence |
| **cosign** | subprocess | Container image signatures |
| **Rekor** | HTTPS | Transparency log inclusion proofs |

Backends are pluggable via Python entry points (`arbiter_hub.backends`).

### Authentication

| Mode | Mechanism | When |
|------|-----------|------|
| Dev (`ARBITER_DEV_MODE=true`) | X-Caller-* headers | Local development |
| Production | OIDC token validation | Deployment (Phase 2.5) |
| Backend-to-backend | mTLS client certs | Phase 3 |

RBAC roles: `attestation-admin`, `attestation-reader`, `policy-editor`

### KBS Secret Gate

Secret release is gated on workload state. A workload must be in the secret's `required_state` (typically `HEALTHY`) with a recent attestation to receive secrets. The gate uses row-level locking to prevent race conditions during concurrent revocation.

### Networking

- Pod network is `Internal=true` — only nginx and MCP (localhost) are externally accessible
- nginx provides load balancing with passive health checks (`max_fails=3 fail_timeout=10s`)
- `proxy_next_upstream` retries failed requests on healthy nodes
- All inter-container communication is plaintext over the internal bridge (TLS planned for Phase 3)

### Telemetry

- **OpenTelemetry** traces on all API endpoints
- **Prometheus** metrics at `/metrics` (attestation counts, state distribution, backend latency)
- **OCSF** event formatting for security events
- **Webhooks** for external integrations (configurable per event type)

### Deployment

Podman Quadlet units managed by systemd. Ansible role follows ansible-freeipa patterns.

```
systemctl --user start arbiter-hub-db
systemctl --user start arbiter-hub-api    # depends on db
systemctl --user start arbiter-hub-kbs    # depends on db
systemctl --user start arbiter-hub-mcp    # depends on api
systemctl --user start arbiter-hub-ui     # depends on api
```

Container images built from UBI 10 base images. API runs as UID 1001, UI uses nginx default non-root user. All containers mount volumes read-only where possible.

## Phase 3 Planned Components

### Falco eBPF Runtime Monitoring

eBPF-based syscall monitoring on attested workloads. Falco alerts trigger state machine transitions (HEALTHY → FAILED) with behavioral evidence recorded in the attestation log.

### Event-Driven Ansible (EDA) Remediation

Attestation state transitions fire webhooks to EDA, which evaluates rulebooks and runs remediation playbooks (quarantine, re-attest, forensic collection, decommission).
