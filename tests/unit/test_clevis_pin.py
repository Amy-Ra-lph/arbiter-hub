# tests/unit/test_clevis_pin.py
import pytest
import json
import subprocess
import os

SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "clevis-pin", "clevis-pin-arbiter")


def test_pin_script_exists():
    assert os.path.exists(SCRIPT_PATH)


def test_pin_rejects_missing_url():
    result = subprocess.run(
        ["python3", SCRIPT_PATH],
        input=json.dumps({}),
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "url" in result.stderr.lower()


def test_pin_rejects_missing_workload():
    result = subprocess.run(
        ["python3", SCRIPT_PATH],
        input=json.dumps({"url": "https://localhost:8400"}),
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "workload" in result.stderr.lower()
