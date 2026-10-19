"""Verify Falco alert endpoint requires authentication."""

import inspect

from server.api.alerts import receive_falco_alert


def test_falco_alert_has_auth_dependency():
    sig = inspect.signature(receive_falco_alert)
    param_names = list(sig.parameters.keys())
    assert "caller" in param_names, (
        "receive_falco_alert must have a 'caller' parameter for auth"
    )
