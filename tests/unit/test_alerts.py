import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from server.models.db import (
    WorkloadState,
    WorkloadType,
)


def _make_mock_workload(**overrides):
    w = MagicMock()
    w.id = overrides.get("id", uuid.uuid4())
    w.ipa_principal = overrides.get("ipa_principal", "agent-test@EXAMPLE.COM")
    w.display_name = overrides.get("display_name", "Test Agent")
    w.workload_type = overrides.get("workload_type", WorkloadType.AGENTIC)
    w.current_state = overrides.get("current_state", WorkloadState.HEALTHY)
    w.backend_types = overrides.get("backend_types", ["keylime", "falco"])
    w.stale_ttl_seconds = overrides.get("stale_ttl_seconds", 3600)
    w.metadata_ = overrides.get("metadata_", {"container_id": "abc123def"})
    return w


FALCO_ALERT = {
    "uuid": str(uuid.uuid4()),
    "output": "Warning Sensitive file opened for reading by non-trusted program",
    "priority": "Warning",
    "rule": "Read sensitive file untrusted",
    "time": "2026-10-19T12:00:00Z",
    "output_fields": {
        "container.id": "abc123def",
        "container.name": "test-agent",
        "evt.type": "openat",
        "fd.name": "/etc/shadow",
    },
}


@pytest.mark.asyncio
@patch("server.api.alerts.transition")
async def test_falco_alert_transitions_healthy_to_failed(mock_transition):
    from server.api.alerts import _handle_falco_alert

    workload = _make_mock_workload()
    mock_session = AsyncMock()

    result_scalars = MagicMock()
    result_scalars.all.return_value = [workload]
    mock_result = MagicMock()
    mock_result.scalars.return_value = result_scalars
    mock_session.execute.return_value = mock_result

    mock_transition.return_value = MagicMock()

    response = await _handle_falco_alert(FALCO_ALERT, mock_session)
    assert response["transitioned"] is True
    mock_transition.assert_called_once()
    call_args = mock_transition.call_args
    assert call_args[1]["justification"] or call_args[0][2] == WorkloadState.FAILED


@pytest.mark.asyncio
async def test_falco_alert_unknown_container():
    from server.api.alerts import _handle_falco_alert

    mock_session = AsyncMock()
    result_scalars = MagicMock()
    result_scalars.all.return_value = []
    mock_result = MagicMock()
    mock_result.scalars.return_value = result_scalars
    mock_session.execute.return_value = mock_result

    response = await _handle_falco_alert(FALCO_ALERT, mock_session)
    assert response["transitioned"] is False
    assert "no workload" in response["detail"]


@pytest.mark.asyncio
async def test_falco_alert_low_priority_no_transition():
    from server.api.alerts import _handle_falco_alert

    workload = _make_mock_workload()
    mock_session = AsyncMock()
    result_scalars = MagicMock()
    result_scalars.all.return_value = [workload]
    mock_result = MagicMock()
    mock_result.scalars.return_value = result_scalars
    mock_session.execute.return_value = mock_result

    low_alert = {**FALCO_ALERT, "priority": "Notice"}
    response = await _handle_falco_alert(low_alert, mock_session)
    assert response["transitioned"] is False
    assert workload.current_state == WorkloadState.HEALTHY
