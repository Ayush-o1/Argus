"""Reads ARGUS's own published findings, for the rule engine to alert on.

Separate from `alert_repo` (which persists alerts) because this is the *input*
side, and keeping them apart makes the admissibility property checkable by
reading one file: every query here selects from the assessment and correlation
tables, and nothing else. There is no join to `Incident`, and the isolation test
fails the build if one appears.

All SQL is static. The queries are parameterised or fully literal — none is
assembled from a caller-supplied string — which is what keeps bandit's B608
quiet honestly rather than by annotation.
"""

from __future__ import annotations

from typing import Any

from app.alerting.evidence import (
    AlertingEvidence,
    AssessmentFinding,
    ClusterFinding,
    LinkFinding,
)
from app.database.postgres import acquire

__all__ = ["fetch_alerting_evidence"]


# Current assessment per subject, with the band that subject held at the
# previous run. The previous band is a LATERAL rather than a window over all
# assessments because a subject may have been assessed many times, and only the
# immediately preceding one is a comparison anyone would make.
_ASSESSMENTS = """
    SELECT c.subject_ref,
           c.subject_type,
           c.band,
           c.score,
           c.evidence_coverage,
           c.families_fired,
           c.computed_at,
           c.run_id,
           c.model_fingerprint,
           p.band        AS previous_band,
           p.computed_at AS previous_computed_at
    FROM assessment_current c
    LEFT JOIN LATERAL (
        SELECT a.band, a.computed_at
        FROM assessments a
        WHERE a.subject_ref = c.subject_ref
          AND a.computed_at < c.computed_at
        ORDER BY a.computed_at DESC
        LIMIT 1
    ) p ON true
    WHERE c.band = ANY($1::text[])
"""

# Signals behind the current assessments, for the subjects in scope. Fetched in
# one query rather than per subject: 8,466 assessed subjects would otherwise be
# 8,466 round trips.
_SIGNALS = """
    SELECT s.assessment_id,
           c.subject_ref,
           s.signal_id,
           s.family,
           s.magnitude,
           s.summary
    FROM assessment_signals s
    JOIN assessment_current c ON c.assessment_id = s.assessment_id
    WHERE c.band = ANY($1::text[])
      AND s.magnitude IS NOT NULL
      AND s.magnitude > 0
    ORDER BY c.subject_ref, s.contribution DESC
"""

_LINKS = """
    SELECT ref_a, ref_b, tier, strength, coverage, corroborating_families
    FROM correlation_current_links
"""

# Members live in their own table, so they are aggregated here rather than read
# from the view. The band stored on a member row is the one it held when the
# correlation ran; it is deliberately not selected. The convergence rule asks
# what ARGUS believes *now*, and a stale band would let a cluster keep claiming
# concurrence with an assessment that has since been withdrawn.
_CLUSTERS = """
    SELECT c.cluster_key,
           c.size,
           c.families,
           c.weakest_bridge,
           array_agg(m.subject_ref ORDER BY m.subject_ref) AS members
    FROM correlation_current_clusters c
    JOIN correlation_cluster_members m ON m.cluster_id = c.cluster_id
    GROUP BY c.cluster_key, c.size, c.families, c.weakest_bridge
"""

_LATEST_RUNS = """
    SELECT (SELECT max(run_id) FROM assessment_runs WHERE status = 'complete')  AS assessment_run_id,
           (SELECT max(run_id) FROM correlation_runs WHERE status = 'complete') AS correlation_run_id
"""


