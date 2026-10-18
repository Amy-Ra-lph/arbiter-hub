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
