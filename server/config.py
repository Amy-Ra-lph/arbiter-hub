from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://arbiter:arbiter@localhost:5432/arbiter"
    api_host: str = "0.0.0.0"
    api_port: int = 8400
    kbs_port: int = 8085
    mcp_port: int = 8401

    keylime_verifier_url: str = ""
    keylime_ca_cert: str = ""
    keylime_client_cert: str = ""
    keylime_client_key: str = ""

    trustee_url: str = ""
    cosign_binary: str = "cosign"
    rekor_url: str = ""

    oidc_issuer: str = ""
    oidc_client_id: str = "arbiter-hub"
    oidc_audience: str = "arbiter-hub"

    kbs_encryption_key_file: str = "/etc/arbiter/kbs.key"
    policy_file: str = "/etc/arbiter/policies.yaml"
    webhook_config_file: str = "/etc/arbiter/webhooks.yaml"

    stale_check_interval_seconds: int = 60
    default_stale_ttl_seconds: int = 3600

    otel_exporter_endpoint: str = ""
    otel_service_name: str = "arbiter-hub"

    model_config = {"env_prefix": "ARBITER_"}


settings = Settings()
