import pytest
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from server.main import create_app
from server.models.db import get_session, Workload, WorkloadState, WorkloadType, BackendType, Policy, AttestationVerdict
from server.backends.base import AttestationResult, BackendRegistry, AttestationBackend


# Simple mock workload object that Pydantic can serialize
@dataclass
class MockWorkload:
    ipa_principal: str
    display_name: str
    workload_type: WorkloadType
    backend_type: BackendType
    stale_ttl_seconds: int
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    current_state: WorkloadState = WorkloadState.REGISTERED
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_attested_at: datetime | None = None
    metadata_: dict = field(default_factory=dict)

    # Property to map metadata to metadata_ for Pydantic
    @property
    def metadata(self):
        return self.metadata_


# In-memory storage for tests
test_workloads = {}
test_policies = {}


class MockAsyncSession:
    """Mock session that stores data in memory for testing writes"""

    def __init__(self):
        self.added = []

    async def execute(self, stmt):
        """Mock execute that handles queries"""
        result = MagicMock()

        # Try to extract the WHERE clause to check for specific queries
        # This is a simplified approach that works for basic queries
        stmt_str = str(stmt)

        # Check if querying for a workload by principal
        if "workloads.ipa_principal" in stmt_str:
            # Extract principal from the query (simplified parsing)
            for principal, workload in test_workloads.items():
                if principal in stmt_str or f"'{principal}'" in stmt_str:
                    result.scalar_one_or_none = lambda w=workload: w
                    return result

        # Check if querying for workload by ID
        if "workloads.id" in stmt_str and test_workloads:
            # Return first matching workload (simplified)
            for workload in test_workloads.values():
                result.scalar_one_or_none = lambda w=workload: w
                return result

        # Default: return None (not found)
        result.scalar_one_or_none = lambda: None
        result.scalar_one = lambda: 0
        result.scalars = lambda: []
        return result

    def add(self, obj):
        """Mock add that tracks added objects"""
        from datetime import datetime, timezone
        self.added.append(obj)
        if isinstance(obj, Workload):
            # Convert SQLAlchemy Workload to simple mock for testing
            mock_obj = MockWorkload(
                id=obj.id if hasattr(obj, 'id') and obj.id else uuid.uuid4(),
                ipa_principal=obj.ipa_principal,
                display_name=obj.display_name,
                workload_type=obj.workload_type,
                backend_type=obj.backend_type,
                stale_ttl_seconds=obj.stale_ttl_seconds,
                current_state=obj.current_state if hasattr(obj, 'current_state') and obj.current_state else WorkloadState.REGISTERED,
                registered_at=obj.registered_at if hasattr(obj, 'registered_at') and obj.registered_at else datetime.now(timezone.utc),
                last_attested_at=obj.last_attested_at if hasattr(obj, 'last_attested_at') else None,
                metadata_=obj.metadata_ if hasattr(obj, 'metadata_') and obj.metadata_ else {},
            )
            # Update the original object with generated values for the endpoint to use
            obj.id = mock_obj.id
            obj.current_state = mock_obj.current_state
            obj.registered_at = mock_obj.registered_at
            if not obj.metadata_:
                obj.metadata_ = {}
            test_workloads[obj.ipa_principal] = mock_obj
        elif isinstance(obj, Policy):
            if not hasattr(obj, 'id') or obj.id is None:
                obj.id = uuid.uuid4()
            if not hasattr(obj, 'active') or obj.active is None:
                obj.active = True
            if not hasattr(obj, 'created_at') or obj.created_at is None:
                obj.created_at = datetime.now(timezone.utc)
            if not hasattr(obj, 'updated_at') or obj.updated_at is None:
                obj.updated_at = datetime.now(timezone.utc)
            test_policies[obj.name] = obj

    async def commit(self):
        """Mock commit"""
        pass

    async def refresh(self, obj):
        """Mock refresh - copy values from stored mock back to obj"""
        if isinstance(obj, Workload) and hasattr(obj, 'ipa_principal') and obj.ipa_principal in test_workloads:
            mock = test_workloads[obj.ipa_principal]
            obj.id = mock.id
            obj.current_state = mock.current_state
            obj.registered_at = mock.registered_at
            obj.last_attested_at = mock.last_attested_at
            obj.metadata_ = mock.metadata_
            # Add a metadata property that Pydantic can use
            if not hasattr(obj.__class__, '_test_metadata_property_added'):
                # Add property dynamically to avoid SQLAlchemy Base.metadata conflict
                obj.__class__.metadata = property(lambda self: self.metadata_)
                obj.__class__._test_metadata_property_added = True
        elif isinstance(obj, Policy) and hasattr(obj, 'name') and obj.name in test_policies:
            stored = test_policies[obj.name]
            obj.id = stored.id
            obj.active = stored.active
            obj.created_at = stored.created_at
            obj.updated_at = stored.updated_at

    async def rollback(self):
        """Mock rollback"""
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


_test_initialized = False

async def mock_get_session():
    """Mock database session for testing"""
    global test_workloads, test_policies, _test_initialized
    # Only clear once per test fixture, not on every request
    if not _test_initialized:
        test_workloads.clear()
        test_policies.clear()
        _test_initialized = True
    yield MockAsyncSession()


class MockBackend:
    """Mock attestation backend for testing"""

    async def verify(self, workload):
        return AttestationResult(
            verdict=AttestationVerdict.PASS,
            backend="keylime",
            evidence_hash="mock_hash_123",
            detail={"test": "data"},
        )

    async def enroll(self, workload, policy):
        return MagicMock(success=True, backend="keylime")

    async def revoke(self, workload):
        return MagicMock(success=True, backend="keylime")

    async def health(self):
        return MagicMock(healthy=True, backend="keylime")


