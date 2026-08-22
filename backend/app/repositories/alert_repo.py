"""Persistence for alerts, their occurrences, groups, transitions and suppressions.

This module replaces the one the audit described as "a database view, not a
system". The previous implementation was:

    MATCH (i:Incident) WHERE i.severity IN ['High','Critical']

against nodes the scenario generator wrote at world-build time — one per
storyline, summarising the storyline. Nothing generated an alert, nothing
deduplicated, and the only mutation was a bare `SET i.status = $status` with no
validation and no record of who did it. Alerts now live in PostgreSQL because
they need transactions, constraints and an attributable history, none of which
the graph offers here.

All SQL is static. Filters vary by predicate rather than by string assembly, so
no query is built from caller input.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.database.postgres import acquire, transaction


def _decoded(value: Any) -> Any:
    """asyncpg hands JSONB back as text unless a codec is registered.

    Decoded here, at the repository boundary, rather than by installing a
    connection-wide codec: the same convention `assessment_repo` and
    `correlation_repo` already use, and it keeps the decision visible at the
    place the column is read. Without it the API serialises the column as a JSON
    *string*, and a client doing `"factors" in alert.priority_factors` gets a
    substring search over text that happens not to throw — which is how this
    surfaced as a TypeError in the browser rather than as a failing test.
    """
    return json.loads(value) if isinstance(value, str) else value


def _alert_row(row: Any) -> dict[str, Any]:
    out = dict(row)
    for column in ("priority_factors", "evidence"):
        if column in out:
            out[column] = _decoded(out[column])
    return out

__all__ = [
    "apply_transition",
    "assign_alert",
    "count_groups",
    "count_open_high_priority",
    "count_suppressed",
    "create_suppression",
    "fail_run",
    "finish_run",
    "get_alert",
    "group_rollup",
    "list_alerts",
    "list_suppressions",
    "list_transitions",
    "queue_counts",
    "revoke_suppression",
    "start_run",
    "store_evaluation",
    "latest_evaluation",
    "upsert_alert",
    "upsert_group",
]


# ── runs ──────────────────────────────────────────────────────────────────

async def start_run(
    rules_fingerprint: str,
    assessment_run_id: int | None,
    correlation_run_id: int | None,
) -> int:
    async with acquire() as conn:
        run_id: int = await conn.fetchval(
            """
            INSERT INTO alert_runs (rules_fingerprint, assessment_run_id, correlation_run_id)
            VALUES ($1, $2, $3) RETURNING run_id
            """,
            rules_fingerprint,
            assessment_run_id,
            correlation_run_id,
        )
        return run_id


async def finish_run(run_id: int, **counts: int) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE alert_runs
               SET status = 'complete',
                   finished_at = now(),
                   subjects_considered = $2,
                   firings = $3,
                   alerts_created = $4,
                   alerts_repeated = $5,
                   alerts_suppressed = $6,
                   groups_formed = $7
             WHERE run_id = $1
            """,
            run_id,
            counts.get("subjects_considered", 0),
            counts.get("firings", 0),
            counts.get("alerts_created", 0),
            counts.get("alerts_repeated", 0),
            counts.get("alerts_suppressed", 0),
            counts.get("groups_formed", 0),
        )


async def fail_run(run_id: int, error: str) -> None:
    async with acquire() as conn:
        await conn.execute(
            "UPDATE alert_runs SET status='failed', finished_at=now(), error=$2 WHERE run_id=$1",
            run_id,
            error,
        )


async def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM alert_runs ORDER BY run_id DESC LIMIT $1", limit
        )
    return [dict(r) for r in rows]


# ── groups ────────────────────────────────────────────────────────────────

async def upsert_group(conn: Any, group_key: str, basis: str, subjects: list[str], summary: str) -> None:
    await conn.execute(
        """
        INSERT INTO alert_groups (group_key, basis, subjects, summary)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (group_key) DO UPDATE
            SET last_seen_at = now(),
                summary      = EXCLUDED.summary
        """,
        group_key,
        basis,
        subjects,
        summary,
    )


# ── alerts ────────────────────────────────────────────────────────────────

