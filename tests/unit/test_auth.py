import pytest

from server.auth.models import CallerIdentity
from server.auth.rbac import check_permission, check_scope


def test_admin_can_do_everything():
    identity = CallerIdentity(
        principal="admin@EXAMPLE.COM",
        actor_type="admin",
        roles=["attestation-admin"],
        scopes=["*"],
    )
    assert check_permission(identity, "register_workload") is True
    assert check_permission(identity, "revoke_workload") is True
    assert check_permission(identity, "create_policy") is True


def test_pipeline_can_attest_but_not_revoke():
    identity = CallerIdentity(
        principal="pipeline@EXAMPLE.COM",
        actor_type="pipeline",
        roles=["attestation-pipeline"],
        scopes=["*"],
    )
    assert check_permission(identity, "trigger_attestation") is True
    assert check_permission(identity, "sign_artifact") is True
    assert check_permission(identity, "revoke_workload") is False


def test_agent_is_read_only_plus_reattest():
    identity = CallerIdentity(
        principal="agent-foo@EXAMPLE.COM",
        actor_type="agent",
        roles=["attestation-agent"],
        scopes=["agent-foo"],
    )
    assert check_permission(identity, "read_workload") is True
    assert check_permission(identity, "request_reattest") is True
    assert check_permission(identity, "register_workload") is False
    assert check_permission(identity, "revoke_workload") is False


def test_viewer_read_only():
    identity = CallerIdentity(
        principal="viewer@EXAMPLE.COM",
        actor_type="admin",
        roles=["attestation-viewer"],
        scopes=["*"],
    )
    assert check_permission(identity, "read_workload") is True
    assert check_permission(identity, "trigger_attestation") is False


def test_scope_check_wildcard():
    identity = CallerIdentity(
        principal="admin@EXAMPLE.COM",
        actor_type="admin",
        roles=["attestation-admin"],
        scopes=["*"],
    )
    assert check_scope(identity, "any-workload-scope") is True


def test_scope_check_specific():
    identity = CallerIdentity(
        principal="agent-foo@EXAMPLE.COM",
        actor_type="agent",
        roles=["attestation-agent"],
        scopes=["agent-foo"],
    )
    assert check_scope(identity, "agent-foo") is True
    assert check_scope(identity, "agent-bar") is False


def test_auth_mode_defaults_to_dev():
    from server.auth.dependencies import _resolve_auth_mode

    assert _resolve_auth_mode(auth_mode="dev", dev_mode_legacy=False) == "dev"


def test_dev_mode_legacy_sets_auth_mode_dev():
    from server.auth.dependencies import _resolve_auth_mode

    assert _resolve_auth_mode(auth_mode="", dev_mode_legacy=True) == "dev"


def test_auth_mode_overrides_dev_mode():
    from server.auth.dependencies import _resolve_auth_mode

    assert _resolve_auth_mode(auth_mode="oidc", dev_mode_legacy=True) == "oidc"


def test_auth_mode_proxy():
    from server.auth.dependencies import _resolve_auth_mode

    assert _resolve_auth_mode(auth_mode="proxy", dev_mode_legacy=False) == "proxy"


@pytest.mark.asyncio
async def test_auth_config_endpoint():
    from httpx import ASGITransport, AsyncClient

    from server.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/auth/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "auth_mode" in data
        assert "client_id" in data
        assert "issuer" in data
