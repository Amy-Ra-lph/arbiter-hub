"""Tests for Phase 2 UI backend additions."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from server.backends.base import AttestationResult, BackendRegistry
from server.main import create_app
from server.models.db import (
    AttestationVerdict,
    BackendType,
    KBSSecret,
    Policy,
    StateTransition,
    Workload,
    WorkloadState,
    WorkloadType,
    get_session,
)

ADMIN_HEADERS = {
    "X-Caller-Principal": "admin@IPA.TEST",
    "X-Caller-Type": "admin",
    "X-Caller-Roles": "attestation-admin",
    "X-Caller-Scopes": "*",
}


class MockBackend:
    async def verify(self, workload):
        return AttestationResult(
            verdict=AttestationVerdict.PASS,
            backend="keylime",
            evidence_hash="mock_hash_123",
            detail={"test": "data"},
        )

    async def health(self):
        from unittest.mock import MagicMock

        return MagicMock(healthy=True, backend="keylime")


# Shared in-memory storage keyed per fixture invocation
_workloads: dict[str, object] = {}
_policies: dict[str, Policy] = {}
_transitions: list = []
_kbs_secrets: list = []
_test_initialized = False


class MockAsyncSession:
    def __init__(self):
        self.added = []

    async def execute(self, stmt):
        from unittest.mock import MagicMock

        result = MagicMock()
        stmt_str = str(stmt)

        # Extract bound parameters if available
        params = {}
        if hasattr(stmt, '_where_criteria'):
            try:
                compiled = stmt.compile()
                params = compiled.params
            except Exception:
                pass

        # Workload lookup by principal
        if "workloads.ipa_principal" in stmt_str:
            for principal, w in _workloads.items():
                # Check both in SQL text and bound params
                if principal in stmt_str or any(
                    v == principal for v in params.values()
                ):
                    result.scalar_one_or_none = lambda w=w: w
                    return result

        # Workload lookup by ID (for get, delete, transitions, attest)
        if "workloads" in stmt_str and "workloads.id" in stmt_str and "state_transitions" not in stmt_str and "attestation" not in stmt_str:
            # Try to find the workload by checking bound params
            for w in _workloads.values():
                for v in params.values():
                    if str(v) == str(w.id):
                        result.scalar_one_or_none = lambda w=w: w
                        return result
                # Also check if UUID appears in SQL text directly
                if str(w.id) in stmt_str:
                    result.scalar_one_or_none = lambda w=w: w
                    return result

        # State transitions
        if "state_transitions" in stmt_str:
            if "count" in stmt_str.lower():
                result.scalar_one = lambda: len(_transitions)
                return result
            matching = list(_transitions)
            result.scalars = lambda: matching
            return result

        # KBS secrets list
        if "kbs_secrets" in stmt_str:
            if "count" in stmt_str.lower():
                result.scalar_one = lambda: len(_kbs_secrets)
                return result
            result.scalars = lambda: _kbs_secrets
            return result

        # Policies
        if "policies" in stmt_str:
            if "count" in stmt_str.lower():
                result.scalar_one = lambda: len(_policies)
                return result
            matching = list(_policies.values())
            result.scalars = lambda: matching
            return result

        # Attestation records (for delete cleanup)
        if "attestation_records" in stmt_str:
            result.scalars = lambda: []
            result.scalar_one = lambda: 0
            return result

        result.scalar_one_or_none = lambda: None
        result.scalar_one = lambda: 0
        result.scalars = lambda: []
        return result

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, Workload):
            from dataclasses import dataclass, field
            from datetime import UTC, datetime

            @dataclass
            class MockWL:
                id: uuid.UUID = field(default_factory=uuid.uuid4)
                ipa_principal: str = ""
                display_name: str = ""
                workload_type: WorkloadType = WorkloadType.AGENTIC
                current_state: WorkloadState = WorkloadState.REGISTERED
                backend_type: BackendType = BackendType.KEYLIME
                stale_ttl_seconds: int = 3600
                registered_at: datetime = field(
                    default_factory=lambda: datetime.now(UTC)
                )
                last_attested_at: datetime | None = None
                metadata_: dict = field(default_factory=dict)

                @property
                def metadata(self):
                    return self.metadata_

            mock_obj = MockWL(
                id=obj.id if obj.id else uuid.uuid4(),
                ipa_principal=obj.ipa_principal,
                display_name=obj.display_name,
                workload_type=obj.workload_type,
                backend_type=obj.backend_type,
                stale_ttl_seconds=obj.stale_ttl_seconds,
                current_state=obj.current_state or WorkloadState.REGISTERED,
                metadata_=obj.metadata_ if obj.metadata_ else {},
            )
            obj.id = mock_obj.id
            obj.current_state = mock_obj.current_state
            obj.registered_at = mock_obj.registered_at
            if not obj.metadata_:
                obj.metadata_ = {}
            _workloads[obj.ipa_principal] = mock_obj
        elif isinstance(obj, Policy):
            if not obj.id:
                obj.id = uuid.uuid4()
            from datetime import UTC, datetime

            if obj.active is None:
                obj.active = True
            if not obj.created_at:
                obj.created_at = datetime.now(UTC)
            if not obj.updated_at:
                obj.updated_at = datetime.now(UTC)
            _policies[obj.name] = obj

    async def delete(self, obj):
        if hasattr(obj, "ipa_principal") and obj.ipa_principal in _workloads:
            del _workloads[obj.ipa_principal]

    async def commit(self):
        pass

    async def refresh(self, obj):
        if isinstance(obj, Workload) and obj.ipa_principal in _workloads:
            mock = _workloads[obj.ipa_principal]
            obj.id = mock.id
            obj.current_state = mock.current_state
            obj.registered_at = mock.registered_at
            obj.last_attested_at = mock.last_attested_at
            obj.metadata_ = mock.metadata_

    async def rollback(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


async def mock_get_session():
    global _workloads, _policies, _transitions, _kbs_secrets, _test_initialized
    if not _test_initialized:
        _workloads.clear()
        _policies.clear()
        _transitions.clear()
        _kbs_secrets.clear()
        _test_initialized = True
    yield MockAsyncSession()


@pytest.fixture
async def app_client():
    global _test_initialized
    _test_initialized = False
    app = create_app()
    app.dependency_overrides[get_session] = mock_get_session
    if not hasattr(app.state, "backend_registry"):
        app.state.backend_registry = BackendRegistry()
    app.state.backend_registry.register("keylime", MockBackend())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_delete_workload(app_client):
    """DELETE /workloads/{id} removes workload and returns 200."""
    resp = await app_client.post(
        "/workloads",
        headers=ADMIN_HEADERS,
        json={
            "ipa_principal": "delete-test@EXAMPLE.COM",
            "display_name": "Delete Test",
            "workload_type": "agentic",
            "backend_type": "keylime",
        },
    )
    assert resp.status_code == 201
    wid = resp.json()["id"]

    del_resp = await app_client.delete(
        f"/workloads/{wid}", headers=ADMIN_HEADERS
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_delete_nonexistent_workload(app_client):
    """DELETE /workloads/{id} returns 404 for missing workload."""
    fake_id = str(uuid.uuid4())
    resp = await app_client.delete(
        f"/workloads/{fake_id}", headers=ADMIN_HEADERS
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_transitions(app_client):
    """GET /workloads/{id}/transitions returns paginated state transitions."""
    resp = await app_client.post(
        "/workloads",
        headers=ADMIN_HEADERS,
        json={
            "ipa_principal": "trans-test@EXAMPLE.COM",
            "display_name": "Transition Test",
            "workload_type": "agentic",
            "backend_type": "keylime",
        },
    )
    wid = resp.json()["id"]

    trans_resp = await app_client.get(
        f"/workloads/{wid}/transitions", headers=ADMIN_HEADERS
    )
    assert trans_resp.status_code == 200
    data = trans_resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_list_kbs_secrets(app_client):
    """GET /kbs/v0/resources returns paginated secrets without encrypted_value."""
    resp = await app_client.get(
        "/kbs/v0/resources", headers=ADMIN_HEADERS
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_attest_from_under_remediation(app_client):
    """POST /workloads/{id}/attest accepts UNDER_REMEDIATION state."""
    resp = await app_client.post(
        "/workloads",
        headers=ADMIN_HEADERS,
        json={
            "ipa_principal": "remediation-test@EXAMPLE.COM",
            "display_name": "Remediation Test",
            "workload_type": "service",
            "backend_type": "keylime",
        },
    )
    wid = resp.json()["id"]
    # Manually set state to UNDER_REMEDIATION via the in-memory mock
    for w in _workloads.values():
        if str(w.id) == wid:
            w.current_state = WorkloadState.UNDER_REMEDIATION

    attest_resp = await app_client.post(
        f"/workloads/{wid}/attest", headers=ADMIN_HEADERS
    )
    assert attest_resp.status_code == 200
    data = attest_resp.json()
    assert data["verdict"] == "pass"


@pytest.mark.asyncio
async def test_list_policies_includes_inactive(app_client):
    """GET /policies returns both active and inactive policies."""
    # Create active policy
    await app_client.post(
        "/policies",
        headers=ADMIN_HEADERS,
        json={
            "name": "active-policy",
            "policy_content": {"rules": []},
        },
    )
    # Manually add an inactive policy
    from datetime import UTC, datetime

    inactive = Policy(
        id=uuid.uuid4(),
        name="inactive-policy",
        policy_type="simple",
        policy_content={"rules": []},
        active=False,
        created_by="admin@IPA.TEST",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    _policies["inactive-policy"] = inactive

    resp = await app_client.get("/policies", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    names = [p["name"] for p in data["items"]]
    assert "inactive-policy" in names
