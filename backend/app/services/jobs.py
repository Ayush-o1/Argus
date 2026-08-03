"""In-process asyncio background jobs with Redis-backed status (ARGUS_PLAN.md
Phase 11 — replaces v1's dedicated ARQ worker: at this project's scale every
job completes in low single-digit seconds, so a separate always-running
worker process is overhead without payoff). Kick off job -> poll status ->
get result, backed by a plain Redis hash per job id."""

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from redis.asyncio import Redis

JOB_TTL_SECONDS = 60 * 60  # 1 hour, per ARGUS_PLAN.md Phase 11


def _key(job_id: str) -> str:
    return f"job:{job_id}"


async def create_job(redis: Redis, job_type: str) -> str:
    job_id = str(uuid.uuid4())
    await redis.set(
        _key(job_id),
        json.dumps({"job_type": job_type, "status": "running", "result": None, "error": None}),
        ex=JOB_TTL_SECONDS,
    )
    return job_id


async def get_job(redis: Redis, job_id: str) -> dict[str, Any] | None:
    raw = await redis.get(_key(job_id))
    if raw is None:
        return None
    return json.loads(raw)


async def run_job(redis: Redis, job_id: str, coro: Awaitable[Any]) -> None:
    """Awaited inside an `asyncio.create_task` fire-and-forget from the route
    handler; writes the terminal state back to Redis under the same key."""
    try:
        result = await coro
        await redis.set(
            _key(job_id),
            json.dumps({"job_type": None, "status": "done", "result": result, "error": None}),
            ex=JOB_TTL_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - job errors surface to the poller, not the process
        await redis.set(
            _key(job_id),
            json.dumps({"job_type": None, "status": "failed", "result": None, "error": str(exc)}),
            ex=JOB_TTL_SECONDS,
        )


async def start_job(
    redis: Redis,
    job_type: str,
    work: Callable[[], Awaitable[Any]],
) -> str:
    """Creates the job record and schedules `work` to run in the background,
    returning the job_id immediately."""
    job_id = await create_job(redis, job_type)
    asyncio.create_task(run_job(redis, job_id, work()))
    return job_id
