"""Database access for ingestion: connectors, batches, raw landing, the DLQ.

Reads and writes only. Everything that decides *what* to do — whether a record
is valid, whether a source has drifted, whether to quarantine — lives in
`app/services/ingest.py`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from app.database.postgres import acquire


@dataclass(frozen=True)
class ConnectorRow:
    connector_id: str
    source_id: str
    connector_type: str
    display_name: str
    config: dict[str, Any]
    mapping: dict[str, Any]
    enabled: bool
    poll_interval_seconds: int
    quarantined_at: datetime | None
    quarantine_reason: str | None
    cursor: str | None
    last_run_at: datetime | None
    last_success_at: datetime | None

    @property
    def is_runnable(self) -> bool:
        return self.enabled and self.quarantined_at is None


def _connector_from_row(row: asyncpg.Record) -> ConnectorRow:
    return ConnectorRow(
        connector_id=row["connector_id"],
        source_id=row["source_id"],
        connector_type=row["connector_type"],
        display_name=row["display_name"],
        config=json.loads(row["config"]),
        mapping=json.loads(row["mapping"]),
        enabled=row["enabled"],
        poll_interval_seconds=row["poll_interval_seconds"],
        quarantined_at=row["quarantined_at"],
        quarantine_reason=row["quarantine_reason"],
        cursor=row["cursor"],
        last_run_at=row["last_run_at"],
        last_success_at=row["last_success_at"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Connectors
# ─────────────────────────────────────────────────────────────────────────────


async def upsert_connector(
    *,
    connector_id: str,
    source_id: str,
    connector_type: str,
    display_name: str,
    config: dict[str, Any],
    mapping: dict[str, Any],
    poll_interval_seconds: int = 300,
    enabled: bool = True,
) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO connectors (
                connector_id, source_id, connector_type, display_name,
                config, mapping, poll_interval_seconds, enabled
            ) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8)
            ON CONFLICT (connector_id) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                config = EXCLUDED.config,
                mapping = EXCLUDED.mapping,
                poll_interval_seconds = EXCLUDED.poll_interval_seconds,
                enabled = EXCLUDED.enabled
            """,
            connector_id,
            source_id,
            connector_type,
            display_name,
            json.dumps(config),
            json.dumps(mapping),
            poll_interval_seconds,
            enabled,
        )


async def get_connector(connector_id: str) -> ConnectorRow | None:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM connectors WHERE connector_id = $1", connector_id)
    return _connector_from_row(row) if row else None


async def list_connectors() -> list[ConnectorRow]:
    async with acquire() as conn:
        rows = await conn.fetch("SELECT * FROM connectors ORDER BY connector_id")
    return [_connector_from_row(row) for row in rows]


async def due_connectors() -> list[ConnectorRow]:
    """Connectors whose poll interval has elapsed.

    Quarantined and disabled connectors are excluded here rather than filtered
    later, so a quarantine actually stops work instead of merely labelling it.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM connectors
             WHERE enabled AND quarantined_at IS NULL
               AND (last_run_at IS NULL
                    OR last_run_at < now() - make_interval(secs => poll_interval_seconds))
             ORDER BY last_run_at ASC NULLS FIRST
            """
        )
    return [_connector_from_row(row) for row in rows]


async def mark_run(connector_id: str, *, succeeded: bool, cursor: str | None) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE connectors
               SET last_run_at = now(),
                   last_success_at = CASE WHEN $2 THEN now() ELSE last_success_at END,
                   cursor = COALESCE($3, cursor)
             WHERE connector_id = $1
            """,
            connector_id,
            succeeded,
            cursor,
        )


async def set_quarantine(connector_id: str, reason: str | None) -> None:
    """Quarantine or release a connector. `reason=None` releases it."""
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE connectors
               SET quarantined_at = CASE WHEN $2::text IS NULL THEN NULL ELSE now() END,
                   quarantine_reason = $2
             WHERE connector_id = $1
            """,
            connector_id,
            reason,
        )


async def set_enabled(connector_id: str, enabled: bool) -> None:
    async with acquire() as conn:
        await conn.execute(
            "UPDATE connectors SET enabled = $2 WHERE connector_id = $1", connector_id, enabled
        )


# ─────────────────────────────────────────────────────────────────────────────
# Batches
# ─────────────────────────────────────────────────────────────────────────────


async def start_batch(connector_id: str) -> int:
    async with acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO ingest_batches (connector_id) VALUES ($1) RETURNING batch_id",
            connector_id,
        )


