"""Forward-only Neo4j schema migrations.

Before this module the schema was a side effect of running the data generator
(`generator/generators/neo4j_writer.py` created constraints and indexes on every
world build). That meant a deployed backend could not acquire a new index
without someone re-running the generator against production data — and the
generator's default path begins by wiping the graph.

Migrations here are:
  - **numbered and forward-only** — no down-migrations. Rolling back schema on a
    live graph is more dangerous than rolling forward, and every migration below
    is written to be safe to leave in place.
  - **idempotent** — each uses IF NOT EXISTS or an equivalent guard, so a partial
    application can simply be re-run.
  - **applied at backend startup**, recorded on a single :SchemaVersion node.

Add a migration by appending to MIGRATIONS with the next sequential version.
Never renumber or edit an already-released migration — write a new one.
"""

from app.database.migrations.runner import (
    MIGRATIONS,
    Migration,
    applied_versions,
    current_version,
    run_migrations,
)

__all__ = [
    "MIGRATIONS",
    "Migration",
    "applied_versions",
    "current_version",
    "run_migrations",
]
