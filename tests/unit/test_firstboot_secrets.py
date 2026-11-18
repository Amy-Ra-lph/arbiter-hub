import re
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2] / "deploy/bootc/server-firstboot.sh").read_text()


def test_umask_set_before_secret_writes():
    assert re.search(r"^umask 077$", SCRIPT, re.MULTILINE)


def test_no_password_in_environment_lines():
    assert not re.search(r"^Environment=\S*PASSWORD", SCRIPT, re.MULTILINE)
    assert "DB_PASSWORD_URLENC" not in SCRIPT


def test_secret_helpers_present_and_idempotent():
    assert "ensure_secret_file()" in SCRIPT
    assert "ensure_podman_secret()" in SCRIPT
    assert "podman secret inspect" in SCRIPT


def test_migration_does_not_pass_dsn_on_argv():
    assert "ALEMBIC_DB_URL=" not in SCRIPT
    assert "target=ALEMBIC_DB_PASSWORD" in SCRIPT


def test_dropins_are_private():
    assert re.search(r"chmod 600 .*arbiter-hub-api\.container\.d", SCRIPT)


def test_resets_failed_container_units_before_start():
    """Containers may have hit the start-rate limiter before secrets existed."""
    assert "systemctl reset-failed arbiter-hub-db arbiter-hub-api arbiter-hub-mcp" in SCRIPT
