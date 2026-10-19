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
    rhtas_fulcio_url: str = ""
    rhtas_tuf_root: str = ""

    auth_mode: str = "dev"

    oidc_issuer: str = ""
    oidc_client_id: str = "arbiter-hub"
    oidc_audience: str = "arbiter-hub"
    oidc_principal_claim: str = "sub"
    oidc_role_claim: str = "realm_access.roles"
    oidc_scope_claim: str = "scope"
    oidc_role_prefix: str = ""
    oidc_jwks_cache_ttl: int = 3600
    oidc_actor_type_claim: str = ""
    oidc_scopes: str = "openid profile"

    kbs_encryption_key_file: str = "/etc/arbiter/kbs.key"
    policy_file: str = "/etc/arbiter/policies.yaml"
    webhook_config_file: str = "/etc/arbiter/webhooks.yaml"

    stale_check_interval_seconds: int = 60
    default_stale_ttl_seconds: int = 3600

    cors_allowed_origins: list[str] = []

    otel_exporter_endpoint: str = ""
    otel_service_name: str = "arbiter-hub"

    model_config = {"env_prefix": "ARBITER_"}


settings = Settings()