# The dedup statement. A repeat firing must not create a row, must not reset the
# analyst's state, and must not lose the original sighting — so `state`,
# `assigned_to`, `first_seen_at` and `first_run_id` are all absent from the
# UPDATE. What a repeat does change is the current priority and the evidence
# behind it, because those are statements about now.
#
# `xmax = 0` is the standard way to distinguish an INSERT from an UPDATE in a
# single round trip: on a freshly inserted row the deleting-transaction slot is
# zero, on an updated one it holds the transaction that superseded the old
# version.
_UPSERT_ALERT = """
    INSERT INTO alerts (
        alert_key, rule_id, rule_version, scope, group_key, title, summary,
        priority, priority_band, priority_factors, evidence,
        suppressed, suppressed_by, first_run_id, last_run_id
    )
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$14)
    ON CONFLICT (alert_key) DO UPDATE
        SET occurrence_count = alerts.occurrence_count + 1,
            last_seen_at     = now(),
            last_run_id      = EXCLUDED.last_run_id,
            priority         = EXCLUDED.priority,
            priority_band    = EXCLUDED.priority_band,
            priority_factors = EXCLUDED.priority_factors,
            evidence         = EXCLUDED.evidence,
            summary          = EXCLUDED.summary,
            group_key        = EXCLUDED.group_key,
            suppressed       = EXCLUDED.suppressed,
            suppressed_by    = EXCLUDED.suppressed_by
    RETURNING (xmax = 0) AS created, occurrence_count
"""


async def upsert_alert(
    conn: Any,
    *,
    alert_key: str,
    rule_id: str,
    rule_version: int,
    scope: list[str],
    group_key: str,
    title: str,
    summary: str,
    priority: float,
    priority_band: str,
    priority_factors: str,
    evidence: str,
    suppressed: bool,
    suppressed_by: str | None,
    run_id: int,
) -> tuple[bool, int]:
    """Insert or count. Returns (created, occurrence_count)."""
    row = await conn.fetchrow(
        _UPSERT_ALERT,
        alert_key,
        rule_id,
        rule_version,
        scope,
        group_key,
        title,
        summary,
        priority,
        priority_band,
        priority_factors,
        evidence,
        suppressed,
        suppressed_by,
        run_id,
    )
    return bool(row["created"]), int(row["occurrence_count"])


async def record_occurrence(
    conn: Any, alert_key: str, run_id: int, priority: float, magnitude: float, confidence: float
) -> None:
    # A run that re-fires the same rule on the same scope twice is a bug in the
    # rule, not an occurrence; the unique constraint makes it a no-op rather
    # than a double count.
    await conn.execute(
        """
        INSERT INTO alert_occurrences (alert_key, run_id, priority, magnitude, confidence)
        VALUES ($1,$2,$3,$4,$5)
        ON CONFLICT (alert_key, run_id) DO NOTHING
        """,
        alert_key,
        run_id,
        priority,
        magnitude,
        confidence,
    )


# The column list is repeated in full in every statement below rather than
# interpolated from a shared constant. An f-string around SQL is a pattern worth
# not having in a repository at all: it reads identically whether the inserted
# value is a module constant or a request parameter, so review has to check
# every occurrence to know which. Static text costs some duplication and makes
# the property obvious — the same trade `correlation_repo` makes.

