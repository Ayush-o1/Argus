"""Entity resolution API — the review queue, the decision ledger, and clusters.

The queue endpoint returns counts for every band, not just the one being
displayed. An analyst looking at 14 pending pairs needs to know that the
matcher also declined to raise 300 as too thin and rejected 4,000 outright;
without those, "14" reads as "14 duplicates exist", which is a claim ARGUS
cannot make.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.dependencies import require_permission
from app.database.neo4j import get_driver
from app.models.envelope import Envelope
from app.repositories import resolution_graph_repo as graph_repo
from app.repositories import resolution_repo as repo
from app.resolution.profile import SUPPORTED_TYPES
from app.resolution.scoring import DEFAULT_MODEL, RULES
from app.security.roles import Permission
from app.security.sessions import AuthenticatedUser
from app.services import audit, queue, resolution

router = APIRouter(
    prefix="/api/resolution",
    tags=["resolution"],
    dependencies=[Depends(require_permission(Permission.RESOLUTION_READ))],
)

MAX_RATIONALE = 2_000


class DecideRequest(BaseModel):
    verdict: str = Field(pattern="^(same|different)$")
    # Required, and not defaulted. A merge whose reason is "" is a merge nobody
    # can review, and the whole point of the queue is that decisions stay
    # answerable to the next analyst.
    rationale: str = Field(min_length=3, max_length=MAX_RATIONALE)


class DecidePairRequest(BaseModel):
    left_ref: str = Field(min_length=1, max_length=64)
    right_ref: str = Field(min_length=1, max_length=64)
    verdict: str = Field(pattern="^(same|different)$")
    rationale: str = Field(min_length=3, max_length=MAX_RATIONALE)


class ReverseRequest(BaseModel):
    rationale: str = Field(min_length=3, max_length=MAX_RATIONALE)


class PinRequest(BaseModel):
    ref: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=3, max_length=MAX_RATIONALE)


class RunRequest(BaseModel):
    entity_types: list[str] | None = None
    # Score without merging anything. The mode to use after changing weights:
    # the effect lands in the queue where it can be inspected before it is
    # allowed to act on its own.
    apply_auto: bool = True


@router.get("/queue")
async def get_queue(
    band: str = Query("review", pattern="^(review|auto|insufficient|reject)$"),
    entity_type: str | None = None,
    include_decided: bool = False,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Envelope[dict]:
    candidates = await repo.list_candidates(
        band=band,
        status="decided" if include_decided else "open",
        entity_type=entity_type,
        limit=limit,
        offset=offset,
    )
    return Envelope(
        data={
            "candidates": [_candidate_payload(c) for c in candidates],
            # Every band, every status — the denominators.
            "counts": await repo.candidate_counts(),
            "clusters": await repo.cluster_counts(),
            "labels": await repo.label_counts(),
            "model": {
                "version": DEFAULT_MODEL.version,
                "fingerprint": DEFAULT_MODEL.fingerprint(),
                "auto_score": DEFAULT_MODEL.auto_score,
                "review_score": DEFAULT_MODEL.review_score,
                "min_evidence_for_review": DEFAULT_MODEL.min_evidence_for_review,
                "min_evidence_for_auto": DEFAULT_MODEL.min_evidence_for_auto,
            },
            "supported_types": sorted(SUPPORTED_TYPES),
        }
    )


@router.get("/model")
async def get_model() -> Envelope[dict]:
    """The full rule set — every attribute, its weight, and its role.

    Published rather than buried so an analyst can see exactly what the score
    in front of them was computed from. A weighting nobody can inspect is not
    reviewable, however well documented the code is.
    """
    return Envelope(
        data={
            "version": DEFAULT_MODEL.version,
            "fingerprint": DEFAULT_MODEL.fingerprint(),
            "thresholds": {
                "auto_score": DEFAULT_MODEL.auto_score,
                "review_score": DEFAULT_MODEL.review_score,
                "min_evidence_for_review": DEFAULT_MODEL.min_evidence_for_review,
                "min_evidence_for_auto": DEFAULT_MODEL.min_evidence_for_auto,
            },
            "rules": {
                entity_type: [
                    {
                        "key": rule.key,
                        "label": rule.label,
                        "comparator": rule.comparator,
                        "weight": rule.weight,
                        "disqualifying": rule.disqualifying,
                        "strong_identifier": rule.strong_identifier,
                    }
                    for rule in rules
                ]
                for entity_type, rules in sorted(RULES.items())
            },
        }
    )


@router.get("/candidates/{candidate_id}")
async def get_candidate(candidate_id: int) -> Envelope[dict]:
    candidate = await repo.get_candidate(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    payload = _candidate_payload(candidate)
    payload["history"] = [
        _decision_payload(d)
        for d in await repo.decision_history(candidate.left_ref, candidate.right_ref)
    ]
    return Envelope(data=payload)


@router.post("/candidates/{candidate_id}/decide")
async def decide_candidate(
    candidate_id: int,
    payload: DecideRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.RESOLUTION_DECIDE)),
) -> Envelope[dict]:
    candidate = await repo.get_candidate(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.status == "decided":
        raise HTTPException(
            status_code=409,
            detail=(
                "This pair has already been decided. Reverse the existing decision "
                "rather than deciding again, so the change is recorded as a reversal."
            ),
        )

    try:
        result = await resolution.decide(
            left_ref=candidate.left_ref,
            right_ref=candidate.right_ref,
            verdict=payload.verdict,
            actor=f"user:{user.id}",
            actor_kind="analyst",
            rationale=payload.rationale,
            entity_type=candidate.entity_type,
            candidate_id=candidate.candidate_id,
            score=candidate.score,
            evidence_weight=candidate.evidence_weight,
            model_version=candidate.model_version,
            model_fingerprint=candidate.model_fingerprint,
            audit_actor=user,
        )
    except resolution.DecisionRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Envelope(data=result)


@router.post("/decisions")
async def decide_pair(
    payload: DecidePairRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.RESOLUTION_DECIDE)),
) -> Envelope[dict]:
    """Record a decision about two records the matcher never proposed.

    The escape hatch for the one failure in this pipeline that leaves no trace:
    a pair no blocking key brings together is never scored, never queued, and
    appears nowhere as something ARGUS declined to consider. Blocking recall is
    measured (see the evaluation report) but it is not 1.0 in general, so an
    analyst who finds a duplicate by hand has to be able to say so.

    The pair is scored on the way through, so the decision still carries what
    the model thought at the time — including, usefully, the cases where the
    model disagreed with the person.
    """
    for ref in (payload.left_ref, payload.right_ref):
        if not await graph_repo.entity_exists(get_driver(), ref):
            raise HTTPException(status_code=404, detail=f"No entity {ref}")

    left = await graph_repo.fetch_profile(get_driver(), payload.left_ref)
    right = await graph_repo.fetch_profile(get_driver(), payload.right_ref)
    scored = None
    if left is not None and right is not None and left.entity_type == right.entity_type:
        from app.resolution.scoring import compare

        scored = compare(left, right)

    try:
        result = await resolution.decide(
            left_ref=payload.left_ref,
            right_ref=payload.right_ref,
            verdict=payload.verdict,
            actor=f"user:{user.id}",
            actor_kind="analyst",
            rationale=payload.rationale,
            score=scored.score if scored else None,
            evidence_weight=scored.evidence_weight if scored else None,
            model_version=scored.model_version if scored else None,
            model_fingerprint=scored.model_fingerprint if scored else None,
            audit_actor=user,
        )
    except resolution.DecisionRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Envelope(
        data={
            **result,
            "matcher_band": scored.band if scored else None,
            "matcher_reason": scored.band_reason if scored else None,
        }
    )


@router.get("/decisions")
async def list_decisions(
    verdict: str | None = Query(None, pattern="^(same|different)$"),
    limit: int = Query(50, ge=1, le=200),
) -> Envelope[list[dict]]:
    rows = await repo.recent_decisions(verdict=verdict, limit=limit)
    return Envelope(data=[_decision_payload(d) for d in rows])


@router.get("/decisions/pair")
async def pair_history(left: str, right: str) -> Envelope[dict]:
    """Full lineage for a pair — every decision ever made about it.

    Returned as a list rather than a current state on purpose: "merged,
    un-merged, merged again by someone else" is a different situation from
    "merged", and collapsing the history hides which one you are looking at.
    """
    history = await repo.decision_history(left, right)
    current = await repo.current_decision(left, right)
    return Envelope(
        data={
            "left_ref": left,
            "right_ref": right,
            "current": _decision_payload(current) if current else None,
            "history": [_decision_payload(d) for d in history],
        }
    )


@router.post("/decisions/{decision_id}/reverse")
async def reverse(
    decision_id: int,
    payload: ReverseRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.RESOLUTION_MANAGE)),
) -> Envelope[dict]:
    """Undo a decision by recording its opposite. Nothing is deleted."""
    try:
        result = await resolution.reverse_decision(
            decision_id,
            actor=f"user:{user.id}",
            actor_kind="analyst",
            rationale=payload.rationale,
            audit_actor=user,
        )
    except resolution.DecisionRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Envelope(data=result)


@router.get("/clusters")
async def list_clusters(
    contested_only: bool = False,
    entity_type: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> Envelope[dict]:
    clusters = await repo.list_clusters(
        contested_only=contested_only, entity_type=entity_type, limit=limit
    )
    return Envelope(data={"clusters": clusters, "counts": await repo.cluster_counts()})


@router.get("/entity/{ref}")
async def entity_resolution_state(ref: str) -> Envelope[dict]:
    """Everything resolution knows about one record.

    Consumed by the entity profile so a page can say "ARGUS believes this is
    the same record as two others" beside the record itself, rather than only
    in a queue an analyst has to remember to visit.
    """
    cluster = await repo.cluster_for_ref(ref)
    return Envelope(
        data={
            "ref": ref,
            "exists": await graph_repo.entity_exists(get_driver(), ref),
            "cluster": cluster,
            "same_as": await graph_repo.same_as_neighbours(get_driver(), ref),
            "candidates": [_candidate_payload(c) for c in await repo.candidates_for_ref(ref)],
            "decisions": [_decision_payload(d) for d in await repo.decisions_for_ref(ref)],
        }
    )


@router.post("/clusters/pin")
async def pin_canonical(
    payload: PinRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.RESOLUTION_MANAGE)),
) -> Envelope[dict]:
    """Choose which record represents a cluster.

    Canonical selection is otherwise a stated rule (most observations, then
    lowest id). Pinning overrides it with a human judgement, and the basis
    shown in the UI changes to say so — the point is never to hide which of the
    two it was.
    """
    if not await graph_repo.entity_exists(get_driver(), payload.ref):
        raise HTTPException(status_code=404, detail=f"No entity {payload.ref}")
    await repo.pin_canonical(payload.ref, pinned_by=f"user:{user.id}", reason=payload.reason)
    summary = await resolution.rebuild_clusters()
    await audit.record(
        audit.AuditEvent(
            action="resolution.canonical_pinned",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="ResolutionCluster",
            resource_id=payload.ref,
            after_state={"reason": payload.reason},
            request_id=getattr(request.state, "request_id", None),
        )
    )
    return Envelope(data=summary)


@router.get("/runs")
async def list_runs(limit: int = Query(10, ge=1, le=50)) -> Envelope[list[dict]]:
    return Envelope(data=await repo.recent_runs(limit))


@router.post("/runs")
async def start_run(
    payload: RunRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.RESOLUTION_MANAGE)),
) -> Envelope[dict]:
    """Queue a matcher sweep. Returns the job id, not the result.

    Durable rather than inline for the same reason ingestion runs are: a sweep
    over the population is minutes of work, and an HTTP request is the least
    durable place to hold it.
    """
    unknown = [t for t in (payload.entity_types or []) if t not in SUPPORTED_TYPES]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=(
                f"ARGUS does not resolve identity for: {', '.join(unknown)}. "
                f"Supported: {', '.join(sorted(SUPPORTED_TYPES))}"
            ),
        )
    job_id = await queue.enqueue(
        resolution.MATCH_JOB_KIND,
        {
            "entity_types": payload.entity_types,
            "apply_auto": payload.apply_auto,
            "triggered_by": f"user:{user.id}",
        },
        priority=50,
    )
    await audit.record(
        audit.AuditEvent(
            action="resolution.run_requested",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="ResolutionRun",
            resource_id=str(job_id),
            after_state={
                "entity_types": payload.entity_types,
                "apply_auto": payload.apply_auto,
            },
            request_id=getattr(request.state, "request_id", None),
        )
    )
    return Envelope(data={"job_id": job_id, "queued": job_id is not None})


@router.get("/evaluations")
async def list_evaluations(limit: int = Query(10, ge=1, le=50)) -> Envelope[list[dict]]:
    """Published precision and recall, per model fingerprint."""
    return Envelope(data=await repo.recent_evaluations(limit))


@router.post("/evaluations")
async def run_evaluation(
    request: Request,
    entity_type: str = Query("Person"),
    sample: int = Query(1500, ge=100, le=20_000),
    user: AuthenticatedUser = Depends(require_permission(Permission.RESOLUTION_MANAGE)),
) -> Envelope[dict]:
    if entity_type not in SUPPORTED_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported entity type {entity_type}")
    reports = await resolution.run_evaluation(entity_type=entity_type, sample=sample)
    await audit.record(
        audit.AuditEvent(
            action="resolution.evaluated",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="ResolutionEvaluation",
            resource_id=DEFAULT_MODEL.fingerprint(),
            after_state={"entity_type": entity_type, "sample": sample},
            request_id=getattr(request.state, "request_id", None),
        )
    )
    return Envelope(data=reports)


@router.post("/rebuild-projection")
async def rebuild_projection(
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.RESOLUTION_MANAGE)),
) -> Envelope[dict]:
    """Re-derive every SAME_AS edge from the decision ledger.

    A repair tool and a proof at once: if the graph and Postgres ever disagree
    about what has been merged, this makes Postgres win.
    """
    result = await resolution.rebuild_projection()
    await audit.record(
        audit.AuditEvent(
            action="resolution.projection_rebuilt",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="ResolutionProjection",
            resource_id="graph",
            after_state=result,
            request_id=getattr(request.state, "request_id", None),
        )
    )
    return Envelope(data=result)


def _candidate_payload(candidate: Any) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "entity_type": candidate.entity_type,
        "left_ref": candidate.left_ref,
        "right_ref": candidate.right_ref,
        "score": candidate.score,
        "evidence_weight": candidate.evidence_weight,
        "band": candidate.band,
        "band_reason": candidate.band_reason,
        "comparisons": candidate.comparisons,
        "blocking_keys": candidate.blocking_keys,
        "model_version": candidate.model_version,
        "model_fingerprint": candidate.model_fingerprint,
        "status": candidate.status,
        "created_at": candidate.created_at,
        "updated_at": candidate.updated_at,
    }


def _decision_payload(decision: Any) -> dict[str, Any]:
    return {
        "decision_id": decision.decision_id,
        "entity_type": decision.entity_type,
        "left_ref": decision.left_ref,
        "right_ref": decision.right_ref,
        "verdict": decision.verdict,
        "decided_by": decision.decided_by,
        "decided_by_display": decision.decided_by_display,
        "decided_by_kind": decision.decided_by_kind,
        "decided_at": decision.decided_at,
        "rationale": decision.rationale,
        "score": decision.score,
        "evidence_weight": decision.evidence_weight,
        "model_version": decision.model_version,
        "model_fingerprint": decision.model_fingerprint,
        "candidate_id": decision.candidate_id,
        "reverses_decision_id": decision.reverses_decision_id,
    }
