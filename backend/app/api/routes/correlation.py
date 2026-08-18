"""Correlation API — what ARGUS connected, and on what grounds.

Three things every response here does that a conventional "related entities"
endpoint does not:

  * **The reason travels with the link.** No endpoint returns a strength
    without the dimensions that produced it and the ones that could not be
    evaluated. A link with no working shown is an assertion of authority.
  * **Weak links are returned, labelled weak.** `possible` links are published
    so an analyst can dismiss one with its reason visible, rather than being
    shown a shorter list that looks more decisive than the evidence was.
  * **Clusters carry their own fragility.** Every cluster states which links
    hold it together and how strong the weakest of those is, because a group of
    eleven hanging off one uncertain link is not a discovery of eleven
    connected subjects.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.api.dependencies import require_permission
from app.correlation.linking import dimension_catalogue
from app.correlation.model import (
    FAMILIES,
    FAMILY_CEILINGS,
    FAMILY_MEANING,
    IDENTIFYING_FAMILIES,
    TIER_MEANING,
    TIERS,
    default_model,
)
from app.correlation.projection import catalogue as projection_catalogue
from app.database.neo4j import get_driver
from app.models.envelope import Envelope, Meta
from app.repositories import correlation_repo as repo
from app.security.roles import Permission
from app.security.sessions import AuthenticatedUser
from app.services import audit, queue
from app.services import correlation as service

router = APIRouter(
    prefix="/api/correlation",
    tags=["correlation"],
    dependencies=[Depends(require_permission(Permission.CORRELATION_READ))],
)


class RunRequest(BaseModel):
    # Publishing the evaluation alongside the run is opt-in: it reads ground
    # truth, which exists only in a synthetic dataset. On a real deployment
    # there is nothing to measure against, and an endpoint that pretended
    # otherwise would be inventing a score.
    evaluate: bool = False


def _link_payload(row: repo.LinkRow) -> dict[str, Any]:
    return {
        "link_id": row.link_id,
        "ref_a": row.ref_a,
        "ref_b": row.ref_b,
        "type_a": row.type_a,
        "type_b": row.type_b,
        "strength": row.strength,
        "tier": row.tier,
        "tier_meaning": TIER_MEANING.get(row.tier, ""),
        "coverage": row.coverage,
        "evaluable_dimensions": row.evaluable_dimensions,
        "applicable_dimensions": row.applicable_dimensions,
        "corroborating_families": row.corroborating_families,
        "model_version": row.model_version,
        "model_fingerprint": row.model_fingerprint,
        "computed_at": row.computed_at.isoformat(),
        "dimensions": row.dimensions,
    }


def _cluster_payload(row: repo.ClusterRow) -> dict[str, Any]:
    return {
        "cluster_id": row.cluster_id,
        "cluster_key": row.cluster_key,
        "size": row.size,
        "families": row.families,
        "mean_strength": row.mean_strength,
        "min_strength": row.min_strength,
        "weakest_bridge": row.weakest_bridge,
        "bridge_count": row.bridge_count,
        "over_merged": row.over_merged,
        "basis": row.basis,
        "model_version": row.model_version,
        "model_fingerprint": row.model_fingerprint,
        "computed_at": row.computed_at.isoformat(),
        "members": row.members,
    }


@router.get("/model")
async def get_model() -> Envelope[dict]:
    """The model in full: every dimension, its family, and the question it asks.

    Published deliberately, as the assessment model is. A correlation nobody can
    interrogate is worse than a risk score nobody can interrogate, because it
    makes a claim about two people at once.
    """
    model = default_model()
    return Envelope(
        data={
            "version": model.version,
            "fingerprint": model.fingerprint(),
            "short_fingerprint": model.short_fingerprint,
            "method": model.method,
            "tiers": [{"tier": tier, "meaning": TIER_MEANING[tier]} for tier in TIERS],
            "families": [
                {
                    "family": family,
                    "meaning": FAMILY_MEANING[family],
                    "ceiling": FAMILY_CEILINGS[family],
                    # Whether this family can establish a link on its own, or
                    # only corroborate one. Published because "proximity is not
                    # evidence of association" is a design claim, and a reader
                    # is entitled to check that the arithmetic agrees with it.
                    "identifying": family in IDENTIFYING_FAMILIES,
                }
                for family in FAMILIES
            ],
            "thresholds": {
                "min_strength": model.min_strength,
                "probable_strength": model.probable_strength,
                "established_strength": model.established_strength,
                "established_min_families": model.established_min_families,
                "dimension_floor": model.dimension_floor,
                "cluster_min_strength": model.cluster_min_strength,
                "cluster_min_size": model.cluster_min_size,
                "max_cluster_size": model.max_cluster_size,
                "max_shared_key_fanout": model.max_shared_key_fanout,
                "path_max_hops": model.path_max_hops,
                "proximity_trigger_km": model.proximity_trigger_km,
                "coincidence_window_hours": model.coincidence_window_hours,
            },
            "dimensions": dimension_catalogue(),
            "projections": projection_catalogue(),
        }
    )


@router.get("/summary")
async def get_summary() -> Envelope[dict]:
    """Tier counts across the current generation, plus the last run.

    `keys_skipped` and `search_truncated` are part of the summary rather than
    buried in a diagnostics endpoint. Both mean ARGUS did not look everywhere,
    and a link count presented without them reads as exhaustive when it is not.
    """
    counts = await repo.current_tier_counts()
    run = await repo.latest_run()
    total = sum(counts.values())
    clusters = await repo.list_current_clusters(limit=1000)
    return Envelope(
        data={
            "tier_counts": [
                {
                    "tier": tier,
                    "count": counts.get(tier, 0),
                    "share": round(counts.get(tier, 0) / total, 4) if total else None,
                    "meaning": TIER_MEANING[tier],
                }
                for tier in TIERS
            ],
            "links_total": total,
            "clusters_total": len(clusters),
            "over_merged_clusters": sum(1 for c in clusters if c.over_merged),
            "clustered_subjects": sum(c.size for c in clusters),
            "last_run": None
            if run is None
            else {
                "run_id": run.run_id,
                "status": run.status,
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "model_version": run.model_version,
                "model_fingerprint": run.model_fingerprint,
                "assessment_run_id": run.assessment_run_id,
                "anchors": run.anchors,
                "candidate_pairs": run.candidate_pairs,
                "links_recorded": run.links_recorded,
                "clusters_found": run.clusters_found,
                "keys_skipped": run.keys_skipped,
                "search_truncated": run.search_truncated,
                "evidence_summary": run.evidence_summary,
                "triggered_by": run.triggered_by,
                "error": run.error,
            },
        }
    )


@router.get("/links")
async def list_links(
    tier: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
) -> Envelope[list[dict]]:
    if tier is not None and tier not in TIERS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown tier {tier!r}. Tiers: {', '.join(TIERS)}",
        )
    counts = await repo.current_tier_counts()
    total = counts.get(tier, 0) if tier else sum(counts.values())
    rows = await repo.list_current_links(
        tier=tier, limit=page_size, offset=(page - 1) * page_size
    )
    return Envelope(
        data=[_link_payload(row) for row in rows],
        meta=Meta(total=total, page=page, page_size=page_size),
    )


@router.get("/subject/{subject_ref}")
async def get_subject(subject_ref: str, limit: int = Query(25, ge=1, le=100)) -> Envelope[dict]:
    """Everything ARGUS links this subject to, and every cluster it belongs to.

    Returns an empty list rather than a 404 when there are none. "ARGUS found no
    correlation" is a finding; "this subject does not exist" is a different one,
    and a shared status code would make them indistinguishable to the caller.
    """
    links = await repo.links_for_subject(subject_ref, limit=limit)
    clusters = await repo.clusters_for_subject(subject_ref)
    return Envelope(
        data={
            "subject_ref": subject_ref,
            "links": [_link_payload(row) for row in links],
            "clusters": [_cluster_payload(row) for row in clusters],
        }
    )


@router.get("/clusters")
async def list_clusters(limit: int = Query(25, ge=1, le=100)) -> Envelope[list[dict]]:
    rows = await repo.list_current_clusters(limit=limit)
    return Envelope(data=[_cluster_payload(row) for row in rows])


@router.get("/cluster/{cluster_key}")
async def get_cluster(cluster_key: str) -> Envelope[dict]:
    row = await repo.cluster_by_key(cluster_key)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No current cluster with key {cluster_key}. Cluster keys are derived from "
                f"membership, so a cluster that gained or lost a member has a different key — "
                f"this one may have existed in an earlier run."
            ),
        )
    return Envelope(data=_cluster_payload(row))


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
                "assessment_run_id": run.assessment_run_id,
                "anchors": run.anchors,
                "candidate_pairs": run.candidate_pairs,
                "pairs_scored": run.pairs_scored,
                "links_recorded": run.links_recorded,
                "clusters_found": run.clusters_found,
                "keys_skipped": run.keys_skipped,
                "search_truncated": run.search_truncated,
                "evidence_summary": run.evidence_summary,
                "triggered_by": run.triggered_by,
                "error": run.error,
            }
            for run in runs
        ]
    )


@router.get("/evaluation")
async def get_evaluation(fingerprint: str | None = None) -> Envelope[dict | None]:
    """The published measurement of the model against ground truth.

    Returns the whole report or nothing. The caveats are part of the figure
    rather than commentary on it — in particular the one saying an unlabelled
    link is not a wrong link, without which the strict precision figure means
    something considerably worse than what it measures.
    """
    return Envelope(data=await repo.latest_evaluation(fingerprint))


@router.post("/run", dependencies=[Depends(require_permission(Permission.CORRELATION_RUN))])
async def request_run(
    payload: RunRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.CORRELATION_RUN)),
) -> Envelope[dict]:
    """Queue a full re-correlation.

    Queued rather than executed inline: the pair count grows faster than the
    anchor count, so tying a population-wide recomputation to the lifetime of
    one HTTP request would mean a dropped connection could leave half a
    generation of links written under one model and half under another.
    """
    job_id = await queue.enqueue(
        service.CORRELATION_JOB_KIND,
        {"triggered_by": f"user:{user.id}", "evaluate": payload.evaluate},
        priority=50,
    )
    await audit.record(
        audit.AuditEvent(
            action="correlation.run_requested",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="CorrelationRun",
            resource_id=str(job_id),
            after_state={"evaluate": payload.evaluate},
            request_id=getattr(request.state, "request_id", None),
        )
    )
    return Envelope(data={"job_id": job_id, "queued": job_id is not None})


@router.post(
    "/projection/rebuild",
    dependencies=[Depends(require_permission(Permission.CORRELATION_RUN))],
)
async def rebuild_projection(
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.CORRELATION_RUN)),
) -> Envelope[dict]:
    """Drop the graph's cached cluster properties and rebuild them from the
    ledger. Exposed because a cache that cannot be rebuilt on demand is not a
    cache — it is a second source of truth nobody audits."""
    result = await service.rebuild_projection(get_driver())
    await audit.record(
        audit.AuditEvent(
            action="correlation.projection_rebuilt",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="CorrelationProjection",
            resource_id="all",
            after_state=result,
            request_id=getattr(request.state, "request_id", None),
        )
    )
    return Envelope(data=result)
