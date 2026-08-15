"""PostgreSQL connection pool for identity, authorization and audit.

Why a second datastore exists at all, given the audit's own rule that new
infrastructure must be justified: the audit log has to survive compromise of the
application. Neo4j Community has no per-label privilege model, so any process
holding write credentials — which ARGUS must — can `SET` or `DELETE` an audit
node. Postgres can grant the application role INSERT only and reject UPDATE and
DELETE with a trigger, so tampering requires database-superuser access rather
than merely compromising the API.

That is a security property the existing stack cannot express, which is the bar
this project set for adding a dependency. The graph remains authoritative for
entities and relationships; nothing about the intelligence model moves here.

Raw asyncpg rather than an ORM: the schema is small, and the security property
depends on exact GRANT and trigger statements that are better read directly than
generated.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg

from app.config import get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def connect_postgres() -> asyncpg.Pool:
    """Create the process-wide connection pool. Called once at app startup."""
    global _pool
    settings = get_settings()
    _pool = await asyncpg.create_pool(
        dsn=settings.postgres_dsn,
        min_size=2,
        max_size=10,
        # A query that hangs holds a pool connection until the client gives up;
        # ten of those take identity down, which takes everything down.
        command_timeout=settings.postgres_command_timeout_seconds,
    )
    if _pool is None:  # pragma: no cover - asyncpg raises rather than returning None
        raise RuntimeError("Failed to create PostgreSQL pool")
    async with _pool.acquire() as conn:
        await conn.execute("SELECT 1")
    return _pool


async def close_postgres() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("PostgreSQL pool not initialized — app startup did not run.")
    return _pool


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    async with get_pool().acquire() as conn:
        yield conn


@asynccontextmanager
async def transaction() -> AsyncIterator[asyncpg.Connection]:
    """A connection inside a transaction.

    Audit writes share the mutation's transaction so the two commit or roll back
    together — an audited action that succeeds while its audit record is lost is
    exactly the gap an audit log exists to close.
    """
    async with get_pool().acquire() as conn, conn.transaction():
        yield conn
