"""Running the assessor, publishing what it found, and measuring how well it did.

The order of operations here is the phase's integrity story in miniature:

  1. gather evidence through a projection that cannot see the answer key,
  2. score every subject under one fingerprinted model,
  3. write the result to Postgres, which is the record,
  4. project it onto the graph, which is a cache,
  5. publish the material findings as assertions, so provenance can show what
     ARGUS believes *and* what it inferred it from,
  6. separately, and only on request, measure the model against ground truth.

Step 6 is the only one that touches a `Storyline`, and it reads nothing that
steps 1–5 produce beyond the assessments themselves.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from neo4j import AsyncDriver

from app.assessment.evaluation import EvaluationReport, evaluate
from app.assessment.model import (
    BAND_ELEVATED,
    BAND_INSUFFICIENT,
    BAND_NOTABLE,
    RiskModel,
    default_model,
)
from app.assessment.scoring import Assessment, assess_all
from app.models.provenance import EpistemicKind, Rating
from app.repositories import assessment_graph_repo, assessment_repo, provenance_repo
from app.services import queue
from app.services.provenance import DERIVED_SOURCE_ID

logger = logging.getLogger(__name__)

ASSESSMENT_JOB_KIND = "assessment.run"
ASSESSMENT_PREDICATE = "argus_risk_assessment"

# The actor recorded when the scheduler, rather than a person, asks for a run.
ASSESSOR_ACTOR = "argus.assessor"

# Bands whose findings are published as assertions. `routine` and
# `insufficient_evidence` are deliberately not: writing 4,000 assertions a run
# saying "nothing found" would bury the provenance store under noise, and the
# assessment itself remains readable in full through the assessment API. The
# distinction is between what ARGUS *believes about a subject* and what it
# merely computed.
PUBLISHED_BANDS = frozenset({BAND_ELEVATED, BAND_NOTABLE})


@dataclass
class RunOutcome:
    run_id: int
    subjects_assessed: int
    band_counts: dict[str, int]
    cycles_found: int
    search_truncated: bool
    projected: int
    assertions_published: int


async def run_assessment(
    driver: AsyncDriver,
    *,
    triggered_by: str,
    model: RiskModel | None = None,
    publish_assertions: bool = True,
) -> RunOutcome:
    """Assess every subject in the graph, once, under one model."""
    active = model or default_model()
    run_id = await assessment_repo.start_run(active.version, active.fingerprint(), triggered_by)

    try:
        bundle = await assessment_graph_repo.fetch_evidence(driver)
        result = assess_all(bundle, active)

        await assessment_repo.store_assessments(run_id, result.assessments)

        evidence_summary = {
            "subjects": len(bundle.subjects),
            "transfers": len(bundle.transfers),
            "contacts": len(bundle.contacts),
            "accounts": len(bundle.accounts),
            "shipments": len(bundle.shipments),
            "directorships": len(bundle.directorships),
            "persons_with_devices": len(bundle.persons_with_devices),
            "cycles_found": result.cycles_found,
        }
        await assessment_repo.finish_run(
            run_id,
            band_counts=result.band_counts,
            evidence_summary=evidence_summary,
            search_truncated=result.cycle_search_truncated,
        )

        projected = await assessment_graph_repo.project_assessments(
            driver,
            [
                {
                    "subject_ref": a.subject_ref,
                    "subject_type": a.subject_type,
                    "band": a.band,
                    "score": a.score,
                    "coverage": a.evidence_coverage,
                    "model_fingerprint": a.model_fingerprint,
                    "computed_at": a.computed_at.isoformat(),
                }
                for a in result.assessments
            ],
        )

        published = 0
        if publish_assertions:
            published = await _publish_assertions(result.assessments, active)

        logger.info(
            "assessment run %s complete: %s subjects, bands=%s, %s cycles, %s assertions",
            run_id,
            len(result.assessments),
            result.band_counts,
            result.cycles_found,
            published,
        )
        return RunOutcome(
            run_id=run_id,
            subjects_assessed=len(result.assessments),
            band_counts=result.band_counts,
            cycles_found=result.cycles_found,
            search_truncated=result.cycle_search_truncated,
            projected=projected,
            assertions_published=published,
        )
    except Exception as exc:  # noqa: BLE001 - recorded, then re-raised
        await assessment_repo.fail_run(run_id, f"{type(exc).__name__}: {exc}")
        raise


async def _current_assertions_by_subject(method: str) -> dict[str, str]:
    """Every current assessment assertion from this model, in one query.

    Read up front rather than per subject: the per-subject form was a query for
    each published finding, which is the same N+1 that made the Phase 4 matcher
    unusable under a real feed.
    """
    from app.database.postgres import acquire

    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (subject_ref) subject_ref, assertion_id::text AS assertion_id
              FROM assertions
             WHERE predicate = $1 AND method = $2
               AND superseded_at IS NULL AND retracted_at IS NULL
             ORDER BY subject_ref, asserted_at DESC
            """,
            ASSESSMENT_PREDICATE,
            method,
        )
    return {row["subject_ref"]: row["assertion_id"] for row in rows}


