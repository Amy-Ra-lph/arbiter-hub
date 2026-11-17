import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
API_UNITS = [
    REPO / "deploy/quadlet/arbiter-hub-api.container",
    REPO / "deploy/multi-node/arbiter-hub-api-2.container",
]


@pytest.mark.parametrize("unit", API_UNITS)
def test_api_unit_mounts_both_secrets(unit):
    text = unit.read_text()
    assert "Secret=arbiter-hub-db-password,type=mount,target=arbiter_db_password" in text
    assert (
        "Secret=arbiter-hub-admin-password,type=mount,target=arbiter_local_admin_password"
        in text
    )


@pytest.mark.parametrize("unit", API_UNITS)
def test_api_unit_has_no_password_env(unit):
    text = unit.read_text()
    assert not re.search(r"^Environment=\S*PASSWORD", text, re.MULTILINE)
    assert "ARBITER_DATABASE_URL" not in text