async def fetch_alerting_evidence(bands: tuple[str, ...]) -> AlertingEvidence:
    """Gather every finding the rules may consult, for one run.

    `bands` bounds the assessment side. Passing every band would pull all 8,466
    assessed subjects including the ~2,700 with insufficient evidence, and no
    rule fires on those — the filter is here rather than in the rules so the
    cost is not paid before it is discarded.
    """
    evidence = AlertingEvidence()

    async with acquire() as conn:
        runs = await conn.fetchrow(_LATEST_RUNS)
        if runs is not None:
            evidence.assessment_run_id = runs["assessment_run_id"]
            evidence.correlation_run_id = runs["correlation_run_id"]

        band_list = list(bands)
        rows = await conn.fetch(_ASSESSMENTS, band_list)
        signal_rows = await conn.fetch(_SIGNALS, band_list)
        link_rows = await conn.fetch(_LINKS)
        cluster_rows = await conn.fetch(_CLUSTERS)

    signals_by_subject: dict[str, list[tuple[str, str, float | None, str]]] = {}
    for row in signal_rows:
        signals_by_subject.setdefault(row["subject_ref"], []).append(
            (
                row["signal_id"],
                row["family"],
                float(row["magnitude"]) if row["magnitude"] is not None else None,
                row["summary"],
            )
        )

    for row in rows:
        ref = row["subject_ref"]
        evidence.assessments[ref] = AssessmentFinding(
            subject_ref=ref,
            subject_type=row["subject_type"],
            band=row["band"],
            score=float(row["score"]) if row["score"] is not None else None,
            evidence_coverage=float(row["evidence_coverage"]),
            families_fired=tuple(row["families_fired"] or ()),
            computed_at=row["computed_at"],
            run_id=row["run_id"],
            model_fingerprint=row["model_fingerprint"],
            previous_band=row["previous_band"],
            previous_computed_at=row["previous_computed_at"],
            # Bounded: an alert shows the reasons, and a subject with forty
            # signals does not need forty in the payload for someone to decide
            # whether to open it. Ordered by contribution, so these are the ones
            # that mattered most.
            signals=tuple(signals_by_subject.get(ref, [])[:8]),
        )

    evidence.links = [
        LinkFinding(
            ref_a=row["ref_a"],
            ref_b=row["ref_b"],
            tier=row["tier"],
            strength=float(row["strength"]),
            coverage=float(row["coverage"]),
            corroborating_families=tuple(row["corroborating_families"] or ()),
        )
        for row in link_rows
    ]

    evidence.clusters = [
        ClusterFinding(
            cluster_key=row["cluster_key"],
            members=tuple(row["members"] or ()),
            size=row["size"],
            families=tuple(row["families"] or ()),
            weakest_bridge=(
                float(row["weakest_bridge"]) if row["weakest_bridge"] is not None else None
            ),
        )
        for row in cluster_rows
    ]

    return evidence


async def subject_types(refs: list[str]) -> dict[str, Any]:
    """Subject types for a set of refs, from assessments rather than the graph.

    Used by the API to label an alert's scope without a second datastore round
    trip, and deliberately sourced from what ARGUS assessed rather than from the
    graph — an alert is about a finding, and the finding names its own subject.
    """
    if not refs:
        return {}
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT subject_ref, subject_type FROM assessment_current WHERE subject_ref = ANY($1::text[])",
            refs,
        )
    return {row["subject_ref"]: row["subject_type"] for row in rows}


async def subject_context(driver: Any, refs: list[str]) -> dict[str, dict[str, Any]]:
    """Everything the detail panel needs about an alert's subjects.

    Two reads, joined by ref: the current assessment band and score from
    PostgreSQL, and the geography from the graph. Kept out of `fetch_alerting_evidence`
    because no *rule* may consult geography — a rule that fired on country would
    be profiling by location, which is a different system from this one. It is
    display context for an analyst who has already been shown the alert, not an
    input to raising it.
    """
    if not refs:
        return {}

    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT subject_ref, subject_type, band, score, evidence_coverage
              FROM assessment_current WHERE subject_ref = ANY($1::text[])
            """,
            refs,
        )

    context: dict[str, dict[str, Any]] = {
        r["subject_ref"]: {
            "subject_ref": r["subject_ref"],
            "subject_type": r["subject_type"],
            "band": r["band"],
            "score": float(r["score"]) if r["score"] is not None else None,
            "evidence_coverage": float(r["evidence_coverage"]),
            "country": None,
            "region": None,
        }
        for r in rows
    }
    for ref in refs:
        context.setdefault(
            ref,
            {
                "subject_ref": ref,
                "subject_type": None,
                "band": None,
                "score": None,
                "evidence_coverage": None,
                "country": None,
                "region": None,
            },
        )

    # Geography, by human-readable id across the four assessed labels. One
    # query rather than one per subject.
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (n)
            WHERE (n.person_id IN $refs OR n.org_id IN $refs
                   OR n.account_id IN $refs OR n.shipment_id IN $refs)
            RETURN coalesce(n.person_id, n.org_id, n.account_id, n.shipment_id) AS ref,
                   n.country AS country, n.region AS region
            """,
            refs=refs,
        )
        async for record in result:
            entry = context.get(record["ref"])
            if entry is not None:
                entry["country"] = record["country"]
                entry["region"] = record["region"]

    return context


def spread_of(context: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Distinct countries and regions across **every** subject.

    Computed over the whole scope, never over a display preview. The audit found
    the previous alert surface deriving "N countries · Crosses N regions" from a
    five-entity preview and printing it under a heading reading "Spread" — a
    truncation presented as a complete finding (B-04). There is no preview here
    to derive it from, and the totals travel with the list.
    """
    countries = sorted({c["country"] for c in context.values() if c.get("country")})
    regions = sorted({c["region"] for c in context.values() if c.get("region")})
    located = sum(1 for c in context.values() if c.get("country"))
    return {
        "countries": countries,
        "country_count": len(countries),
        "regions": regions,
        "region_count": len(regions),
        "subjects_total": len(context),
        "subjects_located": located,
        # Stated so an absent country reads as "not recorded" rather than as
        # "not abroad". A spread computed over 3 of 12 subjects is a different
        # claim from one computed over all 12.
        "basis": "complete" if located == len(context) else "partial",
    }
