import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from server.backends.base import BackendRegistry, compute_composite_verdict
from server.models.db import (
    AttestationRecord,
    AttestationVerdict,
    Workload,
    WorkloadState,
    async_session,
)
from server.state.machine import check_stale_workloads, transition

log = logging.getLogger(__name__)

REATTEST_THRESHOLD = 0.8


class StalenessScheduler:
    def __init__(self, interval_seconds: int = 30, registry: BackendRegistry | None = None):
        self.interval = interval_seconds
        self.registry = registry
        self._task: asyncio.Task | None = None

    async def _run(self):
        while True:
            try:
                async with async_session() as session:
                    reattest_count = await self._proactive_reattest(session)
                    if reattest_count:
                        log.info("Proactively re-attested %d workloads", reattest_count)

                    stale_ids = await check_stale_workloads(session)
                    if stale_ids:
                        log.info("Transitioned %d workloads to Stale", len(stale_ids))
            except Exception:
                log.exception("Staleness check failed")
            await asyncio.sleep(self.interval)

    async def _proactive_reattest(self, session) -> int:
        if not self.registry:
            return 0

        now = datetime.now(UTC)
        stmt = select(Workload).where(
            Workload.current_state == WorkloadState.HEALTHY,
            Workload.last_attested_at.isnot(None),
        )
        result = await session.execute(stmt)
        count = 0

        for workload in result.scalars():
            elapsed = (now - workload.last_attested_at).total_seconds()
            threshold = workload.stale_ttl_seconds * REATTEST_THRESHOLD
            if elapsed < threshold:
                continue

            log.info(
                "Re-attesting %s (%.0f%% of TTL elapsed)",
                workload.display_name,
                (elapsed / workload.stale_ttl_seconds) * 100,
            )

            try:
                await transition(session, workload, WorkloadState.ATTESTING, "reattest_scheduler",
                                 justification=f"TTL {elapsed / workload.stale_ttl_seconds:.0%} elapsed, proactive re-attestation")

                backends = []
                for bt in workload.backend_types:
                    try:
                        backends.append((bt, self.registry.get(bt)))
                    except KeyError:
                        log.warning("backend %s not configured, skipped for re-attest", bt)

                if not backends:
                    await transition(session, workload, WorkloadState.FAILED, "reattest_scheduler",
                                     justification="no backends available")
                    continue

                raw_results = await asyncio.gather(
                    *[b.verify(workload) for _, b in backends], return_exceptions=True
                )

                att_results = []
                for (bt, _), raw in zip(backends, raw_results):
                    if isinstance(raw, Exception):
                        log.error("re-attest backend %s raised %s", bt, raw)
                        from server.backends.base import AttestationResult
                        att_results.append(AttestationResult(
                            verdict=AttestationVerdict.ERROR,
                            backend=bt,
                            evidence_hash="",
                            detail={"error": str(raw)},
                        ))
                    else:
                        att_results.append(raw)

                for ar in att_results:
                    session.add(AttestationRecord(
                        workload_id=workload.id,
                        backend=ar.backend,
                        verdict=ar.verdict,
                        evidence_hash=ar.evidence_hash,
                        detail=ar.detail,
                    ))

                composite = compute_composite_verdict(att_results)
                if composite == AttestationVerdict.PASS:
                    backends_str = "+".join(ar.backend for ar in att_results)
                    await transition(session, workload, WorkloadState.HEALTHY, "reattest_scheduler",
                                     justification=f"all backends passed ({backends_str})")
                    workload.last_attested_at = datetime.now(UTC)
                    count += 1
                elif composite == AttestationVerdict.FAIL:
                    await transition(session, workload, WorkloadState.FAILED, "reattest_scheduler",
                                     justification="proactive re-attestation failed")

            except Exception:
                log.exception("Re-attestation failed for %s", workload.display_name)

        await session.commit()
        return count

    def start(self):
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
