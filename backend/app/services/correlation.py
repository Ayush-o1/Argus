"""Running the correlator, publishing what it found, and measuring how well it did.

The order of operations is the phase's integrity story in miniature:

  1. take the anchors from the assessment ledger — ARGUS's own findings,
  2. gather structure through queries that cannot see a planted link,
  3. propose candidate pairs by blocking on identifying structure only,
  4. score every candidate under one fingerprinted model,
  5. write links and clusters to Postgres, which is the record,
  6. project cluster membership onto the graph, which is a cache,
  7. publish established links as assertions, so provenance can show what ARGUS
     believes and what it inferred it from,
  8. separately, and only on request, measure the model against ground truth.

Step 8 is the only one that touches a `Storyline`, and it reads nothing that
steps 1–7 produce beyond the links themselves.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from neo4j import AsyncDriver

from app.correlation import candidates as candidate_generation
from app.correlation.clustering import CorrelatedCluster, build_clusters
from app.correlation.dimensions import build_context
from app.correlation.evaluation import (
    CorrelationEvaluationReport,
    evaluate,
    pairs_from_storylines,
)
from app.correlation.linking import CorrelationLink, link_pair
from app.correlation.model import (
    TIER_ESTABLISHED,
    TIER_PROBABLE,
    CorrelationModel,
    default_model,
)
from app.models.provenance import EpistemicKind, Rating
from app.repositories import (
    assessment_repo,
    correlation_graph_repo,
    correlation_repo,
    provenance_repo,
)
from app.services import queue
from app.services.provenance import DERIVED_SOURCE_ID

logger = logging.getLogger(__name__)

CORRELATION_JOB_KIND = "correlation.run"
CORRELATION_PREDICATE = "argus_correlated_with"

CORRELATOR_ACTOR = "argus.correlator"

# Tiers whose links are published as assertions. `possible` is deliberately not:
# a possible link is shown so it can be dismissed with its reason visible, which
# is a UI concern, and writing thousands of them into the provenance store would
# bury the findings that matter under the ones that do not.
PUBLISHED_TIERS = frozenset({TIER_ESTABLISHED, TIER_PROBABLE})


@dataclass
class CorrelationOutcome:
    run_id: int
    anchors: int
    anchors_available: int
    candidate_pairs: int
    pairs_scored: int
    links_recorded: int
    tier_counts: dict[str, int] = field(default_factory=dict)
    clusters_found: int = 0
    over_merged_clusters: int = 0
    keys_skipped: int = 0
    search_truncated: bool = False
    projected: int = 0
    assertions_published: int = 0

    @property
    def anchors_truncated(self) -> bool:
        return self.anchors_available > self.anchors


async def run_correlation(
    driver: AsyncDriver,
    *,
    triggered_by: str,
    model: CorrelationModel | None = None,
    publish_assertions: bool = True,
) -> CorrelationOutcome:
    """Correlate every pair of findings worth comparing, once, under one model."""
    active = model or default_model()

    assessment_run = await assessment_repo.latest_run()
    run_id = await correlation_repo.start_run(
        active.version,
        active.fingerprint(),
        assessment_run.run_id if assessment_run else None,
        triggered_by,
    )

    try:
        available = await assessment_repo.count_anchors_for_correlation()
        seeds = await assessment_repo.anchors_for_correlation(active.max_anchors)
        if not seeds:
            # Not an error. A world where ARGUS has found nothing has nothing to
            # correlate, and recording that as a completed run of zero is more
            # honest than failing and leaving no record that the question was
            # asked.
            await correlation_repo.finish_run(
                run_id,
                anchors=0,
                candidate_pairs=0,
                pairs_scored=0,
                links_recorded=0,
                clusters_found=0,
                keys_skipped=0,
                search_truncated=False,
                evidence_summary={"note": "No assessment fired a signal; nothing to correlate."},
            )
            return CorrelationOutcome(
                run_id=run_id,
                anchors=0,
                anchors_available=available,
                candidate_pairs=0,
                pairs_scored=0,
                links_recorded=0,
            )

        evidence = await correlation_graph_repo.fetch_correlation_evidence(driver, seeds)
        ctx = build_context(evidence, active)
        proposed = candidate_generation.generate(ctx)

        links: list[CorrelationLink] = []
        for ref_a, ref_b in sorted(proposed.pairs):
            anchor_a = evidence.anchors.get(ref_a)
            anchor_b = evidence.anchors.get(ref_b)
            if anchor_a is None or anchor_b is None:
                continue
            link = link_pair(ctx, anchor_a, anchor_b)
            if link is not None:
                links.append(link)

        anchor_facts = {
            ref: (anchor.subject_type, anchor.band, anchor.score)
            for ref, anchor in evidence.anchors.items()
        }
        clusters = build_clusters(links, active, anchor_facts)

        await correlation_repo.store_links(run_id, links)
        await correlation_repo.store_clusters(run_id, clusters)

        tier_counts: dict[str, int] = {}
        for link in links:
            tier_counts[link.tier] = tier_counts.get(link.tier, 0) + 1

        evidence_summary = {
            "anchors_available": available,
            "transfers": len(evidence.transfers),
            "contacts": len(evidence.contacts),
            "attendances": len(evidence.attendances),
            "affiliations": len(evidence.affiliations),
            "located_subjects": len(evidence.subject_places),
            "corridors": len(evidence.corridors),
            "pairs_by_source": proposed.pairs_by_source,
            "skipped_keys": proposed.skipped_examples,
            "tier_counts": tier_counts,
        }
        await correlation_repo.finish_run(
            run_id,
            anchors=len(evidence.anchors),
            candidate_pairs=len(proposed.pairs),
            pairs_scored=len(proposed.pairs),
            links_recorded=len(links),
            clusters_found=len(clusters),
            keys_skipped=proposed.keys_skipped,
            search_truncated=bool(ctx.reach_truncated),
            evidence_summary=evidence_summary,
        )

        # Cleared before it is written, not merely overwritten.
        #
        # `project_clusters` only sets properties, so a subject that belonged to
        # a cluster last run and belongs to none now would keep its old
        # `argus_cluster` — the graph asserting a membership the ledger no
        # longer holds. That is the same defect as the stale assertions Phase 5
        # found, in the cache rather than in the record.
        #
        # Clear-then-write is not atomic: a reader between the two sees no
        # clusters. That is the right way round for a cache — briefly showing
        # nothing is recoverable on the next read, while showing a membership
        # that no longer exists is not visibly wrong to anyone.
        await correlation_graph_repo.clear_cluster_projection(driver)
        projected = await correlation_graph_repo.project_clusters(
            driver,
            [
                {
                    "subject_ref": member.ref,
                    "cluster_key": cluster.cluster_key,
                    "cluster_size": cluster.size,
                    "model_fingerprint": active.short_fingerprint,
                }
                for cluster in clusters
                for member in cluster.members
            ],
        )

        published = 0
        if publish_assertions:
            published = await _publish_link_assertions(links, active)

        logger.info(
            "correlation run %s complete: %s anchors, %s candidates, %s links, %s clusters",
            run_id,
            len(evidence.anchors),
            len(proposed.pairs),
            len(links),
            len(clusters),
        )
        return CorrelationOutcome(
            run_id=run_id,
            anchors=len(evidence.anchors),
            anchors_available=available,
            candidate_pairs=len(proposed.pairs),
            pairs_scored=len(proposed.pairs),
            links_recorded=len(links),
            tier_counts=tier_counts,
            clusters_found=len(clusters),
            over_merged_clusters=sum(1 for c in clusters if c.over_merged),
            keys_skipped=proposed.keys_skipped,
            search_truncated=bool(ctx.reach_truncated),
            projected=projected,
            assertions_published=published,
        )
    except Exception as exc:  # noqa: BLE001 - recorded, then re-raised
        await correlation_repo.fail_run(run_id, f"{type(exc).__name__}: {exc}")
        raise


async def _current_link_assertions(method: str) -> dict[str, str]:
    """Every current correlation assertion from this model, in one query.

    Read up front rather than per link, for the reason the assessment service
    does the same: the per-subject form was a query per published finding, which
    is the N+1 that made the Phase 4 matcher unusable under a real feed.
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
            CORRELATION_PREDICATE,
            method,
        )
    return {row["subject_ref"]: row["assertion_id"] for row in rows}


