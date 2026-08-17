"""Persistence for risk assessment.

The table is append-only, so there is no update path here and no "current"
flag to keep in step: the current assessment for a subject is the newest row,
computed by the `assessment_current` view. Re-running the assessor writes a new
generation and leaves the old one legible, which is what makes "why did this
change?" answerable at all.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from app.assessment.scoring import Assessment
from app.database.postgres import acquire


@dataclass(frozen=True)
class AssessmentRow:
    assessment_id: str
    run_id: int
    subject_ref: str
    subject_type: str
    band: str
    score: float | None
    evidence_coverage: float
    evaluable_weight: float
    total_weight: float
    families_fired: list[str]
    model_version: str
    model_fingerprint: str
    computed_at: datetime
    signals: list[dict[str, Any]]


@dataclass(frozen=True)
class RunRow:
    run_id: int
    model_version: str
    model_fingerprint: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    subjects_assessed: int
    elevated_count: int
    notable_count: int
    routine_count: int
    insufficient_count: int
    evidence_summary: dict[str, Any]
    search_truncated: bool
    triggered_by: str
    error: str | None


def _row_to_assessment(row: asyncpg.Record, signals: list[dict[str, Any]]) -> AssessmentRow:
    return AssessmentRow(
        assessment_id=str(row["assessment_id"]),
        run_id=row["run_id"],
        subject_ref=row["subject_ref"],
        subject_type=row["subject_type"],
        band=row["band"],
        score=float(row["score"]) if row["score"] is not None else None,
        evidence_coverage=float(row["evidence_coverage"]),
        evaluable_weight=float(row["evaluable_weight"]),
        total_weight=float(row["total_weight"]),
        families_fired=list(row["families_fired"] or []),
        model_version=row["model_version"],
        model_fingerprint=row["model_fingerprint"],
        computed_at=row["computed_at"],
        signals=signals,
    )


def _row_to_run(row: asyncpg.Record) -> RunRow:
    return RunRow(
        run_id=row["run_id"],
        model_version=row["model_version"],
        model_fingerprint=row["model_fingerprint"],
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        subjects_assessed=row["subjects_assessed"],
        elevated_count=row["elevated_count"],
        notable_count=row["notable_count"],
        routine_count=row["routine_count"],
        insufficient_count=row["insufficient_count"],
        evidence_summary=json.loads(row["evidence_summary"])
        if isinstance(row["evidence_summary"], str)
        else dict(row["evidence_summary"] or {}),
        search_truncated=row["search_truncated"],
        triggered_by=row["triggered_by"],
        error=row["error"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Runs
# ─────────────────────────────────────────────────────────────────────────────


async def start_run(model_version: str, model_fingerprint: str, triggered_by: str) -> int:
    async with acquire() as conn:
        return await conn.fetchval(
            """
            INSERT INTO assessment_runs (model_version, model_fingerprint, triggered_by)
            VALUES ($1, $2, $3) RETURNING run_id
            """,
            model_version,
            model_fingerprint,
            triggered_by,
        )


async def finish_run(
    run_id: int,
    *,
    band_counts: dict[str, int],
    evidence_summary: dict[str, Any],
    search_truncated: bool,
) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE assessment_runs
               SET status = 'complete', finished_at = now(),
                   subjects_assessed = $2, elevated_count = $3, notable_count = $4,
                   routine_count = $5, insufficient_count = $6,
                   evidence_summary = $7::jsonb, search_truncated = $8
             WHERE run_id = $1
            """,
            run_id,
            sum(band_counts.values()),
            band_counts.get("elevated", 0),
            band_counts.get("notable", 0),
            band_counts.get("routine", 0),
            band_counts.get("insufficient_evidence", 0),
            json.dumps(evidence_summary),
            search_truncated,
        )


async def fail_run(run_id: int, error: str) -> None:
    async with acquire() as conn:
        await conn.execute(
            "UPDATE assessment_runs SET status = 'failed', finished_at = now(), error = $2 "
            "WHERE run_id = $1",
            run_id,
            error[:2000],
        )


async def latest_run() -> RunRow | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM assessment_runs ORDER BY started_at DESC LIMIT 1"
        )
        return _row_to_run(row) if row else None


