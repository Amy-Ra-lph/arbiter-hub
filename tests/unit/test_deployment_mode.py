from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[2] / "deploy/bootc/server-firstboot.sh").read_text()


def test_mode_defaults_to_production():
    assert "ARBITER_DEPLOYMENT_MODE:-production" in SCRIPT


def test_production_refuses_demo_password():
    assert "Secret123!" in SCRIPT
    assert "refusing demo IPA admin password" in SCRIPT


def test_production_requires_sealed_credentials():
    assert "systemd-creds decrypt" in SCRIPT
    assert "missing sealed secret" in SCRIPT


def test_local_admin_disabled_in_production():
    assert "ARBITER_ALLOW_LOCAL_ADMIN" in SCRIPT