def _assertion_subject(link: CorrelationLink) -> str:
    """The subject an assertion about a link is filed under.

    A link is about a pair, and the provenance store is keyed by subject. Filing
    it under the lexicographically first reference — the same ordering the table
    enforces — means one assertion per pair rather than two mirror-image copies
    that would each have to be superseded and retracted in step.
    """
    return f"{link.ref_a}|{link.ref_b}"


async def _publish_link_assertions(links: list[CorrelationLink], model: CorrelationModel) -> int:
    """Write the material links into the provenance store.

    Each assertion is INFERRED, attributed to `argus.derived`, and carries the
    model's method identifier including its fingerprint. Reliability is F —
    measured against one synthetic world is not a track record — and credibility
    reflects how many independent families of evidence agreed.

    A pair that *drops out* of the published tiers has its assertion retracted
    with a stated reason rather than left standing. Without that, two entities
    correlated last week and uncorrelated today would still carry a current
    assertion saying they were linked: ARGUS asserting a belief it no longer
    holds, which is worse than never having published it.
    """
    published = 0
    existing = await _current_link_assertions(model.method)
    current_subjects: set[str] = set()

    for link in links:
        subject = _assertion_subject(link)
        if link.tier not in PUBLISHED_TIERS:
            continue
        current_subjects.add(subject)

        await provenance_repo.record_assertion(
            subject_ref=subject,
            subject_type="CorrelationLink",
            predicate=CORRELATION_PREDICATE,
            object_value={
                "ref_a": link.ref_a,
                "ref_b": link.ref_b,
                "strength": link.strength,
                "tier": link.tier,
                "coverage": link.coverage,
                "corroborating_families": list(link.corroborating_families),
                "dimensions": [
                    {
                        "dimension_id": o.dimension_id,
                        "family": o.family,
                        "magnitude": o.magnitude,
                        "summary": o.summary,
                    }
                    for o in link.fired
                ],
            },
            epistemic_kind=EpistemicKind.INFERRED,
            rating=Rating(reliability=link.reliability, credibility=link.credibility),
            method=model.method,
            asserted_by=f"source:{DERIVED_SOURCE_ID}",
            note=(
                f"{link.basis()} Strength {link.strength:.2f} is a combination of independent "
                f"families of evidence, bounded below 1 — it is not a probability that these "
                f"two subjects are acting together, and ARGUS has no evidence about intent. "
                f"{link.evaluable_dimensions} of {link.applicable_dimensions} applicable "
                f"dimensions could be evaluated."
            ),
            supersedes=existing.get(subject),
        )
        published += 1

    for subject, assertion_id in existing.items():
        if subject in current_subjects:
            continue
        await provenance_repo.retract_assertion(
            assertion_id,
            retracted_by=f"source:{DERIVED_SOURCE_ID}",
            reason=(
                "Re-correlated: this pair no longer reaches a published tier. The evidence "
                "that supported the link no longer does, so the finding is withdrawn rather "
                "than left standing."
            ),
        )

    return published


