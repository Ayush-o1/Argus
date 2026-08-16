"""Persistence for entity resolution.

Two things in here are load-bearing and easy to get subtly wrong, so they are
centralised rather than left to callers:

  * **Pair ordering.** Every read and write goes through `order_pair`, so a
    pair has exactly one identity no matter which way round a caller holds it.
    The database enforces `left_ref < right_ref` as a backstop.
  * **Current decision.** There is no "active" flag to keep in step. The
    current decision for a pair is the highest `decision_id`, computed by the
    `resolution_current_decisions` view. Reversal is an INSERT.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from app.database.postgres import acquire
from app.resolution.blocking import order_pair
from app.resolution.scoring import MatchResult


@dataclass(frozen=True)
class CandidateRow:
    candidate_id: int
    run_id: int | None
    entity_type: str
    left_ref: str
    right_ref: str
    score: float | None
    evidence_weight: float
    band: str
    band_reason: str
    comparisons: list[dict[str, Any]]
    blocking_keys: list[str]
    model_version: str
    model_fingerprint: str
    status: str
    created_at: datetime
    updated_at: datetime
    withdrawn_at: datetime | None = None
    withdrawn_reason: str | None = None


@dataclass(frozen=True)
class DecisionRow:
    decision_id: int
    entity_type: str
    left_ref: str
    right_ref: str
    verdict: str
    decided_by: str
    decided_by_kind: str
    decided_at: datetime
    rationale: str
    score: float | None
    evidence_weight: float | None
    model_version: str | None
    model_fingerprint: str | None
    candidate_id: int | None
    reverses_decision_id: int | None
    # Resolved at read time, never stored — same reasoning as assertions in
    # Phase 2. The row is immutable, so a denormalised username would freeze at
    # write time and a later rename would attribute a merge to a name that no
    # longer exists. COALESCE falls back to the raw identifier when the user is
    # gone, which is the honest answer rather than a blank byline.
    decided_by_display: str = ""


# The matcher decides under its own name rather than a person's, so the join
# has to fall through to the raw identifier for those rows — `argus.matcher`
# reads correctly on its own.
_DECISION_SELECT = """
    SELECT d.*, COALESCE(u.display_name, d.decided_by) AS decided_by_display
      FROM {source} d
      LEFT JOIN users u
             ON d.decided_by LIKE 'user:%'
            AND u.id::text = substring(d.decided_by from 6)
"""


def _candidate_from_row(row: asyncpg.Record) -> CandidateRow:
    return CandidateRow(
        candidate_id=row["candidate_id"],
        run_id=row["run_id"],
        entity_type=row["entity_type"],
        left_ref=row["left_ref"],
        right_ref=row["right_ref"],
        score=row["score"],
        evidence_weight=row["evidence_weight"],
        band=row["band"],
        band_reason=row["band_reason"],
        comparisons=json.loads(row["comparisons"]),
        blocking_keys=list(row["blocking_keys"] or []),
        model_version=row["model_version"],
        model_fingerprint=row["model_fingerprint"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        withdrawn_at=row["withdrawn_at"],
        withdrawn_reason=row["withdrawn_reason"],
    )


def _decision_from_row(row: asyncpg.Record) -> DecisionRow:
    return DecisionRow(
        decision_id=row["decision_id"],
        entity_type=row["entity_type"],
        left_ref=row["left_ref"],
        right_ref=row["right_ref"],
        verdict=row["verdict"],
        decided_by=row["decided_by"],
        decided_by_kind=row["decided_by_kind"],
        decided_at=row["decided_at"],
        rationale=row["rationale"],
        score=row["score"],
        evidence_weight=row["evidence_weight"],
        model_version=row["model_version"],
        model_fingerprint=row["model_fingerprint"],
        candidate_id=row["candidate_id"],
        reverses_decision_id=row["reverses_decision_id"],
        decided_by_display=row["decided_by_display"],
    )


# ── Runs ─────────────────────────────────────────────────────────────────────


async def start_run(
    *, entity_types: list[str], model_version: str, model_fingerprint: str, triggered_by: str
) -> int:
    async with acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO resolution_runs
                (entity_types, model_version, model_fingerprint, triggered_by)
            VALUES ($1, $2, $3, $4)
            RETURNING run_id
            """,
            entity_types,
            model_version,
            model_fingerprint,
            triggered_by,
        )


