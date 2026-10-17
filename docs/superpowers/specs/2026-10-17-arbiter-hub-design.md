# Arbiter Hub — Design Specification

**Date:** 2026-10-17
**Status:** Draft
**Author:** Amy Ralph + Claude

## 1. Purpose

Arbiter Hub is a federation hub for workload attestation. It arbitrates trust
decisions across multiple attestation backends (Keylime TPM/IMA, Trustee TEE,
cosign/Sigstore, Rekor transparency log). It manages workload lifecycle via a
7-state machine, releases secrets through an integrated Key Broker Service (KBS)
only after attestation passes, and exposes both a REST API and read-only MCP
tools for agentic workflows.

### Success Criteria

- Single API surface federates Keylime, Trustee, cosign, and Rekor backends
- Workloads tracked through 7-state lifecycle with immutable audit trail
- KBS releases secrets only to workloads in attested state
- MCP tools enable read-only agent queries (status, compliance, gates, audit)
- Deployable as Podman containers orchestrated by Quadlet on RHEL
- Container images signed with cosign, chained to ipacta/Dogtag root CA via Fulcio
- Host-level attestation (TPM + Keylime IMA) covers arbiter-hub's own binaries

### Design Principles

- **Standards-first API:** OpenAPI 3.1 spec published. Attestation evidence
  uses IETF EAT (Entity Attestation Token, RFC 9711) and RATS formats.
  Any tool that speaks REST + OpenAPI can integrate without custom SDK.
- **Standards-based telemetry:** OpenTelemetry for traces/metrics/logs.
  Security events emitted in OCSF (Open Cybersecurity Schema Framework)
  for SIEM consumption. Prometheus metrics endpoint for dashboards.
- **Plugin extensibility:** Backend adapters, policy engines, and event
  handlers are pluggable. Third-party tools attach via webhooks, event
  streams, or custom adapter plugins without forking the core.

### Non-Goals (Phase 1)

- Web UI (Phase 2 — API-first, UI builds against stable contract)
- OPA/Cedar policy engine (Phase 1 uses simple rules engine with OPA-compatible interface)
- Multi-node / HA deployment
- CAEP revocation feedback (WIMSE alignment — future)
- Grafana dashboards

## 2. Architecture

### 2.1 Federation Hub Model

Arbiter Hub sits above individual attestation engines. It does not reimplement
verification — it federates results from specialized backends through a common
adapter interface, applies policy, manages workload state, and provides a
unified API.

```
                    ┌─────────────────────┐
                    │   Arbiter Hub API    │
                    │      (:8400)         │
                    └─────────┬───────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
     ┌────────┴──┐   ┌───────┴───┐   ┌───────┴───┐
     │  Keylime  │   │  Trustee  │   │   Cosign   │
     │  Adapter  │   │  Adapter  │   │  Adapter   │
     └────────┬──┘   └───────┬───┘   └───────┬───┘
              │               │               │
     Keylime Verifier   Trustee KBS    Fulcio/Rekor
     (TPM/IMA)          (TEE/CVM)      (Sigstore)
```

### 2.2 RATS RFC 9334 Mapping

| RATS Role        | Arbiter Hub Component            |
|------------------|----------------------------------|
| Attester         | Workload (Keylime agent, TEE)    |
| Verifier         | Backend adapters (Keylime, Trustee) |
| Relying Party    | KBS, OBO daemon, pipelines       |
| Endorser         | CA chain (ipacta/Dogtag → Fulcio) |
| Verifier Owner   | Arbiter Hub API (policy, state)  |

### 2.3 Container Architecture

All containers run in a single Podman pod, orchestrated by Quadlet.

| Container           | Base Image          | Role                          | Port |
|---------------------|---------------------|-------------------------------|------|
| `arbiter-hub-api`   | UBI10-minimal       | FastAPI REST API, orchestration | 8400 |
| `arbiter-hub-kbs`   | UBI10-minimal       | KBS v0 API, secret release    | 8085 |
| `arbiter-hub-db`    | UBI10 PostgreSQL 16 | State, audit, policy store    | 5432 |
| `arbiter-hub-mcp`   | UBI10-minimal       | FastMCP read-only tools       | 8401 |
| `arbiter-hub-otel`  | OTel Collector      | Telemetry pipeline (optional) | 4317/4318 |

Networking: `arbiter-hub.network` Quadlet. API and MCP containers are
frontend-facing. DB is backend-only (no external port exposure). KBS is
frontend-facing but RBAC-gated.

### 2.4 Container Hardening

- `SecurityLabelType` per container (custom SELinux types, not generic `container_t`)
- Read-only rootfs (`ReadOnly=true` in Quadlet)
- No capabilities beyond minimum (`CapDrop=ALL`, explicit `CapAdd` only as needed)
- Secrets via `podman secret`, never environment variables
- `containers-policy.json` on host verifies cosign signatures on pull
- No `Privileged=true` — ever

### 2.5 Four-Layer Bootstrap (Who Attests the Attestor?)

```
Layer 0: Hardware TPM (PCRs, measured boot)
         Root of trust. No software dependency.

Layer 1: Host OS + Keylime agent
         Attested by TPM. IMA policy covers host binaries.
         Reports to Layer 1 verifier (standalone, not arbiter-hub).

Layer 2: Podman + signed containers
         containers-policy.json verifies cosign signatures on pull.
         IMA covers container binary execution (Layer 1).
         Arbiter-hub containers live here.

Layer 3: Arbiter Hub (this project)
         Running, verified, attested by layers below.
         Becomes the verifier for all other workloads.

Layer 4: Workloads (agentic agents, CVMs, services)
         Attested by Layer 3. Secrets released by Layer 3 KBS.
```

