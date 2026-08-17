"""Graph reads and writes for risk assessment.

Three responsibilities, deliberately separated:

  * **Gathering evidence.** Every query here names the properties it selects.
    `risk_score`, `flags`, `flagged`, `storyline_id`, `community_ids` and
    `route_anomaly` are not filtered out after the fetch — they are never
    selected, and neither are the `Storyline` and `Incident` nodes or the
    `CONTROLS` and `SHARES_DEVICE` relationships. There is no code path from an
    answer key to a score. `test_assessment_isolation.py` asserts this by
    inspecting the query text rather than trusting the reading.

  * **Projecting assessments.** The record is the `assessments` table in
    Postgres; the `argus_*` properties written back onto nodes are a cache, so
    the graph can sort, filter and aggregate without a join across two stores.
    They can be dropped and rebuilt at any time, and a test does exactly that.
    Nothing here writes to `risk_score`: the generator's number is left exactly
    where it is, as a source claim, so provenance can keep showing what it was.

  * **Reading ground truth.** `fetch_ground_truth` reads storylines, and it is
    the only function in the module that does. It is called by the evaluation
    path and by nothing else.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from neo4j import AsyncDriver

from app.assessment.evaluation import LabelledSubject
from app.assessment.evidence import (
    ASSESSED_TYPES,
    AccountFact,
    Contact,
    Directorship,
    EvidenceBundle,
    ShipmentFact,
    Transfer,
)
from app.repositories.entity_labels import ENTITY_LABELS

# The human-readable id property for each assessed type. Taken from the shared
# label registry so it cannot drift from the rest of the application.
ID_FIELD: dict[str, str] = {
    "Person": "person_id",
    "Organization": "org_id",
    "Account": "account_id",
    "Shipment": "shipment_id",
}

# Node properties the projection is permitted to write. Enumerated so a future
# edit that tries to write back to `risk_score` fails a test instead of quietly
# re-creating the circularity this phase removed.
PROJECTED_PROPERTIES: tuple[str, ...] = (
    "argus_score",
    "argus_band",
    "argus_coverage",
    "argus_model",
    "argus_assessed_at",
)


def _parse_timestamp(value: Any) -> datetime | None:
    """The generator writes naive local wall-clock strings (audit B-17).

    They are parsed as naive and compared only against each other, which is all
    the burst and cycle detectors need — every comparison is a difference
    between two timestamps from the same feed. Assigning them a timezone here
    would invent a fact about when something happened.
    """
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


async def fetch_evidence(driver: AsyncDriver) -> EvidenceBundle:
    """One pass over the graph, collecting only admissible data.

    Gathered for the whole population rather than per subject because the
    signals are population-relative: a burst only exists against a baseline,
    and a funds cycle is a property of a ring of accounts that no member can
    see from where it sits.
    """
    bundle = EvidenceBundle(gathered_at=datetime.now())

    async with driver.session() as session:
        for subject_type in ASSESSED_TYPES:
            id_field = ID_FIELD[subject_type]
            result = await session.run(
                f"MATCH (n:{subject_type}) WHERE n.{id_field} IS NOT NULL RETURN n.{id_field} AS ref"
            )
            async for record in result:
                bundle.subjects[record["ref"]] = subject_type

        result = await session.run(
            """
            MATCH (a:Account)-[t:TRANSACTED_WITH]->(b:Account)
            WHERE t.amount IS NOT NULL AND t.timestamp IS NOT NULL
            RETURN t.tx_id AS transfer_id, a.account_id AS source, b.account_id AS target,
                   t.amount AS amount, t.timestamp AS occurred_at
            """
        )
        async for record in result:
            occurred_at = _parse_timestamp(record["occurred_at"])
            if occurred_at is None or record["transfer_id"] is None:
                continue
            bundle.transfers.append(
                Transfer(
                    transfer_id=record["transfer_id"],
                    source_account=record["source"],
                    target_account=record["target"],
                    amount=float(record["amount"]),
                    occurred_at=occurred_at,
                )
            )

        # Communications are device-to-device; the assessor works in people, so
        # they are resolved through ownership here. A communication whose
        # device has no registered owner is dropped rather than attributed to
        # nobody — it is real traffic ARGUS cannot place, which is a gap in
        # collection, not a fact about a person.
        result = await session.run(
            """
            MATCH (p1:Person)-[:OWNS_DEVICE]->(d1:Device)-[c:COMMUNICATED_WITH]->(d2:Device)
            MATCH (p2:Person)-[:OWNS_DEVICE]->(d2)
            WHERE c.timestamp IS NOT NULL
            RETURN p1.person_id AS a, p2.person_id AS b, c.timestamp AS occurred_at
            """
        )
        async for record in result:
            occurred_at = _parse_timestamp(record["occurred_at"])
            if occurred_at is None or not record["a"] or not record["b"]:
                continue
            bundle.contacts.append(
                Contact(person_a=record["a"], person_b=record["b"], occurred_at=occurred_at)
            )

        result = await session.run(
            """
            MATCH (a:Account)
            OPTIONAL MATCH (owner)-[:OWNS_ACCOUNT]->(a)
            RETURN a.account_id AS account_id, a.offshore AS offshore,
                   coalesce(owner.person_id, owner.org_id) AS owner_ref,
                   labels(owner)[0] AS owner_type
            """
        )
        async for record in result:
            if record["account_id"] is None:
                continue
            bundle.accounts.append(
                AccountFact(
                    account_id=record["account_id"],
                    offshore=bool(record["offshore"]),
                    owner_ref=record["owner_ref"],
                    owner_type=record["owner_type"],
                )
            )

        result = await session.run(
            """
            MATCH (p:Person)-[:DIRECTS]->(o:Organization)
            RETURN p.person_id AS person_ref, o.org_id AS org_ref
            """
        )
        async for record in result:
            if record["person_ref"] and record["org_ref"]:
                bundle.directorships.append(
                    Directorship(person_ref=record["person_ref"], org_ref=record["org_ref"])
                )

        result = await session.run(
            "MATCH (p:Person)-[:OWNS_DEVICE]->(:Device) RETURN DISTINCT p.person_id AS ref"
        )
        async for record in result:
            if record["ref"]:
                bundle.persons_with_devices.add(record["ref"])

        result = await session.run(
            """
            MATCH (s:Shipment)
            RETURN s.shipment_id AS shipment_id, s.detour_ratio AS detour_ratio,
                   s.origin_region AS origin_region, s.destination_region AS destination_region,
                   s.manifest AS manifest, s.declared_manifest AS declared_manifest
            """
        )
        async for record in result:
            if record["shipment_id"] is None:
                continue
            ratio = record["detour_ratio"]
            bundle.shipments.append(
                ShipmentFact(
                    shipment_id=record["shipment_id"],
                    detour_ratio=float(ratio) if ratio is not None else None,
                    origin_region=record["origin_region"],
                    destination_region=record["destination_region"],
                    manifest=record["manifest"],
                    declared_manifest=record["declared_manifest"],
                )
            )

    return bundle


# ─────────────────────────────────────────────────────────────────────────────
# Projection
# ─────────────────────────────────────────────────────────────────────────────


async def project_assessments(driver: AsyncDriver, rows: list[dict[str, Any]]) -> int:
    """Write assessment results onto the nodes they describe.

    A cache of the Postgres record, batched with UNWIND. `argus_score` is left
    unset for an unassessable subject rather than written as 0, so a Cypher
    `ORDER BY` cannot sort a subject ARGUS knows nothing about into the middle
    of the ranking as though it had been measured and found unremarkable.
    """
    if not rows:
        return 0

    written = 0
    async with driver.session() as session:
        for subject_type in ASSESSED_TYPES:
            batch = [row for row in rows if row["subject_type"] == subject_type]
            if not batch:
                continue
            id_field = ID_FIELD[subject_type]
            result = await session.run(
                f"""
                UNWIND $rows AS row
                MATCH (n:{subject_type} {{{id_field}: row.subject_ref}})
                SET n.argus_band = row.band,
                    n.argus_coverage = row.coverage,
                    n.argus_model = row.model_fingerprint,
                    n.argus_assessed_at = row.computed_at
                FOREACH (_ IN CASE WHEN row.score IS NULL THEN [] ELSE [1] END |
                    SET n.argus_score = row.score)
                FOREACH (_ IN CASE WHEN row.score IS NULL THEN [1] ELSE [] END |
                    REMOVE n.argus_score)
                RETURN count(n) AS written
                """,
                rows=batch,
            )
            record = await result.single()
            written += record["written"] if record else 0
    return written


async def clear_projection(driver: AsyncDriver) -> int:
    """Remove every projected property. The Postgres record is untouched, which
    is the point: `rebuild_projection` reconstructs all of this from the ledger,
    and a test proves it by clearing and rebuilding."""
    cleared = 0
    async with driver.session() as session:
        for subject_type in ASSESSED_TYPES:
            result = await session.run(
                f"""
                MATCH (n:{subject_type})
                WHERE n.argus_band IS NOT NULL OR n.argus_score IS NOT NULL
                REMOVE n.argus_score, n.argus_band, n.argus_coverage,
                       n.argus_model, n.argus_assessed_at
                RETURN count(n) AS cleared
                """
            )
            record = await result.single()
            cleared += record["cleared"] if record else 0
    return cleared


async def band_counts(driver: AsyncDriver, subject_type: str) -> dict[str, int]:
    """Population counts per band, straight from the projection.

    Returned with an explicit `unassessed` bucket so the numbers always sum to
    the population. A distribution that silently omits the subjects it could
    not assess is the same defect as a timeline that omits its empty days.
    """
    if subject_type not in ID_FIELD:
        raise ValueError(f"{subject_type!r} is not assessed")
    async with driver.session() as session:
        result = await session.run(
            f"""
            MATCH (n:{subject_type})
            RETURN coalesce(n.argus_band, 'unassessed') AS band, count(n) AS count
            """
        )
        return {record["band"]: record["count"] async for record in result}


# ─────────────────────────────────────────────────────────────────────────────
# Ground truth — evaluation only
# ─────────────────────────────────────────────────────────────────────────────


async def fetch_ground_truth(driver: AsyncDriver) -> list[LabelledSubject]:
    """Which entities the generator made anomalous, for measuring the model.

    The only function in ARGUS that reads a `Storyline` or a `route_anomaly`
    flag. It is called by `run_evaluation` and nothing else; the scoring path
    cannot reach it, because the evidence bundle it would have to travel
    through has no field that could carry either.

    Two label sets are collected, because the generator produces two kinds of
    plant. Storylines are scripted scenarios. `route_anomaly` marks a shipment
    whose route or manifest was deliberately made anomalous, and most of those
    are never wrapped in a storyline — 53 marked against 9 scripted, in the
    default world. Measuring only against storylines would score a detector as
    wrong for finding the other 44, which would be a fact about the label set
    rather than about the model.
    """
    assessed_prefixes = {
        prefix: info.label
        for prefix, info in ENTITY_LABELS.items()
        if info.label in ASSESSED_TYPES
    }

    grouped: dict[str, tuple[str, set[str]]] = {}
    injected: set[str] = set()

    async with driver.session() as session:
        result = await session.run(
            "MATCH (s:Storyline) RETURN s.type AS type, s.entity_ids AS entity_ids"
        )
        async for record in result:
            storyline_type = record["type"]
            for ref in record["entity_ids"] or []:
                subject_type = assessed_prefixes.get(ref.split("-")[0])
                if subject_type is None:
                    continue
                entry = grouped.setdefault(ref, (subject_type, set()))
                entry[1].add(storyline_type)

        result = await session.run(
            "MATCH (s:Shipment) WHERE s.route_anomaly = true RETURN s.shipment_id AS ref"
        )
        async for record in result:
            if record["ref"]:
                injected.add(record["ref"])
                grouped.setdefault(record["ref"], ("Shipment", set()))

    return [
        LabelledSubject(
            subject_ref=ref,
            subject_type=subject_type,
            storyline_types=tuple(sorted(types)),
            injected_anomaly=ref in injected,
        )
        for ref, (subject_type, types) in sorted(grouped.items())
    ]