async def finish_batch(
    batch_id: int,
    *,
    status: str,
    fetched: int = 0,
    new: int = 0,
    duplicate: int = 0,
    failed: int = 0,
    error: str | None = None,
) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE ingest_batches
               SET finished_at = now(), status = $2, records_fetched = $3,
                   records_new = $4, records_duplicate = $5, records_failed = $6,
                   error = $7
             WHERE batch_id = $1
            """,
            batch_id,
            status,
            fetched,
            new,
            duplicate,
            failed,
            error[:4000] if error else None,
        )


async def recent_batches(connector_id: str, limit: int = 20) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT batch_id, started_at, finished_at, status, records_fetched,
                   records_new, records_duplicate, records_failed, error
              FROM ingest_batches
             WHERE connector_id = $1
             ORDER BY started_at DESC LIMIT $2
            """,
            connector_id,
            limit,
        )
    return [dict(row) for row in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Raw landing
# ─────────────────────────────────────────────────────────────────────────────


async def land_raw(
    conn: asyncpg.Connection,
    *,
    connector_id: str,
    batch_id: int,
    content_hash: str,
    payload: dict[str, Any],
) -> int | None:
    """Store a raw record. Returns its id, or None if already seen.

    The uniqueness constraint on `(connector_id, content_hash)` is the first of
    two idempotency layers — the second is the observation's own content hash.
    Both exist because they catch different things: this one stops a re-read of
    the same file doing any work at all, the other stops two connectors for the
    same source double-counting corroboration.
    """
    return await conn.fetchval(
        """
        INSERT INTO raw_records (connector_id, batch_id, content_hash, payload)
        VALUES ($1, $2, $3, $4::jsonb)
        ON CONFLICT (connector_id, content_hash) DO NOTHING
        RETURNING raw_id
        """,
        connector_id,
        batch_id,
        content_hash,
        json.dumps(payload, default=str),
    )


async def mark_raw(
    conn: asyncpg.Connection,
    raw_id: int,
    *,
    status: str,
    observation_id: str | None = None,
) -> None:
    await conn.execute(
        """
        UPDATE raw_records
           SET status = $2, processed_at = now(), observation_id = $3::uuid
         WHERE raw_id = $1
        """,
        raw_id,
        status,
        observation_id,
    )


async def get_raw(raw_id: int) -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM raw_records WHERE raw_id = $1", raw_id)
    if row is None:
        return None
    record = dict(row)
    record["payload"] = json.loads(record["payload"])
    return record


# ─────────────────────────────────────────────────────────────────────────────
# Dead-letter queue
# ─────────────────────────────────────────────────────────────────────────────


async def record_failure(
    conn: asyncpg.Connection,
    *,
    connector_id: str,
    batch_id: int | None,
    raw_id: int | None,
    stage: str,
    error_type: str,
    error_detail: str,
) -> int:
    return await conn.fetchval(
        """
        INSERT INTO ingest_failures
            (connector_id, batch_id, raw_id, stage, error_type, error_detail)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING failure_id
        """,
        connector_id,
        batch_id,
        raw_id,
        stage,
        error_type,
        error_detail[:4000],
    )


async def list_failures(
    *, connector_id: str | None = None, include_resolved: bool = False, limit: int = 100
) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT f.*, c.display_name AS connector_name
              FROM ingest_failures f
              JOIN connectors c ON c.connector_id = f.connector_id
             WHERE ($1::text IS NULL OR f.connector_id = $1)
               AND ($2::boolean OR f.resolved_at IS NULL)
             ORDER BY f.occurred_at DESC
             LIMIT $3
            """,
            connector_id,
            include_resolved,
            limit,
        )
    return [dict(row) for row in rows]


async def open_failure_count(connector_id: str | None = None) -> int:
    async with acquire() as conn:
        return (
            await conn.fetchval(
                """
                SELECT count(*) FROM ingest_failures
                 WHERE resolved_at IS NULL AND ($1::text IS NULL OR connector_id = $1)
                """,
                connector_id,
            )
            or 0
        )


async def resolve_failure(
    failure_id: int, *, resolved_by: str, resolution: str, replayed: bool
) -> bool:
    async with acquire() as conn:
        status = await conn.execute(
            """
            UPDATE ingest_failures
               SET resolved_at = now(), resolved_by = $2, resolution = $3,
                   replay_count = replay_count + CASE WHEN $4 THEN 1 ELSE 0 END
             WHERE failure_id = $1 AND resolved_at IS NULL
            """,
            failure_id,
            resolved_by,
            resolution,
            replayed,
        )
    return status.endswith(" 1")


async def get_failure(failure_id: int) -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM ingest_failures WHERE failure_id = $1", failure_id)
    return dict(row) if row else None


# ─────────────────────────────────────────────────────────────────────────────
# Field statistics — schema-drift detection
# ─────────────────────────────────────────────────────────────────────────────


async def record_field_paths(
    conn: asyncpg.Connection, connector_id: str, paths: set[str]
) -> set[str]:
    """Record which fields were seen. Returns those never seen before.

    The return value is what makes a new field *detectable*: a source that
    silently starts emitting something new is a schema change, and a schema
    change is a signal that whatever ARGUS derives from that feed may no longer
    mean what it did.
    """
    if not paths:
        return set()

    known = {
        row["field_path"]
        for row in await conn.fetch(
            "SELECT field_path FROM connector_field_stats WHERE connector_id = $1", connector_id
        )
    }
    await conn.executemany(
        """
        INSERT INTO connector_field_stats (connector_id, field_path, occurrences)
        VALUES ($1, $2, 1)
        ON CONFLICT (connector_id, field_path) DO UPDATE
            SET occurrences = connector_field_stats.occurrences + 1,
                last_seen_at = now()
        """,
        [(connector_id, path) for path in sorted(paths)],
    )
    return paths - known


async def known_fields(connector_id: str) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT field_path, first_seen_at, last_seen_at, occurrences
              FROM connector_field_stats WHERE connector_id = $1
             ORDER BY field_path
            """,
            connector_id,
        )
    return [dict(row) for row in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────


async def health_rows() -> list[dict[str, Any]]:
    """Per-connector health, computed from what actually happened.

    Derived from `ingest_batches` rather than maintained as counters, so the
    numbers cannot drift from the events they describe — a counter that is
    updated in one code path and forgotten in another is how a dashboard comes
    to disagree with reality.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                c.connector_id,
                c.display_name,
                c.source_id,
                c.connector_type,
                c.enabled,
                c.quarantined_at,
                c.quarantine_reason,
                c.poll_interval_seconds,
                c.last_run_at,
                c.last_success_at,
                c.created_at,
                s.name             AS source_name,
                s.reliability      AS source_reliability,
                s.is_synthetic     AS source_is_synthetic,
                s.staleness_hours  AS staleness_hours,
                COALESCE(b.batches_24h, 0)      AS batches_24h,
                COALESCE(b.failed_batches_24h, 0) AS failed_batches_24h,
                COALESCE(b.records_24h, 0)      AS records_24h,
                COALESCE(b.new_24h, 0)          AS new_24h,
                COALESCE(b.failed_records_24h, 0) AS failed_records_24h,
                COALESCE(f.open_failures, 0)    AS open_failures
              FROM connectors c
              JOIN sources s ON s.source_id = c.source_id
              LEFT JOIN (
                    SELECT connector_id,
                           count(*)                                  AS batches_24h,
                           count(*) FILTER (WHERE status = 'failed') AS failed_batches_24h,
                           sum(records_fetched)                      AS records_24h,
                           sum(records_new)                          AS new_24h,
                           sum(records_failed)                       AS failed_records_24h
                      FROM ingest_batches
                     WHERE started_at > now() - interval '24 hours'
                     GROUP BY connector_id
              ) b ON b.connector_id = c.connector_id
              LEFT JOIN (
                    SELECT connector_id, count(*) AS open_failures
                      FROM ingest_failures WHERE resolved_at IS NULL
                     GROUP BY connector_id
              ) f ON f.connector_id = c.connector_id
             ORDER BY c.connector_id
            """
        )
    return [dict(row) for row in rows]


async def volume_baseline(connector_id: str, *, window: int = 20) -> dict[str, float] | None:
    """Mean and standard deviation of records per successful batch.

    Used to notice a feed that is still succeeding but has quietly stopped
    carrying data — the failure mode no error rate catches, because nothing
    errored.
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT avg(records_fetched)::float AS mean,
                   coalesce(stddev_pop(records_fetched), 0)::float AS stddev,
                   count(*)                    AS samples
              FROM (
                    SELECT records_fetched FROM ingest_batches
                     WHERE connector_id = $1 AND status = 'succeeded'
                     ORDER BY started_at DESC LIMIT $2
              ) recent
            """,
            connector_id,
            window,
        )
    if row is None or not row["samples"]:
        return None
    return {"mean": row["mean"], "stddev": row["stddev"], "samples": row["samples"]}
