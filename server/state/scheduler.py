import asyncio
import logging

from server.models.db import async_session
from server.state.machine import check_stale_workloads

log = logging.getLogger(__name__)


class StalenessScheduler:
    def __init__(self, interval_seconds: int = 60):
        self.interval = interval_seconds
        self._task: asyncio.Task | None = None

    async def _run(self):
        while True:
            try:
                async with async_session() as session:
                    stale_ids = await check_stale_workloads(session)
                    if stale_ids:
                        log.info("Transitioned %d workloads to Stale", len(stale_ids))
            except Exception:
                log.exception("Staleness check failed")
            await asyncio.sleep(self.interval)

    def start(self):
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
