"""Applies the .sql migrations in this directory, in order, exactly once."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import asyncpg

from app.config import get_settings

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent
_FILENAME = re.compile(r"^(\d{3})_([a-z0-9_]+)\.sql$")


class PgMigrationError(RuntimeError):
    """Aborts startup: serving requests against a half-migrated identity schema
    risks authorising something that should not be authorised."""


def _discover() -> list[tuple[int, str, Path]]:
    found: list[tuple[int, str, Path]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        match = _FILENAME.match(path.name)
        if match is None:
            raise PgMigrationError(
                f"Migration filename {path.name!r} does not match NNN_snake_case.sql"
            )
        found.append((int(match.group(1)), match.group(2), path))

    versions = [v for v, _, _ in found]
    if len(set(versions)) != len(versions):
        raise PgMigrationError(f"Duplicate migration version numbers: {sorted(versions)}")
    return found


async def _ensure_version_table(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


async def applied_versions(conn: asyncpg.Connection) -> set[int]:
    await _ensure_version_table(conn)
    rows = await conn.fetch("SELECT version FROM schema_migrations")
    return {row["version"] for row in rows}


async def current_version(conn: asyncpg.Connection) -> int:
    versions = await applied_versions(conn)
    return max(versions) if versions else 0


async def _set_app_role_password(conn: asyncpg.Connection, password: str) -> None:
    """Set the application role's password.

    Kept out of the migration files so a credential never appears in a committed
    .sql, and re-asserted on every startup so rotating the configured password
    takes effect without writing a new migration.

    ALTER ROLE is DDL and cannot take a bind parameter, so the literal is quoted
    by Postgres itself via format('%L') rather than by string-escaping here —
    hand-rolled quoting of a credential into DDL is how SQL injection gets into
    the one place it must never be.
    """
    quoted = await conn.fetchval(
        "SELECT format('ALTER ROLE argus_app WITH PASSWORD %L', $1::text)", password
    )
    await conn.execute(quoted)


async def run_pg_migrations() -> list[int]:
    """Connect as the admin role, apply pending migrations, set the app password.

    Returns the versions applied. Uses its own short-lived connection rather
    than the application pool, because the application pool authenticates as the
    least-privilege role that these migrations create.
    """
    settings = get_settings()
    conn = await asyncpg.connect(dsn=settings.postgres_admin_dsn)
    try:
        already = await applied_versions(conn)
        pending = [m for m in _discover() if m[0] not in already]

        applied_now: list[int] = []
        for version, name, path in pending:
            logger.info("applying pg migration %03d %s", version, name)
            sql = path.read_text()
            try:
                # Each migration runs in one transaction: a partially applied
                # privilege change is a security hole, not merely an
                # inconsistency.
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version, name) VALUES ($1, $2)",
                        version,
                        name,
                    )
            except Exception as exc:
                raise PgMigrationError(f"pg migration {version:03d} ({name}) failed: {exc}") from exc

            applied_now.append(version)
            logger.info("applied pg migration %03d %s", version, name)

        await _set_app_role_password(conn, settings.postgres_app_password)
        return applied_now
    finally:
        await conn.close()
