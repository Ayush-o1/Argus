"""Persistence for correlation.

The tables are append-only, so there is no update path here and no "current"
flag to keep in step: the current links are those belonging to the newest
completed run, computed by the `correlation_current_links` view. Re-running
appends a generation and leaves the previous one legible, which is what makes
"why did this link appear?" answerable at all.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from app.correlation.clustering import CorrelatedCluster
from app.correlation.linking import CorrelationLink
from app.database.postgres import acquire


@dataclass(frozen=True)
class LinkRow:
    link_id: str
    run_id: int
    ref_a: str
    ref_b: str
    type_a: str
    type_b: str
    strength: float
    tier: str
    coverage: float
    evaluable_dimensions: int
    applicable_dimensions: int
    corroborating_families: list[str]
    model_version: str
    model_fingerprint: str
    computed_at: datetime
    dimensions: list[dict[str, Any]]


@dataclass(frozen=True)
class ClusterRow:
    cluster_id: str
    run_id: int
    cluster_key: str
    size: int
    families: list[str]
    mean_strength: float
    min_strength: float
    weakest_bridge: float | None
    bridge_count: int
    over_merged: bool
    basis: str
    model_version: str
    model_fingerprint: str
    computed_at: datetime
    members: list[dict[str, Any]]


@dataclass(frozen=True)
class RunRow:
    run_id: int
    model_version: str
    model_fingerprint: str
    assessment_run_id: int | None
    status: str
    started_at: datetime
    finished_at: datetime | None
    anchors: int
    candidate_pairs: int
    pairs_scored: int
    links_recorded: int
    clusters_found: int
    keys_skipped: int
    search_truncated: bool
    evidence_summary: dict[str, Any]
    triggered_by: str
    error: str | None


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


# Bulk inserts are issued in chunks of this size rather than as one enormous
# statement.
#
# Found in live verification: a run that produced 91,212 links wrote ~700,000
# dimension rows in a single `executemany`, and the connection's 10-second
# command timeout killed it. The run recorded itself as failed, correctly, but
# the failure was in the write rather than in anything about the correlation.
#
# Chunking is the right fix rather than raising the timeout. Ten seconds is a
# sensible ceiling for the interactive queries the rest of the application
# makes, and lifting it globally to accommodate one bulk writer would remove
# that protection everywhere. Every chunk still runs inside the same
# transaction, so a generation remains all-or-nothing.
_INSERT_CHUNK = 2_000


async def _insert_in_chunks(conn: Any, statement: str, rows: list[tuple]) -> None:
    for start in range(0, len(rows), _INSERT_CHUNK):
        await conn.executemany(statement, rows[start : start + _INSERT_CHUNK])


def _row_to_run(row: asyncpg.Record) -> RunRow:
    return RunRow(
        run_id=row["run_id"],
        model_version=row["model_version"],
        model_fingerprint=row["model_fingerprint"],
        assessment_run_id=row["assessment_run_id"],
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        anchors=row["anchors"],
        candidate_pairs=row["candidate_pairs"],
        pairs_scored=row["pairs_scored"],
        links_recorded=row["links_recorded"],
        clusters_found=row["clusters_found"],
        keys_skipped=row["keys_skipped"],
        search_truncated=row["search_truncated"],
        evidence_summary=_json(row["evidence_summary"]) or {},
        triggered_by=row["triggered_by"],
        error=row["error"],
    )


def _dimensions_of(row: asyncpg.Record) -> list[dict[str, Any]]:
    raw = _json(row["dimensions"])
    if not raw:
        return []
    for dimension in raw:
        for key in ("magnitude", "contribution"):
            if dimension.get(key) is not None:
                dimension[key] = float(dimension[key])
        if isinstance(dimension.get("evidence"), str):
            dimension["evidence"] = json.loads(dimension["evidence"])
    return raw


def _row_to_link(row: asyncpg.Record) -> LinkRow:
    return LinkRow(
        link_id=str(row["link_id"]),
        run_id=row["run_id"],
        ref_a=row["ref_a"],
        ref_b=row["ref_b"],
        type_a=row["type_a"],
        type_b=row["type_b"],
        strength=float(row["strength"]),
        tier=row["tier"],
        coverage=float(row["coverage"]),
        evaluable_dimensions=row["evaluable_dimensions"],
        applicable_dimensions=row["applicable_dimensions"],
        corroborating_families=list(row["corroborating_families"] or []),
        model_version=row["model_version"],
        model_fingerprint=row["model_fingerprint"],
        computed_at=row["computed_at"],
        dimensions=_dimensions_of(row),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Runs
# ─────────────────────────────────────────────────────────────────────────────


async def start_run(
    model_version: str,
    model_fingerprint: str,
    assessment_run_id: int | None,
    triggered_by: str,
) -> int:
    async with acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO correlation_runs (
                model_version, model_fingerprint, assessment_run_id, triggered_by
            ) VALUES ($1, $2, $3, $4)
            RETURNING run_id
            """,
            model_version,
            model_fingerprint,
            assessment_run_id,
            triggered_by,
        )


