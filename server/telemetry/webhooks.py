import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml

log = logging.getLogger(__name__)


@dataclass
class WebhookConfig:
    name: str
    url: str
    events: list[str]
    format: str = "ocsf"
    auth: str | None = None
    secret: str | None = None
    retry: int = 3


class WebhookDelivery:
    def __init__(self, configs: list[WebhookConfig]):
        self._configs = configs

    @classmethod
    def from_yaml(cls, path: str) -> "WebhookDelivery":
        p = Path(path)
        if not p.exists():
            return cls([])
        with open(p) as f:
            data = yaml.safe_load(f) or {}
        configs = []
        for wh in data.get("webhooks", []):
            configs.append(WebhookConfig(**wh))
        return cls(configs)

    async def deliver(self, event_type: str, payload: dict) -> None:
        matching = [c for c in self._configs if event_type in c.events]
        if not matching:
            return
        tasks = [self._send(cfg, payload) for cfg in matching]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _send(self, config: WebhookConfig, payload: dict) -> None:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if config.auth == "bearer_token" and config.secret:
            headers["Authorization"] = f"Bearer {config.secret}"

        for attempt in range(config.retry):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(config.url, json=payload, headers=headers)
                    resp.raise_for_status()
                    return
            except Exception as e:
                log.warning(
                    "Webhook %s delivery attempt %d failed: %s",
                    config.name,
                    attempt + 1,
                    e,
                )
                if attempt < config.retry - 1:
                    await asyncio.sleep(2**attempt)
        log.error("Webhook %s delivery failed after %d attempts", config.name, config.retry)
