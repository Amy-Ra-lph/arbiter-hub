"""EDA source plugin for Arbiter Hub webhook events.

Receives outbound webhooks from Arbiter Hub, validates HMAC-SHA256
signatures, and pushes validated events to the EDA event queue.
"""

import hashlib
import hmac
import json
import logging
from typing import Any

from aiohttp import web

log = logging.getLogger(__name__)


def validate_hmac(body: bytes, signature: str, secret: str) -> bool:
    expected = f"sha256={hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}"
    return hmac.compare_digest(expected, signature)


async def main(queue: Any, args: dict[str, Any]) -> None:
    host = args.get("host", "0.0.0.0")
    port = args.get("port", 5001)
    secret = args.get("secret", "")

    app = web.Application()

    async def handle_webhook(request: web.Request) -> web.Response:
        body = await request.read()
        sig = request.headers.get("X-Arbiter-Signature", "")

        if secret and not validate_hmac(body, sig, secret):
            log.warning("HMAC validation failed")
            return web.Response(status=401, text="invalid signature")

        try:
            event = json.loads(body)
        except json.JSONDecodeError:
            return web.Response(status=400, text="invalid JSON")

        await queue.put(event)
        log.info("queued event: %s", event.get("event_type", "unknown"))
        return web.Response(status=200, text="ok")

    app.router.add_post("/", handle_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("arbiter-hub EDA source listening on %s:%d", host, port)

    try:
        while True:
            import asyncio

            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()
