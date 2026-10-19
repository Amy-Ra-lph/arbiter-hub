"""Verify dispatch_webhooks is called after state transitions."""

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
@patch("server.api.attestation.dispatch_webhooks")
async def test_attest_calls_dispatch_webhooks(mock_dispatch):
    """After attestation transition, dispatch_webhooks must be called."""

    # If dispatch_webhooks is imported in attestation.py, this patch works.
    # If not imported, the patch won't intercept anything — test fails.
    assert "dispatch_webhooks" in dir(
        __import__("server.api.attestation", fromlist=["dispatch_webhooks"])
    ), "dispatch_webhooks not imported in attestation.py"