Arbiter Hub never attests itself. The host (TPM + IMA + Keylime Layer 1
verifier) attests arbiter-hub. Different trust domains.

Arbiter Hub containers are signed and IMA-verified but NOT encrypted. Host
protects them via full-disk LUKS (TPM-sealed, unlocked at measured boot).
Image encryption is for workload containers that arbiter-hub manages.

## 3. CA Chain and Signing

### 3.1 Certificate Hierarchy

```
ipacta Root CA (long-term) / Dogtag Root CA (current)
  └── Fulcio Intermediate CA
        └── Short-lived signing certificates (OIDC-issued)
              └── Container image signatures
              └── Artifact attestations
              └── SARIF seals
              └── State transition receipts
```

Signing uses Fulcio keyless mode: build pipeline authenticates via OIDC
(ahdapa or Keycloak), receives short-lived certificate from Fulcio, signs
artifact, certificate chains to root CA. No long-lived signing keys on disk.

### 3.2 CA Backend Transition

Current: Fulcio → Dogtag intermediate → Dogtag root CA.
Future: Fulcio → ipacta intermediate → ipacta root CA.
Transition is transparent — Fulcio interface unchanged, only backend swap.

## 4. Workload State Machine

Based on Mubeen's 7-state model. Applies uniformly to CVM workloads, agentic
agents, and attested services.

```
                    ┌──────────┐
         enroll     │Registered│
        ────────────►          │
                    └────┬─────┘
                         │ begin attestation
                    ┌────▼─────┐
            ┌───────│Attesting │◄──────────────────┐
            │       └────┬─────┘                    │
            │            │ pass                     │ re-attest
            │       ┌────▼─────┐              ┌────┴─────┐
            │       │ Healthy  ├──────────────► Stale    │
            │       └────┬─────┘  TTL expires  └──────────┘
            │            │ fail
            │       ┌────▼─────┐
            │       │ Failed   ├──────────────────┐
            │       └────┬─────┘                   │
            │            │ remediate          revoke│
            │       ┌────▼──────────┐        ┌────▼─────┐
            │       │Under          │        │ Revoked  │
            │       │Remediation    │        │(terminal)│
            │       └────┬──────────┘        └──────────┘
            │            │ retry
            │            │ (→ Attesting)
            └────────────┘
```

### 4.1 Transition Rules

| Transition                      | Trigger                          | Required Privilege |
|---------------------------------|----------------------------------|--------------------|
| → Registered                    | Enrollment (admin or pipeline)   | admin              |
| Registered → Attesting          | Attestation request              | pipeline, admin    |
| Attesting → Healthy             | All backends pass                | system (automatic) |
| Attesting → Failed              | Any backend fails                | system (automatic) |
| Healthy → Stale                 | TTL expires without re-attestation | system (automatic) |
| Stale → Attesting               | Re-attestation triggered         | pipeline, admin, agent (request) |
| Failed → Under Remediation      | Remediation initiated            | admin              |
| Under Remediation → Attesting   | Remediation complete, retry      | admin              |
| Failed → Revoked                | Revocation decision              | admin              |
| Healthy → Revoked               | Emergency revocation             | admin              |

### 4.2 Backward Transition Constraints

- Failed → Healthy: PROHIBITED. Must go through Under Remediation → Attesting → Healthy.
- Revoked → any state: PROHIBITED. Requires new enrollment (new workload identity).
- All backward transitions require elevated privilege + written justification.
- All transitions logged to Rekor transparency log (immutable external audit).

## 5. Backend Adapter Interface

```python
from typing import Protocol
from dataclasses import dataclass
from enum import Enum

class AttestationVerdict(Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    UNAVAILABLE = "unavailable"

@dataclass
class AttestationResult:
    verdict: AttestationVerdict
    backend: str
    evidence_hash: str
    detail: dict
    timestamp: datetime

@dataclass
class BackendHealth:
    healthy: bool
    backend: str
    last_check: datetime
    detail: str

class AttestationBackend(Protocol):
    """Common interface for all attestation backends."""

    async def verify(self, workload: Workload) -> AttestationResult:
        """Run attestation verification for a workload."""
        ...

    async def enroll(self, workload: Workload, policy: Policy) -> EnrollResult:
        """Enroll a workload with this backend."""
        ...

    async def revoke(self, workload: Workload) -> RevokeResult:
        """Revoke a workload from this backend."""
        ...

    async def health(self) -> BackendHealth:
        """Check backend availability and health."""
        ...
```

### 5.1 Backend Implementations

**KeylimeBackend:**
- Communicates with Keylime verifier REST API over mTLS
- Enrollment: `keylime_tenant` CLI or REST API
- Verification: polls verifier for agent operational state
- Evidence: IMA log hash, TPM quote
- Ported from existing `keylime_tools.py` (remove hardcoded IPs, add config)

**TrusteeBackend:**
- Communicates with Trustee KBS for TEE attestation
- Enrollment: registers expected TEE measurements
- Verification: validates TEE evidence (SEV-SNP, TDX, TPM-based)
- Evidence: TEE attestation report, firmware measurements
- Currently "sample" attestation driver — real TEE hardware when available