async def finish_run(
    run_id: int,
    *,
    status: str,
    profiles_examined: int = 0,
    pairs_scored: int = 0,
    bands: dict[str, int] | None = None,
    blocking_report: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    counts = bands or {}
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE resolution_runs
               SET status = $2,
                   finished_at = now(),
                   profiles_examined = $3,
                   pairs_scored = $4,
                   auto_count = $5,
                   review_count = $6,
                   insufficient_count = $7,
                   reject_count = $8,
                   blocking_report = $9::jsonb,
                   error = $10
             WHERE run_id = $1
            """,
            run_id,
            status,
            profiles_examined,
            pairs_scored,
            counts.get("auto", 0),
            counts.get("review", 0),
            counts.get("insufficient", 0),
            counts.get("reject", 0),
            json.dumps(blocking_report or {}, default=str),
            error,
        )


async def recent_runs(limit: int = 20) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT run_id, entity_types, model_version, model_fingerprint, status,
                   started_at, finished_at, profiles_examined, pairs_scored,
                   auto_count, review_count, insufficient_count, reject_count,
                   blocking_report, triggered_by, error
              FROM resolution_runs
             ORDER BY started_at DESC
             LIMIT $1
            """,
            limit,
        )
    return [
        {**dict(row), "blocking_report": json.loads(row["blocking_report"])} for row in rows
    ]


# ── Candidates ───────────────────────────────────────────────────────────────


async def upsert_candidate(
    conn: asyncpg.Connection, run_id: int | None, result: MatchResult
) -> int | None:
    """Record a scored pair. Returns the candidate id, or None if it was left alone.

    A pair that has already been decided is **not** re-opened by a later run.
    Re-scoring is cheap and happens often; silently reviving a question a person
    has already answered would make the review queue grow back every night and
    quietly discard analyst work.
    """
    left, right = order_pair(result.left_ref, result.right_ref)
    # Comparisons are stored in the pair's canonical order, so the review screen
    # never shows the two records swapped relative to the stored refs.
    flip = (left, right) != (result.left_ref, result.right_ref)
    comparisons = [
        {**c.as_dict(), **({"left": c.right, "right": c.left} if flip else {})}
        for c in result.comparisons
    ]

    return await conn.fetchval(
        """
        INSERT INTO resolution_candidates
            (run_id, entity_type, left_ref, right_ref, score, evidence_weight,
             band, band_reason, comparisons, blocking_keys,
             model_version, model_fingerprint)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12)
        ON CONFLICT (left_ref, right_ref) DO UPDATE
           SET run_id = EXCLUDED.run_id,
               score = EXCLUDED.score,
               evidence_weight = EXCLUDED.evidence_weight,
               band = EXCLUDED.band,
               band_reason = EXCLUDED.band_reason,
               comparisons = EXCLUDED.comparisons,
               blocking_keys = EXCLUDED.blocking_keys,
               model_version = EXCLUDED.model_version,
               model_fingerprint = EXCLUDED.model_fingerprint,
               updated_at = now(),
               -- A withdrawn pair the model produces again is a live candidate
               -- once more. A decided one is not reopened: see the docstring.
               status = 'open',
               withdrawn_at = NULL,
               withdrawn_reason = NULL
         WHERE resolution_candidates.status IN ('open', 'withdrawn')
        RETURNING candidate_id
        """,
        run_id,
        result.entity_type,
        left,
        right,
        result.score,
        result.evidence_weight,
        result.band,
        result.band_reason,
        json.dumps(comparisons, default=str),
        result.blocking_keys,
        result.model_version,
        result.model_fingerprint,
    )