async def rebuild_projection(driver: AsyncDriver) -> dict[str, int]:
    """Drop every projected cluster property and rebuild it from Postgres.

    The proof that the graph properties are a cache and not a second source of
    truth. If this produced a different result from the last run, one of the two
    stores would be lying, and a test clears and rebuilds precisely to catch it.
    """
    cleared = await correlation_graph_repo.clear_cluster_projection(driver)
    rows = await correlation_repo.all_current_clusters_for_projection()
    written = await correlation_graph_repo.project_clusters(driver, rows)
    return {"cleared": cleared, "written": written}


async def run_evaluation(
    driver: AsyncDriver, *, triggered_by: str, model: CorrelationModel | None = None
) -> CorrelationEvaluationReport:
    """Measure the current links against the generator's planted storylines.

    Reads ground truth. Nothing it returns is written back into a link, and the
    links it measures were produced by a pipeline that could not see the labels
    — which is what makes the resulting figure worth anything.
    """
    active = model or default_model()

    run = await correlation_repo.latest_complete_run()
    if run is None:
        raise ValueError("No completed correlation run to evaluate — run the correlator first.")

    link_rows = await correlation_repo.list_current_links(limit=1_000_000)
    cluster_rows = await correlation_repo.list_current_clusters(limit=1_000_000)

    storylines = await correlation_graph_repo.fetch_correlation_ground_truth(driver)
    seeds = await assessment_repo.anchors_for_correlation(active.max_anchors)
    seeded = {seed["subject_ref"] for seed in seeds}

    # The same folding the correlator applied, so ground truth names the
    # subjects that were actually correlated. An account whose holder is also a
    # finding was folded into that holder; a storyline naming the account is
    # naming something correlation no longer treats as a separate subject.
    holders = await correlation_graph_repo.fetch_account_holders(driver)
    aliases = {
        account: holder
        for account, holder in holders.items()
        if account in seeded and holder in seeded
    }

    anchors = {row.ref_a for row in link_rows} | {row.ref_b for row in link_rows}
    anchors |= {aliases.get(ref, ref) for ref in seeded}

    planted: dict[str, tuple[str, ...]] = {}
    for storyline_type, refs in storylines:
        for ref in refs:
            canonical = aliases.get(ref, ref)
            planted[canonical] = tuple(
                sorted({*planted.get(canonical, ()), storyline_type})
            )

    labelled_pairs = pairs_from_storylines(storylines, anchors, aliases)

    # The evaluator is given the stored rows re-hydrated into the shapes it
    # expects, rather than the in-memory objects from the run. That is
    # deliberate: it measures what was actually persisted and is served to
    # users, not what the correlator believed before writing.
    links = [_link_from_row(row) for row in link_rows]
    clusters = [_cluster_from_row(row) for row in cluster_rows]

    report = evaluate(
        links,
        clusters,
        labelled_pairs,
        planted,
        anchors,
        active,
        candidate_pairs=run.candidate_pairs,
    )
    await correlation_repo.store_evaluation(
        run.run_id, active.version, active.fingerprint(), report.to_dict(), triggered_by
    )
    return report


