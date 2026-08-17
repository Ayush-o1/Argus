"""Risk assessment API — what ARGUS concluded, and what it could not.

Two things every response here does that the risk endpoints it replaces did
not:

  * **The denominator travels with the number.** No endpoint returns a score
    without the share of the model that could be evaluated to produce it.
  * **Unassessable subjects are counted, not filtered.** The queue and the
    band counts both include them, plainly labelled. A queue that silently
    dropped every entity ARGUS knows nothing about would present a population
    ARGUS had an opinion about as though it were the whole population.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.dependencies import require_permission
from app.assessment.evidence import ASSESSED_TYPES
from app.assessment.model import BAND_MEANING, BANDS, default_model
from app.assessment.scoring import signal_catalogue
from app.database.neo4j import get_driver
from app.models.envelope import Envelope, Meta
from app.repositories import assessment_repo as repo
from app.security.roles import Permission
from app.security.sessions import AuthenticatedUser
from app.services import assessment as service
from app.services import audit, queue

router = APIRouter(
    prefix="/api/assessment",
    tags=["assessment"],
    dependencies=[Depends(require_permission(Permission.ASSESSMENT_READ))],
)


class RunRequest(BaseModel):
    # Publishing the evaluation alongside the run is opt-in: it reads ground
    # truth, which is meaningful only against a synthetic dataset, and on a real
    # deployment there is nothing to measure against.
    evaluate: bool = False


def _assessment_payload(row: repo.AssessmentRow) -> dict[str, Any]:
    return {
        "subject_ref": row.subject_ref,
        "subject_type": row.subject_type,
        "band": row.band,
        "band_meaning": BAND_MEANING.get(row.band, ""),
        "score": row.score,
        "evidence_coverage": row.evidence_coverage,
        "evaluable_weight": row.evaluable_weight,
        "total_weight": row.total_weight,
        "families_fired": row.families_fired,
        "model_version": row.model_version,
        "model_fingerprint": row.model_fingerprint,
        "computed_at": row.computed_at.isoformat(),
        "signals": row.signals,
    }


@router.get("/model")
async def get_model() -> Envelope[dict]:
    """The model in full: every signal, its weight, and the question it asks.

    Published deliberately. A model whose questions are secret cannot be argued
    with, and a finding nobody can argue with is not intelligence — it is an
    assertion of authority.
    """
    model = default_model()
    return Envelope(
        data={
            "version": model.version,
            "fingerprint": model.fingerprint(),
            "short_fingerprint": model.short_fingerprint,
            "method": model.method,
            "assessed_types": list(ASSESSED_TYPES),
            "bands": [{"band": band, "meaning": BAND_MEANING[band]} for band in BANDS],
            "thresholds": {
                "elevated_score": model.elevated_score,
                "notable_score": model.notable_score,
                "min_coverage_for_score": model.min_coverage_for_score,
                "min_coverage_for_elevated": model.min_coverage_for_elevated,
                "reference_weight": model.reference_weight,
            },
            "signals": signal_catalogue(),
        }
    )


@router.get("/summary")
async def get_summary() -> Envelope[dict]:
    """Band counts across the whole assessed population, plus the last run.

    The counts sum to the population by construction, `insufficient_evidence`
    included. That bucket is usually the largest one, and hiding it would make
    the rest look like a complete picture of a world ARGUS has mostly not seen.
    """
    counts = await repo.current_band_counts()
    run = await repo.latest_run()
    total = sum(counts.values())
    return Envelope(
        data={
            "band_counts": [
                {
                    "band": band,
                    "count": counts.get(band, 0),
                    "share": round(counts.get(band, 0) / total, 4) if total else None,
                    "meaning": BAND_MEANING[band],
                }
                for band in BANDS
            ],
            "assessed_total": total,
            "last_run": None
            if run is None
            else {
                "run_id": run.run_id,
                "status": run.status,
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "model_version": run.model_version,
                "model_fingerprint": run.model_fingerprint,
                "evidence_summary": run.evidence_summary,
                "search_truncated": run.search_truncated,
                "triggered_by": run.triggered_by,
                "error": run.error,
            },
        }
    )


@router.get("/queue")
async def get_queue(
    band: str | None = Query(None),
    subject_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> Envelope[list[dict]]:
    if band is not None and band not in BANDS:
        raise HTTPException(status_code=422, detail=f"Unknown band {band!r}")
    if subject_type is not None and subject_type not in ASSESSED_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"ARGUS does not assess {subject_type!r}. Assessed types: "
            f"{', '.join(ASSESSED_TYPES)}",
        )

    rows, total = await repo.list_current(
        band=band, subject_type=subject_type, page=page, page_size=page_size
    )
    return Envelope(
        data=[_assessment_payload(row) for row in rows],
        meta=Meta(total=total, page=page, page_size=page_size),
    )


@router.get("/subject/{subject_ref}")
async def get_subject(subject_ref: str) -> Envelope[dict]:
    row = await repo.current_for_subject(subject_ref)
    if row is None:
        # Not a 404 for the entity — a 404 for the *assessment*, with the
        # reason. "ARGUS has not assessed this" and "this does not exist" are
        # different facts and must not share a response.
        raise HTTPException(
            status_code=404,
            detail=(
                f"No assessment exists for {subject_ref}. ARGUS assesses "
                f"{', '.join(ASSESSED_TYPES)}; other entity types carry no assessment, and a "
                f"run may not have covered this subject yet."
            ),
        )
    return Envelope(data=_assessment_payload(row))


@router.get("/subject/{subject_ref}/history")
async def get_history(
    subject_ref: str, limit: int = Query(20, ge=1, le=100)
) -> Envelope[list[dict]]:
    """Every generation for one subject.

    The reason the table is append-only: "why did this change?" is a question
    an analyst is entitled to ask, and it can only be answered if both answers
    still exist.
    """
    rows = await repo.history_for_subject(subject_ref, limit=limit)
    return Envelope(
        data=[
            {
                "assessment_id": row.assessment_id,
                "run_id": row.run_id,
                "band": row.band,
                "score": row.score,
                "evidence_coverage": row.evidence_coverage,
                "model_fingerprint": row.model_fingerprint,
                "computed_at": row.computed_at.isoformat(),
            }
            for row in rows
        ]
    )


@router.get("/runs")
async def list_runs(limit: int = Query(10, ge=1, le=50)) -> Envelope[list[dict]]:
    runs = await repo.list_runs(limit)
    return Envelope(
        data=[
            {
                "run_id": run.run_id,
                "status": run.status,
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "model_version": run.model_version,
                "model_fingerprint": run.model_fingerprint,
                "subjects_assessed": run.subjects_assessed,
                "band_counts": {
                    "elevated": run.elevated_count,
                    "notable": run.notable_count,
                    "routine": run.routine_count,
                    "insufficient_evidence": run.insufficient_count,
                },
                "evidence_summary": run.evidence_summary,
                "search_truncated": run.search_truncated,
                "triggered_by": run.triggered_by,
                "error": run.error,
            }
            for run in runs
        ]
    )


@router.get("/evaluation")
async def get_evaluation(fingerprint: str | None = None) -> Envelope[dict | None]:
    """The published measurement of the model against ground truth.

    Returns the whole report or nothing. The per-storyline breakdown and the
    caveats are part of the figure, not commentary on it: precision quoted
    without the note saying which planted phenomena are undetectable by
    construction would be a different and more flattering claim.
    """
    return Envelope(data=await repo.latest_evaluation(fingerprint))


@router.post("/run", dependencies=[Depends(require_permission(Permission.ASSESSMENT_RUN))])
async def request_run(
    payload: RunRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.ASSESSMENT_RUN)),
) -> Envelope[dict]:
    """Queue a full re-assessment.

    Queued rather than executed inline: a run rewrites every risk figure in the
    product, and tying that to the lifetime of one HTTP request would mean a
    dropped connection could leave the population half-assessed under two
    different models.
    """
    job_id = await queue.enqueue(
        service.ASSESSMENT_JOB_KIND,
        {"triggered_by": f"user:{user.id}", "evaluate": payload.evaluate},
        priority=50,
    )
    await audit.record(
        audit.AuditEvent(
            action="assessment.run_requested",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="AssessmentRun",
            resource_id=str(job_id),
            after_state={"evaluate": payload.evaluate},
            request_id=getattr(request.state, "request_id", None),
        )
    )
    return Envelope(data={"job_id": job_id, "queued": job_id is not None})


@router.post(
    "/projection/rebuild",
    dependencies=[Depends(require_permission(Permission.ASSESSMENT_RUN))],
)
async def rebuild_projection(
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.ASSESSMENT_RUN)),
) -> Envelope[dict]:
    """Drop the graph's cached assessment properties and rebuild them from the
    ledger. Exposed because a cache that cannot be rebuilt on demand is not a
    cache — it is a second source of truth nobody audits."""
    result = await service.rebuild_projection(get_driver())
    await audit.record(
        audit.AuditEvent(
            action="assessment.projection_rebuilt",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="AssessmentProjection",
            resource_id="all",
            after_state=result,
            request_id=getattr(request.state, "request_id", None),
        )
    )
    return Envelope(data=result)