# Four static statements rather than one built from a filter string. Verbose,
# and the verbosity is the point: nothing here concatenates caller input into
# SQL.
_LIST_OPEN = """
    SELECT alert_key, rule_id, rule_version, scope, group_key, title, summary,
           priority, priority_band, priority_factors, evidence, state, assigned_to,
           closed_at, dismissal_reason, suppressed, suppressed_by, occurrence_count,
           first_seen_at, last_seen_at, first_run_id, last_run_id
      FROM alerts
     WHERE state NOT IN ('resolved','dismissed') AND NOT suppressed
     ORDER BY priority DESC, last_seen_at DESC LIMIT $1 OFFSET $2
"""
_LIST_BY_STATE = """
    SELECT alert_key, rule_id, rule_version, scope, group_key, title, summary,
           priority, priority_band, priority_factors, evidence, state, assigned_to,
           closed_at, dismissal_reason, suppressed, suppressed_by, occurrence_count,
           first_seen_at, last_seen_at, first_run_id, last_run_id
      FROM alerts
     WHERE state = $3 AND NOT suppressed
     ORDER BY priority DESC, last_seen_at DESC LIMIT $1 OFFSET $2
"""
_LIST_SUPPRESSED = """
    SELECT alert_key, rule_id, rule_version, scope, group_key, title, summary,
           priority, priority_band, priority_factors, evidence, state, assigned_to,
           closed_at, dismissal_reason, suppressed, suppressed_by, occurrence_count,
           first_seen_at, last_seen_at, first_run_id, last_run_id
      FROM alerts
     WHERE suppressed
     ORDER BY priority DESC, last_seen_at DESC LIMIT $1 OFFSET $2
"""
_LIST_ALL = """
    SELECT alert_key, rule_id, rule_version, scope, group_key, title, summary,
           priority, priority_band, priority_factors, evidence, state, assigned_to,
           closed_at, dismissal_reason, suppressed, suppressed_by, occurrence_count,
           first_seen_at, last_seen_at, first_run_id, last_run_id
      FROM alerts
     ORDER BY priority DESC, last_seen_at DESC LIMIT $1 OFFSET $2
"""
_LIST_FOR_GROUP = """
    SELECT alert_key, rule_id, rule_version, scope, group_key, title, summary,
           priority, priority_band, priority_factors, evidence, state, assigned_to,
           closed_at, dismissal_reason, suppressed, suppressed_by, occurrence_count,
           first_seen_at, last_seen_at, first_run_id, last_run_id
      FROM alerts
     WHERE group_key = $3
     ORDER BY priority DESC, last_seen_at DESC LIMIT $1 OFFSET $2
"""
_LIST_FOR_SUBJECT = """
    SELECT alert_key, rule_id, rule_version, scope, group_key, title, summary,
           priority, priority_band, priority_factors, evidence, state, assigned_to,
           closed_at, dismissal_reason, suppressed, suppressed_by, occurrence_count,
           first_seen_at, last_seen_at, first_run_id, last_run_id
      FROM alerts
     WHERE $3 = ANY(scope)
     ORDER BY priority DESC, last_seen_at DESC LIMIT $1 OFFSET $2
"""

_COUNT_OPEN = "SELECT count(*) FROM alerts WHERE state NOT IN ('resolved','dismissed') AND NOT suppressed"
_COUNT_BY_STATE = "SELECT count(*) FROM alerts WHERE state = $1 AND NOT suppressed"
_COUNT_SUPPRESSED = "SELECT count(*) FROM alerts WHERE suppressed"
_COUNT_ALL = "SELECT count(*) FROM alerts"
_COUNT_FOR_GROUP = "SELECT count(*) FROM alerts WHERE group_key = $1"
_COUNT_FOR_SUBJECT = "SELECT count(*) FROM alerts WHERE $1 = ANY(scope)"

_GET_ALERT = """
    SELECT alert_key, rule_id, rule_version, scope, group_key, title, summary,
           priority, priority_band, priority_factors, evidence, state, assigned_to,
           closed_at, dismissal_reason, suppressed, suppressed_by, occurrence_count,
           first_seen_at, last_seen_at, first_run_id, last_run_id
      FROM alerts WHERE alert_key = $1
"""

_ASSIGN_ALERT = """
    UPDATE alerts SET assigned_to = $2 WHERE alert_key = $1
    RETURNING alert_key, rule_id, rule_version, scope, group_key, title, summary,
           priority, priority_band, priority_factors, evidence, state, assigned_to,
           closed_at, dismissal_reason, suppressed, suppressed_by, occurrence_count,
           first_seen_at, last_seen_at, first_run_id, last_run_id
"""

_MOVE_ALERT = """
    UPDATE alerts
       SET state            = $2,
           dismissal_reason = CASE WHEN $2 = 'dismissed' THEN $3 ELSE NULL END,
           closed_at        = CASE WHEN $4 THEN now() ELSE NULL END
     WHERE alert_key = $1 AND state = $5
    RETURNING alert_key, rule_id, rule_version, scope, group_key, title, summary,
           priority, priority_band, priority_factors, evidence, state, assigned_to,
           closed_at, dismissal_reason, suppressed, suppressed_by, occurrence_count,
           first_seen_at, last_seen_at, first_run_id, last_run_id
"""