def _link_from_row(row: correlation_repo.LinkRow) -> CorrelationLink:
    from app.correlation.dimensions import DimensionOutcome

    outcomes = tuple(
        DimensionOutcome(
            dimension_id=d["dimension_id"],
            family=d["family"],
            evaluable=bool(d["evaluable"]),
            magnitude=d.get("magnitude"),
            summary=d.get("summary", ""),
            evidence=d.get("evidence") or {},
        )
        for d in row.dimensions
    )
    return CorrelationLink(
        ref_a=row.ref_a,
        ref_b=row.ref_b,
        type_a=row.type_a,
        type_b=row.type_b,
        strength=row.strength,
        tier=row.tier,
        coverage=row.coverage,
        evaluable_dimensions=row.evaluable_dimensions,
        applicable_dimensions=row.applicable_dimensions,
        families=(),
        corroborating_families=tuple(row.corroborating_families),
        outcomes=outcomes,
        model_fingerprint=row.model_fingerprint,
        model_version=row.model_version,
        computed_at=row.computed_at,
    )


def _cluster_from_row(row: correlation_repo.ClusterRow) -> CorrelatedCluster:
    from app.correlation.clustering import ClusterMember

    return CorrelatedCluster(
        cluster_key=row.cluster_key,
        members=tuple(
            ClusterMember(
                ref=m["subject_ref"],
                subject_type=m["subject_type"],
                band=m["band"],
                score=m.get("score"),
                degree=m.get("degree", 0),
            )
            for m in row.members
        ),
        links=(),
        families=tuple(row.families),
        mean_strength=row.mean_strength,
        min_strength=row.min_strength,
        bridges=(),
        weakest_bridge=row.weakest_bridge,
        over_merged=row.over_merged,
        computed_at=row.computed_at,
    )


# ── Job registration ─────────────────────────────────────────────────────────


@queue.register(CORRELATION_JOB_KIND)
async def _run_correlation_job(job: queue.Job) -> None:
    """Durable-queue entry point, so a full sweep survives a restart.

    Correlating every candidate pair is seconds on the reference world and will
    not stay that way — the pair count grows faster than the anchor count.
    Running it inside the HTTP request that asked for it would tie a
    population-wide recomputation to the least durable thing in the system.
    """
    from app.database.neo4j import get_driver

    payload = job.payload or {}
    outcome = await run_correlation(
        get_driver(),
        triggered_by=str(payload.get("triggered_by", CORRELATOR_ACTOR)),
    )
    logger.info(
        "correlation run complete",
        extra={"run_id": outcome.run_id, "links": outcome.links_recorded},
    )

    if payload.get("evaluate"):
        report = await run_evaluation(
            get_driver(), triggered_by=str(payload.get("triggered_by", CORRELATOR_ACTOR))
        )
        logger.info(
            "correlation evaluation published",
            extra={"fingerprint": report.model_fingerprint},
        )


__all__ = [
    "CORRELATION_JOB_KIND",
    "CORRELATION_PREDICATE",
    "CORRELATOR_ACTOR",
    "CorrelationOutcome",
    "rebuild_projection",
    "run_correlation",
    "run_evaluation",
]
