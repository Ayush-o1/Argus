"""Shared fixtures, including a real Neo4j and a real PostgreSQL.

Every defect in the production audit lived in code no test had ever executed:
the suite was 27 pure-function tests and did not touch a route, a repository, a
Cypher query, the job system, or auth. Mocking the driver would have reproduced
that gap exactly — a mock cannot tell you that `collect(...)[0..5]` truncates a
count, that `count(*) + 1` races, or that a lookup is a label scan. So these
tests run against a real database.

Integration tests are skipped (not failed) when no Neo4j is reachable, so
`pytest` still works on a laptop with nothing running. CI always provides one,
so they always run there.

**PostgreSQL is redirected to a separate database before anything imports the
settings.** The graph fixtures isolate by tagging every created node and
deleting exactly those afterwards, but the Postgres integration tests had no
equivalent: they connected on `settings.postgres_dsn` and wrote into whichever
database the developer was actually using. A full run appended real rows to
`audit_events` — a table that is deliberately append-only, so the pollution
could not be undone — and left run records behind in `resolution_runs`. Tests
that mutate the data you are verifying make the verification worth less than it
looks, so the redirect happens here, at import time, and is not optional.

The override is an environment variable rather than a fixture because
`get_settings()` is `lru_cache`d: by the time a fixture could run, any module
that read configuration at import would already hold the working DSN. conftest
is imported before test modules, which makes this the last moment the choice can
still be made once for the whole process.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio
from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import get_settings

# The database tests are allowed to write to. Never the application's own.
TEST_POSTGRES_DB = os.environ.get("ARGUS_TEST_POSTGRES_DB", "argus_test")

# Read the working configuration *before* overriding it, so the guard below
# compares against what the application actually uses — which normally comes
# from the .env file rather than the environment, and so cannot be recovered
# from os.environ once the override is in place.
_WORKING_POSTGRES_DB = get_settings().postgres_db

if _WORKING_POSTGRES_DB == TEST_POSTGRES_DB:
    raise RuntimeError(
        f"ARGUS_TEST_POSTGRES_DB is {TEST_POSTGRES_DB!r}, which is also the "
        "application's configured database. Refusing to run: the suite writes "
        "rows that append-only tables will not let anyone remove afterwards."
    )

# Actual environment variables outrank the .env file in pydantic-settings (see
# app/config.py), so this wins over whatever POSTGRES_DB the developer has set.
# The cache is cleared because the read above populated it with the working DSN.
os.environ["POSTGRES_DB"] = TEST_POSTGRES_DB
get_settings.cache_clear()

NEO4J_URI = os.environ.get("TEST_NEO4J_URI", os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
NEO4J_USER = os.environ.get("TEST_NEO4J_USER", os.environ.get("NEO4J_USER", "neo4j"))
NEO4J_PASSWORD = os.environ.get("TEST_NEO4J_PASSWORD", os.environ.get("NEO4J_PASSWORD", "argus_dev_password"))

# Tests write into a dedicated database so they can never touch a working graph.
# Neo4j Community allows only the single default database, so when the target is
# Community we fall back to namespacing by label prefix and cleaning up after
# ourselves instead (see `graph` fixture).
TEST_DATABASE = os.environ.get("TEST_NEO4J_DATABASE", "neo4j")


async def _probe() -> bool:
    try:
        driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        try:
            await driver.verify_connectivity()
            return True
        finally:
            await driver.close()
    except Exception:
        return False


@pytest_asyncio.fixture(scope="session")
async def neo4j_available() -> bool:
    return await _probe()


@pytest_asyncio.fixture
async def driver(neo4j_available: bool) -> AsyncIterator[AsyncDriver]:
    if not neo4j_available:
        pytest.skip(f"No Neo4j reachable at {NEO4J_URI}; skipping integration test")

    drv = AsyncGraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD), database=TEST_DATABASE
    )
    try:
        await drv.verify_connectivity()
        yield drv
    finally:
        await drv.close()


@pytest.fixture
def tag() -> str:
    """A unique marker for one test's data.

    Every node a test creates carries `_test_tag`, and the `graph` fixture
    deletes exactly those afterwards. This is what lets integration tests run
    against a populated development graph without disturbing it — the
    alternative, wiping the database between tests, would make running the suite
    locally a destructive act.
    """
    return f"test-{uuid.uuid4().hex[:12]}"


@pytest_asyncio.fixture
async def graph(driver: AsyncDriver, tag: str) -> AsyncIterator[AsyncDriver]:
    """Yields the driver, then removes everything tagged by this test."""
    try:
        yield driver
    finally:
        async with driver.session() as session:
            await session.run("MATCH (n) WHERE n._test_tag = $tag DETACH DELETE n", tag=tag)


def _maintenance_dsn() -> str:
    """Admin DSN pointing at `postgres`, the database that always exists.

    CREATE DATABASE cannot run from inside the database being created, and the
    admin DSN now resolves to the test database, which may not exist yet.
    """
    s = get_settings()
    return (
        f"postgresql://{s.postgres_superuser}:{s.postgres_superuser_password}"
        f"@{s.postgres_host}:{s.postgres_port}/postgres"
    )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def postgres_test_database() -> AsyncIterator[None]:
    """Create the test database if absent and bring its schema up to date.

    Autouse and session-scoped: every Postgres-touching test in the suite needs
    it, and creating it per test would cost more than the suite does.

    The database is left in place afterwards rather than dropped. Re-creating it
    on each run would add the migration cost to every invocation, and a schema
    that survives between runs is also the only way an accidental dependency on
    leftover state becomes visible — a suite that silently recreates the world
    cannot tell you it has one.
    """
    from app.database.pg_migrations import run_pg_migrations

    try:
        conn = await asyncpg.connect(dsn=_maintenance_dsn(), timeout=5)
    except Exception as exc:  # pragma: no cover - depends on local environment
        pytest.skip(f"No PostgreSQL reachable for tests: {exc}")

    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", TEST_POSTGRES_DB)
        if not exists:
            # Identifier, so it cannot be a bind parameter. quote_ident is
            # Postgres's own quoting rather than string formatting here.
            quoted = await conn.fetchval("SELECT quote_ident($1)", TEST_POSTGRES_DB)
            await conn.execute(f"CREATE DATABASE {quoted}")
    finally:
        await conn.close()

    # Runs against the test database, because the settings now resolve there.
    # This also exercises the migrations from an empty database on every fresh
    # machine, which running them only against a long-lived working database
    # never does.
    await run_pg_migrations()
    yield