async def list_alerts(
    *,
    state: str | None = None,
    include_suppressed: bool = False,
    suppressed_only: bool = False,
    group_key: str | None = None,
    subject_ref: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    offset = (page - 1) * page_size
    async with acquire() as conn:
        if subject_ref is not None:
            rows = await conn.fetch(_LIST_FOR_SUBJECT, page_size, offset, subject_ref)
            total = await conn.fetchval(_COUNT_FOR_SUBJECT, subject_ref)
        elif group_key is not None:
            rows = await conn.fetch(_LIST_FOR_GROUP, page_size, offset, group_key)
            total = await conn.fetchval(_COUNT_FOR_GROUP, group_key)
        elif suppressed_only:
            rows = await conn.fetch(_LIST_SUPPRESSED, page_size, offset)
            total = await conn.fetchval(_COUNT_SUPPRESSED)
        elif state is not None:
            rows = await conn.fetch(_LIST_BY_STATE, page_size, offset, state)
            total = await conn.fetchval(_COUNT_BY_STATE, state)
        elif include_suppressed:
            rows = await conn.fetch(_LIST_ALL, page_size, offset)
            total = await conn.fetchval(_COUNT_ALL)
        else:
            rows = await conn.fetch(_LIST_OPEN, page_size, offset)
            total = await conn.fetchval(_COUNT_OPEN)
    return [_alert_row(r) for r in rows], int(total or 0)


async def get_alert(alert_key: str) -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(_GET_ALERT, alert_key)
    return _alert_row(row) if row else None


async def queue_counts() -> dict[str, int]:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT count(*)                                                  AS total,
                   count(*) FILTER (WHERE state = 'open' AND NOT suppressed)  AS open,
                   count(*) FILTER (WHERE state = 'acknowledged')             AS acknowledged,
                   count(*) FILTER (WHERE state = 'investigating')            AS investigating,
                   count(*) FILTER (WHERE state = 'resolved')                 AS resolved,
                   count(*) FILTER (WHERE state = 'dismissed')                AS dismissed,
                   count(*) FILTER (WHERE suppressed)                         AS suppressed
            FROM alerts
            """
        )
    return {k: int(v) for k, v in dict(row).items()} if row else {}


async def count_open_high_priority() -> int:
    """Open, unsuppressed alerts in the top priority band.

    The dashboard puts this in one sentence with `open_alerts`, so it must share
    that denominator: both count over every alert, never over a display list.
    The audit found exactly that mistake — "N alerts are open, M of them
    critical", where M was filtered from a six-row preview and so could never
    exceed six whatever the data held (B-05).
    """
    async with acquire() as conn:
        return int(
            await conn.fetchval(
                "SELECT count(*) FROM alerts "
                "WHERE state NOT IN ('resolved','dismissed') AND NOT suppressed "
                "AND priority_band = 'high'"
            )
            or 0
        )


async def count_suppressed() -> int:
    async with acquire() as conn:
        return int(await conn.fetchval(_COUNT_SUPPRESSED) or 0)


async def count_groups() -> int:
    """Groups holding at least one alert.

    Separate from `group_rollup`'s row count on purpose. The rollup is paginated
    and a caller that counts what it received is reporting its own page size —
    the precise mistake the audit found twice on the old alert surface, where a
    truncated list supplied a figure presented as a total.
    """
    async with acquire() as conn:
        return int(
            await conn.fetchval("SELECT count(*) FROM alert_group_rollup WHERE alert_count > 0") or 0
        )


async def group_rollup(limit: int = 50) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM alert_group_rollup
             WHERE alert_count > 0
             -- Largest groups first, then priority. Ordering by priority alone
             -- floats single-alert "groups" to the top, which is precisely what
             -- this view exists to get out of an analyst's way.
             ORDER BY alert_count DESC, top_priority DESC NULLS LAST, last_seen_at DESC
             LIMIT $1
            """,
            limit,
        )
    return [dict(r) for r in rows]


# ── transitions ───────────────────────────────────────────────────────────

async def apply_transition(
    *,
    alert_key: str,
    from_state: str,
    to_state: str,
    reason_code: str | None,
    note: str | None,
    actor_username: str,
    actor_role: str,
    terminal: bool,
) -> dict[str, Any] | None:
    """Write the history row and move the alert, in one transaction.

    Both or neither: an alert whose state moved without a transition row is
    exactly the unanswerable-history problem this phase exists to fix, and a
    transition row without the move is a lie about the current state.

    The UPDATE is guarded on `state = from_state`, so two analysts triaging the
    same alert concurrently cannot both succeed — the second sees the row it
    expected to change was not there and gets a conflict rather than silently
    overwriting the first.
    """
    async with transaction() as conn:
        await conn.execute(
            """
            INSERT INTO alert_transitions
                (alert_key, from_state, to_state, reason_code, note, actor_username, actor_role)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            """,
            alert_key,
            from_state,
            to_state,
            reason_code,
            note,
            actor_username,
            actor_role,
        )
        row = await conn.fetchrow(
            _MOVE_ALERT,
            alert_key,
            to_state,
            reason_code,
            terminal,
            from_state,
        )
    return _alert_row(row) if row else None