async def _publish_assertions(assessments: list[Assessment], model: RiskModel) -> int:
    """Write the material findings into the provenance store.

    Each assertion is INFERRED, attributed to `argus.derived`, and carries the
    model's method identifier including its fingerprint. The rating is F on
    reliability — ARGUS has measured this model against one synthetic world,
    which is not a track record — and a credibility that reflects how many
    independent signal families agreed.

    Supersession is by subject and method: a new assessment replaces the
    previous one from the same model rather than accumulating alongside it, so
    the provenance view shows one current belief and its history rather than a
    stack of near-duplicates.

    A subject that *leaves* the published bands has its assertion retracted
    with a stated reason, not merely left alone. Without that, an entity found
    elevated last week and unremarkable today would still carry a current
    assertion saying it was elevated — ARGUS asserting a belief it no longer
    holds, which is a worse failure than never having published it.
    """
    published = 0
    existing = await _current_assertions_by_subject(model.method)

    for assessment in assessments:
        if assessment.band not in PUBLISHED_BANDS:
            stale = existing.get(assessment.subject_ref)
            if stale is not None:
                await provenance_repo.retract_assertion(
                    stale,
                    retracted_by=f"source:{DERIVED_SOURCE_ID}",
                    reason=(
                        f"Re-assessed as '{assessment.band}' on "
                        f"{assessment.computed_at.date().isoformat()}. The evidence that "
                        f"supported the previous finding no longer does, so the finding is "
                        f"withdrawn rather than left standing."
                    ),
                )
            continue

        previous = existing.get(assessment.subject_ref)
        fired = [
            {
                "signal_id": c.signal_id,
                "title": c.title,
                "magnitude": c.magnitude,
                "weight": c.weight,
                "summary": c.summary,
            }
            for c in assessment.fired
        ]
        note = (
            f"{assessment.headline()} "
            f"The score is a share of the {assessment.evaluable_weight:.0f} of "
            f"{assessment.total_weight:.0f} weight that could be evaluated for this subject, "
            f"not of the whole model. It is a recommendation to review, not a conclusion about "
            f"the subject, and it supersedes nothing the generator asserted — the synthetic "
            f"source's own figure remains recorded separately, as its own claim."
        )
        await provenance_repo.record_assertion(
            subject_ref=assessment.subject_ref,
            subject_type=assessment.subject_type,
            predicate=ASSESSMENT_PREDICATE,
            object_value={
                "band": assessment.band,
                "score": assessment.score,
                "evidence_coverage": assessment.evidence_coverage,
                "families_fired": list(assessment.families_fired),
                "signals": fired,
            },
            epistemic_kind=EpistemicKind.INFERRED,
            rating=Rating(
                reliability=assessment.reliability, credibility=assessment.credibility
            ),
            method=model.method,
            asserted_by=f"source:{DERIVED_SOURCE_ID}",
            note=note,
            supersedes=previous,
        )
        published += 1
    return published


async def rebuild_projection(driver: AsyncDriver) -> dict[str, int]:
    """Drop every projected property and rebuild it from Postgres.

    The proof that the graph properties are a cache and not a second source of
    truth. If this ever produced a different result from the last run, one of
    the two stores would be lying, and a test clears and rebuilds precisely to
    catch that.
    """
    cleared = await assessment_graph_repo.clear_projection(driver)
    rows = await assessment_repo.all_current_for_projection()
    written = await assessment_graph_repo.project_assessments(driver, rows)
    return {"cleared": cleared, "written": written}


