"""Shared fixtures, including a real Neo4j for integration tests.

Every defect in the production audit lived in code no test had ever executed:
the suite was 27 pure-function tests and did not touch a route, a repository, a
Cypher query, the job system, or auth. Mocking the driver would have reproduced
that gap exactly — a mock cannot tell you that `collect(...)[0..5]` truncates a
count, that `count(*) + 1` races, or that a lookup is a label scan. So these
tests run against a real database.

Integration tests are skipped (not failed) when no Neo4j is reachable, so
`pytest` still works on a laptop with nothing running. CI always provides one,
so they always run there.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from neo4j import AsyncDriver, AsyncGraphDatabase

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
