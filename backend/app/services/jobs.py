"""In-process asyncio background jobs with Redis-backed status.

At this project's scale every job completes in low single-digit seconds, so a
separate always-running worker process is overhead without payoff. That tradeoff
still holds — but the original implementation had three defects the audit
recorded as B-07, all fixed here:

  1. `asyncio.create_task(...)` was called without keeping the returned task.
     The event loop holds only a weak reference, so a task could be garbage
     collected mid-execution. Tasks are now retained in `_ACTIVE_TASKS` until
     they finish.
  2. Jobs did not survive a restart: the process died, the Redis record stayed
     "running", and the frontend polled it forever at 1.2s intervals until the
     hour-long TTL expired. `reap_stale_jobs` now marks orphans failed at
     startup, and records carry the pid/boot id that owns them.
  3. There was no concurrency limit, so a client could start unbounded
     concurrent GDS jobs. `start_job` now rejects work beyond
     `max_concurrent_jobs` with a clear error rather than accepting it and
     degrading the host.

Contract is unchanged for callers: kick off a job, poll status, get the result.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from redis.asyncio import Redis

from app.config import get_settings

logger = logging.getLogger(__name__)

JOB_TTL_SECONDS = 60 * 60  # 1 hour

# Identifies the process that owns a job record. A record whose owner is not the
# current process cannot still be running, because jobs are in-process only —
# that is exactly what makes orphan detection reliable rather than a heuristic.
_BOOT_ID = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"

# Strong references to in-flight tasks (defect 1 above). Entries are discarded by
# the task's own done-callback.
_ACTIVE_TASKS: set[asyncio.Task[None]] = set()

_semaphore: asyncio.Semaphore | None = None


class JobRejected(RuntimeError):
    """Raised when the concurrency ceiling is already reached. Surfaced to the
    caller as 429 rather than silently queueing, so the client learns the system
    is saturated instead of waiting on a job that has not started."""


def _get_semaphore() -> asyncio.Semaphore:
    # Built lazily: constructing an asyncio primitive at import time binds it to
    # whichever loop happens to be current, which breaks under pytest-asyncio
    # where each test gets a fresh loop.
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().max_concurrent_jobs)
    return _semaphore


def _key(job_id: str) -> str:
    return f"job:{job_id}"


def active_job_count() -> int:
    return len(_ACTIVE_TASKS)


async def create_job(redis: Redis, job_type: str) -> str:
    job_id = str(uuid.uuid4())
    await redis.set(
        _key(job_id),
        json.dumps(
            {
                "job_id": job_id,
                "job_type": job_type,
                "status": "running",
                "result": None,
                "error": None,
                "stages": [],
                "owner": _BOOT_ID,
                "started_at": time.time(),
            }
        ),
        ex=JOB_TTL_SECONDS,
    )
    return job_id


async def get_job(redis: Redis, job_id: str) -> dict[str, Any] | None:
    raw = await redis.get(_key(job_id))
    if raw is None:
        return None
    return json.loads(raw)


async def update_job_progress(redis: Redis, job_id: str, stages: list[str]) -> None:
    """Appends live progress to a still-running job — used by jobs that report
    incremental stages (e.g. scenario generation) rather than a single result."""
    existing = await get_job(redis, job_id)
    if existing is None:
        return
    existing["stages"] = stages
    await redis.set(_key(job_id), json.dumps(existing), ex=JOB_TTL_SECONDS)


async def _write_terminal(
    redis: Redis, job_id: str, status: str, result: Any, error: str | None
) -> None:
    # Re-read *after* the coroutine finishes, not before: a job that calls
    # update_job_progress while running would otherwise have its terminal record
    # overwritten with the stale (empty) stages captured before it ran.
    existing = await get_job(redis, job_id) or {}
    await redis.set(
        _key(job_id),
        json.dumps(
            {
                "job_id": job_id,
                "job_type": existing.get("job_type"),
                "status": status,
                "result": result,
                "error": error,
                "stages": existing.get("stages", []),
                "owner": existing.get("owner", _BOOT_ID),
                "started_at": existing.get("started_at"),
                "finished_at": time.time(),
            }
        ),
        ex=JOB_TTL_SECONDS,
    )


async def run_job(redis: Redis, job_id: str, coro: Awaitable[Any], job_type: str = "") -> None:
    """Runs the work and writes its terminal state. Holds the concurrency
    semaphore for the duration."""
    async with _get_semaphore():
        started = time.perf_counter()
        try:
            result = await coro
        except asyncio.CancelledError:
            # Shutdown or explicit cancellation. Record it so the poller sees a
            # terminal state instead of a job stuck on "running", then re-raise
            # so cancellation semantics are preserved.
            await _write_terminal(redis, job_id, "failed", None, "Job cancelled")
            raise
        except Exception as exc:  # noqa: BLE001 - job errors surface to the poller, not the process
            logger.exception(
                "job failed", extra={"job_id": job_id, "job_type": job_type, "outcome": "failed"}
            )
            await _write_terminal(redis, job_id, "failed", None, str(exc))
        else:
            await _write_terminal(redis, job_id, "done", result, None)
            logger.info(
                "job completed",
                extra={
                    "job_id": job_id,
                    "job_type": job_type,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "outcome": "done",
                },
            )


def _spawn(redis: Redis, job_id: str, coro: Awaitable[Any], job_type: str) -> None:
    task = asyncio.create_task(run_job(redis, job_id, coro, job_type))
    _ACTIVE_TASKS.add(task)
    task.add_done_callback(_ACTIVE_TASKS.discard)


def _check_capacity() -> None:
    limit = get_settings().max_concurrent_jobs
    if len(_ACTIVE_TASKS) >= limit:
        raise JobRejected(
            f"Too many jobs already running ({len(_ACTIVE_TASKS)}/{limit}). Retry when one completes."
        )


async def start_job(redis: Redis, job_type: str, work: Callable[[], Awaitable[Any]]) -> str:
    """Creates the job record and schedules `work`, returning the job_id
    immediately. Raises JobRejected when at capacity."""
    _check_capacity()
    job_id = await create_job(redis, job_type)
    _spawn(redis, job_id, work(), job_type)
    return job_id


async def start_job_with_progress(
    redis: Redis, job_type: str, work: Callable[[str], Awaitable[Any]]
) -> str:
    """Like `start_job`, but `work` receives the job_id so it can call
    `update_job_progress` as it goes."""
    _check_capacity()
    job_id = await create_job(redis, job_type)
    _spawn(redis, job_id, work(job_id), job_type)
    return job_id


async def reap_stale_jobs(redis: Redis) -> int:
    """Mark jobs owned by a previous process as failed. Called at startup.

    Jobs run in-process, so a "running" record owned by a different boot id
    cannot still be executing — its process is gone. Without this the frontend
    polls such a job forever (audit B-07 defect 2).

    Uses SCAN rather than KEYS so a large keyspace does not block Redis.
    """
    reaped = 0
    async for key in redis.scan_iter(match="job:*", count=100):
        raw = await redis.get(key)
        if raw is None:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("discarding unparseable job record", extra={"job_key": key})
            continue

        if record.get("status") != "running" or record.get("owner") == _BOOT_ID:
            continue

        record.update(
            {
                "status": "failed",
                "error": "Job did not survive a backend restart and was not completed.",
                "finished_at": time.time(),
            }
        )
        await redis.set(key, json.dumps(record), ex=JOB_TTL_SECONDS)
        reaped += 1

    return reaped


async def cancel_active_jobs(timeout: float = 5.0) -> None:
    """Cancel in-flight jobs and wait briefly for them to record terminal state.
    Called during shutdown so jobs do not become orphans this process could have
    accounted for itself."""
    if not _ACTIVE_TASKS:
        return
    tasks = list(_ACTIVE_TASKS)
    for task in tasks:
        task.cancel()
    await asyncio.wait(tasks, timeout=timeout)