async def finish_run(
    run_id: int,
    *,
    anchors: int,
    candidate_pairs: int,
    pairs_scored: int,
    links_recorded: int,
    clusters_found: int,
    keys_skipped: int,
    search_truncated: bool,
    evidence_summary: dict[str, Any],
) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE correlation_runs
               SET status = 'complete', finished_at = now(),
                   anchors = $2, candidate_pairs = $3, pairs_scored = $4,
                   links_recorded = $5, clusters_found = $6, keys_skipped = $7,
                   search_truncated = $8, evidence_summary = $9::jsonb
             WHERE run_id = $1
            """,
            run_id,
            anchors,
            candidate_pairs,
            pairs_scored,
            links_recorded,
            clusters_found,
            keys_skipped,
            search_truncated,
            json.dumps(evidence_summary),
        )


async def fail_run(run_id: int, error: str) -> None:
    """Record a failure with its reason.

    The previous generation is untouched. A failed run must not leave the
    application with no links at all — that would turn a transient database
    outage into a silent claim that nothing is connected.
    """
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE correlation_runs
               SET status = 'failed', finished_at = now(), error = $2
             WHERE run_id = $1
            """,
            run_id,
            error[:2000],
        )


async def latest_run() -> RunRow | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM correlation_runs ORDER BY started_at DESC, run_id DESC LIMIT 1"
        )
        return _row_to_run(row) if row else None


async def latest_complete_run() -> RunRow | None:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM correlation_latest_run")
        return _row_to_run(row) if row else None


