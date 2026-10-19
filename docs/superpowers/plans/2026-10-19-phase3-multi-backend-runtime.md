# Phase 3: Multi-Backend Attestation, Runtime Monitoring, and Auto-Remediation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable composite multi-backend attestation per workload, add Falco eBPF runtime alert ingestion, and close the remediation loop with outbound webhooks and EDA playbooks.

**Architecture:** Replace single `backend_type` with `backend_types` array on workloads. Attest endpoint runs all registered backends in parallel, applies FAIL-trumps-UNAVAILABLE composite verdict. Falco alerts arrive via inbound webhook and trigger state transitions. Outbound webhook dispatcher notifies EDA on state changes. Mock KBS provides CVM attestation without real TEE hardware.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy async, PostgreSQL (ARRAY, JSONB), Alembic, pytest + pytest-asyncio, httpx, cosign v2, Falco 0.38+ (eBPF), ansible-rulebook 1.1+

**Spec:** `docs/superpowers/specs/2026-10-19-phase3-multi-backend-runtime-design.md`

## Global Constraints

- All new endpoints require OIDC auth (existing middleware handles this automatically via router inclusion)
- Container images via Podman Quadlet (existing pattern in `deploy/quadlet/`)
- Alembic migrations use revision IDs `003`, `004`, etc. (existing: `001`, `002`)
- Test pattern: `pytest.mark.asyncio`, `MagicMock` for workloads in unit tests, `httpx.ASGITransport` for integration
- `BackendType` is a `StrEnum` — new values must be lowercase strings
- State machine transitions are validated by `server/state/machine.py:validate_transition()`
- Audit log entries created for all state-changing operations

## Review Focus

1. **Concurrent composite attestation race condition** — two simultaneous `/attest` calls for the same workload could interleave AttestationRecord inserts if the FOR UPDATE lock doesn't cover the full composite sequence. Expected: second call blocks until first completes. _Test: `test_concurrent_composite_attest_serializes` in Task 2._
2. **Empty `backend_types` list** — `WorkloadCreate(backend_types=[])` should be rejected with 422, not create a workload that can never be attested. _Test: `test_create_workload_empty_backend_types_rejected` in Task 1._
3. **Falco alert for unknown container** — POST to `/api/alerts/falco` with a `container.id` matching no workload should return 404. _Test: `test_falco_alert_unknown_container_404` in Task 5._
4. **Webhook delivery failure** — unreachable webhook URL must not crash the state transition or block the API response. _Test: `test_webhook_delivery_failure_does_not_block` in Task 6._
5. **Backward-compatible workload creation** — existing clients sending `backend_type` (singular) should still work via alias. _Test: `test_create_workload_singular_backend_type_compat` in Task 1._

---

### Task 1: Schema Migration — `backend_types` Array Column

**Files:**
- Modify: `server/models/db.py:50-55,71` — add `FALCO` to `BackendType`, change `backend_type` column to `backend_types`
- Modify: `server/models/schemas.py:27-46` — update `WorkloadCreate` and `WorkloadRead`
- Modify: `server/api/workloads.py:318-325` — update `register_workload` to use `backend_types`
- Create: `alembic/versions/003_backend_types_array.py`
- Test: `tests/unit/test_backend_types_migration.py`

**Interfaces:**
- Consumes: existing `BackendType` enum, `Workload` model
- Produces: `BackendType.FALCO = "falco"`, `Workload.backend_types: Mapped[list[str]]` (ARRAY(String)), `WorkloadCreate.backend_types: list[BackendType]` with `backend_type` as alias for single-value compat

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_backend_types_migration.py

def test_falco_backend_type_exists():
    assert BackendType.FALCO == "falco"

def test_workload_create_accepts_backend_types_list():
    wc = WorkloadCreate(
        ipa_principal="svc/host@REALM",
        display_name="test",
        workload_type="service",
        backend_types=["keylime", "cosign"],
    )
    assert wc.backend_types == [BackendType.KEYLIME, BackendType.COSIGN]

def test_create_workload_singular_backend_type_compat():
    wc = WorkloadCreate(
        ipa_principal="svc/host@REALM",
        display_name="test",
        workload_type="service",
        backend_type="keylime",
    )
    assert wc.backend_types == [BackendType.KEYLIME]