async def list_runs(limit: int = 20) -> list[RunRow]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM assessment_runs ORDER BY started_at DESC LIMIT $1", limit
        )
        return [_row_to_run(row) for row in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Assessments
# ─────────────────────────────────────────────────────────────────────────────


async def store_assessments(run_id: int, assessments: list[Assessment]) -> int:
    """Write a generation of assessments and their signal working.

    One transaction for the whole batch: a partially written generation would
    leave some subjects assessed under the new model and some under the old,
    with nothing to say which is which.
    """
    if not assessments:
        return 0

    # Identifiers are minted here rather than by the database so the signal
    # rows can be built in the same pass. `executemany` gives no RETURNING, and
    # a second query to read the ids back would be one more place for a
    # generation to end up half-written.
    ids = [uuid.uuid4() for _ in assessments]

    async with acquire() as conn, conn.transaction():
        await conn.executemany(
            """
            INSERT INTO assessments (
                assessment_id, run_id, subject_ref, subject_type, band, score,
                evidence_coverage, evaluable_weight, total_weight,
                families_fired, model_version, model_fingerprint, computed_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
            [
                (
                    assessment_id,
                    run_id,
                    a.subject_ref,
                    a.subject_type,
                    a.band,
                    a.score,
                    a.evidence_coverage,
                    a.evaluable_weight,
                    a.total_weight,
                    list(a.families_fired),
                    a.model_version,
                    a.model_fingerprint,
                    a.computed_at,
                )
                for assessment_id, a in zip(ids, assessments, strict=True)
            ],
        )

        signal_rows = [
            (
                assessment_id,
                contribution.signal_id,
                contribution.family,
                contribution.weight,
                contribution.evaluable,
                contribution.magnitude,
                contribution.contribution,
                contribution.summary,
                json.dumps(contribution.detail),
            )
            for assessment_id, assessment in zip(ids, assessments, strict=True)
            for contribution in assessment.contributions
        ]
        await conn.executemany(
            """
            INSERT INTO assessment_signals (
                assessment_id, signal_id, family, weight, evaluable,
                magnitude, contribution, summary, detail
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
            """,
            signal_rows,
        )
        return len(ids)


_CURRENT_SELECT = """
    SELECT a.*, s.signals
      FROM assessment_current a
      LEFT JOIN LATERAL (
          SELECT json_agg(
                     json_build_object(
                         'signal_id', sig.signal_id,
                         'family', sig.family,
                         'weight', sig.weight,
                         'evaluable', sig.evaluable,
                         'magnitude', sig.magnitude,
                         'contribution', sig.contribution,
                         'summary', sig.summary,
                         'detail', sig.detail
                     ) ORDER BY sig.contribution DESC, sig.signal_id
                 ) AS signals
            FROM assessment_signals sig
           WHERE sig.assessment_id = a.assessment_id
      ) s ON true
"""


def _signals_of(row: asyncpg.Record) -> list[dict[str, Any]]:
    raw = row["signals"]
    if raw is None:
        return []
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    for signal in parsed:
        for key in ("weight", "magnitude", "contribution"):
            if signal.get(key) is not None:
                signal[key] = float(signal[key])
        if isinstance(signal.get("detail"), str):
            signal["detail"] = json.loads(signal["detail"])
    return parsed


async def current_for_subject(subject_ref: str) -> AssessmentRow | None:
    async with acquire() as conn:
        row = await conn.fetchrow(f"{_CURRENT_SELECT} WHERE a.subject_ref = $1", subject_ref)
        return _row_to_assessment(row, _signals_of(row)) if row else None


async def current_for_subjects(subject_refs: list[str]) -> dict[str, AssessmentRow]:
    """Several subjects in one query.

    Exists because the single-subject form was about to be called in a loop by
    the entity list — the same N+1 that made the resolution matcher unusable
    under a real feed in Phase 4.
    """
    if not subject_refs:
        return {}
    async with acquire() as conn:
        rows = await conn.fetch(
            f"{_CURRENT_SELECT} WHERE a.subject_ref = ANY($1::text[])", subject_refs
        )
        return {row["subject_ref"]: _row_to_assessment(row, _signals_of(row)) for row in rows}


async def history_for_subject(subject_ref: str, limit: int = 20) -> list[AssessmentRow]:
    """Every generation for one subject, newest first.

    The reason the table is append-only: a score that changed between Tuesday
    and Thursday is a question an analyst is entitled to ask, and it can only be
    answered if both answers still exist.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM assessments
             WHERE subject_ref = $1
             ORDER BY computed_at DESC, assessment_id
             LIMIT $2
            """,
            subject_ref,
            limit,
        )
        return [_row_to_assessment(row, []) for row in rows]


async def list_current(
    *,
    band: str | None = None,
    subject_type: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[AssessmentRow], int]:
    """The queue: current assessments, strongest first.

    Subjects with no score sort last rather than being dropped — an
    `insufficient_evidence` subject belongs in the list, plainly labelled,
    because filtering it out would present the queue as though ARGUS had an
    opinion about everyone.
    """
    # Both statements are written out in full rather than sharing an
    # interpolated WHERE fragment. The fragment was safe — a module constant
    # containing only placeholders — but "safe" then rested on reading the code
    # rather than on its shape, which is the same objection that got the audit
    # listing query rewritten in Phase 4.
    filters = [band or None, subject_type or None]
    async with acquire() as conn:
        total = await conn.fetchval(
            """
            SELECT count(*) FROM assessment_current a
             WHERE ($1::text IS NULL OR a.band = $1)
               AND ($2::text IS NULL OR a.subject_type = $2)
            """,
            *filters,
        )
        rows = await conn.fetch(
            _CURRENT_SELECT
            + """
            WHERE ($1::text IS NULL OR a.band = $1)
              AND ($2::text IS NULL OR a.subject_type = $2)
            -- NULLS LAST so a subject ARGUS could not assess sorts to the end
            -- of the queue rather than the top of it.
            ORDER BY a.score DESC NULLS LAST, a.subject_ref
            LIMIT $3 OFFSET $4
            """,
            *filters,
            page_size,
            (page - 1) * page_size,
        )
        return [_row_to_assessment(row, _signals_of(row)) for row in rows], total or 0


async def current_band_counts() -> dict[str, int]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT band, count(*) AS count FROM assessment_current GROUP BY band"
        )
        return {row["band"]: row["count"] for row in rows}


async def all_current_for_projection() -> list[dict[str, Any]]:
    """Every current assessment, in the shape the graph projection consumes.

    This is what makes the graph properties a cache rather than a second source
    of truth: they are rebuilt from here, and `rebuild_projection` proves it by
    clearing them first.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT subject_ref, subject_type, band, score, evidence_coverage,
                   model_fingerprint, computed_at
              FROM assessment_current
            """
        )
        return [
            {
                "subject_ref": row["subject_ref"],
                "subject_type": row["subject_type"],
                "band": row["band"],
                "score": float(row["score"]) if row["score"] is not None else None,
                "coverage": float(row["evidence_coverage"]),
                "model_fingerprint": row["model_fingerprint"],
                "computed_at": row["computed_at"].isoformat(),
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
            INSERT INTO assessment_evaluations (
                run_id, model_version, model_fingerprint, report, triggered_by
            ) VALUES ($1, $2, $3, $4::jsonb, $5) RETURNING evaluation_id
            """,
            run_id,
            model_version,
            model_fingerprint,
            json.dumps(report),
            triggered_by,
        )


async def latest_evaluation(model_fingerprint: str | None = None) -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM assessment_evaluations
             WHERE ($1::text IS NULL OR model_fingerprint = $1)
             ORDER BY generated_at DESC LIMIT 1
            """,
            model_fingerprint,
        )
        if row is None:
            return None
        report = row["report"]
        return {
            "evaluation_id": row["evaluation_id"],
            "run_id": row["run_id"],
            "model_version": row["model_version"],
            "model_fingerprint": row["model_fingerprint"],
            "generated_at": row["generated_at"].isoformat(),
            "triggered_by": row["triggered_by"],
            "report": json.loads(report) if isinstance(report, str) else report,
        }