**CosignBackend:**
- Wraps cosign CLI for artifact signing and verification
- Verification: checks cosign signature against CA chain (Fulcio → ipacta/Dogtag)
- Signing: pipeline-only (not agent-callable), short-lived Fulcio certs
- Ported from existing `cosign.py` (fix deprecated COSIGN_EXPERIMENTAL)

**RekorBackend:**
- Writes to Rekor transparency log for immutable audit
- Verification: confirms entries exist and are consistent
- Not a standalone attestation backend — used by other backends for audit

## 6. Two-Interface Security Model

### 6.1 Principle

MCP tools are thin clients to the API server. All logic, state, and policy
evaluation lives in the API server. MCP never implements business logic directly.

```
Agent ──→ MCP tool ──→ API server ──→ policy engine ──→ backend
Pipeline ──→ REST client ──→ API server ──→ policy engine ──→ backend
Admin ──→ REST client ──→ API server ──→ policy engine ──→ backend
Future UI ──→ browser ──→ API server ──→ policy engine ──→ backend
```

### 6.2 MCP Tools (Read-Only, Agent-Callable)

| Tool                     | API Mapping                    | Purpose                    |
|--------------------------|--------------------------------|----------------------------|
| `check_workload_status`  | GET `/workloads/{id}`          | Workload detail + state    |
| `list_workloads_by_state`| GET `/workloads?state=X`       | Filter workloads by state  |
| `check_compliance`       | GET `/workloads/{id}/compliance`| Policy compliance check   |
| `verify_artifact`        | POST `/verify`                 | Verify cosign signature    |
| `gate_check`             | Composite                      | Full gate evaluation       |
| `query_audit_log`        | GET `/audit`                   | Audit trail query          |
| `backend_health`         | GET `/backends`                | Backend status             |

MCP tools authenticate via workload certificate. Each agent can only query
workloads within its scope (determined by IPA identity and RBAC rules).

### 6.3 REST API (Authenticated, RBAC-Enforced)

**Read endpoints (admin, pipeline, scoped agent):**

| Method | Endpoint                       | Purpose                         |
|--------|--------------------------------|---------------------------------|
| GET    | `/workloads`                   | List workloads, filter by state |
| GET    | `/workloads/{id}`              | Workload detail + history       |
| GET    | `/workloads/{id}/compliance`   | Policy compliance check         |
| GET    | `/workloads/{id}/attestations` | Attestation record history      |
| GET    | `/audit`                       | Audit log query                 |
| GET    | `/backends`                    | Backend health status           |
| GET    | `/policies`                    | List active policies            |
| GET    | `/health`                      | Service health                  |

**Write endpoints (admin, pipeline — never agent-callable):**

| Method | Endpoint                       | Purpose                         |
|--------|--------------------------------|---------------------------------|
| POST   | `/workloads`                   | Register new workload           |
| POST   | `/workloads/{id}/attest`       | Trigger attestation             |
| POST   | `/workloads/{id}/revoke`       | Revoke workload                 |
| POST   | `/workloads/{id}/remediate`    | Move to Under Remediation       |
| POST   | `/sign`                        | Sign artifact (pipeline-only)   |
| POST   | `/verify`                      | Verify artifact signature       |
| POST   | `/policies`                    | Create policy                   |
| PUT    | `/policies/{id}`               | Update policy                   |
| POST   | `/kbs/v0/resource/{repo}/{type}/{tag}` | KBS secret operations  |

### 6.4 Operations That Need Both Interfaces

Some operations are legitimately triggered by both agents and pipelines, via
different paths to the same server endpoint:

| Operation        | Agent Path (MCP)                    | Service Path (REST)              |
|------------------|-------------------------------------|----------------------------------|
| Re-attest        | Agent detects drift, requests       | Pipeline triggers on schedule    |
| Quarantine       | Agent sees failed check, requests   | Keylime revocation callback      |
| Promote tier     | Agent completes gate, requests      | CI/CD pipeline promotes on green |
| Fetch evidence   | Agent needs for decision            | RP needs for token issuance      |

For these, the MCP tool submits a **request** to the API. The API evaluates
policy (is this agent authorized to request re-attestation of this workload?)
and either executes or rejects. The MCP tool is a request interface, not a
direct execution interface.

### 6.5 What Must NEVER Be Agent-Callable

| Operation            | Why                                                |
|----------------------|----------------------------------------------------|
| Sign artifact        | Signing = trust assertion. Pipeline/admin only     |
| Generate keypair     | Key lifecycle is infrastructure                    |
| KBS store/release    | Service-to-service. Agent knowing secrets = breach |
| Enroll workload      | Enrollment = granting trust. Admin only            |
| Update IMA policy    | Policy mutation. Admin only                        |
| Revoke (direct)      | Agent can request; server decides                  |

## 7. Authentication and Authorization

### 7.1 Identity Types

| Caller Type      | Auth Method                     | Identity Source    |
|------------------|---------------------------------|--------------------|
| Admin            | OIDC (ahdapa)                   | IPA user principal |
| Pipeline         | Service account certificate     | IPA service principal |
| Agent (MCP)      | Workload certificate            | IPA workload identity (`oauth2WorkloadClient`) |
| Future UI        | OIDC (ahdapa) + session         | IPA user principal |

### 7.2 RBAC Model

Roles map to IPA groups (reuse existing `setup-attestation-roles.sh` pattern):