async def get_candidate(candidate_id: int) -> CandidateRow | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM resolution_candidates WHERE candidate_id = $1", candidate_id
        )
    return _candidate_from_row(row) if row else None


async def get_candidate_for_pair(left_ref: str, right_ref: str) -> CandidateRow | None:
    left, right = order_pair(left_ref, right_ref)
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM resolution_candidates WHERE left_ref = $1 AND right_ref = $2",
            left,
            right,
        )
    return _candidate_from_row(row) if row else None


async def list_candidates(
    *,
    band: str = "review",
    status: str = "open",
    entity_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[CandidateRow]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM resolution_candidates
             WHERE band = $1
               AND status = $2
               AND ($3::text IS NULL OR entity_type = $3)
             ORDER BY score DESC NULLS LAST, candidate_id ASC
             LIMIT $4 OFFSET $5
            """,
            band,
            status,
            entity_type,
            limit,
            offset,
        )
    return [_candidate_from_row(row) for row in rows]


async def candidate_counts() -> dict[str, dict[str, int]]:
    """Queue depth by band and status — the denominator for the review UI.

    A review screen showing "12 pending" without saying 12 of how many, or how
    many the matcher declined to raise at all, is the kind of number this
    project keeps refusing to display.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT band, status, count(*) AS n FROM resolution_candidates GROUP BY band, status"
        )
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        out.setdefault(row["band"], {})[row["status"]] = row["n"]
    return out


async def close_candidate(conn: asyncpg.Connection, candidate_id: int) -> None:
    await conn.execute(
        "UPDATE resolution_candidates SET status = 'decided', updated_at = now() "
        "WHERE candidate_id = $1",
        candidate_id,
    )


async def withdraw_stale_candidates(
    conn: asyncpg.Connection, *, entity_type: str, run_id: int, reason: str
) -> int:
    """Retire open candidates a complete run did not re-produce.

    Called only after a full, untruncated sweep of a type: if the run examined
    a subset, "the current model no longer produces this pair" is not something
    it is in a position to say.

    Decided candidates are untouched — a pair someone has already ruled on is
    not withdrawn by a later model change, because the person's decision stands
    on its own.
    """
    return await conn.fetchval(
        """
        WITH stale AS (
            UPDATE resolution_candidates
               SET status = 'withdrawn',
                   withdrawn_at = now(),
                   withdrawn_reason = $3,
                   updated_at = now()
             WHERE entity_type = $1
               AND status = 'open'
               AND (run_id IS DISTINCT FROM $2)
            RETURNING 1
        )
        SELECT count(*) FROM stale
        """,
        entity_type,
        run_id,
        reason,
    )