async def list_runs(limit: int = 20) -> list[RunRow]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM correlation_runs ORDER BY started_at DESC, run_id DESC LIMIT $1",
            limit,
        )
        return [_row_to_run(row) for row in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Links and clusters
# ─────────────────────────────────────────────────────────────────────────────


async def store_links(run_id: int, links: list[CorrelationLink]) -> int:
    """Write a generation of links and their dimension working.

    One transaction for the whole batch. A half-written generation would leave
    some pairs linked under the new model and some under the old, with nothing
    to say which is which — and the `correlation_current_links` view would then
    be a mixture rather than a generation.

    Identifiers are minted here rather than by the database so the dimension
    rows can be built in the same pass: `executemany` gives no RETURNING, and
    reading the ids back would be one more place for a generation to end up
    partly written.
    """
    if not links:
        return 0

    ids = [uuid.uuid4() for _ in links]

    async with acquire() as conn, conn.transaction():
        await _insert_in_chunks(
            conn,
            """
            INSERT INTO correlation_links (
                link_id, run_id, ref_a, ref_b, type_a, type_b, strength, tier,
                coverage, evaluable_dimensions, applicable_dimensions,
                corroborating_families, model_version, model_fingerprint, computed_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            """,
            [
                (
                    link_id,
                    run_id,
                    link.ref_a,
                    link.ref_b,
                    link.type_a,
                    link.type_b,
                    link.strength,
                    link.tier,
                    link.coverage,
                    link.evaluable_dimensions,
                    link.applicable_dimensions,
                    list(link.corroborating_families),
                    link.model_version,
                    link.model_fingerprint,
                    link.computed_at,
                )
                for link_id, link in zip(ids, links, strict=True)
            ],
        )

        contribution_by_family = {
            link_id: {f.dimension_id: f.contribution for f in link.families}
            for link_id, link in zip(ids, links, strict=True)
        }
        dimension_rows = [
            (
                link_id,
                outcome.dimension_id,
                outcome.family,
                outcome.evaluable,
                outcome.magnitude,
                contribution_by_family[link_id].get(outcome.dimension_id, 0.0),
                outcome.summary,
                json.dumps(outcome.evidence),
            )
            for link_id, link in zip(ids, links, strict=True)
            for outcome in link.outcomes
        ]
        await _insert_in_chunks(
            conn,
            """
            INSERT INTO correlation_link_dimensions (
                link_id, dimension_id, family, evaluable, magnitude,
                contribution, summary, evidence
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            """,
            dimension_rows,
        )
    return len(ids)


async def store_clusters(run_id: int, clusters: list[CorrelatedCluster]) -> int:
    if not clusters:
        return 0

    ids = [uuid.uuid4() for _ in clusters]

    async with acquire() as conn, conn.transaction():
        await _insert_in_chunks(
            conn,
            """
            INSERT INTO correlation_clusters (
                cluster_id, run_id, cluster_key, size, families, mean_strength,
                min_strength, weakest_bridge, bridge_count, over_merged, basis,
                model_version, model_fingerprint, computed_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            """,
            [
                (
                    cluster_id,
                    run_id,
                    cluster.cluster_key,
                    cluster.size,
                    list(cluster.families),
                    cluster.mean_strength,
                    cluster.min_strength,
                    cluster.weakest_bridge,
                    len(cluster.bridges),
                    cluster.over_merged,
                    cluster.basis(),
                    cluster.links[0].model_version if cluster.links else "",
                    cluster.links[0].model_fingerprint if cluster.links else "",
                    cluster.computed_at,
                )
                for cluster_id, cluster in zip(ids, clusters, strict=True)
            ],
        )

        member_rows = [
            (cluster_id, m.ref, m.subject_type, m.band, m.score, m.degree)
            for cluster_id, cluster in zip(ids, clusters, strict=True)
            for m in cluster.members
        ]
        await _insert_in_chunks(
            conn,
            """
            INSERT INTO correlation_cluster_members (
                cluster_id, subject_ref, subject_type, band, score, degree
            ) VALUES ($1, $2, $3, $4, $5, $6)
            """,
            member_rows,
        )
    return len(ids)


# The statements below are written out in full rather than composed from a
# shared fragment with an f-string.
#
# Every value is still a bound parameter and none was ever caller-controlled, so
# the f-string version was safe — but bandit flags string-built SQL (B608) and
# the standing rule on this project is to remove the construct rather than
# annotate the warning away. A reviewer skimming for injection risk should not
# have to reconstruct a query from two places to satisfy themselves, and the
# duplication that costs is a few lines of SELECT list.


_LINKS_ALL = """
    SELECT l.*, d.dimensions
      FROM correlation_current_links l
      LEFT JOIN LATERAL (
          SELECT json_agg(
                     json_build_object(
                         'dimension_id', dim.dimension_id,
                         'family', dim.family,
                         'evaluable', dim.evaluable,
                         'magnitude', dim.magnitude,
                         'contribution', dim.contribution,
                         'summary', dim.summary,
                         'evidence', dim.evidence
                     ) ORDER BY dim.contribution DESC, dim.dimension_id
                 ) AS dimensions
            FROM correlation_link_dimensions dim
           WHERE dim.link_id = l.link_id
      ) d ON true
 ORDER BY l.strength DESC, l.ref_a, l.ref_b LIMIT $1 OFFSET $2
"""

_LINKS_BY_TIER = """
    SELECT l.*, d.dimensions
      FROM correlation_current_links l
      LEFT JOIN LATERAL (
          SELECT json_agg(
                     json_build_object(
                         'dimension_id', dim.dimension_id,
                         'family', dim.family,
                         'evaluable', dim.evaluable,
                         'magnitude', dim.magnitude,
                         'contribution', dim.contribution,
                         'summary', dim.summary,
                         'evidence', dim.evidence
                     ) ORDER BY dim.contribution DESC, dim.dimension_id
                 ) AS dimensions
            FROM correlation_link_dimensions dim
           WHERE dim.link_id = l.link_id
      ) d ON true
 WHERE l.tier = $1
     ORDER BY l.strength DESC, l.ref_a, l.ref_b LIMIT $2 OFFSET $3
"""

_LINKS_FOR_SUBJECT = """
    SELECT l.*, d.dimensions
      FROM correlation_current_links l
      LEFT JOIN LATERAL (
          SELECT json_agg(
                     json_build_object(
                         'dimension_id', dim.dimension_id,
                         'family', dim.family,
                         'evaluable', dim.evaluable,
                         'magnitude', dim.magnitude,
                         'contribution', dim.contribution,
                         'summary', dim.summary,
                         'evidence', dim.evidence
                     ) ORDER BY dim.contribution DESC, dim.dimension_id
                 ) AS dimensions
            FROM correlation_link_dimensions dim
           WHERE dim.link_id = l.link_id
      ) d ON true
 WHERE l.ref_a = $1 OR l.ref_b = $1
     ORDER BY l.strength DESC LIMIT $2
"""


async def list_current_links(
    *, tier: str | None = None, limit: int = 100, offset: int = 0
) -> list[LinkRow]:
    """The newest generation of links."""
    async with acquire() as conn:
        if tier is None:
            rows = await conn.fetch(_LINKS_ALL, limit, offset)
        else:
            rows = await conn.fetch(_LINKS_BY_TIER, tier, limit, offset)
        return [_row_to_link(row) for row in rows]


async def links_for_subject(subject_ref: str, limit: int = 50) -> list[LinkRow]:
    async with acquire() as conn:
        rows = await conn.fetch(_LINKS_FOR_SUBJECT, subject_ref, limit)
        return [_row_to_link(row) for row in rows]


async def current_tier_counts() -> dict[str, int]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT tier, count(*) AS n FROM correlation_current_links GROUP BY tier"
        )
        return {row["tier"]: row["n"] for row in rows}