| Role               | Permissions                                          |
|--------------------|------------------------------------------------------|
| `attestation-admin`| All operations                                       |
| `attestation-operator` | Enroll, attest, remediate. No revoke, no policy edit |
| `attestation-pipeline` | Attest, sign, verify. No enroll, no revoke       |
| `attestation-viewer`| Read-only: status, compliance, audit                |
| `attestation-agent` | Read-only + request re-attestation (scoped)         |

### 7.3 Scope Restriction

Agents see only workloads they are authorized for, based on IPA identity.
An agent with principal `agent-foo@REALM` can query workloads tagged with
scope `agent-foo` but not `agent-bar`. Scope enforcement happens in the API
server, not in MCP tools.

## 8. Policy Engine

### 8.1 Phase 1: Simple Rules Engine

JSON/YAML policy files evaluated by a Python rules engine. Interface contract
designed for OPA compatibility so the engine is swappable.

```python
class PolicyEngine(Protocol):
    async def evaluate(
        self,
        subject: str,        # who is asking
        action: str,         # what they want to do
        resource: str,       # which workload/artifact
        context: dict        # attestation state, backend results, etc.
    ) -> PolicyDecision:
        ...

@dataclass
class PolicyDecision:
    allowed: bool
    obligations: list[str]   # actions required (e.g., "log to rekor")
    reason: str
```

### 8.2 Phase 2: OPA Integration

Same interface, OPA Rego backend. Policy bundles stored in PostgreSQL, loaded
by OPA sidecar container. Cedar is an alternative if AuthZEN alignment with
WIMSE is prioritized.

### 8.3 Example Policy (Phase 1 YAML)

```yaml
policies:
  - name: kbs-secret-release
    description: "KBS releases secrets only to Healthy workloads"
    rules:
      - action: kbs_release
        require:
          workload_state: Healthy
          attestation_age_max: 3600  # seconds
          backend_results:
            - backend: keylime
              verdict: pass
    obligations:
      - log_to_rekor

  - name: agent-reattestion-request
    description: "Agents can request re-attestation of their own workloads"
    rules:
      - action: request_reattest
        require:
          caller_role: attestation-agent
          caller_scope_includes_target: true
          target_state:
            - Stale
            - Failed
```

## 9. Key Broker Service (KBS)

### 9.1 KBS v0 API

Maintains compatibility with existing KBS v0 interface (from `kbs-simple.py`).

```
GET  /kbs/v0/resource/{repo}/{type}/{tag}   — retrieve secret (attestation-gated)
POST /kbs/v0/resource/{repo}/{type}/{tag}   — store secret (admin-only)
GET  /kbs/v0/health                         — health check
```

### 9.2 Attestation Gate

Secret release requires:
1. Caller presents workload certificate
2. Arbiter Hub checks workload state machine: must be `Healthy`
3. Arbiter Hub checks attestation recency: must be within TTL
4. Policy engine evaluates `kbs_release` policy
5. If all pass: decrypt and release secret
6. Log release event to audit log + Rekor

### 9.3 Secret Lifecycle

- Secrets encrypted at rest in PostgreSQL (workload-scoped encryption keys)
- Never bulk-exportable — one secret per authenticated request
- Short-lived where possible (OAuth2 token model via OBO)
- Revocation triggers active invalidation: revoked workload's cached secrets
  become useless because downstream relying parties also check attestation state
- Secret rotation: new version stored, workload fetches on next attestation cycle

### 9.4 CVM vs Agentic KBS Use Cases

| Use Case | Secret Type             | Attestation Backend | Release Trigger        |
|----------|------------------------|--------------------|-----------------------|
| CVM      | LUKS decryption key    | Trustee (TEE)      | TEE attestation pass  |
| Agentic  | OAuth2/LDAP credentials| Keylime (TPM/IMA)  | IMA attestation pass  |
| Agentic  | Signing keys           | Keylime + cosign   | Attestation + policy  |
| Both     | Policy bundles         | Any                | Attestation pass      |

## 10. Data Model

### 10.1 PostgreSQL Schema

```sql
CREATE TYPE workload_type AS ENUM ('agentic', 'cvm', 'service');
CREATE TYPE workload_state AS ENUM (
    'registered', 'attesting', 'healthy', 'stale',
    'failed', 'under_remediation', 'revoked'
);
CREATE TYPE attestation_verdict AS ENUM ('pass', 'fail', 'error', 'unavailable');
CREATE TYPE backend_type AS ENUM ('keylime', 'trustee', 'cosign', 'rekor');

CREATE TABLE workloads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ipa_principal VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    workload_type workload_type NOT NULL,
    current_state workload_state NOT NULL DEFAULT 'registered',
    backend_type backend_type NOT NULL,
    stale_ttl_seconds INTEGER NOT NULL DEFAULT 3600,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_attested_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}'
);

CREATE TABLE attestation_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workload_id UUID NOT NULL REFERENCES workloads(id),
    backend backend_type NOT NULL,
    verdict attestation_verdict NOT NULL,
    evidence_hash VARCHAR(128),
    policy_hash VARCHAR(128),
    detail JSONB DEFAULT '{}',
    rekor_entry_uuid VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_attest_workload ON attestation_records(workload_id, created_at DESC);

CREATE TABLE state_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workload_id UUID NOT NULL REFERENCES workloads(id),
    from_state workload_state NOT NULL,
    to_state workload_state NOT NULL,
    triggered_by VARCHAR(255) NOT NULL,
    justification TEXT,
    rekor_entry_uuid VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_transitions_workload ON state_transitions(workload_id, created_at DESC);

CREATE TABLE policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    policy_type VARCHAR(50) NOT NULL DEFAULT 'simple',
    policy_content JSONB NOT NULL,
    scope VARCHAR(255),
    active BOOLEAN NOT NULL DEFAULT true,
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor VARCHAR(255) NOT NULL,
    actor_type VARCHAR(50) NOT NULL,
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(50),
    target_id UUID,
    detail JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_created ON audit_log(created_at DESC);
CREATE INDEX idx_audit_actor ON audit_log(actor);

CREATE TABLE kbs_secrets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo VARCHAR(255) NOT NULL,
    secret_type VARCHAR(255) NOT NULL,
    tag VARCHAR(255) NOT NULL,
    encrypted_value BYTEA NOT NULL,
    required_state workload_state NOT NULL DEFAULT 'healthy',
    workload_scope VARCHAR(255),
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    rotated_at TIMESTAMPTZ,
    UNIQUE(repo, secret_type, tag)
);
```