async def candidates_for_ref(ref: str, limit: int = 50) -> list[CandidateRow]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM resolution_candidates
             WHERE left_ref = $1 OR right_ref = $1
             ORDER BY score DESC NULLS LAST
             LIMIT $2
            """,
            ref,
            limit,
        )
    return [_candidate_from_row(row) for row in rows]


# ── Decisions ────────────────────────────────────────────────────────────────


async def record_decision(
    conn: asyncpg.Connection,
    *,
    entity_type: str,
    left_ref: str,
    right_ref: str,
    verdict: str,
    decided_by: str,
    decided_by_kind: str,
    rationale: str,
    score: float | None = None,
    evidence_weight: float | None = None,
    model_version: str | None = None,
    model_fingerprint: str | None = None,
    candidate_id: int | None = None,
    reverses_decision_id: int | None = None,
) -> int:
    left, right = order_pair(left_ref, right_ref)
    return await conn.fetchval(
        """
        INSERT INTO resolution_decisions
            (entity_type, left_ref, right_ref, verdict, decided_by, decided_by_kind,
             rationale, score, evidence_weight, model_version, model_fingerprint,
             candidate_id, reverses_decision_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        RETURNING decision_id
        """,
        entity_type,
        left,
        right,
        verdict,
        decided_by,
        decided_by_kind,
        rationale,
        score,
        evidence_weight,
        model_version,
        model_fingerprint,
        candidate_id,
        reverses_decision_id,
    )


async def current_decision(left_ref: str, right_ref: str) -> DecisionRow | None:
    left, right = order_pair(left_ref, right_ref)
    async with acquire() as conn:
        row = await conn.fetchrow(
            _DECISION_SELECT.format(source="resolution_current_decisions")
            + " WHERE d.left_ref = $1 AND d.right_ref = $2",
            left,
            right,
        )
    return _decision_from_row(row) if row else None


async def get_decision(decision_id: int) -> DecisionRow | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            _DECISION_SELECT.format(source="resolution_decisions")
            + " WHERE d.decision_id = $1",
            decision_id,
        )
    return _decision_from_row(row) if row else None


async def active_same_pairs(
    conn: asyncpg.Connection | None = None,
) -> list[tuple[str, str, str]]:
    """Every pair currently judged the same: (entity_type, left, right).

    The input to cluster rebuilding. Read from the view so a reversal takes
    effect without anything having been updated in place.
    """

    async def _run(c: asyncpg.Connection) -> list[tuple[str, str, str]]:
        rows = await c.fetch(
            "SELECT entity_type, left_ref, right_ref FROM resolution_current_decisions "
            "WHERE verdict = 'same' ORDER BY left_ref, right_ref"
        )
        return [(r["entity_type"], r["left_ref"], r["right_ref"]) for r in rows]

    if conn is not None:
        return await _run(conn)
    async with acquire() as own:
        return await _run(own)


async def active_different_pairs(
    conn: asyncpg.Connection | None = None,
) -> set[tuple[str, str]]:
    """Pairs explicitly judged different — the constraints on clustering."""

    async def _run(c: asyncpg.Connection) -> set[tuple[str, str]]:
        rows = await c.fetch(
            "SELECT left_ref, right_ref FROM resolution_current_decisions "
            "WHERE verdict = 'different'"
        )
        return {(r["left_ref"], r["right_ref"]) for r in rows}

    if conn is not None:
        return await _run(conn)
    async with acquire() as own:
        return await _run(own)


async def decision_history(left_ref: str, right_ref: str) -> list[DecisionRow]:
    """Every decision ever made about a pair, oldest first.

    This is the merge lineage. It is a list rather than a current state because
    "merged, un-merged, merged again by a different analyst" is a materially
    different situation from "merged", and only one of them is visible if the
    history is collapsed.
    """
    left, right = order_pair(left_ref, right_ref)
    async with acquire() as conn:
        rows = await conn.fetch(
            _DECISION_SELECT.format(source="resolution_decisions")
            + " WHERE d.left_ref = $1 AND d.right_ref = $2 ORDER BY d.decision_id ASC",
            left,
            right,
        )
    return [_decision_from_row(row) for row in rows]


async def recent_decisions(
    *, verdict: str | None = None, limit: int = 100
) -> list[DecisionRow]:
    async with acquire() as conn:
        rows = await conn.fetch(
            _DECISION_SELECT.format(source="resolution_decisions")
            + """
             WHERE ($1::text IS NULL OR d.verdict = $1)
             ORDER BY d.decision_id DESC
             LIMIT $2
            """,
            verdict,
            limit,
        )
    return [_decision_from_row(row) for row in rows]


async def decisions_for_ref(ref: str) -> list[DecisionRow]:
    async with acquire() as conn:
        rows = await conn.fetch(
            _DECISION_SELECT.format(source="resolution_decisions")
            + " WHERE d.left_ref = $1 OR d.right_ref = $1 ORDER BY d.decision_id DESC",
            ref,
        )
    return [_decision_from_row(row) for row in rows]


# ── Clusters (derived) ───────────────────────────────────────────────────────


async def replace_clusters(
    conn: asyncpg.Connection, clusters: list[dict[str, Any]]
) -> None:
    """Swap the whole cluster projection inside the caller's transaction.

    Delete-then-insert is safe here in a way it would never be for the ledger:
    these rows are derived, and `rebuild_clusters` can reconstruct them from
    `resolution_decisions` at any time.
    """
    await conn.execute("DELETE FROM resolution_cluster_members")
    await conn.execute("DELETE FROM resolution_clusters")
    if not clusters:
        return

    await conn.executemany(
        """
        INSERT INTO resolution_clusters
            (cluster_key, entity_type, canonical_ref, canonical_basis, member_count,
             contested, contested_reason)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        [
            (
                c["cluster_key"],
                c["entity_type"],
                c["canonical_ref"],
                c["canonical_basis"],
                len(c["members"]),
                c["contested"],
                c["contested_reason"],
            )
            for c in clusters
        ],
    )
    await conn.executemany(
        "INSERT INTO resolution_cluster_members (ref, cluster_key, entity_type) "
        "VALUES ($1, $2, $3)",
        [
            (ref, c["cluster_key"], c["entity_type"])
            for c in clusters
            for ref in c["members"]
        ],
    )


