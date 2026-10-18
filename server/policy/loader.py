from pathlib import Path

import yaml


def load_policies(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    with open(p) as f:
        data = yaml.safe_load(f)
    return data.get("policies", []) if data else []
