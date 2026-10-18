"""Test configuration and basic setup."""

import pytest
from server.config import Settings
from server.main import create_app


def test_settings_defaults():
    """Test that settings have correct default values."""
    settings = Settings()
    assert settings.api_port == 8400
    assert settings.kbs_port == 8085
    assert settings.mcp_port == 8401
    assert settings.otel_service_name == "arbiter-hub"


def test_settings_env_prefix():
    """Test that settings use ARBITER_ env prefix."""
    settings = Settings()
    assert settings.model_config["env_prefix"] == "ARBITER_"


def test_create_app():
    """Test that app factory creates a FastAPI instance."""
    app = create_app()
    assert app.title == "Arbiter Hub"
    assert app.version == "0.1.0"
    assert app.description == "Federation hub for workload attestation"


@pytest.mark.asyncio
async def test_app_with_client(client):
    """Test that async client fixture works."""
    # Just verify we can get a 404 on a non-existent route
    # This proves the app is running and the client fixture works
    response = await client.get("/nonexistent")
    assert response.status_code == 404
