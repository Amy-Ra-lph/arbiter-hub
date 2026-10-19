import sys
from pathlib import Path

import pytest

from server.api.webhooks import compute_hmac_signature

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eda"))

aiohttp = pytest.importorskip("aiohttp")


def test_eda_source_validates_hmac():
    from plugins.event_source.arbiter_hub import validate_hmac

    body = b'{"event_type": "state_transition"}'
    secret = "test-secret"
    sig = compute_hmac_signature(body, secret)
    assert validate_hmac(body, sig, secret) is True
    assert validate_hmac(body, "sha256=wrong", secret) is False


def test_eda_source_validates_hmac_empty_body():
    from plugins.event_source.arbiter_hub import validate_hmac

    body = b""
    secret = "key"
    sig = compute_hmac_signature(body, secret)
    assert validate_hmac(body, sig, secret) is True