## 11. Deployment

### 11.1 Quadlet Files

**arbiter-hub.network:**
```ini
[Network]
Driver=bridge
Internal=false
```

**arbiter-hub-db.container:**
```ini
[Unit]
Description=Arbiter Hub PostgreSQL
After=arbiter-hub.network

[Container]
Image=registry.redhat.io/rhel10/postgresql-16
ContainerName=arbiter-hub-db
Network=arbiter-hub.network
Volume=arbiter-hub-db.volume:/var/lib/pgsql/data:Z
Environment=POSTGRESQL_DATABASE=arbiter
Secret=arbiter-hub-db-password,type=env,target=POSTGRESQL_PASSWORD
Secret=arbiter-hub-db-user,type=env,target=POSTGRESQL_USER
SecurityLabelType=arbiter_db_t
ReadOnly=false

[Service]
Restart=always

[Install]
WantedBy=multi-user.target default.target
```

**arbiter-hub-api.container:**
```ini
[Unit]
Description=Arbiter Hub API Server
After=arbiter-hub-db.container
Requires=arbiter-hub-db.container

[Container]
Image=quay.io/afarley/arbiter-hub-api:latest
ContainerName=arbiter-hub-api
Network=arbiter-hub.network
PublishPort=8400:8400
Volume=arbiter-hub-certs.volume:/etc/arbiter/certs:ro,Z
Secret=arbiter-hub-db-password,type=env,target=DATABASE_PASSWORD
Environment=DATABASE_HOST=arbiter-hub-db
Environment=DATABASE_NAME=arbiter
Environment=KBS_URL=http://arbiter-hub-kbs:8085
SecurityLabelType=arbiter_api_t
ReadOnly=true

[Service]
Restart=always

[Install]
WantedBy=multi-user.target default.target
```

**arbiter-hub-kbs.container:**
```ini
[Unit]
Description=Arbiter Hub Key Broker Service
After=arbiter-hub-db.container
Requires=arbiter-hub-db.container

[Container]
Image=quay.io/afarley/arbiter-hub-kbs:latest
ContainerName=arbiter-hub-kbs
Network=arbiter-hub.network
PublishPort=8085:8085
Volume=arbiter-hub-kbs-data.volume:/var/lib/kbs:Z
Volume=arbiter-hub-certs.volume:/etc/arbiter/certs:ro,Z
SecurityLabelType=arbiter_kbs_t
ReadOnly=true

[Service]
Restart=always

[Install]
WantedBy=multi-user.target default.target
```

**arbiter-hub-mcp.container:**
```ini
[Unit]
Description=Arbiter Hub MCP Tools (read-only)
After=arbiter-hub-api.container
Requires=arbiter-hub-api.container

[Container]
Image=quay.io/afarley/arbiter-hub-mcp:latest
ContainerName=arbiter-hub-mcp
Network=arbiter-hub.network
PublishPort=8401:8401
Environment=API_URL=http://arbiter-hub-api:8400
SecurityLabelType=arbiter_mcp_t
ReadOnly=true

[Service]
Restart=always

[Install]
WantedBy=multi-user.target default.target
```

### 11.2 Multi-Stage Containerfiles

Each container uses a multi-stage build: full UBI10 toolchain for build,
RHHI (Red Hat Hardened Images) for runtime. RHHI provides near-zero CVE
base images with minimal attack surface — the attestation server eats its
own dogfood by running on hardened images.

Fallback: if RHHI Python micro variant is not yet available, use
UBI10-minimal as runtime base until RHHI GA (May 2026).

```dockerfile
# Build stage (full toolchain)
FROM registry.redhat.io/ubi10/python-312 AS builder
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Runtime stage (hardened — near-zero CVE)
# Primary: RHHI micro (when available)
# Fallback: registry.redhat.io/ubi10/ubi-minimal
FROM registry.redhat.io/rhhi/python-312-micro
COPY --from=builder /opt/app-root /opt/app-root
USER 1001
EXPOSE 8400
CMD ["python", "-m", "arbiter_hub.api"]
```

### 11.3 Ansible Deployment

Ansible role for full deployment:
1. Install Quadlet files to `/etc/containers/systemd/`
2. Create podman secrets (DB password, certs)
3. Create volumes
4. Configure `containers-policy.json` for cosign verification
5. Set up IPA roles and HBAC rules (port existing `setup-attestation-roles.sh`)
6. Start services via `systemctl --user daemon-reload && systemctl --user start arbiter-hub-api`