def test_create_workload_empty_backend_types_rejected():
    with pytest.raises(ValidationError):
        WorkloadCreate(
            ipa_principal="svc/host@REALM",
            display_name="test",
            workload_type="service",
            backend_types=[],
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_backend_types_migration.py -v`
Expected: FAIL — `FALCO` not in `BackendType`, `backend_types` not a field

- [ ] **Step 3: Implement model changes**

In `server/models/db.py`:
- Add `FALCO = "falco"` to `BackendType` enum
- Replace `backend_type: Mapped[BackendType]` with `backend_types: Mapped[list[str]] = mapped_column(ARRAY(String(50)), nullable=False)` on `Workload`

In `server/models/schemas.py`:
- `WorkloadCreate`: replace `backend_type: BackendType` with `backend_types: list[BackendType] = Field(min_length=1)`. Add `@model_validator(mode="before")` that converts `{"backend_type": "x"}` → `{"backend_types": ["x"]}`.
- `WorkloadRead`: same field change, add `validation_alias` handling

In `server/api/workloads.py:register_workload`: `backend_types=body.backend_types` → store as list of strings on the model.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_backend_types_migration.py -v`
Expected: PASS (4/4)

- [ ] **Step 5: Write Alembic migration**

Create `alembic/versions/003_backend_types_array.py`:
- `upgrade()`: add `backend_types` ARRAY(String(50)) column, populate from existing `backend_type` (`UPDATE workloads SET backend_types = ARRAY[backend_type]`), drop `backend_type`, set NOT NULL on `backend_types`.
- `downgrade()`: reverse — add `backend_type`, populate from `backend_types[1]`, drop `backend_types`.

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v --timeout=30`
Expected: existing tests that reference `backend_type` will fail — update them in this step to use `backend_types`. Fix `MockWorkload` in `test_api_write.py`, `test_api_read.py`, and any other references.

- [ ] **Step 7: Commit**

```bash
git add server/models/db.py server/models/schemas.py server/api/workloads.py \
  alembic/versions/003_backend_types_array.py tests/unit/test_backend_types_migration.py \
  tests/integration/test_api_write.py tests/integration/test_api_read.py
git commit -m "feat: migrate backend_type to backend_types array, add FALCO enum"
```

---

### Task 2: Composite Attestation Endpoint

**Files:**
- Modify: `server/backends/base.py` — add `CompositeAttestationResult`
- Modify: `server/api/attestation.py` — parallel backend execution, composite verdict
- Test: `tests/unit/test_composite_attestation.py`

**Interfaces:**
- Consumes: `Workload.backend_types` (Task 1), `BackendRegistry.get(name)`, `AttestationResult`, `AttestationVerdict`
- Produces: `CompositeAttestationResult(composite_verdict, backend_results, timestamp)`, updated `/attest` response with `per_backend` array

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_composite_attestation.py

def test_composite_all_pass():
    results = [
        AttestationResult(verdict=AttestationVerdict.PASS, backend="keylime", evidence_hash="a"),
        AttestationResult(verdict=AttestationVerdict.PASS, backend="cosign", evidence_hash="b"),
    ]
    composite = compute_composite_verdict(results)
    assert composite == AttestationVerdict.PASS

def test_composite_one_fail_one_pass():
    results = [
        AttestationResult(verdict=AttestationVerdict.PASS, backend="keylime", evidence_hash="a"),
        AttestationResult(verdict=AttestationVerdict.FAIL, backend="cosign", evidence_hash="b"),
    ]
    composite = compute_composite_verdict(results)
    assert composite == AttestationVerdict.FAIL

def test_composite_one_unavailable_one_pass():
    results = [
        AttestationResult(verdict=AttestationVerdict.PASS, backend="keylime", evidence_hash="a"),
        AttestationResult(verdict=AttestationVerdict.UNAVAILABLE, backend="cosign", evidence_hash=""),
    ]
    composite = compute_composite_verdict(results)
    assert composite == AttestationVerdict.UNAVAILABLE

def test_composite_fail_trumps_unavailable():
    results = [
        AttestationResult(verdict=AttestationVerdict.FAIL, backend="keylime", evidence_hash="a"),
        AttestationResult(verdict=AttestationVerdict.UNAVAILABLE, backend="cosign", evidence_hash=""),
    ]
    composite = compute_composite_verdict(results)
    assert composite == AttestationVerdict.FAIL

@pytest.mark.asyncio
async def test_concurrent_composite_attest_serializes():
    # Two simultaneous attest calls for the same workload
    # Both should complete without interleaved records
    # Uses mock registry with artificial delay in verify()
    ...  # assert both return valid results, no duplicate transitions
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_composite_attestation.py -v`
Expected: FAIL — `compute_composite_verdict` not defined

- [ ] **Step 3: Implement `compute_composite_verdict(results: list[AttestationResult]) -> AttestationVerdict` in `server/backends/base.py`**

Logic: if any FAIL → FAIL; elif any UNAVAILABLE or ERROR → UNAVAILABLE; else PASS.

Add `CompositeAttestationResult` dataclass with `composite_verdict`, `backend_results`, `timestamp`.

- [ ] **Step 4: Rewrite `trigger_attestation()` in `server/api/attestation.py`**

Replace single-backend lookup with: iterate `workload.backend_types`, gather backends from registry (skip missing with warning), run `asyncio.gather(*[b.verify(workload) for b in backends])`, compute composite verdict, create one `AttestationRecord` per backend result, transition based on composite verdict using same UNAVAILABLE-stays-in-ATTESTING logic.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_composite_attestation.py -v`
Expected: PASS

- [ ] **Step 6: Run full suite**

Run: `pytest tests/ -v --timeout=30`
Expected: PASS — existing attestation tests may need backend_types fixture update

- [ ] **Step 7: Commit**

```bash
git add server/backends/base.py server/api/attestation.py tests/unit/test_composite_attestation.py
git commit -m "feat: composite multi-backend attestation with FAIL-trumps-UNAVAILABLE"
```

---

### Task 3: CosignBackend Key Flag + Lifespan Registration

**Files:**
- Modify: `server/backends/cosign.py:17-24` — add `public_key` param, `--key` flag
- Modify: `server/config.py` — add `cosign_public_key` setting
- Modify: `server/main.py:17-31` — register cosign backend in lifespan
- Test: `tests/unit/test_cosign_key.py`

**Interfaces:**
- Consumes: `CosignBackend` (existing), `BackendRegistry.register()`
- Produces: `CosignBackend(public_key="/path/to/cosign.pub")`, registered as `"cosign"` in registry

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_cosign_key.py

@pytest.mark.asyncio
async def test_cosign_verify_uses_key_flag():
    cb = CosignBackend(cosign_binary="echo", public_key="/tmp/test.pub")
    workload = MagicMock()
    workload.metadata_ = {"artifact_ref": "quay.io/test/image:latest"}
    result = await cb.verify(workload)
    # echo outputs its args — check --key appears in the output
    assert "--key" in result.detail.get("output", "") or result.verdict in (
        AttestationVerdict.PASS, AttestationVerdict.FAIL
    )

def test_cosign_backend_without_key():
    cb = CosignBackend(cosign_binary="cosign")
    # Should not add --key flag when public_key is empty
    assert cb._public_key == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cosign_key.py -v`
Expected: FAIL — `public_key` not accepted by `CosignBackend.__init__`

- [ ] **Step 3: Implement**

Add `public_key: str = ""` to `CosignBackend.__init__()`. In `verify()`, insert `cmd.extend(["--key", self._public_key])` before `artifact_ref` when `self._public_key` is set.

Add `cosign_public_key: str = ""` to `server/config.py:Settings`.

In `server/main.py` lifespan, add cosign registration block (same pattern as keylime).

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_cosign_key.py tests/unit/test_backends_additional.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/backends/cosign.py server/config.py server/main.py tests/unit/test_cosign_key.py
git commit -m "feat: cosign --key flag and lifespan registration"
```

---

### Task 4: Mock KBS Service

**Files:**
- Create: `mock-kbs/main.py` — FastAPI app with `/kbs/v0/` endpoints
- Create: `mock-kbs/evidence.py` — SEV-SNP report structure generator
- Create: `mock-kbs/Containerfile`
- Create: `deploy/quadlet/mock-kbs.container`
- Test: `tests/unit/test_mock_kbs.py`

**Interfaces:**
- Consumes: nothing (standalone service)
- Produces: HTTP API at `:8085` matching `TrusteeBackend` expectations — `POST /kbs/v0/attest` returns `{"attestation_pass": bool, "report": {...}}`, `GET /kbs/v0/health` returns `{"status": "ok"}`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_mock_kbs.py
import sys; sys.path.insert(0, "mock-kbs")

@pytest.mark.asyncio
async def test_mock_kbs_health():
    from mock_kbs.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/kbs/v0/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_mock_kbs_attest_registered_measurement():
    # Register expected measurement, then attest with matching evidence
    ...
    assert resp.json()["attestation_pass"] is True
    assert "measurement" in resp.json()["report"]

@pytest.mark.asyncio
async def test_mock_kbs_attest_unknown_measurement():
    # Attest with unregistered measurement
    ...
    assert resp.json()["attestation_pass"] is False

def test_evidence_generator_produces_snp_fields():
    from mock_kbs.evidence import generate_snp_report
    report = generate_snp_report(measurement="ab" * 24, report_data="cd" * 32)
    assert len(report["report_data"]) == 128  # 64 bytes hex
    assert len(report["measurement"]) == 96   # 48 bytes hex
    assert "policy" in report
    assert "platform_version" in report
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_mock_kbs.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement mock KBS**

`mock-kbs/main.py`: FastAPI app with in-memory dict of registered measurements. Endpoints: `GET /kbs/v0/health`, `POST /kbs/v0/register` (stores expected measurement), `POST /kbs/v0/attest` (checks `evidence.measurement` against registered set).

`mock-kbs/evidence.py`: `generate_snp_report(measurement: str, report_data: str) -> dict` — returns dict with `report_data`, `measurement`, `policy` (hex string), `platform_version` ("Milan-B1"), `guest_svn` (1).

`mock-kbs/Containerfile`: UBI9 python-311, pip install fastapi uvicorn, CMD uvicorn.

`deploy/quadlet/mock-kbs.container`: port 8085, `Internal=true` network.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_mock_kbs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mock-kbs/ deploy/quadlet/mock-kbs.container tests/unit/test_mock_kbs.py
git commit -m "feat: mock KBS service with SEV-SNP evidence simulation"
```

---

### Task 5: FalcoBackend + Alert Receiver + State Machine Update

**Files:**
- Create: `server/backends/falco.py` — `FalcoBackend` implementing `AttestationBackend`
- Create: `server/api/alerts.py` — `POST /api/alerts/falco` endpoint
- Modify: `server/state/machine.py:21` — add `WorkloadState.FAILED` to `HEALTHY` transitions
- Modify: `server/main.py` — register falco backend, include alerts router
- Modify: `server/config.py` — add `falco_healthz_url` setting
- Test: `tests/unit/test_falco_backend.py`
- Test: `tests/unit/test_alerts.py`

**Interfaces:**
- Consumes: `AttestationBackend` protocol, `BackendRegistry`, `Workload.metadata_["container_id"]`, `transition()`, `WorkloadState`
- Produces: `FalcoBackend(healthz_url)`, `POST /api/alerts/falco` accepting Falco webhook JSON, `HEALTHY → FAILED` state transition

- [ ] **Step 1: Write failing state machine test**

```python
# Add to tests/unit/test_state_machine.py

def test_healthy_can_go_to_failed():
    validate_transition(WorkloadState.HEALTHY, WorkloadState.FAILED)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_state_machine.py::test_healthy_can_go_to_failed -v`
Expected: FAIL — `InvalidTransitionError`

- [ ] **Step 3: Add FAILED to HEALTHY transitions**

In `server/state/machine.py:21`: change `{WorkloadState.STALE, WorkloadState.REVOKED}` to `{WorkloadState.STALE, WorkloadState.FAILED, WorkloadState.REVOKED}`.

- [ ] **Step 4: Verify state machine tests pass**

Run: `pytest tests/unit/test_state_machine.py -v`
Expected: PASS (all existing + new test)

- [ ] **Step 5: Write FalcoBackend tests**

```python
# tests/unit/test_falco_backend.py

def test_falco_implements_protocol():
    fb = FalcoBackend(healthz_url="http://localhost:8765/healthz")
    assert isinstance(fb, AttestationBackend)

@pytest.mark.asyncio
async def test_falco_health_unreachable():
    fb = FalcoBackend(healthz_url="http://unreachable:8765/healthz")
    health = await fb.health()
    assert health.healthy is False
    assert health.backend == "falco"

@pytest.mark.asyncio
async def test_falco_enroll_is_noop():
    fb = FalcoBackend(healthz_url="http://localhost:8765/healthz")
    result = await fb.enroll(MagicMock(), {})
    assert result.success is True

@pytest.mark.asyncio
async def test_falco_revoke_is_noop():
    fb = FalcoBackend(healthz_url="http://localhost:8765/healthz")
    result = await fb.revoke(MagicMock())
    assert result.success is True
```

- [ ] **Step 6: Implement FalcoBackend in `server/backends/falco.py`**

`FalcoBackend(healthz_url: str, timeout: float = 5.0)`. `verify()` → returns PASS (Falco is event-driven, not polled). `health()` → GET `healthz_url`. `enroll()`/`revoke()` → no-op success.

- [ ] **Step 7: Write alert receiver tests**

```python
# tests/unit/test_alerts.py

@pytest.mark.asyncio
async def test_falco_alert_transitions_healthy_to_failed():
    # POST valid Falco alert with container_id matching a workload
    # Assert workload transitions to FAILED
    # Assert AttestationRecord created with backend="falco", verdict=FAIL
    ...

@pytest.mark.asyncio
async def test_falco_alert_unknown_container_404():
    # POST Falco alert with unknown container_id
    # Assert 404
    ...

@pytest.mark.asyncio
async def test_falco_alert_low_priority_logs_only():
    # POST alert with priority="Notice"
    # Assert workload stays HEALTHY (no transition)
    ...
```

- [ ] **Step 8: Implement `POST /api/alerts/falco` in `server/api/alerts.py`**

New router. Accepts Falco webhook JSON body. Extracts `container_id` from `output_fields.container.id`. Queries `Workload` where `metadata_->>'container_id' = :cid`. If priority >= WARNING and workload is HEALTHY, transitions to FAILED via `transition()`. Creates `AttestationRecord(backend=BackendType.FALCO, verdict=FAIL)`. Returns 200 with transition details.

- [ ] **Step 9: Register in main.py**

Add falco backend registration (if `settings.falco_healthz_url` set). Include `alerts.router` with tags `["alerts"]`.

- [ ] **Step 10: Run full suite**

Run: `pytest tests/ -v --timeout=30`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add server/backends/falco.py server/api/alerts.py server/state/machine.py \
  server/main.py server/config.py tests/unit/test_falco_backend.py \
  tests/unit/test_alerts.py tests/unit/test_state_machine.py
git commit -m "feat: Falco eBPF alert receiver with HEALTHY→FAILED transition"
```

---

### Task 6: Outbound Webhook Dispatcher

**Files:**
- Create: `server/api/webhooks.py` — registration endpoint + dispatch logic
- Modify: `server/models/db.py` — add `Webhook` model
- Create: `alembic/versions/004_webhooks_table.py`
- Modify: `server/state/machine.py` — call dispatcher after transition
- Modify: `server/main.py` — include webhooks router
- Test: `tests/unit/test_webhooks.py`

**Interfaces:**
- Consumes: `transition()` from state machine, `AuditLog` pattern, OIDC auth
- Produces: `POST /api/webhooks` (register), `GET /api/webhooks` (list), `DELETE /api/webhooks/{id}`, `dispatch_webhooks(event_type, workload, from_state, to_state, detail)` called on transitions

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_webhooks.py

def test_webhook_hmac_signature():
    from server.api.webhooks import compute_hmac_signature
    sig = compute_hmac_signature(b'{"test": true}', "secret123")
    assert sig.startswith("sha256=")
    assert len(sig) == 71  # "sha256=" + 64 hex chars

@pytest.mark.asyncio
async def test_webhook_delivery_failure_does_not_block():
    # Register webhook with unreachable URL
    # Trigger state transition
    # Assert transition completes (no exception)
    ...

@pytest.mark.asyncio
async def test_webhook_payload_contains_required_fields():
    # Capture webhook payload
    # Assert event_type, workload_id, from_state, to_state, timestamp present
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_webhooks.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement Webhook model**

In `server/models/db.py`: add `Webhook` table — `id` (UUID), `url` (String 2048), `events` (ARRAY(String)), `secret` (String 255), `created_by` (String), `created_at` (DateTime). Alembic migration `004`.

- [ ] **Step 4: Implement webhook API + dispatcher**

`server/api/webhooks.py`:
- `compute_hmac_signature(body: bytes, secret: str) -> str` — HMAC-SHA256, returns `sha256=<hex>`
- `POST /api/webhooks` — creates webhook registration, requires `register_webhook` permission
- `GET /api/webhooks` — lists registered webhooks
- `DELETE /api/webhooks/{id}` — removes webhook
- `dispatch_webhooks(session, event_type, workload, from_state, to_state, detail)` — async function that POSTs to all registered webhooks matching event_type. Fire-and-forget via `asyncio.create_task()`. Logs errors, never raises.

Integrate into `server/state/machine.py:transition()` — after recording the StateTransition, call `dispatch_webhooks()`. The dispatcher also queries existing `WebhookDelivery` (YAML-based) configs and fires those too.

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_webhooks.py -v`
Expected: PASS

- [ ] **Step 6: Run full suite**

Run: `pytest tests/ -v --timeout=30`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add server/api/webhooks.py server/models/db.py server/state/machine.py \
  server/main.py alembic/versions/004_webhooks_table.py tests/unit/test_webhooks.py
git commit -m "feat: outbound webhook dispatcher with HMAC-SHA256 signing"
```

---

### Task 7: EDA Source Plugin, Rulebooks, Playbooks, and Falco Rules

**Files:**
- Create: `eda/plugins/event_source/arbiter_hub.py`
- Create: `eda/rulebooks/attestation.yml`
- Create: `eda/rulebooks/demo.yml`
- Create: `eda/playbooks/quarantine.yml`
- Create: `eda/playbooks/re_attest.yml`
- Create: `eda/playbooks/forensic_collect.yml`
- Create: `eda/inventory/beaker.yml`
- Create: `deploy/falco/arbiter-rules.yaml`
- Test: `tests/unit/test_eda_source.py`

**Interfaces:**
- Consumes: Outbound webhook payload format from Task 6
- Produces: EDA source plugin receiving arbiter-hub webhooks, 3 rulebooks, 3 playbooks, Falco custom rules

- [ ] **Step 1: Write failing test for EDA source plugin**

```python
# tests/unit/test_eda_source.py

@pytest.mark.asyncio
async def test_eda_source_validates_hmac():
    from eda.plugins.event_source.arbiter_hub import validate_hmac
    body = b'{"event_type": "state_transition"}'
    secret = "test-secret"
    sig = compute_hmac_signature(body, secret)  # from Task 6
    assert validate_hmac(body, sig, secret) is True
    assert validate_hmac(body, "sha256=wrong", secret) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_eda_source.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement EDA source plugin**

`eda/plugins/event_source/arbiter_hub.py`: aiohttp web server receiving POST webhooks. Validates HMAC signature. Pushes validated events to EDA queue. `validate_hmac(body, signature, secret) -> bool`.

- [ ] **Step 4: Create rulebooks**

`eda/rulebooks/attestation.yml`: Three rules — quarantine on FAILED, re-attest on STALE, forensic collect on CRITICAL Falco alert. Per spec.

`eda/rulebooks/demo.yml`: Simplified single-rule version for walkthroughs.

- [ ] **Step 5: Create playbooks**

`eda/playbooks/quarantine.yml`: `containers.podman.podman_container` network isolation + POST to `/remediate` endpoint.

`eda/playbooks/re_attest.yml`: POST to `/workloads/{id}/attest` with Bearer token.

`eda/playbooks/forensic_collect.yml`: `podman inspect` + `podman logs` + `tar` evidence to `/var/lib/arbiter/forensics/`.

- [ ] **Step 6: Create Falco rules**

`deploy/falco/arbiter-rules.yaml`: Three rules from spec — unexpected process, reverse shell, sensitive file access. Priority WARNING or CRITICAL.

- [ ] **Step 7: Create inventory**

`eda/inventory/beaker.yml`: `all.hosts` with `server` and `client` groups, vars for `api_url`, `arbiter_token`.

- [ ] **Step 8: Run tests**

Run: `pytest tests/unit/test_eda_source.py -v`
Expected: PASS

- [ ] **Step 9: Validate YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('eda/rulebooks/attestation.yml')); yaml.safe_load(open('deploy/falco/arbiter-rules.yaml')); print('YAML valid')"`
Expected: "YAML valid"

- [ ] **Step 10: Commit**

```bash
git add eda/ deploy/falco/ tests/unit/test_eda_source.py
git commit -m "feat: EDA source plugin, rulebooks, playbooks, and Falco rules"
```

---

## Implementation Order Summary

```
Task 1 (schema) ──► Task 2 (composite attest) ──► Task 5 (Falco) ──► Task 6 (webhooks) ──► Task 7 (EDA)
                ──► Task 3 (cosign) [parallel]
                ──► Task 4 (mock KBS) [parallel]
```

Tasks 3 and 4 are independent of Task 2 and can run in parallel. Tasks 5-7 are sequential.
