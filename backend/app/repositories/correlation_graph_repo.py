"""Graph reads and writes for correlation.

Three responsibilities, deliberately separated — the same shape as
`assessment_graph_repo`, for the same reasons.

  * **Gathering evidence.** Every query names the properties it selects. The
    `Storyline`, `Incident` and `Case` nodes are never matched, and neither are
    the `INVOLVES`, `LINKED_TO`, `CONTROLS` and `SHARES_DEVICE` relationships
    that join their members. There is no code path from a planted link to a
    discovered one, and `test_correlation_isolation.py` asserts that by
    inspecting the query text rather than trusting a reading of it.

  * **Projecting clusters.** The record is the `correlation_*` tables in
    Postgres; the `argus_cluster` properties written onto nodes are a cache, so
    the graph can filter and traverse without a join across two stores. They can
    be dropped and rebuilt at any time, and a test does exactly that.

  * **Reading ground truth.** `fetch_correlation_ground_truth` reads storylines,
    and it is the only function here that does. It is called by the evaluation
    path and by nothing else.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from neo4j import AsyncDriver

from app.correlation.evidence import (
    Affiliation,
    Anchor,
    Attendance,
    CorrelationEvidence,
    DeviceContact,
    Place,
    Transfer,
)

# Node properties the cluster projection may write. Enumerated so an edit that
# tries to write anywhere else fails a test instead of quietly mutating the
# world the correlator reads from on its next run.
PROJECTED_PROPERTIES: tuple[str, ...] = (
    "argus_cluster",
    "argus_cluster_size",
    "argus_cluster_model",
)


def _parse_timestamp(value: Any) -> datetime | None:
    """The generator writes naive local wall-clock strings (audit B-17).

    Parsed as naive and compared only against each other, which is all the
    coincidence and path windows need — every comparison is a difference between
    two timestamps from the same feed. Assigning a timezone here would invent a
    fact about when something happened.
    """
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


async def fetch_correlation_evidence(
    driver: AsyncDriver, anchor_seeds: list[dict[str, Any]]
) -> CorrelationEvidence:
    """One pass over the graph, collecting only admissible structure.

    `anchor_seeds` come from the assessment ledger in Postgres: every subject
    whose current assessment fired at least one signal. Correlation runs over
    ARGUS's own findings, so the set of things worth correlating is decided by
    what ARGUS found — never by what the generator planted.
    """
    evidence = CorrelationEvidence(gathered_at=datetime.now())
    activity: dict[str, list[datetime]] = defaultdict(list)
    anchor_refs = {seed["subject_ref"] for seed in anchor_seeds}

    async with driver.session() as session:
        # ── Account ownership ────────────────────────────────────────────────
        result = await session.run(
            """
            MATCH (owner)-[:OWNS_ACCOUNT]->(a:Account)
            WHERE a.account_id IS NOT NULL
            RETURN a.account_id AS account,
                   coalesce(owner.person_id, owner.org_id) AS owner_ref
            """
        )
        async for record in result:
            if record["owner_ref"]:
                evidence.account_owner[record["account"]] = record["owner_ref"]

        # ── Transfers ────────────────────────────────────────────────────────
        result = await session.run(
            """
            MATCH (a:Account)-[t:TRANSACTED_WITH]->(b:Account)
            WHERE t.amount IS NOT NULL AND t.timestamp IS NOT NULL
            RETURN a.account_id AS source, b.account_id AS target,
                   t.amount AS amount, t.timestamp AS occurred_at
            """
        )
        async for record in result:
            occurred_at = _parse_timestamp(record["occurred_at"])
            if occurred_at is None:
                continue
            evidence.transfers.append(
                Transfer(
                    source_account=record["source"],
                    target_account=record["target"],
                    amount=float(record["amount"]),
                    occurred_at=occurred_at,
                )
            )

        # ── Communications, resolved to their owners ─────────────────────────
        result = await session.run(
            """
            MATCH (pa:Person)-[:OWNS_DEVICE]->(da:Device)-[c:COMMUNICATED_WITH]->(db:Device)
            MATCH (pb:Person)-[:OWNS_DEVICE]->(db)
            WHERE c.timestamp IS NOT NULL AND pa.person_id <> pb.person_id
            RETURN pa.person_id AS person_a, pb.person_id AS person_b,
                   c.timestamp AS occurred_at
            """
        )
        async for record in result:
            occurred_at = _parse_timestamp(record["occurred_at"])
            if occurred_at is None:
                continue
            evidence.contacts.append(
                DeviceContact(
                    person_a=record["person_a"],
                    person_b=record["person_b"],
                    occurred_at=occurred_at,
                )
            )

        result = await session.run(
            "MATCH (p:Person)-[:OWNS_DEVICE]->(:Device) RETURN DISTINCT p.person_id AS ref"
        )
        async for record in result:
            if record["ref"]:
                evidence.subjects_with_devices.add(record["ref"])

        # ── Attendance and where it happened ─────────────────────────────────
        result = await session.run(
            """
            MATCH (p:Person)-[:ATTENDED]->(e:Event)
            RETURN p.person_id AS person, e.event_id AS event, e.timestamp AS occurred_at
            """
        )
        async for record in result:
            evidence.attendances.append(
                Attendance(
                    person_ref=record["person"],
                    event_ref=record["event"],
                    occurred_at=_parse_timestamp(record["occurred_at"]),
                )
            )

        result = await session.run(
            """
            MATCH (e:Event)-[:OCCURRED_AT]->(l:Location)
            WHERE l.lat IS NOT NULL AND l.lng IS NOT NULL
            RETURN e.event_id AS event, l.lat AS lat, l.lng AS lng
            """
        )
        async for record in result:
            evidence.event_places[record["event"]] = Place(
                ref=record["event"], lat=float(record["lat"]), lng=float(record["lng"])
            )

        # ── Affiliations ─────────────────────────────────────────────────────
        for rel_type in ("DIRECTS", "EMPLOYED_BY"):
            result = await session.run(
                f"""
                MATCH (p:Person)-[:{rel_type}]->(o:Organization)
                RETURN p.person_id AS person, o.org_id AS org
                """
            )
            async for record in result:
                if record["person"] and record["org"]:
                    evidence.affiliations.append(
                        Affiliation(
                            person_ref=record["person"],
                            org_ref=record["org"],
                            kind=rel_type,
                        )
                    )

        # ── Where subjects are ───────────────────────────────────────────────
        for label, id_field in (("Person", "person_id"), ("Organization", "org_id")):
            result = await session.run(
                f"""
                MATCH (n:{label})
                WHERE n.lat IS NOT NULL AND n.lng IS NOT NULL AND n.{id_field} IS NOT NULL
                RETURN n.{id_field} AS ref, n.lat AS lat, n.lng AS lng
                """
            )
            async for record in result:
                evidence.subject_places[record["ref"]] = Place(
                    ref=record["ref"], lat=float(record["lat"]), lng=float(record["lng"])
                )

        # ── Shipments: corridor, place and time ──────────────────────────────
        result = await session.run(
            """
            MATCH (s:Shipment)
            WHERE s.origin_id IS NOT NULL AND s.destination_id IS NOT NULL
            OPTIONAL MATCH (origin:Location {id: s.origin_id})
            OPTIONAL MATCH (destination:Location {id: s.destination_id})
            RETURN s.shipment_id AS ref, s.departure AS departure,
                   origin.location_id AS origin, destination.location_id AS destination,
                   origin.lat AS lat, origin.lng AS lng
            """
        )
        async for record in result:
            ref = record["ref"]
            if ref is None:
                continue
            if record["origin"] and record["destination"]:
                evidence.corridors[ref] = f"{record['origin']}>{record['destination']}"
            if record["lat"] is not None and record["lng"] is not None:
                evidence.subject_places[ref] = Place(
                    ref=ref, lat=float(record["lat"]), lng=float(record["lng"])
                )
            departure = _parse_timestamp(record["departure"])
            if departure is not None and ref in anchor_refs:
                activity[ref].append(departure)

    # ── Activity, assembled from what was already gathered ───────────────────
    #
    # Derived rather than queried again: every timestamp here has already been
    # read once, and a second pass would be a second chance to select something
    # inadmissible.
    # A transfer is activity for the account and, separately, for whoever owns
    # it. Both are recorded because either can be an anchor: an Account is a
    # subject in its own right, and a Person is active when their account moves.
    for transfer in evidence.transfers:
        for account in (transfer.source_account, transfer.target_account):
            if account in anchor_refs:
                activity[account].append(transfer.occurred_at)
            holder = evidence.account_owner.get(account)
            if holder is not None and holder in anchor_refs:
                activity[holder].append(transfer.occurred_at)

    for contact in evidence.contacts:
        for person in (contact.person_a, contact.person_b):
            if person in anchor_refs:
                activity[person].append(contact.occurred_at)

    for attendance in evidence.attendances:
        if attendance.occurred_at is not None and attendance.person_ref in anchor_refs:
            activity[attendance.person_ref].append(attendance.occurred_at)

    # An account whose holder is also an anchor is folded into the holder. The
    # account's transfers, counterparties and timing are already attributed to
    # them, so keeping both would report every financial link twice — once under
    # the account and once under whoever holds it. See `folded_accounts`.
    seeded = {seed["subject_ref"] for seed in anchor_seeds}
    for seed in anchor_seeds:
        ref = seed["subject_ref"]
        if seed["subject_type"] == "Account":
            holder = evidence.account_owner.get(ref)
            if holder is not None and holder in seeded:
                evidence.folded_accounts.add(ref)
                continue
        evidence.anchors[ref] = Anchor(
            ref=ref,
            subject_type=seed["subject_type"],
            band=seed["band"],
            score=seed["score"],
            signal_ids=tuple(seed["signal_ids"]),
            activity=tuple(sorted(activity.get(ref, ()))),
        )

    return evidence


# ─────────────────────────────────────────────────────────────────────────────
# Projection
# ─────────────────────────────────────────────────────────────────────────────


async def project_clusters(driver: AsyncDriver, rows: list[dict[str, Any]]) -> int:
    """Write cluster membership onto nodes as a cache.

    A subject that has left every cluster has its properties removed rather than
    set to null: a node carrying `argus_cluster = null` is indistinguishable in
    a query from one that was never assessed, and the difference is the whole
    point of the three-state discipline elsewhere in this system.
    """
    if not rows:
        return 0

    written = 0
    async with driver.session() as session:
        for chunk_start in range(0, len(rows), 500):
            chunk = rows[chunk_start : chunk_start + 500]
            result = await session.run(
                """
                UNWIND $rows AS row
                MATCH (n)
                WHERE n.person_id = row.subject_ref OR n.org_id = row.subject_ref
                   OR n.account_id = row.subject_ref OR n.shipment_id = row.subject_ref
                SET n.argus_cluster = row.cluster_key,
                    n.argus_cluster_size = row.cluster_size,
                    n.argus_cluster_model = row.model_fingerprint
                RETURN count(n) AS written
                """,
                rows=chunk,
            )
            record = await result.single()
            if record:
                written += record["written"]
    return written


async def clear_cluster_projection(driver: AsyncDriver) -> int:
    """Remove every projected cluster property.

    Exists so `rebuild_projection` can prove the cache is a cache: clear it,
    rebuild from the ledger, and compare. A cache that has never been shown to
    be reconstructible is a second source of truth wearing a cache's name.
    """
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (n) WHERE n.argus_cluster IS NOT NULL
            REMOVE n.argus_cluster, n.argus_cluster_size, n.argus_cluster_model
            RETURN count(n) AS cleared
            """
        )
        record = await result.single()
        return record["cleared"] if record else 0


