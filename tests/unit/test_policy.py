import pytest
from server.policy.engine import SimpleRulesEngine


@pytest.fixture
def engine():
    policies = [
        {
            "name": "kbs-secret-release",
            "rules": [
                {
                    "action": "kbs_release",
                    "require": {
                        "workload_state": "healthy",
                        "attestation_age_max": 3600,
                    },
                }
            ],
            "obligations": ["log_to_rekor"],
        },
        {
            "name": "agent-reattest-request",
            "rules": [
                {
                    "action": "request_reattest",
                    "require": {
                        "caller_role": "attestation-agent",
                        "caller_scope_includes_target": True,
                        "target_state": ["stale", "failed"],
                    },
                }
            ],
            "obligations": [],
        },
    ]
    return SimpleRulesEngine(policies)


@pytest.mark.asyncio
async def test_kbs_release_allowed_when_healthy(engine):
    decision = await engine.evaluate(
        subject="pipeline-1",
        action="kbs_release",
        resource="workload-1",
        context={"workload_state": "healthy", "attestation_age": 100},
    )
    assert decision.allowed is True
    assert "log_to_rekor" in decision.obligations


@pytest.mark.asyncio
async def test_kbs_release_denied_when_failed(engine):
    decision = await engine.evaluate(
        subject="pipeline-1",
        action="kbs_release",
        resource="workload-1",
        context={"workload_state": "failed", "attestation_age": 100},
    )
    assert decision.allowed is False


@pytest.mark.asyncio
async def test_kbs_release_denied_when_attestation_stale(engine):
    decision = await engine.evaluate(
        subject="pipeline-1",
        action="kbs_release",
        resource="workload-1",
        context={"workload_state": "healthy", "attestation_age": 7200},
    )
    assert decision.allowed is False


@pytest.mark.asyncio
async def test_agent_reattest_allowed_when_scoped(engine):
    decision = await engine.evaluate(
        subject="agent-foo",
        action="request_reattest",
        resource="workload-1",
        context={
            "caller_role": "attestation-agent",
            "caller_scope_includes_target": True,
            "target_state": "stale",
        },
    )
    assert decision.allowed is True


@pytest.mark.asyncio
async def test_agent_reattest_denied_when_not_scoped(engine):
    decision = await engine.evaluate(
        subject="agent-foo",
        action="request_reattest",
        resource="workload-1",
        context={
            "caller_role": "attestation-agent",
            "caller_scope_includes_target": False,
            "target_state": "stale",
        },
    )
    assert decision.allowed is False


@pytest.mark.asyncio
async def test_unknown_action_denied(engine):
    decision = await engine.evaluate(
        subject="anyone",
        action="delete_everything",
        resource="workload-1",
        context={},
    )
    assert decision.allowed is False
    assert "no matching policy" in decision.reason.lower()