async def list_clusters(
    *, contested_only: bool = False, entity_type: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.*, array_agg(m.ref ORDER BY m.ref) AS members
              FROM resolution_clusters c
              JOIN resolution_cluster_members m ON m.cluster_key = c.cluster_key
             WHERE (NOT $1::boolean OR c.contested)
               AND ($2::text IS NULL OR c.entity_type = $2)
             GROUP BY c.cluster_key
             ORDER BY c.contested DESC, c.member_count DESC, c.cluster_key
             LIMIT $3
            """,
            contested_only,
            entity_type,
            limit,
        )
    return [dict(row) for row in rows]


async def cluster_for_ref(ref: str) -> dict[str, Any] | None:
    """The cluster a record belongs to, or None if it stands alone.

    None is the common case and the correct answer: most records are not
    duplicates of anything, and inventing a one-member cluster for each would
    make the cluster table a second copy of the entity population.
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT c.*, array_agg(m2.ref ORDER BY m2.ref) AS members
              FROM resolution_cluster_members m
              JOIN resolution_clusters c ON c.cluster_key = m.cluster_key
              JOIN resolution_cluster_members m2 ON m2.cluster_key = c.cluster_key
             WHERE m.ref = $1
             GROUP BY c.cluster_key
            """,
            ref,
        )
    return dict(row) if row else None


async def cluster_counts() -> dict[str, int]:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT count(*) AS clusters,
                   coalesce(sum(member_count), 0) AS members,
                   count(*) FILTER (WHERE contested) AS contested
              FROM resolution_clusters
            """
        )
    return {k: int(v) for k, v in dict(row).items()}


async def pinned_canonicals(conn: asyncpg.Connection | None = None) -> dict[str, str]:
    async def _run(c: asyncpg.Connection) -> dict[str, str]:
        rows = await c.fetch("SELECT ref, pinned_by FROM resolution_canonical_pins")
        return {r["ref"]: r["pinned_by"] for r in rows}

    if conn is not None:
        return await _run(conn)
    async with acquire() as own:
        return await _run(own)