## 12. Clevis, Tang, and Network-Bound Disk Encryption

### 12.1 Role of Clevis+Tang

Tang and KBS solve the same problem — conditional release of cryptographic
material. Tang's condition is network presence; KBS's condition is attestation.
Combined via Clevis SSS (Shamir Secret Sharing), they provide defense in depth:
right hardware AND right network AND attested.

### 12.2 Host Bootstrap (Layer 0.5)

Arbiter-hub host LUKS uses Clevis SSS:

```
Clevis SSS (threshold: 2 of 2)
  ├── TPM2 pin    → bound to host hardware
  └── Tang pin    → bound to management network
```

Host only decrypts when both conditions are met. A stolen disk is useless
off-network.

### 12.3 Clevis Pin for Arbiter Hub

A custom `clevis pin arbiter` integrates arbiter-hub into the RHEL-native
NBDE workflow. RHEL admins use familiar Clevis commands:

```bash
clevis luks bind -d /dev/sda2 arbiter \
  '{"url":"https://arbiter-hub:8400","workload":"vm-prod-01"}'
```

Clevis calls arbiter-hub API → arbiter-hub checks attestation state →
releases key on pass. Same workflow as Tang, different trust condition.

Use cases by workload type:

| Workload | Clevis Pin         | Attestation Backend | What's Released      |
|----------|--------------------|--------------------|-----------------------|
| CVM      | `clevis pin arbiter` | Trustee (TEE)    | LUKS decryption key   |
| Host     | `clevis pin tpm2 + tang` (SSS) | N/A     | Host disk unlock      |
| Agent    | KBS API (programmatic) | Keylime (TPM/IMA) | OAuth2 credentials  |

### 12.4 Tang Deployment Options

Tang is stateless, tiny, and has no dependency on arbiter-hub or IdM.
Co-location is a deployment choice, not an architectural requirement.
Arbiter-hub references Tang by URL only.

| Option | How | Notes |
|--------|-----|-------|
| **Co-locate with IdM** (recommended) | `tang` RPM on IdM host, or Quadlet in freeipa-podman pod | IdM is already the trust anchor on the management network. Tang rides the same HA topology (one per IdM replica). |
| Standalone on arbiter-hub host | Quadlet alongside arbiter-hub containers | Simpler single-host deployment |
| Dedicated Tang server | Standard RHEL deployment | Traditional enterprise pattern |

Co-location with IdM is the natural fit: IdM servers are already on the
management network (where Tang binds), already HA (replicated), and already
the trust infrastructure hub (identity + CA + Kerberos). Adding Tang extends
IdM from "identity and CA" to "identity, CA, and network-bound trust."

Future deeper integration (not Phase 1):
- Tang JWK advertisement published in IPA LDAP for automated Clevis discovery
- Tang key rotation managed by ipacta/Dogtag policy
- IPA HBAC could gate Tang access via reverse proxy

### 12.5 Arbiter Hub Storage Protection

PostgreSQL data volume uses Clevis for encryption at rest:

```
Clevis SSS (threshold: 2 of 2)
  ├── TPM2 pin       → bound to host hardware
  └── Tang pin        → bound to management network
```

### 12.6 Updated Bootstrap Layers

```
Layer 0:   Hardware TPM (PCRs, measured boot)
Layer 0.5: Clevis + Tang (NBDE — network-bound disk unlock)
Layer 1:   Host OS + Keylime agent (IMA)
Layer 2:   Podman + signed containers (RHHI images)
Layer 3:   Arbiter Hub
           ├── KBS (raw API for programmatic access)
           └── Clevis pin arbiter (RHEL-native NBDE integration)
Layer 4:   Workloads
           ├── CVMs: clevis pin arbiter for LUKS
           ├── Agents: KBS API for credential release
           └── Both: attestation-gated
```

## 13. Integration Points

### 13.1 IPA (Identity)

- Workloads registered as `oauth2WorkloadClient` objects in IPA
- Attestation status can gate OBO token delegation (`oauth2DelegateRequireAttestation`)
- IPA roles/groups used for RBAC
- IPA HBAC rules gate pipeline checkpoints

### 13.2 Enforcement-MCP

- Arbiter Hub verifies attestation state; enforcement-mcp enforces policy (SELinux, fapolicyd, MLS, AIDE)
- Complementary, not overlapping: arbiter-hub answers "is this workload trusted?", enforcement-mcp answers "is this workload's host configured correctly?"
- Future: attestation gate check includes enforcement-mcp policy compliance

### 13.3 OBO Daemon

- OBO daemon is a Relying Party — checks attestation status before issuing delegated tokens
- Existing `oauth2DelegateRequireAttestation` attribute gates delegation
- OBO can query arbiter-hub API instead of Keylime directly (abstraction layer)

### 13.4 Agentic Trust Tiers

- Trust tier transitions map to arbiter-hub gate checks
- `submitted → untrusted`: cosign verify (arbiter-hub `/verify` endpoint)
- `untrusted → verified`: keylime attestation (arbiter-hub `/workloads/{id}/attest`)
- `verified → sovereign`: human approval + full chain audit (arbiter-hub audit log)

### 13.5 Sigstore Stack

- Fulcio: issues signing certs, chained to ipacta/Dogtag root CA
- Rekor: transparency log for immutable audit trail
- Both are external to arbiter-hub but consumed by cosign and rekor adapters

