from server.telemetry.metrics import ATTESTATION_COUNTER, STATE_TRANSITION_COUNTER
from server.telemetry.ocsf import OCSFEventFormatter


def test_ocsf_security_finding_format():
    formatter = OCSFEventFormatter()
    event = formatter.format_security_finding(
        workload_id="wl-123",
        finding_type="attestation_failure",
        severity="high",
        detail={"backend": "keylime", "reason": "IMA mismatch"},
    )
    assert event["class_uid"] == 2001
    assert event["category_uid"] == 2
    assert event["severity_id"] >= 1
    assert "wl-123" in str(event)


def test_ocsf_entity_management_format():
    formatter = OCSFEventFormatter()
    event = formatter.format_entity_management(
        entity_type="workload",
        entity_id="wl-123",
        action="state_transition",
        detail={"from": "healthy", "to": "stale"},
        actor="staleness_scheduler",
    )
    assert event["class_uid"] == 3004
    assert event["activity_id"] == 3  # update


def test_ocsf_api_activity_format():
    formatter = OCSFEventFormatter()
    event = formatter.format_api_activity(
        method="GET",
        path="/workloads",
        actor="admin@EXAMPLE.COM",
        status_code=200,
    )
    assert event["class_uid"] == 6003


def test_attestation_counter_exists():
    assert ATTESTATION_COUNTER is not None
    assert STATE_TRANSITION_COUNTER is not None
