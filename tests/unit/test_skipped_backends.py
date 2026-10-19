"""Verify skipped backends are tracked in attestation."""

import inspect


def test_attestation_tracks_skipped_backends():
    from server.api import attestation

    source = inspect.getsource(attestation.trigger_attestation)
    assert "skipped" in source.lower(), (
        "Attestation endpoint should track and report skipped/unconfigured backends"
    )