async def pin_canonical(ref: str, *, pinned_by: str, reason: str) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO resolution_canonical_pins (ref, pinned_by, reason)
            VALUES ($1, $2, $3)
            ON CONFLICT (ref) DO UPDATE
               SET pinned_by = EXCLUDED.pinned_by,
                   reason = EXCLUDED.reason,
                   pinned_at = now()
            """,
            ref,
            pinned_by,
            reason,
        )


# ── Blocking index (derived) ─────────────────────────────────────────────────


async def replace_blocking_index(
    conn: asyncpg.Connection, entity_type: str, rows: list[tuple[str, str]]
) -> int:
    """Swap one entity type's blocking index. `rows` is (ref, block_key).

    Scoped to a type so a Person run does not discard the Organization index —
    the two are matched independently and often on different schedules.
    """
    await conn.execute("DELETE FROM resolution_blocking_index WHERE entity_type = $1", entity_type)
    if not rows:
        return 0
    await conn.executemany(
        "INSERT INTO resolution_blocking_index (ref, entity_type, block_key) VALUES ($1, $2, $3) "
        "ON CONFLICT (ref, block_key) DO NOTHING",
        [(ref, entity_type, key) for ref, key in rows],
    )
    return len(rows)


async def refs_for_block_keys(keys: list[str], *, limit: int = 200) -> list[str]:
    """Records sharing any of these blocking keys.

    Bounded: a key that returns hundreds of records has stopped discriminating,
    and scoring against all of them would turn one inbound record into a
    quadratic problem. The bound is a ceiling on work, not a filter on quality,
    so `resolve_subject` reports when it hits it rather than presenting a
    truncated search as an exhaustive one.
    """
    if not keys:
        return []
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT ref FROM resolution_blocking_index WHERE block_key = ANY($1::text[]) "
            "ORDER BY ref LIMIT $2",
            keys,
            limit,
        )
    return [row["ref"] for row in rows]


async def blocking_index_size() -> dict[str, int]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT entity_type, count(DISTINCT ref) AS refs, count(*) AS entries "
            "FROM resolution_blocking_index GROUP BY entity_type"
        )
    return {row["entity_type"]: row["refs"] for row in rows}


async def observation_counts(refs: list[str]) -> dict[str, int]:
    """How many observations name each ref, for canonical selection.

    The canonical record of a cluster should be the one the most sources have
    actually said something about — not an arbitrary pick, and not the newest,
    which would let a thin record from one feed displace a well-corroborated one.
    """
    if not refs:
        return {}
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT subject_ref, count(*) AS n FROM observation_subjects "
            "WHERE subject_ref = ANY($1::text[]) GROUP BY subject_ref",
            refs,
        )
    return {row["subject_ref"]: row["n"] for row in rows}


# ── Labels and evaluations ───────────────────────────────────────────────────


async def add_label(
    conn: asyncpg.Connection,
    *,
    entity_type: str,
    left_ref: str,
    right_ref: str,
    is_same: bool,
    origin: str,
    note: str | None = None,
) -> int | None:
    """Record a ground-truth label. Returns None if one already exists.

    Existing labels are never overwritten — the table is append-only at the
    database level. A label that could be revised after a measurement was taken
    against it would make that measurement meaningless.
    """
    # Swapping the pair does not change whether the two refs denote the same
    # thing, so canonical ordering is applied without touching `is_same`.
    left, right = order_pair(left_ref, right_ref)
    return await conn.fetchval(
        """
        INSERT INTO resolution_labels (entity_type, left_ref, right_ref, is_same, origin, note)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (left_ref, right_ref, origin) DO NOTHING
        RETURNING label_id
        """,
        entity_type,
        left,
        right,
        is_same,
        origin,
        note,
    )


async def labels(origin: str | None = None) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM resolution_labels WHERE ($1::text IS NULL OR origin = $1) "
            "ORDER BY label_id",
            origin,
        )
    return [dict(row) for row in rows]


async def label_counts() -> dict[str, int]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT origin, is_same, count(*) AS n FROM resolution_labels "
            "GROUP BY origin, is_same"
        )
    return {f"{r['origin']}_{'same' if r['is_same'] else 'different'}": r["n"] for r in rows}


async def record_evaluation(
    *,
    model_version: str,
    model_fingerprint: str,
    dataset: str,
    metrics: dict[str, Any],
    notes: str | None = None,
) -> int:
    async with acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO resolution_evaluations
                (model_version, model_fingerprint, dataset, metrics, notes)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            RETURNING evaluation_id
            """,
            model_version,
            model_fingerprint,
            dataset,
            json.dumps(metrics, default=str),
            notes,
        )


async def recent_evaluations(limit: int = 20) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM resolution_evaluations ORDER BY ran_at DESC LIMIT $1", limit
        )
    return [{**dict(row), "metrics": json.loads(row["metrics"])} for row in rows]