def _row_to_cluster(row: asyncpg.Record) -> ClusterRow:
    members = _json(row["members"]) or []
    for member in members:
        if member.get("score") is not None:
            member["score"] = float(member["score"])
    return ClusterRow(
        cluster_id=str(row["cluster_id"]),
        run_id=row["run_id"],
        cluster_key=row["cluster_key"],
        size=row["size"],
        families=list(row["families"] or []),
        mean_strength=float(row["mean_strength"]),
        min_strength=float(row["min_strength"]),
        weakest_bridge=(
            float(row["weakest_bridge"]) if row["weakest_bridge"] is not None else None
        ),
        bridge_count=row["bridge_count"],
        over_merged=row["over_merged"],
        basis=row["basis"],
        model_version=row["model_version"],
        model_fingerprint=row["model_fingerprint"],
        computed_at=row["computed_at"],
        members=members,
    )


_CLUSTERS_ALL = """
    SELECT c.*, m.members
      FROM correlation_current_clusters c
      LEFT JOIN LATERAL (
          SELECT json_agg(
                     json_build_object(
                         'subject_ref', mem.subject_ref,
                         'subject_type', mem.subject_type,
                         'band', mem.band,
                         'score', mem.score,
                         'degree', mem.degree
                     ) ORDER BY mem.degree DESC, mem.subject_ref
                 ) AS members
            FROM correlation_cluster_members mem
           WHERE mem.cluster_id = c.cluster_id
      ) m ON true
 ORDER BY c.over_merged, c.size DESC, c.mean_strength DESC LIMIT $1
"""

_CLUSTER_BY_KEY = """
    SELECT c.*, m.members
      FROM correlation_current_clusters c
      LEFT JOIN LATERAL (
          SELECT json_agg(
                     json_build_object(
                         'subject_ref', mem.subject_ref,
                         'subject_type', mem.subject_type,
                         'band', mem.band,
                         'score', mem.score,
                         'degree', mem.degree
                     ) ORDER BY mem.degree DESC, mem.subject_ref
                 ) AS members
            FROM correlation_cluster_members mem
           WHERE mem.cluster_id = c.cluster_id
      ) m ON true
 WHERE c.cluster_key = $1
"""

