"""A durable job queue on PostgreSQL.

`asyncio.create_task` loses every in-flight job when the process restarts (audit
B-07 / G-21). Phase 0 stopped orphaned jobs from *looking* alive — they are
reaped and marked failed — but it could not make the work survive, because the
work only ever existed in memory. Ingestion cannot lose a batch to a deploy, so
the queue is a table.

## Why Postgres and not a broker

`SELECT ... FOR UPDATE SKIP LOCKED` is a complete queue primitive: it hands each
row to exactly one worker, skips rows another worker holds, and needs no polling
coordination. The database is already here for identity, audit and provenance.
And it buys a property no separate broker can offer — a job can be enqueued *in
the same transaction as the change that should cause it*, so there is no window
where the write committed and the follow-up work was lost.

Kafka and Celery were both considered and rejected in the audit: neither solves
a problem ARGUS has at any realistic scale for this project, and each is a
permanent operational commitment.

## Delivery semantics, stated plainly

**At-least-once.** A worker that dies mid-job holds a *lease*, not a lock; when
`locked_until` passes, the job is reclaimed and runs again. That is the correct
trade for ingestion — a batch processed twice is deduplicated by content hash
downstream, whereas a batch processed zero times is data ARGUS never sees and
cannot know it is missing.

Handlers must therefore be idempotent. That is a requirement, not an aspiration,
and it is why raw landing is keyed on `(connector_id, content_hash)`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from app.database.postgres import acquire

logger = logging.getLogger(__name__)

JobHandler = Callable[["Job"], Awaitable[None]]

_HANDLERS: dict[str, JobHandler] = {}

# Identifies this process in `locked_by`, so an operator looking at a stuck job
# can tell which worker held it.
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"

# How long a claimed job stays leased before another worker may reclaim it.
# Long enough that a slow-but-alive job is not stolen, short enough that a
# crashed worker's jobs resume promptly.
DEFAULT_LEASE_SECONDS = 300

# Exponential, capped. A source that is down stays down for minutes, not
# milliseconds, and hammering it changes nothing except the log volume.
_BACKOFF_BASE_SECONDS = 5
_BACKOFF_CAP_SECONDS = 900


@dataclass(frozen=True)
class Job:
    job_id: int
    kind: str
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    created_at: datetime

    @property
    def is_final_attempt(self) -> bool:
        return self.attempts >= self.max_attempts


class UnknownJobKind(RuntimeError):
    """Raised when a queued job names a handler this process does not have.

    Not fatal to the worker: a rolling deploy legitimately has one process
    running older code. The job is released rather than failed, so a worker that
    *does* know the kind can pick it up.
    """


def register(kind: str) -> Callable[[JobHandler], JobHandler]:
    """Register a handler for a job kind."""

    def decorator(handler: JobHandler) -> JobHandler:
        if kind in _HANDLERS and _HANDLERS[kind] is not handler:
            raise RuntimeError(f"Two handlers registered for job kind {kind!r}")
        _HANDLERS[kind] = handler
        return handler

    return decorator


def registered_kinds() -> frozenset[str]:
    return frozenset(_HANDLERS)


async def enqueue(
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    idempotency_key: str | None = None,
    priority: int = 100,
    run_after: datetime | None = None,
    max_attempts: int = 5,
    conn: asyncpg.Connection | None = None,
) -> int | None:
    """Queue a job. Returns its id, or None if `idempotency_key` already exists.

    Pass `conn` to enlist in a caller's transaction — the reason this queue is
    in the database at all. A job enqueued alongside the write that motivates it
    commits or rolls back with it, so there is no state where the change landed
    and the follow-up silently did not.
    """
    sql = """
        INSERT INTO job_queue (kind, payload, idempotency_key, priority, run_after, max_attempts)
        VALUES ($1, $2::jsonb, $3, $4, COALESCE($5, now()), $6)
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING job_id
    """
    args = (
        kind,
        json.dumps(payload or {}, default=str),
        idempotency_key,
        priority,
        run_after,
        max_attempts,
    )
    if conn is not None:
        return await conn.fetchval(sql, *args)
    async with acquire() as own:
        return await own.fetchval(sql, *args)


async def claim(
    conn: asyncpg.Connection, *, kinds: frozenset[str], lease_seconds: int
) -> Job | None:
    """Take exactly one runnable job, or None.

    `FOR UPDATE SKIP LOCKED` is what makes this safe with several workers: each
    row goes to one claimer and the others move past it rather than blocking.
    The inner SELECT is a separate statement from the UPDATE so the lock is held
    only over the row being claimed.
    """
    row = await conn.fetchrow(
        """
        UPDATE job_queue
           SET status = 'running',
               attempts = attempts + 1,
               locked_by = $1,
               locked_until = now() + make_interval(secs => $2),
               started_at = COALESCE(started_at, now())
         WHERE job_id = (
               SELECT job_id FROM job_queue
                WHERE status = 'queued'
                  AND run_after <= now()
                  AND kind = ANY($3::text[])
                ORDER BY priority ASC, job_id ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
         )
        RETURNING job_id, kind, payload, attempts, max_attempts, created_at
        """,
        WORKER_ID,
        lease_seconds,
        list(kinds),
    )
    if row is None:
        return None
    return Job(
        job_id=row["job_id"],
        kind=row["kind"],
        payload=json.loads(row["payload"]),
        attempts=row["attempts"],
        max_attempts=row["max_attempts"],
        created_at=row["created_at"],
    )


async def complete(conn: asyncpg.Connection, job_id: int) -> None:
    await conn.execute(
        """
        UPDATE job_queue
           SET status = 'succeeded', finished_at = now(), locked_by = NULL, locked_until = NULL
         WHERE job_id = $1
        """,
        job_id,
    )


async def fail(conn: asyncpg.Connection, job: Job, error: str) -> None:
    """Record a failure and either schedule a retry or bury the job.

    A job that has exhausted its attempts becomes `dead` rather than
    disappearing or retrying forever. Dead jobs are the queue's own dead-letter
    queue: visible, countable, and alertable.
    """
    if job.is_final_attempt:
        await conn.execute(
            """
            UPDATE job_queue
               SET status = 'dead', finished_at = now(), last_error = $2,
                   locked_by = NULL, locked_until = NULL
             WHERE job_id = $1
            """,
            job.job_id,
            error[:4000],
        )
        logger.error(
            "job exhausted its attempts and was buried",
            extra={"job_id": job.job_id, "kind": job.kind, "attempts": job.attempts},
        )
        return

    delay = min(_BACKOFF_BASE_SECONDS * (2 ** (job.attempts - 1)), _BACKOFF_CAP_SECONDS)
    await conn.execute(
        """
        UPDATE job_queue
           SET status = 'queued', run_after = now() + make_interval(secs => $2),
               last_error = $3, locked_by = NULL, locked_until = NULL
         WHERE job_id = $1
        """,
        job.job_id,
        delay,
        error[:4000],
    )


async def release(conn: asyncpg.Connection, job: Job) -> None:
    """Put a claimed job back without counting the attempt against it.

    Used when this process cannot run the job at all — an unknown kind during a
    rolling deploy — rather than when the job failed. Charging an attempt for
    "the worker that picked it up was the wrong one" would eventually bury a
    perfectly good job.
    """
    await conn.execute(
        """
        UPDATE job_queue
           SET status = 'queued', attempts = GREATEST(attempts - 1, 0),
               run_after = now() + make_interval(secs => 30),
               locked_by = NULL, locked_until = NULL
         WHERE job_id = $1
        """,
        job.job_id,
    )


async def reclaim_expired(conn: asyncpg.Connection) -> int:
    """Return leases that outlived their worker to the queue.

    This is what makes a crash cost one visibility timeout rather than the job.
    """
    status = await conn.execute(
        """
        UPDATE job_queue
           SET status = 'queued', locked_by = NULL, locked_until = NULL,
               last_error = COALESCE(last_error, 'lease expired; worker presumed dead')
         WHERE status = 'running' AND locked_until < now()
        """
    )
    return int(status.rsplit(" ", 1)[-1])


async def stats() -> dict[str, int]:
    """Queue depth by status, for the health surface."""
    async with acquire() as conn:
        rows = await conn.fetch("SELECT status, count(*) AS n FROM job_queue GROUP BY status")
    return {row["status"]: row["n"] for row in rows}


class Worker:
    """Polls the queue and runs jobs.

    Deliberately a poller rather than LISTEN/NOTIFY. NOTIFY does not survive a
    disconnect, so a worker that reconnects can miss a wake-up and sit idle on a
    non-empty queue — which is a silent stall, the worst failure mode for
    something whose whole job is not losing work. Polling at a couple of seconds
    costs one trivial indexed query and cannot miss anything.
    """

    def __init__(
        self,
        *,
        poll_interval: float = 2.0,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        concurrency: int = 2,
    ) -> None:
        self.poll_interval = poll_interval
        self.lease_seconds = lease_seconds
        self.concurrency = concurrency
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._running: set[asyncio.Task[None]] = set()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._loop(), name="job-worker")

    async def stop(self, timeout: float = 10.0) -> None:
        """Stop accepting work and let in-flight jobs finish.

        In-flight jobs are awaited rather than cancelled: a cancelled job is
        retried after its lease expires, which is correct but slower and noisier
        than simply letting it finish the second it needs.
        """
        self._stopping.set()
        if self._task is not None:
            await asyncio.wait({self._task}, timeout=timeout)
            self._task = None
        if self._running:
            await asyncio.wait(self._running, timeout=timeout)

    async def _loop(self) -> None:
        logger.info("job worker started", extra={"worker_id": WORKER_ID})
        while not self._stopping.is_set():
            try:
                if len(self._running) >= self.concurrency:
                    await self._sleep(self.poll_interval)
                    continue

                async with acquire() as conn:
                    await reclaim_expired(conn)
                    job = await claim(
                        conn, kinds=registered_kinds(), lease_seconds=self.lease_seconds
                    )

                if job is None:
                    await self._sleep(self.poll_interval)
                    continue

                task = asyncio.create_task(self._run(job), name=f"job-{job.job_id}")
                # Strong reference until completion: a task held only by the
                # event loop can be garbage-collected mid-flight, which is the
                # exact defect Phase 0 fixed in the in-process job runner.
                self._running.add(task)
                task.add_done_callback(self._running.discard)

            except asyncio.CancelledError:
                raise
            except Exception:
                # The worker loop must not die on a transient database error —
                # a queue with no consumer is indistinguishable from a queue
                # with no work, and nothing would report it.
                logger.exception("job worker loop error; continuing")
                await self._sleep(self.poll_interval)

        logger.info("job worker stopped", extra={"worker_id": WORKER_ID})

    async def _sleep(self, seconds: float) -> None:
        """Sleep, but wake immediately on shutdown."""
        try:
            await asyncio.wait_for(self._stopping.wait(), timeout=seconds)
        except TimeoutError:
            pass

    async def _run(self, job: Job) -> None:
        handler = _HANDLERS.get(job.kind)
        if handler is None:
            async with acquire() as conn:
                await release(conn, job)
            logger.warning(
                "no handler for job kind; released", extra={"job_id": job.job_id, "kind": job.kind}
            )
            return

        try:
            await handler(job)
        except Exception as exc:
            logger.exception("job failed", extra={"job_id": job.job_id, "kind": job.kind})
            async with acquire() as conn:
                await fail(conn, job, f"{type(exc).__name__}: {exc}")
            return

        async with acquire() as conn:
            await complete(conn, job.job_id)
