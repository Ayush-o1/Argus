"""The durable job queue against a real PostgreSQL.

Every property asserted here is the database's: `FOR UPDATE SKIP LOCKED`
handing a row to exactly one claimer, a UNIQUE constraint collapsing duplicate
enqueues, and a lease expiring so a dead worker's job comes back. A mock would
agree with whatever the code believed about itself, which is the gap that let
the original fire-and-forget job system look correct.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio

from app.config import get_settings
from app.database.postgres import acquire, close_postgres, connect_postgres
from app.services import queue

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def kind() -> AsyncIterator[str]:
    """A unique job kind per test, so tests never claim each other's work."""
    settings = get_settings()
    try:
        probe = await asyncpg.connect(dsn=settings.postgres_dsn, timeout=5)
    except Exception:
        pytest.skip("No PostgreSQL reachable; skipping queue integration tests")
    await probe.close()

    await connect_postgres()
    name = f"test.{uuid.uuid4().hex[:12]}"
    try:
        yield name
    finally:
        # The queue is working state rather than evidence, so unlike the audit
        # log and raw landing it is deletable — and cleaning up is the app
        # role's own privilege, not a superuser act.
        async with acquire() as conn:
            await conn.execute("DELETE FROM job_queue WHERE kind = $1", name)
        await close_postgres()


async def test_a_queued_job_is_claimed_exactly_once(kind: str) -> None:
    await queue.enqueue(kind, {"n": 1})

    async with acquire() as conn:
        first = await queue.claim(conn, kinds=frozenset({kind}), lease_seconds=60)
    async with acquire() as conn:
        second = await queue.claim(conn, kinds=frozenset({kind}), lease_seconds=60)

    assert first is not None
    assert first.payload == {"n": 1}
    assert second is None, "a claimed job must not be handed to a second worker"


async def test_concurrent_workers_never_claim_the_same_job(kind: str) -> None:
    """The property `FOR UPDATE SKIP LOCKED` exists for.

    Ten jobs, ten simultaneous claimers: every job goes to exactly one, and
    nobody blocks waiting for a row someone else holds.
    """
    for n in range(10):
        await queue.enqueue(kind, {"n": n})

    async def claim_one() -> int | None:
        async with acquire() as conn:
            job = await queue.claim(conn, kinds=frozenset({kind}), lease_seconds=60)
        return job.job_id if job else None

    claimed = await asyncio.gather(*[claim_one() for _ in range(10)])
    ids = [c for c in claimed if c is not None]
    assert len(ids) == 10
    assert len(set(ids)) == 10, f"a job was claimed twice: {ids}"


async def test_an_idempotency_key_collapses_duplicate_enqueues(kind: str) -> None:
    """Two schedulers ticking together, or a retry racing a manual trigger, must
    produce one run — not two runs of the same feed."""
    first = await queue.enqueue(kind, {"n": 1}, idempotency_key=f"{kind}:same")
    second = await queue.enqueue(kind, {"n": 1}, idempotency_key=f"{kind}:same")
    assert first is not None
    assert second is None

    async with acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM job_queue WHERE kind = $1", kind)
    assert count == 1


async def test_a_failure_retries_with_backoff_then_buries_the_job(kind: str) -> None:
    """A job that cannot succeed must stop retrying and become *visible* rather
    than looping forever or vanishing."""
    await queue.enqueue(kind, {}, max_attempts=2)

    async with acquire() as conn:
        job = await queue.claim(conn, kinds=frozenset({kind}), lease_seconds=60)
        assert job is not None
        await queue.fail(conn, job, "first failure")
        row = await conn.fetchrow("SELECT status, run_after FROM job_queue WHERE job_id = $1", job.job_id)
        assert row["status"] == "queued"
        # Backoff pushed it into the future, so it is not immediately reclaimable.
        assert await queue.claim(conn, kinds=frozenset({kind}), lease_seconds=60) is None

        # Make it due, take the final attempt, and fail again.
        await conn.execute("UPDATE job_queue SET run_after = now() WHERE job_id = $1", job.job_id)
        final = await queue.claim(conn, kinds=frozenset({kind}), lease_seconds=60)
        assert final is not None and final.is_final_attempt
        await queue.fail(conn, final, "second failure")

        buried = await conn.fetchrow(
            "SELECT status, last_error FROM job_queue WHERE job_id = $1", job.job_id
        )
    assert buried["status"] == "dead"
    assert buried["last_error"] == "second failure"