# ─────────────────────────────────────────────────────────────────────────────
# Ground truth — the evaluation path only
# ─────────────────────────────────────────────────────────────────────────────


async def fetch_account_holders(driver: AsyncDriver) -> dict[str, str]:
    """account_id -> the person or organisation that holds it.

    Used by the evaluation path to follow the same folding the correlator did.
    A storyline that plants a chain of accounts names those accounts, but if
    each account's holder is also a finding then the accounts were folded into
    their holders and the link ARGUS found is between the holders. Without this
    map, ground truth would be looking for a pair of subjects that correlation
    deliberately stopped treating as separate — and would report a recall of
    zero for a storyline it had actually recovered.

    Not part of the correlation path: this is the same ownership relation the
    evidence sweep already reads, exposed separately so the evaluator can use it
    without the evidence bundle.
    """
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (owner)-[:OWNS_ACCOUNT]->(a:Account)
            WHERE a.account_id IS NOT NULL
            RETURN a.account_id AS account,
                   coalesce(owner.person_id, owner.org_id) AS holder
            """
        )
        return {
            record["account"]: record["holder"]
            async for record in result
            if record["holder"]
        }


async def fetch_correlation_ground_truth(driver: AsyncDriver) -> list[tuple[str, tuple[str, ...]]]:
    """Every storyline, as `(type, entity refs)`.

    The only function in this module that reads a planted label, and it is
    called by the evaluation path and nothing else. Kept here rather than in the
    correlation package so the package itself has no query that could reach one.
    """
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (s:Storyline)
            RETURN s.type AS storyline_type, s.entity_ids AS entity_ids
            """
        )
        rows = [dict(record) async for record in result]

    return [
        (row["storyline_type"], tuple(row["entity_ids"] or ()))
        for row in rows
        if row["storyline_type"]
    ]
