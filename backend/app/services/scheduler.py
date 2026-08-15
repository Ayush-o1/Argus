"""Periodic scheduling for ingestion.

A small loop that asks, every so often, which connectors are due and queues a
run for each. Everything it queues is durable; the scheduler itself holds no
state, so losing it loses nothing — the next tick recomputes what is due from
`connectors.last_run_at`.

## Why this is safe to run in every instance

The obvious hazard with an in-process scheduler is several instances firing the
same tick and running one feed several times. It cannot happen here: each queued
job carries an idempotency key built from the connector and the current interval
window, and `job_queue.idempotency_key` is UNIQUE. Two instances scheduling at
the same moment produce one row and one run.

That is deliberately a database guarantee rather than a leader election. Leader
election is a distributed-systems problem with its own failure modes; a unique
constraint is a line of SQL that cannot be wrong.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class IngestScheduler:
    def __init__(self, *, interval: float = 30.0) -> None:
        self.interval = interval
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._loop(), name="ingest-scheduler")

    async def stop(self, timeout: float = 5.0) -> None:
        self._stopping.set()
        if self._task is not None:
            await asyncio.wait({self._task}, timeout=timeout)
            self._task = None

    async def _loop(self) -> None:
        from app.services.ingest import enqueue_due_connectors

        logger.info("ingest scheduler started", extra={"interval": self.interval})
        while not self._stopping.is_set():
            try:
                queued = await enqueue_due_connectors()
                if queued:
                    logger.info("queued %d connector run(s)", queued)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Never let a transient database error kill the scheduler. A
                # scheduler that has silently stopped is indistinguishable from
                # one with nothing to do, and no source would ever be collected
                # again without anybody being told.
                logger.exception("ingest scheduler tick failed; continuing")

            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.interval)
            except TimeoutError:
                pass

        logger.info("ingest scheduler stopped")
