import pytest

from server.db_url import build_dsn


def test_encodes_base64_password():
    assert build_dsn("a/b+c=") == (
        "postgresql+asyncpg://arbiter:a%2Fb%2Bc%3D@arbiter-hub-db:5432/arbiter"
    )


def test_defaults():
    assert build_dsn("pw") == ("postgresql+asyncpg://arbiter:pw@arbiter-hub-db:5432/arbiter")


def test_rejects_empty_password():
    with pytest.raises(ValueError):
        build_dsn("")