## 13. Repo Structure

```
arbiter-hub/
├── server/                    # FastAPI application
│   ├── __init__.py
│   ├── api/                   # REST endpoint routers
│   │   ├── workloads.py
│   │   ├── attestation.py
│   │   ├── policies.py
│   │   ├── audit.py
│   │   ├── signing.py
│   │   ├── kbs.py
│   │   └── health.py
│   ├── backends/              # Attestation backend adapters
│   │   ├── base.py            # Protocol definitions
│   │   ├── keylime.py
│   │   ├── trustee.py
│   │   ├── cosign.py
│   │   └── rekor.py
│   ├── policy/                # Policy engine
│   │   ├── engine.py          # Protocol + simple implementation
│   │   └── loader.py          # YAML policy loader
│   ├── state/                 # State machine
│   │   ├── machine.py         # 7-state transitions
│   │   └── scheduler.py       # Stale TTL checker
│   ├── kbs/                   # Key Broker Service logic
│   │   ├── store.py
│   │   └── gate.py
│   ├── models/                # SQLAlchemy + Pydantic
│   │   ├── db.py
│   │   └── schemas.py
│   ├── auth/                  # Authentication + RBAC
│   │   ├── oidc.py
│   │   ├── cert.py
│   │   └── rbac.py
│   ├── telemetry/             # OpenTelemetry + OCSF
│   │   ├── otel.py            # OTel setup (traces, metrics, logs)
│   │   ├── ocsf.py            # OCSF event formatter
│   │   └── webhooks.py        # Webhook delivery engine
│   ├── plugins/               # Plugin loader
│   │   └── loader.py          # entry_points discovery
│   └── config.py
├── mcp/                       # MCP client SDK
│   ├── __init__.py
│   ├── server.py              # FastMCP tool definitions
│   └── client.py              # HTTP client to API server
├── clevis-pin/                # Clevis pin arbiter (NBDE integration)
│   ├── clevis-pin-arbiter     # Pin executable (shell/Python)
│   └── clevis-pin-arbiter.1   # Man page
├── deploy/
│   ├── quadlet/               # .container, .network, .volume files
│   ├── ansible/               # Deployment roles
│   │   └── roles/
│   │       └── arbiter_hub/
│   ├── containerfiles/        # Multi-stage Containerfiles
│   │   ├── Containerfile.api
│   │   ├── Containerfile.kbs
│   │   └── Containerfile.mcp
│   └── selinux/               # Custom SELinux policy modules
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── docs/
│   ├── api/                   # OpenAPI spec
│   ├── architecture/          # Design docs
│   └── deployment/            # Deployment guides
├── scripts/
│   ├── setup-ipa-roles.sh     # IPA role/HBAC setup
│   └── seed-kbs-secrets.sh    # Dev/test secret seeding
└── pyproject.toml
```

## 14. Testing Strategy

### 14.1 Unit Tests

- State machine transitions (all valid/invalid paths)
- Policy engine evaluation (allow/deny for each policy rule)
- Backend adapter response parsing
- Auth/RBAC permission checks
- KBS gate logic

### 14.2 Integration Tests

- API endpoints with test PostgreSQL (not mocked — per project practice)
- Backend adapters against mock Keylime/Trustee/cosign responses
- Full attestation flow: register → attest → check status → release secret
- State machine with database persistence

### 14.3 E2E Tests

- Full Quadlet deployment in test VM
- Keylime backend with swtpm
- Cosign signing and verification with test CA
- KBS secret release gated by attestation
- MCP tools against running API server

## 15. Security Considerations

### 15.1 Threat Model Summary

| Threat                        | Mitigation                                        |
|-------------------------------|---------------------------------------------------|
| God-box compromise            | HSM/Dogtag-managed signing keys, no bulk export,  |
|                               | quorum for policy changes, immutable Rekor audit   |
| MCP prompt injection          | Read-only tools, scope restriction, rate limiting, |
|                               | workload cert auth, audit every MCP call           |
| Backend impersonation         | mTLS to all backends, cert pinning                 |
| State machine manipulation    | Transitions logged to Rekor, backward transitions  |
|                               | require elevated privilege + justification          |
| Container escape              | Custom SELinux types, read-only rootfs, no caps,   |
|                               | separate networks, podman secrets                  |
| Supply chain (who attests     | 4-layer bootstrap: TPM → host Keylime → Podman    |
| the attestor?)                | signature verify → arbiter-hub → workloads         |
| KBS secret exfiltration       | Encrypted at rest, per-request release, scope      |
|                               | enforcement, revocation triggers invalidation      |
| Audit log tampering           | Rekor transparency log (external, append-only)     |

### 15.2 Read-Only MCP Risk

Even read-only tools leak information. Agent queries reveal:
- Which workloads exist (reconnaissance)
- Workload states (target selection — Failed workloads are vulnerable)
- Operational patterns (timing analysis via audit log)

Mitigation: scope restriction (agents see only their workloads) + rate limiting
+ audit logging of all MCP queries.

### 15.3 KBS Secret Lifecycle Risks

- Secret rotation: new version stored, old version invalidated after grace period
- Revocation latency: workload revoked but cached secret still valid. Mitigated by
  short-lived tokens and downstream RP attestation checks
- Blast radius: secrets scoped per-workload. Compromise of one workload's attestation
  does not expose other workloads' secrets

## 16. Standards and Interoperability

