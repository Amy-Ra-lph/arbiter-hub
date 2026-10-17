from importlib.metadata import entry_points
from typing import Any


class PluginRegistry:
    def __init__(self):
        self.backends: dict[str, Any] = {}
        self.policy_engines: dict[str, Any] = {}
        self.event_handlers: dict[str, Any] = {}

    def register_backend(self, name: str, backend: Any) -> None:
        self.backends[name] = backend

    def register_policy_engine(self, name: str, engine: Any) -> None:
        self.policy_engines[name] = engine

    def register_event_handler(self, name: str, handler: Any) -> None:
        self.event_handlers[name] = handler


def load_entry_point_plugins(group: str) -> dict[str, Any]:
    discovered = {}
    eps = entry_points()
    group_eps = eps.select(group=group) if hasattr(eps, "select") else eps.get(group, [])
    for ep in group_eps:
        try:
            discovered[ep.name] = ep.load()
        except Exception:
            pass
    return discovered
