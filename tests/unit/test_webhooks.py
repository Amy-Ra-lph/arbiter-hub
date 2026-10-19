import uuid


def test_webhook_hmac_signature():
    from server.api.webhooks import compute_hmac_signature

    sig = compute_hmac_signature(b'{"test": true}', "secret123")
    assert sig.startswith("sha256=")
    assert len(sig) == 71


def test_webhook_hmac_deterministic():
    from server.api.webhooks import compute_hmac_signature

    a = compute_hmac_signature(b"same", "key")
    b = compute_hmac_signature(b"same", "key")
    assert a == b


def test_webhook_hmac_different_secrets():
    from server.api.webhooks import compute_hmac_signature

    a = compute_hmac_signature(b"data", "key1")
    b = compute_hmac_signature(b"data", "key2")
    assert a != b


def test_build_webhook_payload():
    from server.api.webhooks import build_webhook_payload

    payload = build_webhook_payload(
        event_type="state_transition",
        workload_id=uuid.uuid4(),
        from_state="healthy",
        to_state="failed",
        detail={"rule": "test"},
    )
    assert payload["event_type"] == "state_transition"
    assert "workload_id" in payload
    assert "from_state" in payload
    assert "to_state" in payload
    assert "timestamp" in payload
    assert "detail" in payload