@pytest.fixture
async def app_client():
    """Test client with mocked database and backends"""
    global _test_initialized
    _test_initialized = False  # Reset for each test
    app = create_app()
    # Override database session with mock
    app.dependency_overrides[get_session] = mock_get_session
    # Initialize backend registry (normally done by lifespan)
    if not hasattr(app.state, 'backend_registry'):
        app.state.backend_registry = BackendRegistry()
    # Register mock backend
    app.state.backend_registry.register("keylime", MockBackend())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_register_workload(app_client):
    headers = {
        "X-Caller-Principal": "admin@IPA.TEST",
        "X-Caller-Type": "admin",
        "X-Caller-Roles": "attestation-admin",
        "X-Caller-Scopes": "*",
    }
    resp = await app_client.post("/workloads", headers=headers, json={
        "ipa_principal": "agent-test@EXAMPLE.COM",
        "display_name": "Test Agent",
        "workload_type": "agentic",
        "backend_type": "keylime",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["current_state"] == "registered"
    assert data["ipa_principal"] == "agent-test@EXAMPLE.COM"


@pytest.mark.asyncio
async def test_register_duplicate_principal_fails(app_client):
    headers = {
        "X-Caller-Principal": "admin@IPA.TEST",
        "X-Caller-Type": "admin",
        "X-Caller-Roles": "attestation-admin",
        "X-Caller-Scopes": "*",
    }
    await app_client.post("/workloads", headers=headers, json={
        "ipa_principal": "dup@EXAMPLE.COM",
        "display_name": "Dup 1",
        "workload_type": "agentic",
        "backend_type": "keylime",
    })
    resp = await app_client.post("/workloads", headers=headers, json={
        "ipa_principal": "dup@EXAMPLE.COM",
        "display_name": "Dup 2",
        "workload_type": "agentic",
        "backend_type": "keylime",
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_revoke_requires_justification(app_client):
    headers = {
        "X-Caller-Principal": "admin@IPA.TEST",
        "X-Caller-Type": "admin",
        "X-Caller-Roles": "attestation-admin",
        "X-Caller-Scopes": "*",
    }
    create_resp = await app_client.post("/workloads", headers=headers, json={
        "ipa_principal": "revoke-test@EXAMPLE.COM",
        "display_name": "Revoke Test",
        "workload_type": "service",
        "backend_type": "keylime",
    })
    wid = create_resp.json()["id"]
    resp = await app_client.post(f"/workloads/{wid}/revoke", headers=headers, json={})
    assert resp.status_code == 422  # missing justification


@pytest.mark.asyncio
async def test_create_policy(app_client):
    headers = {
        "X-Caller-Principal": "admin@IPA.TEST",
        "X-Caller-Type": "admin",
        "X-Caller-Roles": "attestation-admin",
        "X-Caller-Scopes": "*",
    }
    resp = await app_client.post("/policies", headers=headers, json={
        "name": "test-policy",
        "policy_content": {"rules": [{"action": "test", "require": {}}]},
    })
    assert resp.status_code == 201
    assert resp.json()["name"] == "test-policy"


class UnavailableBackend:
    """Mock backend that returns UNAVAILABLE verdict."""

    async def verify(self, workload):
        return AttestationResult(
            verdict=AttestationVerdict.UNAVAILABLE,
            backend="keylime",
            evidence_hash="",
            detail={"error": "verifier unreachable"},
        )

    async def enroll(self, workload, policy):
        return MagicMock(success=True, backend="keylime")

    async def revoke(self, workload):
        return MagicMock(success=True, backend="keylime")

    async def health(self):
        return MagicMock(healthy=False, backend="keylime")


@pytest.fixture
async def app_client_unavailable():
    """Test client with backend that returns UNAVAILABLE."""
    global _test_initialized
    _test_initialized = False
    app = create_app()
    app.dependency_overrides[get_session] = mock_get_session
    if not hasattr(app.state, 'backend_registry'):
        app.state.backend_registry = BackendRegistry()
    app.state.backend_registry.register("keylime", UnavailableBackend())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_attest_workload_pass(app_client):
    """Review Focus #1: attest endpoint transitions REGISTERED → HEALTHY on PASS."""
    headers = {
        "X-Caller-Principal": "admin@IPA.TEST",
        "X-Caller-Type": "admin",
        "X-Caller-Roles": "attestation-admin",
        "X-Caller-Scopes": "*",
    }
    create_resp = await app_client.post("/workloads", headers=headers, json={
        "ipa_principal": "attest-pass@EXAMPLE.COM",
        "display_name": "Attest Pass Test",
        "workload_type": "agentic",
        "backend_type": "keylime",
    })
    assert create_resp.status_code == 201
    wid = create_resp.json()["id"]

    resp = await app_client.post(f"/workloads/{wid}/attest", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "pass"
    assert data["state"] == "healthy"


@pytest.mark.asyncio
async def test_attest_unavailable_stays_in_state(app_client_unavailable):
    """Review Focus #5: UNAVAILABLE != FAIL — workload stays in current state."""
    headers = {
        "X-Caller-Principal": "admin@IPA.TEST",
        "X-Caller-Type": "admin",
        "X-Caller-Roles": "attestation-admin",
        "X-Caller-Scopes": "*",
    }
    create_resp = await app_client_unavailable.post("/workloads", headers=headers, json={
        "ipa_principal": "attest-unavail@EXAMPLE.COM",
        "display_name": "Attest Unavailable Test",
        "workload_type": "agentic",
        "backend_type": "keylime",
    })
    assert create_resp.status_code == 201
    wid = create_resp.json()["id"]

    resp = await app_client_unavailable.post(f"/workloads/{wid}/attest", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "unavailable"
    # CRITICAL: workload must NOT transition to failed
    assert data["state"] != "failed"
    assert "message" in data