_CLUSTERS_FOR_SUBJECT = """
    SELECT c.*, m.members
      FROM correlation_current_clusters c
      LEFT JOIN LATERAL (
          SELECT json_agg(
                     json_build_object(
                         'subject_ref', mem.subject_ref,
                         'subject_type', mem.subject_type,
                         'band', mem.band,
                         'score', mem.score,
                         'degree', mem.degree
                     ) ORDER BY mem.degree DESC, mem.subject_ref
                 ) AS members
            FROM correlation_cluster_members mem
           WHERE mem.cluster_id = c.cluster_id
      ) m ON true
 WHERE EXISTS (
         SELECT 1 FROM correlation_cluster_members mm
          WHERE mm.cluster_id = c.cluster_id AND mm.subject_ref = $1
     )
     ORDER BY c.size DESC
"""


async def list_current_clusters(limit: int = 50) -> list[ClusterRow]:
    async with acquire() as conn:
        rows = await conn.fetch(_CLUSTERS_ALL, limit)
        return [_row_to_cluster(row) for row in rows]


async def cluster_by_key(cluster_key: str) -> ClusterRow | None:
    async with acquire() as conn:
        row = await conn.fetchrow(_CLUSTER_BY_KEY, cluster_key)
        return _row_to_cluster(row) if row else None


async def clusters_for_subject(subject_ref: str) -> list[ClusterRow]:
    async with acquire() as conn:
        rows = await conn.fetch(_CLUSTERS_FOR_SUBJECT, subject_ref)
        return [_row_to_cluster(row) for row in rows]


async def all_current_clusters_for_projection() -> list[dict[str, Any]]:
    """Every current cluster membership, in the shape the graph projection takes.

    This is what makes the `argus_cluster` node properties a cache rather than a
    second source of truth: they are rebuilt from here, and `rebuild_projection`
    proves it by clearing them first.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT m.subject_ref, c.cluster_key, c.size, c.model_fingerprint
              FROM correlation_current_clusters c
              JOIN correlation_cluster_members m ON m.cluster_id = c.cluster_id
            """
        )
        return [
            {
                "subject_ref": row["subject_ref"],
                "cluster_key": row["cluster_key"],
                "cluster_size": row["size"],
                "model_fingerprint": row["model_fingerprint"],
            }
            for row in rows
        ]


# ─────────────────────────────────────────────────────────────────────────────
# Evaluations
# ─────────────────────────────────────────────────────────────────────────────


async def store_evaluation(
    run_id: int | None,
    model_version: str,
    model_fingerprint: str,
    report: dict[str, Any],
    triggered_by: str,
) -> int:
    async with acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO correlation_evaluations (
                run_id, model_version, model_fingerprint, report, triggered_by
            ) VALUES ($1, $2, $3, $4::jsonb, $5)
            RETURNING evaluation_id
            """,
            run_id,
            model_version,
            model_fingerprint,
            json.dumps(report),
            triggered_by,
        )


async def latest_evaluation(model_fingerprint: str | None = None) -> dict[str, Any] | None:
    """The newest evaluation, optionally for one model.

    Filtered by fingerprint by default at the call site, because an evaluation
    of a different model is not an evaluation of this one — showing it beside
    the current results would attribute one model's precision to another's
    output.
    """
    async with acquire() as conn:
        if model_fingerprint is None:
            row = await conn.fetchrow(
                "SELECT * FROM correlation_evaluations ORDER BY generated_at DESC LIMIT 1"
            )
        else:
            row = await conn.fetchrow(
                """
                SELECT * FROM correlation_evaluations
                 WHERE model_fingerprint = $1
                 ORDER BY generated_at DESC LIMIT 1
                """,
                model_fingerprint,
            )
        if row is None:
            return None
        return {
            "evaluation_id": row["evaluation_id"],
            "run_id": row["run_id"],
            "model_version": row["model_version"],
            "model_fingerprint": row["model_fingerprint"],
            "generated_at": row["generated_at"].isoformat(),
            "report": _json(row["report"]),
            "triggered_by": row["triggered_by"],
        }