async def assign_alert(alert_key: str, assignee: str | None) -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(_ASSIGN_ALERT, alert_key, assignee)
    return _alert_row(row) if row else None


async def list_transitions(alert_key: str) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT transition_id, from_state, to_state, reason_code, note,
                   actor_username, actor_role, occurred_at
              FROM alert_transitions WHERE alert_key = $1 ORDER BY occurred_at ASC
            """,
            alert_key,
        )
    return [dict(r) for r in rows]


async def list_occurrences(alert_key: str, limit: int = 50) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT occurrence_id, run_id, priority, magnitude, confidence, observed_at
              FROM alert_occurrences WHERE alert_key = $1
             ORDER BY observed_at DESC LIMIT $2
            """,
            alert_key,
            limit,
        )
    return [dict(r) for r in rows]


# ── suppressions ──────────────────────────────────────────────────────────

async def create_suppression(
    *,
    rule_id: str | None,
    subject_ref: str | None,
    reason_code: str,
    note: str,
    created_by: str,
    expires_at: datetime,
) -> dict[str, Any]:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO alert_suppressions (rule_id, subject_ref, reason_code, note, created_by, expires_at)
            VALUES ($1,$2,$3,$4,$5,$6)
            RETURNING suppression_id, rule_id, subject_ref, reason_code, note,
                      created_by, created_at, expires_at, revoked_at, revoked_by
            """,
            rule_id,
            subject_ref,
            reason_code,
            note,
            created_by,
            expires_at,
        )
    return dict(row)


async def revoke_suppression(suppression_id: str, revoked_by: str) -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE alert_suppressions
               SET revoked_at = now(), revoked_by = $2
             WHERE suppression_id = $1::uuid AND revoked_at IS NULL
            RETURNING suppression_id, rule_id, subject_ref, reason_code, note,
                      created_by, created_at, expires_at, revoked_at, revoked_by
            """,
            suppression_id,
            revoked_by,
        )
    return dict(row) if row else None


async def list_suppressions(active_only: bool = False) -> list[dict[str, Any]]:
    async with acquire() as conn:
        if active_only:
            rows = await conn.fetch(
                """
                SELECT suppression_id, rule_id, subject_ref, reason_code, note,
                       created_by, created_at, expires_at, revoked_at, revoked_by
                  FROM alert_suppressions
                 WHERE revoked_at IS NULL AND expires_at > now()
                 ORDER BY created_at DESC
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT suppression_id, rule_id, subject_ref, reason_code, note,
                       created_by, created_at, expires_at, revoked_at, revoked_by
                  FROM alert_suppressions ORDER BY created_at DESC
                """
            )
    return [dict(r) for r in rows]


# ── evaluation ────────────────────────────────────────────────────────────

async def store_evaluation(
    *,
    run_id: int,
    rules_fingerprint: str,
    alerts_total: int,
    subjects_alerted: int,
    precision_strict: float | None,
    recall: float | None,
    per_rule: str,
    unreachable: str,
) -> int:
    async with acquire() as conn:
        evaluation_id: int = await conn.fetchval(
            """
            INSERT INTO alert_evaluations
                (run_id, rules_fingerprint, alerts_total, subjects_alerted,
                 precision_strict, recall, per_rule, unreachable)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            RETURNING evaluation_id
            """,
            run_id,
            rules_fingerprint,
            alerts_total,
            subjects_alerted,
            precision_strict,
            recall,
            per_rule,
            unreachable,
        )
        return evaluation_id


async def latest_evaluation() -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM alert_evaluations ORDER BY evaluation_id DESC LIMIT 1"
        )
    if row is None:
        return None
    out = dict(row)
    for column in ("per_rule", "unreachable"):
        out[column] = _decoded(out[column])
    return out
