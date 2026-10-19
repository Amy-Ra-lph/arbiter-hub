"""Verify cosign backend only registers when public_key is set."""

import re
import inspect

from server.main import lifespan


def test_cosign_guard_uses_public_key_not_binary():
    source = inspect.getsource(lifespan)
    # Find the if-guard line for cosign registration
    lines = source.split("\n")
    guard_line = None
    for line in lines:
        if "cosign" in line.lower() and "if " in line and "settings." in line:
            guard_line = line.strip()
            break
    assert guard_line is not None, "No cosign guard found in lifespan"
    assert "cosign_public_key" in guard_line, (
        f"Cosign guard should check cosign_public_key, not cosign_binary. "
        f"Found: {guard_line}"
    )
