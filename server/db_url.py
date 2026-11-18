"""Build the asyncpg DSN from components.

The password is percent-encoded here so callers never assemble a URL by
string interpolation — base64 passwords contain '/', '+', and '=', which are
illegal in URL userinfo.
"""

from urllib.parse import quote


def build_dsn(
    password: str,
    user: str = "arbiter",
    host: str = "arbiter-hub-db",
    port: int = 5432,
    database: str = "arbiter",
) -> str:
    if not password:
        raise ValueError("db password is empty")
    encoded = quote(password, safe="")
    return f"postgresql+asyncpg://{user}:{encoded}@{host}:{port}/{database}"