async def run_evaluation(
    driver: AsyncDriver, *, triggered_by: str, model: RiskModel | None = None, top_k: int = 50
) -> EvaluationReport:
    """Measure the current assessments against the generator's planted storylines.

    Reads ground truth. Nothing it returns is written back into a score, and
    the assessments it measures were produced by a pipeline that could not see
    the labels — which is what makes the resulting figure worth anything.
    """
    active = model or default_model()
    labels = await assessment_graph_repo.fetch_ground_truth(driver)

    rows, _ = await assessment_repo.list_current(page=1, page_size=1_000_000)
    if not rows:
        raise ValueError("No assessments to evaluate — run the assessor first.")

    assessments = [
        Assessment(
            subject_ref=row.subject_ref,
            subject_type=row.subject_type,
            band=row.band,
            score=row.score,
            evidence_coverage=row.evidence_coverage,
            evaluable_weight=row.evaluable_weight,
            total_weight=row.total_weight,
            families_fired=tuple(row.families_fired),
            contributions=tuple(_contribution_from_row(s) for s in row.signals),
            model_fingerprint=row.model_fingerprint,
            model_version=row.model_version,
            computed_at=row.computed_at,
        )
        for row in rows
    ]

    report = evaluate(assessments, labels, active, top_k=top_k)
    run = await assessment_repo.latest_run()
    await assessment_repo.store_evaluation(
        run.run_id if run else None,
        active.version,
        active.fingerprint(),
        report.to_dict(),
        triggered_by,
    )
    return report


def _contribution_from_row(signal: dict[str, Any]):
    from app.assessment.scoring import SignalContribution
    from app.assessment.signals import SIGNALS_BY_ID

    definition = SIGNALS_BY_ID.get(signal["signal_id"])
    return SignalContribution(
        signal_id=signal["signal_id"],
        title=definition.title if definition else signal["signal_id"],
        question=definition.question if definition else "",
        family=signal.get("family", ""),
        weight=float(signal.get("weight") or 0.0),
        evaluable=bool(signal.get("evaluable")),
        magnitude=signal.get("magnitude"),
        contribution=float(signal.get("contribution") or 0.0),
        summary=signal.get("summary", ""),
        detail=signal.get("detail") or {},
    )


async def assessment_for(subject_ref: str) -> assessment_repo.AssessmentRow | None:
    return await assessment_repo.current_for_subject(subject_ref)


# ── Job registration ─────────────────────────────────────────────────────────


@queue.register(ASSESSMENT_JOB_KIND)
async def _run_assessment_job(job: queue.Job) -> None:
    """Durable-queue entry point, so a full sweep survives a restart.

    Assessing the whole graph is seconds on the reference world and will not
    stay that way. Running it inside the HTTP request that asked for it would
    tie a population-wide recomputation to the least durable thing in the
    system. The run's own row in `assessment_runs` is the result; the handler
    returns nothing.
    """
    from app.database.neo4j import get_driver

    payload = job.payload or {}
    outcome = await run_assessment(
        get_driver(),
        triggered_by=str(payload.get("triggered_by", ASSESSOR_ACTOR)),
    )
    logger.info(
        "assessment run complete",
        extra={"run_id": outcome.run_id, "bands": outcome.band_counts},
    )

    if payload.get("evaluate"):
        report = await run_evaluation(
            get_driver(), triggered_by=str(payload.get("triggered_by", ASSESSOR_ACTOR))
        )
        logger.info(
            "assessment evaluation published",
            extra={"fingerprint": report.model_fingerprint},
        )


def band_is_publishable(band: str) -> bool:
    """Whether a band represents a finding ARGUS asserts about a subject.

    Exposed so a caller cannot re-derive the rule slightly differently — the
    kind of drift that ends with one surface showing an assertion another
    surface says does not exist.
    """
    return band in PUBLISHED_BANDS and band != BAND_INSUFFICIENT


__all__ = [
    "ASSESSMENT_JOB_KIND",
    "ASSESSOR_ACTOR",
    "ASSESSMENT_PREDICATE",
    "BAND_ELEVATED",
    "BAND_NOTABLE",
    "RunOutcome",
    "assessment_for",
    "band_is_publishable",
    "rebuild_projection",
    "run_assessment",
    "run_evaluation",
]
