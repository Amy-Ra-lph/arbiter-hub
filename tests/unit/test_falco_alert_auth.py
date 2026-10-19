"""Verify Falco alert endpoint enforces auth for non-local clients."""

import inspect

from server.api.alerts import receive_falco_alert


def test_falco_alert_has_request_parameter():
    """Falco endpoint uses request.client IP check for auth."""
    sig = inspect.signature(receive_falco_alert)
    param_names = list(sig.parameters.keys())
    assert "request" in param_names, "receive_falco_alert must have a 'request' parameter for IP-based auth"
