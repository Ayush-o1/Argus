"""Migration definitions and the runner that applies them."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

# The single node carrying applied-migration state. Keyed by a fixed `id` so the
# uniqueness constraint created in migration 001 cannot produce a second one.
SCHEMA_VERSION_KEY = "argus-schema"


@dataclass(frozen=True)
class Migration:
    """One forward-only schema change.

    `statements` are executed in order, each in its own auto-commit transaction —
    Neo4j does not permit mixing schema and data operations in a single
    transaction, and DDL is transactional per-statement anyway.

    `check` runs *before* the statements and may raise to abort the migration
    with an actionable message. It exists because a uniqueness constraint over
    pre-existing data fails with an opaque driver error; catching the conflict
    ourselves lets us tell the operator exactly which records collide.
    """

    version: int
    name: str
    statements: list[str] = field(default_factory=list)
    check: Callable[[AsyncDriver], Awaitable[None]] | None = None


class MigrationError(RuntimeError):
    """Raised when a migration cannot be applied. Aborts startup deliberately:
    running the app against a half-migrated schema is worse than not starting."""


# ─────────────────────────────────────────────────────────────────────────────
# Pre-flight checks
# ─────────────────────────────────────────────────────────────────────────────

# Every label whose human-readable ID is used as a lookup key by the API, paired
# with that ID's property name. Mirrors app/repositories/entity_labels.py — the
# two are asserted equal by tests/test_migrations.py so they cannot drift.
HUMAN_ID_FIELDS: list[tuple[str, str]] = [
    ("Person", "person_id"),
    ("Organization", "org_id"),
    ("Account", "account_id"),
    ("Device", "device_id"),
    ("Vehicle", "vehicle_id"),
    ("Document", "doc_id"),
    ("Shipment", "shipment_id"),
    ("Event", "event_id"),
    ("Location", "location_id"),
    ("Case", "case_id"),
    ("Incident", "incident_id"),
    ("Storyline", "storyline_id"),
]


async def _assert_no_duplicate_human_ids(driver: AsyncDriver) -> None:
    """Fail loudly, with the offending values, if a uniqueness constraint would
    be violated. `create_case`'s previous `count(*) + 1` sequencing could produce
    duplicate case_ids under concurrency (audit B-02), so this is a real
    possibility on an existing graph rather than a theoretical one."""
    conflicts: list[str] = []
    async with driver.session() as session:
        for label, id_field in HUMAN_ID_FIELDS:
            result = await session.run(
                f"""
                MATCH (n:{label})
                WHERE n.{id_field} IS NOT NULL
                WITH n.{id_field} AS value, count(*) AS occurrences
                WHERE occurrences > 1
                RETURN value, occurrences ORDER BY occurrences DESC LIMIT 10
                """
            )
            rows = [dict(record) async for record in result]
            for row in rows:
                conflicts.append(f"  {label}.{id_field} = {row['value']!r} ({row['occurrences']} nodes)")

    if conflicts:
        raise MigrationError(
            "Cannot apply uniqueness constraints — duplicate human-readable IDs already exist:\n"
            + "\n".join(conflicts)
            + "\n\nResolve these before starting the backend. Duplicates are most likely the result "
            "of concurrent case creation under the pre-migration `count(*) + 1` sequencing."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Migrations
# ─────────────────────────────────────────────────────────────────────────────

_HUMAN_ID_CONSTRAINTS = [
    f"CREATE CONSTRAINT {label.lower()}_{id_field}_unique IF NOT EXISTS "
    f"FOR (n:{label}) REQUIRE n.{id_field} IS UNIQUE"
    for label, id_field in HUMAN_ID_FIELDS
]

MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        name="human_id_uniqueness",
        # Two defects in one change (audit B-02, B-09):
        #   correctness — nothing prevented two :Case nodes sharing a case_id,
        #     which made get_case's .single() raise permanently for that case.
        #   performance — every user-facing lookup resolves by human ID
        #     (MATCH (n:Person {person_id: $id})), and only `n.id` (the uuid) was
        #     constrained. A uniqueness constraint creates a backing index, so
        #     these become index seeks instead of full label scans.
        statements=[
            "CREATE CONSTRAINT schema_version_unique IF NOT EXISTS "
            "FOR (n:SchemaVersion) REQUIRE n.id IS UNIQUE",
            *_HUMAN_ID_CONSTRAINTS,
        ],
        check=_assert_no_duplicate_human_ids,
    ),
    Migration(
        version=2,
        name="id_sequence_counters",
        # Backs the transactional counter that replaces `count(*) + 1` for
        # case_id generation (audit B-02). One node per prefix; the uniqueness
        # constraint is what makes MERGE safe under concurrency.
        statements=[
            "CREATE CONSTRAINT id_sequence_unique IF NOT EXISTS "
            "FOR (n:IdSequence) REQUIRE n.prefix IS UNIQUE",
        ],
    ),
    Migration(
        version=3,
        name="analyst_workflow_indexes",
        # Supports the queue/list queries the UI actually issues. `incident_status`
        # already existed from the generator; the rest did not, so case listing
        # and alert-by-storyline lookups were label scans.
        statements=[
            "CREATE INDEX case_status_idx IF NOT EXISTS FOR (n:Case) ON (n.status)",
            "CREATE INDEX case_opened_at_idx IF NOT EXISTS FOR (n:Case) ON (n.opened_at)",
            "CREATE INDEX incident_status_severity_idx IF NOT EXISTS "
            "FOR (n:Incident) ON (n.status, n.severity)",
            "CREATE INDEX incident_timestamp_idx IF NOT EXISTS FOR (n:Incident) ON (n.timestamp)",
            "CREATE INDEX incident_storyline_idx IF NOT EXISTS FOR (n:Incident) ON (n.storyline_id)",
        ],
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────


async def applied_versions(driver: AsyncDriver) -> set[int]:
    """Versions already recorded as applied. Empty on a graph that has never
    been migrated (including a completely empty one)."""
    async with driver.session() as session:
        result = await session.run(
            "MATCH (v:SchemaVersion {id: $key}) RETURN v.applied AS applied",
            key=SCHEMA_VERSION_KEY,
        )
        record = await result.single()
    if record is None or record["applied"] is None:
        return set()
    return {int(v) for v in record["applied"]}


async def current_version(driver: AsyncDriver) -> int:
    applied = await applied_versions(driver)
    return max(applied) if applied else 0


async def _record_applied(driver: AsyncDriver, version: int, name: str) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MERGE (v:SchemaVersion {id: $key})
            ON CREATE SET v.applied = [], v.history = []
            SET v.applied = coalesce(v.applied, []) + [$version],
                v.history = coalesce(v.history, []) + [$entry],
                v.updated_at = datetime()
            """,
            key=SCHEMA_VERSION_KEY,
            version=version,
            entry=f"{version}:{name}",
        )


async def run_migrations(driver: AsyncDriver) -> list[int]:
    """Apply every pending migration in order. Returns the versions applied.

    Raises MigrationError on failure, which aborts startup by design — serving
    requests against a partially-migrated schema risks returning wrong results,
    which is worse than being unavailable.
    """
    already = await applied_versions(driver)
    pending = [m for m in sorted(MIGRATIONS, key=lambda m: m.version) if m.version not in already]

    if not pending:
        logger.info("schema up to date (version %d)", await current_version(driver))
        return []

    applied_now: list[int] = []
    for migration in pending:
        logger.info("applying migration %03d %s", migration.version, migration.name)

        if migration.check is not None:
            await migration.check(driver)

        for statement in migration.statements:
            try:
                async with driver.session() as session:
                    await session.run(statement)
            except Exception as exc:
                raise MigrationError(
                    f"Migration {migration.version:03d} ({migration.name}) failed on statement:\n"
                    f"  {statement}\n{type(exc).__name__}: {exc}"
                ) from exc

        await _record_applied(driver, migration.version, migration.name)
        applied_now.append(migration.version)
        logger.info("applied migration %03d %s", migration.version, migration.name)

    return applied_now