### 16.1 API Standards

- **OpenAPI 3.1** spec auto-generated from FastAPI, published at `/docs` and `/openapi.json`
- **IETF EAT (Entity Attestation Token, RFC 9711)** for attestation evidence format —
  standard token format consumable by any RATS-aware verifier or relying party
- **RATS (RFC 9334)** architecture compliance — components map to Attester/Verifier/RP/Endorser roles
- **KBS v0 API** maintained for backward compatibility with existing Trustee ecosystem
- **SCIM-style pagination** on list endpoints (`?startIndex=1&count=25`) for tooling compatibility
- **RFC 7807 Problem Details** for error responses — standard error format for API consumers

### 16.2 Telemetry and Observability

**OpenTelemetry (OTel)** — primary telemetry framework. All three signals:

| Signal  | Format                    | Consumer                        |
|---------|---------------------------|---------------------------------|
| Traces  | OTLP (gRPC/HTTP)         | Jaeger, Grafana Tempo, any OTLP collector |
| Metrics | OTLP + Prometheus `/metrics` | Prometheus, Grafana, Datadog  |
| Logs    | OTLP structured logs      | Loki, Splunk, ELK              |

**Key metrics exposed:**
- `arbiter_attestations_total` (counter, labels: backend, verdict, workload_type)
- `arbiter_state_transitions_total` (counter, labels: from_state, to_state)
- `arbiter_attestation_duration_seconds` (histogram, labels: backend)
- `arbiter_kbs_releases_total` (counter, labels: repo, result)
- `arbiter_backend_health` (gauge, labels: backend)
- `arbiter_workloads_by_state` (gauge, labels: state, workload_type)

**Security events — OCSF (Open Cybersecurity Schema Framework):**

All security-relevant events emitted in OCSF v1.3 format for SIEM consumption.
OCSF is the emerging standard (AWS, Splunk, IBM, CrowdStrike contribute).

| OCSF Event Class          | Arbiter Hub Event                          |
|---------------------------|--------------------------------------------|
| Authentication (3002)     | Workload identity verification             |
| Authorization (3003)      | Policy evaluation (allow/deny)             |
| Entity Management (3004)  | Workload registration, state transitions   |
| Security Finding (2001)   | Attestation failure, policy violation       |
| Compliance Finding (2003) | Compliance check results                   |
| API Activity (6003)       | All API calls (who did what when)          |

Events delivered via:
- **Structured log output** (stdout, OTel log pipeline) — default
- **Webhook** — push to external consumers (SIEM, SOAR, custom)
- **Syslog (RFC 5424)** — traditional SIEM integration (CEF optional)

### 16.3 Plugin Architecture

Three extension points, all using Python Protocol (structural typing):

**Backend Plugins** — add custom attestation backends:

```python
# Third party implements AttestationBackend Protocol
# Register via config or entry_points in pyproject.toml
[project.entry-points."arbiter_hub.backends"]
my_backend = "my_package:MyBackend"
```

**Policy Engine Plugins** — swap or extend policy evaluation:

```python
[project.entry-points."arbiter_hub.policy_engines"]
opa = "arbiter_hub_opa:OPAEngine"
cedar = "arbiter_hub_cedar:CedarEngine"
```

**Event Handler Plugins** — react to attestation events:

```python
class EventHandler(Protocol):
    async def on_state_transition(self, event: StateTransitionEvent) -> None: ...
    async def on_attestation_result(self, event: AttestationEvent) -> None: ...
    async def on_policy_decision(self, event: PolicyEvent) -> None: ...
    async def on_kbs_release(self, event: KBSReleaseEvent) -> None: ...

[project.entry-points."arbiter_hub.event_handlers"]
siem_forwarder = "my_siem:SIEMForwarder"
slack_notifier = "my_alerts:SlackNotifier"
```

**Webhook System** — no-code integration for external consumers:

```yaml
webhooks:
  - name: siem-forward
    url: https://siem.example.com/api/events
    events: [attestation_failed, workload_revoked, policy_violation]
    format: ocsf      # or raw
    auth: bearer_token
    secret: ${WEBHOOK_SIEM_TOKEN}
    retry: 3
    
  - name: pagerduty
    url: https://events.pagerduty.com/v2/enqueue
    events: [attestation_failed, backend_unhealthy]
    format: pagerduty_v2
```

Webhooks configured via YAML or API (`POST /webhooks`). Each webhook
receives OCSF-formatted events by default, or raw JSON. Delivery is
async with configurable retry. Failed deliveries logged but never block
attestation operations.

## 17. Phase 2 Roadmap (Out of Scope)

Items explicitly deferred to Phase 2:

- **PatternFly Web UI** — React + PatternFly 6.4 + Vite + Fastify + RTK Query.
  Dashboard, workload list, audit viewer, policy editor. Builds against Phase 1 API.
- **OPA/Cedar policy engine** — swap simple rules engine for OPA sidecar container.
  Same `PolicyEngine` interface, Rego policies stored in PostgreSQL.
- **CAEP revocation feedback** — WIMSE/AIMS alignment. Real-time revocation events
  propagated to relying parties via CAEP (Continuous Access Evaluation Protocol).
- **Multi-node HA** — PostgreSQL replication, API server horizontal scaling,
  load balancer (HAProxy or envoy).
- **Grafana dashboards** — attestation metrics, workload health, backend latency.
- **SLSA provenance** — in-toto attestation predicates for build provenance.
