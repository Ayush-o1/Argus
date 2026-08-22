"""Storing exports, logging every access to them, and disposing of them on schedule.

All SQL is static. The one rule this module enforces beyond the schema is that
**an access row is written on the same connection as the thing it records**, so
a read cannot succeed while its log entry fails — a custody log with gaps in
exactly the cases where writing failed is worse than none, because it looks
complete.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.database.postgres import acquire, transaction
from app.evidence.classification import retention_days

__all__ = [
    "count_exports",
    "create_export",
    "dispose_expired",
    "due_for_disposal",
    "fetch_export",
    "fetch_export_content",
    "list_access",
    "list_exports",
    "log_access",
]

_INSERT_EXPORT = """
    INSERT INTO exports
        (export_id, subject_kind, investigation_id, format, classification,
         content, content_sha256, byte_size, requested_by, requester_role,
         requester_clearance, request_ip, purpose, retention_until)
    VALUES ($1, 'investigation', $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
    RETURNING export_id, requested_at, retention_until
"""

_INSERT_ACCESS = """
    INSERT INTO export_access
        (export_id, action, actor_username, actor_role, actor_clearance,
         ip_address, outcome, detail)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
"""

# Content is deliberately excluded from every listing statement below. Reading
# metadata must not drag megabytes across for a row nobody asked to download,
# and — more importantly — it keeps "read the metadata" and "read the content"
# as two operations that log two different actions.
#
# The column list is written out in each statement rather than interpolated from
# a shared constant. An f-string here would be flagged by bandit as B608 and the
# honest answer to that is a static statement, not an annotation saying the
# warning is wrong — the convention Phase 7 settled on when `alert_repo` had the
# same choice.

_SELECT_EXPORT = """
    SELECT export_id, subject_kind, investigation_id, format, classification,
           content_sha256, byte_size, requested_by, requester_role, requester_clearance,
           requested_at, request_ip, purpose, retention_until,
           disposed_at, disposed_by, disposal_reason
    FROM exports WHERE export_id = $1
"""

_SELECT_CONTENT = """
    SELECT content, content_sha256, classification, disposed_at
    FROM exports WHERE export_id = $1
"""

_LIST_EXPORTS = """
    SELECT export_id, subject_kind, investigation_id, format, classification,
           content_sha256, byte_size, requested_by, requester_role, requester_clearance,
           requested_at, request_ip, purpose, retention_until,
           disposed_at, disposed_by, disposal_reason
    FROM exports ORDER BY requested_at DESC LIMIT $1 OFFSET $2
"""

_LIST_FOR_INVESTIGATION = """
    SELECT export_id, subject_kind, investigation_id, format, classification,
           content_sha256, byte_size, requested_by, requester_role, requester_clearance,
           requested_at, request_ip, purpose, retention_until,
           disposed_at, disposed_by, disposal_reason
    FROM exports WHERE investigation_id = $1 ORDER BY requested_at DESC
"""

_COUNT_EXPORTS = "SELECT count(*) AS total FROM exports"

_LIST_ACCESS = """
    SELECT access_id, action, actor_username, actor_role, actor_clearance,
           occurred_at, ip_address, outcome, detail
    FROM export_access WHERE export_id = $1 ORDER BY occurred_at, access_id
"""


async def create_export(
    *,
    investigation_id: str,
    format_: str,
    classification: str,
    content: bytes,
    sha256: str,
    requested_by: str,
    requester_role: str,
    requester_clearance: str,
    purpose: str,
    request_ip: str | None,
) -> dict[str, Any]:
    """Store an artifact and record its creation as the first access to it.

    Both in one transaction. The creation entry is written here rather than left
    to the caller so the access log starts at the moment the bytes existed —
    a log that begins with the second reader cannot answer who produced it.
    """
    export_id = str(uuid.uuid4())
    retain_until = datetime.now(UTC) + timedelta(days=retention_days(classification))

    async with transaction() as conn:
        row = await conn.fetchrow(
            _INSERT_EXPORT,
            export_id,
            investigation_id,
            format_,
            classification,
            content,
            sha256,
            len(content),
            requested_by,
            requester_role,
            requester_clearance,
            request_ip,
            purpose,
            retain_until,
        )
        await conn.execute(
            _INSERT_ACCESS,
            export_id,
            "created",
            requested_by,
            requester_role,
            requester_clearance,
            request_ip,
            "success",
            purpose,
        )
    return {
        "export_id": row["export_id"],
        "requested_at": row["requested_at"],
        "retention_until": row["retention_until"],
        "content_sha256": sha256,
        "byte_size": len(content),
        "classification": classification,
        "format": format_,
    }


async def log_access(
    *,
    export_id: str,
    action: str,
    actor_username: str,
    actor_role: str,
    actor_clearance: str,
    ip_address: str | None = None,
    outcome: str = "success",
    detail: str | None = None,
) -> None:
    """Record an access. Called for refusals as well as successes.

    A denied read is the more interesting of the two and is the one a log like
    this exists to capture, so `outcome='denied'` is a first-class value rather
    than an omission.
    """
    async with acquire() as conn:
        await conn.execute(
            _INSERT_ACCESS,
            export_id,
            action,
            actor_username,
            actor_role,
            actor_clearance,
            ip_address,
            outcome,
            detail,
        )


async def fetch_export(export_id: str) -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(_SELECT_EXPORT, export_id)
    return dict(row) if row else None


async def fetch_export_content(export_id: str) -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(_SELECT_CONTENT, export_id)
    return dict(row) if row else None


async def list_exports(*, investigation_id: str | None, limit: int, offset: int) -> list[dict[str, Any]]:
    async with acquire() as conn:
        if investigation_id is not None:
            rows = await conn.fetch(_LIST_FOR_INVESTIGATION, investigation_id)
        else:
            rows = await conn.fetch(_LIST_EXPORTS, limit, offset)
    return [dict(r) for r in rows]


async def count_exports() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow(_COUNT_EXPORTS)
    return int(row["total"]) if row else 0


async def list_access(export_id: str) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(_LIST_ACCESS, export_id)
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Retention
# ─────────────────────────────────────────────────────────────────────────────

_DUE = """
    SELECT export_id, subject_kind, investigation_id, format, classification,
           content_sha256, byte_size, requested_by, requester_role, requester_clearance,
           requested_at, request_ip, purpose, retention_until,
           disposed_at, disposed_by, disposal_reason
    FROM exports
     WHERE disposed_at IS NULL AND retention_until <= now()
     ORDER BY retention_until
     LIMIT $1
"""

# Empties the content and records the disposal in one statement, which is what
# the schema's trigger requires — it refuses an empty content without a
# disposal, so the two cannot come apart even if this were called wrongly.
_DISPOSE = """
    UPDATE exports
       SET content = ''::bytea,
           disposed_at = now(),
           disposed_by = $2,
           disposal_reason = $3
     WHERE export_id = $1 AND disposed_at IS NULL
    RETURNING export_id, classification, requested_by, content_sha256
"""


async def due_for_disposal(limit: int = 500) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(_DUE, limit)
    return [dict(r) for r in rows]


async def dispose_expired(*, actor: str = "retention.scheduler", limit: int = 500) -> list[dict[str, Any]]:
    """Destroy the content of every export past its retention date.

    The row survives with its hash, its requester and its purpose intact. "An
    export of this investigation was made on this date by this person and has
    since been destroyed on schedule" is a more useful record than the bytes
    were, and deleting the row would leave no trace that the export ever
    happened — which is the opposite of what a retention policy is for.

    Each disposal writes an access-log entry, so a disposal is as visible as a
    download.
    """
    disposed: list[dict[str, Any]] = []
    async with transaction() as conn:
        rows = await conn.fetch(_DUE, limit)
        for row in rows:
            done = await conn.fetchrow(
                _DISPOSE,
                row["export_id"],
                actor,
                "retention period elapsed",
            )
            if done is None:
                continue
            await conn.execute(
                _INSERT_ACCESS,
                row["export_id"],
                "disposed",
                actor,
                "system",
                row["classification"],
                None,
                "success",
                f"retention elapsed {row['retention_until'].isoformat()}",
            )
            disposed.append(dict(done))
    return disposed
