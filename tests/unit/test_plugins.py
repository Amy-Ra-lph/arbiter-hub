from server.plugins.loader import PluginRegistry, load_entry_point_plugins
from server.telemetry.webhooks import WebhookConfig, WebhookDelivery


def test_plugin_registry():
    registry = PluginRegistry()
    registry.register_event_handler("test", lambda: None)
    assert "test" in registry.event_handlers


def test_load_entry_points_returns_list():
    result = load_entry_point_plugins("arbiter_hub.backends")
    assert isinstance(result, dict)


def test_webhook_config_parse():
    cfg = WebhookConfig(
        name="test-hook",
        url="https://example.com/events",
        events=["attestation_failed"],
        format="ocsf",
        retry=3,
    )
    assert cfg.name == "test-hook"
    assert cfg.retry == 3


def test_webhook_delivery_init():
    configs = [
        WebhookConfig(
            name="siem",
            url="https://siem.example.com",
            events=["attestation_failed", "workload_revoked"],
            format="ocsf",
            retry=2,
        )
    ]
    delivery = WebhookDelivery(configs)
    assert len(delivery._configs) == 1