async def test_an_expired_lease_returns_the_job_to_the_queue(kind: str) -> None:
    """What makes a worker crash cost one visibility timeout rather than the
    job. This is the whole reason ingestion moved off `asyncio.create_task`."""
    await queue.enqueue(kind, {})

    async with acquire() as conn:
        job = await queue.claim(conn, kinds=frozenset({kind}), lease_seconds=60)
        assert job is not None
        # Simulate the worker dying: the lease is in the past and nobody
        # completed the job.
        await conn.execute(
            "UPDATE job_queue SET locked_until = now() - interval '1 minute' WHERE job_id = $1",
            job.job_id,
        )
        reclaimed = await queue.reclaim_expired(conn)
        assert reclaimed == 1

        again = await queue.claim(conn, kinds=frozenset({kind}), lease_seconds=60)
    assert again is not None
    assert again.job_id == job.job_id


async def test_a_job_is_never_claimed_before_its_run_after(kind: str) -> None:
    from datetime import UTC, datetime, timedelta

    await queue.enqueue(kind, {}, run_after=datetime.now(UTC) + timedelta(hours=1))
    async with acquire() as conn:
        assert await queue.claim(conn, kinds=frozenset({kind}), lease_seconds=60) is None


async def test_an_unknown_kind_is_released_without_charging_an_attempt(kind: str) -> None:
    """A rolling deploy legitimately has one process running older code. That
    worker must hand the job back rather than burn an attempt, or a perfectly
    good job gets buried by the deploy itself.
    """
    await queue.enqueue(kind, {})
    async with acquire() as conn:
        job = await queue.claim(conn, kinds=frozenset({kind}), lease_seconds=60)
        assert job is not None and job.attempts == 1
        await queue.release(conn, job)
        row = await conn.fetchrow(
            "SELECT status, attempts FROM job_queue WHERE job_id = $1", job.job_id
        )
    assert row["status"] == "queued"
    assert row["attempts"] == 0


async def test_priority_orders_the_queue(kind: str) -> None:
    await queue.enqueue(kind, {"which": "normal"}, priority=100)
    await queue.enqueue(kind, {"which": "urgent"}, priority=1)
    async with acquire() as conn:
        job = await queue.claim(conn, kinds=frozenset({kind}), lease_seconds=60)
    assert job is not None
    assert job.payload["which"] == "urgent"


async def test_a_worker_runs_a_registered_handler_end_to_end(kind: str) -> None:
    """The whole loop, with a real handler and a real worker."""
    seen: list[dict] = []

    @queue.register(kind)
    async def _handler(job: queue.Job) -> None:
        seen.append(job.payload)

    await queue.enqueue(kind, {"hello": "world"})

    worker = queue.Worker(poll_interval=0.1, concurrency=1)
    worker.start()
    try:
        for _ in range(100):
            if seen:
                break
            await asyncio.sleep(0.1)
    finally:
        await worker.stop(timeout=5)

    assert seen == [{"hello": "world"}]
    async with acquire() as conn:
        status = await conn.fetchval("SELECT status FROM job_queue WHERE kind = $1", kind)
    assert status == "succeeded"


async def test_a_handler_that_raises_does_not_kill_the_worker(kind: str) -> None:
    """A worker that dies on a bad job is a queue with no consumer, which is
    indistinguishable from a queue with no work and reports nothing."""
    attempts: list[int] = []

    @queue.register(kind)
    async def _handler(job: queue.Job) -> None:
        attempts.append(job.attempts)
        raise RuntimeError("deliberate failure")

    await queue.enqueue(kind, {}, max_attempts=1)

    worker = queue.Worker(poll_interval=0.1, concurrency=1)
    worker.start()
    try:
        for _ in range(100):
            if attempts:
                break
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.5)
    finally:
        await worker.stop(timeout=5)

    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, last_error FROM job_queue WHERE kind = $1", kind
        )
    assert row["status"] == "dead"
    assert "deliberate failure" in row["last_error"]
