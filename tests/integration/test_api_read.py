import pytest
import uuid
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from server.main import create_app
from server.models.db import get_session


# Mock async session that returns empty results
class MockAsyncSession:
    async def execute(self, stmt):
        result = MagicMock()
        result.scalar_one = lambda: 0
        result.scalar_one_or_none = lambda: None
        result.scalars = lambda: []
        return result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


async def mock_get_session():
    """Mock database session for testing without real database"""
    yield MockAsyncSession()


@pytest.fixture
async def app_client():
    """Test client with mocked database"""
    app = create_app()
    # Override database session with mock
    app.dependency_overrides[get_session] = mock_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health_endpoint(app_client):
    """Test health endpoint returns service status"""
    resp = await app_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "arbiter-hub"
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_backends_health(app_client):
    """Test backends endpoint returns backend health (empty registry)"""
    resp = await app_client.get("/backends")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert data == {}


@pytest.mark.asyncio
async def test_list_workloads_empty(app_client):
    """Test workloads list returns empty result with mock database"""
    headers = {
        "X-Caller-Principal": "admin@IPA.TEST",
        "X-Caller-Type": "admin",
        "X-Caller-Roles": "attestation-admin",
        "X-Caller-Scopes": "*",
    }
    resp = await app_client.get("/workloads", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_workload_not_found(app_client):
    """Test requesting nonexistent workload returns 404"""
    headers = {
        "X-Caller-Principal": "admin@IPA.TEST",
        "X-Caller-Type": "admin",
        "X-Caller-Roles": "attestation-admin",
        "X-Caller-Scopes": "*",
    }
    resp = await app_client.get(f"/workloads/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404
    data = resp.json()
    assert data["detail"] == "workload not found"


@pytest.mark.asyncio
async def test_list_policies_empty(app_client):
    """Test policies list returns empty result"""
    headers = {
        "X-Caller-Principal": "admin@IPA.TEST",
        "X-Caller-Type": "admin",
        "X-Caller-Roles": "attestation-admin",
        "X-Caller-Scopes": "*",
    }
    resp = await app_client.get("/policies", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["items"] == []


@pytest.mark.asyncio
async def test_audit_log_empty(app_client):
    """Test audit log returns empty result"""
    headers = {
        "X-Caller-Principal": "admin@IPA.TEST",
        "X-Caller-Type": "admin",
        "X-Caller-Roles": "attestation-admin",
        "X-Caller-Scopes": "*",
    }
    resp = await app_client.get("/audit", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["items"] == []


@pytest.mark.asyncio
async def test_workload_attestations_not_found(app_client):
    """Test workload attestations for nonexistent workload returns 404"""
    headers = {
        "X-Caller-Principal": "admin@IPA.TEST",
        "X-Caller-Type": "admin",
        "X-Caller-Roles": "attestation-admin",
        "X-Caller-Scopes": "*",
    }
    resp = await app_client.get(f"/workloads/{uuid.uuid4()}/attestations", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_workloads_pagination():
    """Test workloads endpoint respects pagination parameters"""
    app = create_app()
    app.dependency_overrides[get_session] = mock_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {
            "X-Caller-Principal": "admin@IPA.TEST",
            "X-Caller-Type": "admin",
            "X-Caller-Roles": "attestation-admin",
            "X-Caller-Scopes": "*",
        }
        resp = await client.get("/workloads?startIndex=10&count=50", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["start_index"] == 10
        assert data["count"] == 50
