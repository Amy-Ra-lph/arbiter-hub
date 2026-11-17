from server.config import Settings


def test_admin_password_from_secret_file(tmp_path):
    (tmp_path / "arbiter_local_admin_password").write_text("s3cret", encoding="utf-8")
    settings = Settings(_secrets_dir=str(tmp_path))
    assert settings.local_admin_password.get_secret_value() == "s3cret"


def test_empty_admin_password_is_empty_string(tmp_path):
    settings = Settings(_secrets_dir=str(tmp_path))
    assert settings.local_admin_password.get_secret_value() == ""


def test_admin_password_not_in_repr(tmp_path):
    (tmp_path / "arbiter_local_admin_password").write_text("s3cret", encoding="utf-8")
    settings = Settings(_secrets_dir=str(tmp_path))
    assert "s3cret" not in repr(settings)
