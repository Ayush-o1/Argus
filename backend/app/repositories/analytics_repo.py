"""Graph Data Science-backed analytics.

Every algorithm here runs against a **named projection** declared in
`app/correlation/projection.py`, and every result says which one it ran on.

That is a Phase 6 change, and it fixes something that was quietly misleading.
All of these used to share one hard-coded projection — `Account` nodes joined by
`TRANSACTED_WITH` — and none of them mentioned it. A PageRank score appeared on
the analytics page as "influence" with no indication that the graph in question
contained no people, no organisations and no devices, so "influence" actually
meant "receives money from accounts that receive money". An analyst comparing a
PageRank rank against a Louvain community was comparing answers to two different
questions with no way to know it.

Two projections are available. `money` is the original account-only graph, kept
unchanged so results from before this phase remain comparable with results from
after it. `entity` spans people, organisations, accounts and devices with
per-type weights, and is what most questions about "who is central here"
actually mean.

Each Account is denormalised with `owner_id`/`owner_type`, so results are joined
back to the owning Person or Organization for display without extra traversal.
"""

import logging
from typing import Any

from neo4j import AsyncDriver

from app.correlation.projection import WEIGHT_ALIAS, ProjectionSpec, projection, spec_for

logger = logging.getLogger(__name__)


def _with_provenance(spec: ProjectionSpec, results: list[dict] | dict) -> dict:
    """Attach the projection to its own output.

    Returned as one object rather than two so a caller cannot render the numbers
    without the graph that produced them — which is exactly what every one of
    these endpoints did before.
    """
    return {"projection": spec.provenance(), "results": results}


async def owner_lookup(driver: AsyncDriver, account_ids: list[str]) -> dict[str, dict]:
    """Maps Account.id (uuid) -> {account_id, owner_id, owner_label, owner_name, band}."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:Account) WHERE a.id IN $ids
            OPTIONAL MATCH (owner) WHERE owner.id = a.owner_id
            RETURN a.id AS uuid, a.account_id AS account_id, a.owner_id AS owner_id,
                   a.owner_type AS owner_label, a.argus_band AS account_band,
                   a.argus_score AS account_score,
                   coalesce(owner.name, a.account_id) AS owner_name,
                   coalesce(labels(owner)[0], a.owner_type) AS resolved_label,
                   CASE WHEN owner IS NOT NULL THEN
                       coalesce(owner.person_id, owner.org_id)
                   ELSE a.owner_id END AS owner_human_id
            """,
            ids=account_ids,
        )
        rows = [dict(record) async for record in result]
    return {row["uuid"]: row for row in rows}


async def node_lookup(driver: AsyncDriver, uuids: list[str]) -> dict[str, dict]:
    """Resolve any projected node to something displayable.

    The account-only version of this could assume every result was an Account
    and reach for its owner. The entity projection returns people,
    organisations and devices too, so the resolution has to be general —
    otherwise every non-account result would be silently dropped by the shaping
    step below and the ranking would appear to contain only accounts.

    An Account still resolves through to its owner's name, because "the account
    ranked third" is less useful than "the account ranked third, owned by X".
    """
    if not uuids:
        return {}
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (n) WHERE n.id IN $ids
            OPTIONAL MATCH (owner) WHERE n:Account AND owner.id = n.owner_id
            RETURN n.id AS uuid,
                   labels(n)[0] AS label,
                   n.account_id AS account_id,
                   n.argus_band AS account_band,
                   n.argus_score AS account_score,
                   coalesce(owner.name, n.name, n.account_id, n.device_id) AS owner_name,
                   coalesce(labels(owner)[0], labels(n)[0]) AS resolved_label,
                   coalesce(
                       owner.person_id, owner.org_id,
                       n.person_id, n.org_id, n.account_id, n.device_id
                   ) AS owner_human_id
            """,
            ids=uuids,
        )
        rows = [dict(record) async for record in result]
    return {row["uuid"]: row for row in rows}


async def run_pagerank(
    driver: AsyncDriver, top_k: int = 50, projection_name: str | None = None
) -> dict:
    spec = spec_for(projection_name)
    async with projection(driver, spec) as name, driver.session() as session:
        result = await session.run(
            f"""
            CALL gds.pageRank.stream($name, {{ relationshipWeightProperty: '{WEIGHT_ALIAS}' }})
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).id AS uuid, score
            ORDER BY score DESC LIMIT $top_k
            """,
            name=name,
            top_k=top_k,
        )
        rows = [dict(record) async for record in result]

    nodes = await node_lookup(driver, [r["uuid"] for r in rows])
    return _with_provenance(spec, _shape_rows(rows, nodes, "score"))


async def run_betweenness(
    driver: AsyncDriver, top_k: int = 50, projection_name: str | None = None
) -> dict:
    spec = spec_for(projection_name)
    async with projection(driver, spec) as name, driver.session() as session:
        result = await session.run(
            """
            CALL gds.betweenness.stream($name)
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).id AS uuid, score
            ORDER BY score DESC LIMIT $top_k
            """,
            name=name,
            top_k=top_k,
        )
        rows = [dict(record) async for record in result]

    nodes = await node_lookup(driver, [r["uuid"] for r in rows])
    return _with_provenance(spec, _shape_rows(rows, nodes, "score"))


async def run_louvain(driver: AsyncDriver, projection_name: str | None = None) -> dict:
    spec = spec_for(projection_name)
    async with projection(driver, spec) as name, driver.session() as session:
        result = await session.run(
            """
            CALL gds.louvain.stream($name)
            YIELD nodeId, communityId
            RETURN gds.util.asNode(nodeId).id AS uuid, communityId
            """,
            name=name,
        )
        rows = [dict(record) async for record in result]

    owners = await node_lookup(driver, [r["uuid"] for r in rows])
    communities: dict[int, list[dict]] = {}
    for row in rows:
        owner = owners.get(row["uuid"])
        if owner is None:
            continue
        communities.setdefault(row["communityId"], []).append(owner)

    summary: list[dict[str, Any]] = []
    for community_id, members in communities.items():
        # Counts rather than an average score. Averaging assessment scores
        # across a community mixes subjects whose scores have different
        # evidence denominators, and produces a number that looks comparable
        # between communities when it is not. How many members ARGUS flagged,
        # out of how many it could assess at all, is the claim the data
        # supports.
        assessed = [m for m in members if m["account_band"] not in (None, "insufficient_evidence")]
        flagged = [m for m in assessed if m["account_band"] in ("elevated", "notable")]
        scored = [m for m in members if m["account_score"] is not None]
        top_member = (
            max(scored, key=lambda m: m["account_score"]) if scored else members[0]
        )
        summary.append(
            {
                "community_id": community_id,
                "size": len(members),
                "assessed_members": len(assessed),
                "flagged_members": len(flagged),
                "top_entity": {
                    "id": top_member["owner_human_id"],
                    "name": top_member["owner_name"],
                    "label": top_member["resolved_label"],
                    "band": top_member["account_band"],
                    "score": top_member["account_score"],
                },
            }
        )
    summary.sort(key=lambda c: (c["flagged_members"], c["size"]), reverse=True)
    return _with_provenance(
        spec, {"communities": summary, "total_communities": len(summary)}
    )


# node2vec walks the graph randomly, so without a fixed seed the same request
# returned a different "similar entities" list every time, against an unchanged
# graph, with nothing in the UI indicating non-determinism (audit B-14). An
# analyst comparing two runs would have seen a real difference where none
# existed. `concurrency: 1` is required alongside the seed: parallel walk
# threads interleave non-deterministically regardless of seeding.
NODE2VEC_SEED = 42


async def run_node2vec_similarity(
    driver: AsyncDriver,
    seed_human_id: str,
    top_k: int = 10,
    projection_name: str | None = None,
) -> dict:
    spec = spec_for(projection_name)
    async with projection(driver, spec) as name, driver.session() as session:
        result = await session.run(
            """
            CALL gds.node2vec.stream($name, {
                embeddingDimension: 64,
                iterations: 5,
                randomSeed: $seed,
                concurrency: 1
            })
            YIELD nodeId, embedding
            RETURN gds.util.asNode(nodeId).id AS uuid, embedding
            """,
            name=name,
            seed=NODE2VEC_SEED,
        )
        rows = [dict(record) async for record in result]

        # In the money projection the only projected nodes are accounts, so the
        # seed entity has to be reached through the account it owns. In the
        # entity projection the person is in the graph directly. Both are tried,
        # person first, so the same endpoint works against either without the
        # caller having to know which.
        seed_result = await session.run(
            """
            MATCH (owner) WHERE owner.person_id = $seed OR owner.org_id = $seed
            OPTIONAL MATCH (owner)-[:OWNS_ACCOUNT]->(a:Account)
            RETURN owner.id AS owner_uuid, a.id AS account_uuid LIMIT 1
            """,
            seed=seed_human_id,
        )
        seed_record = await seed_result.single()

    if seed_record is None or not rows:
        return _with_provenance(spec, [])

    embeddings = {row["uuid"]: row["embedding"] for row in rows}
    seed_uuid = next(
        (
            candidate
            for candidate in (seed_record["owner_uuid"], seed_record["account_uuid"])
            if candidate in embeddings
        ),
        None,
    )
    if seed_uuid is None:
        return _with_provenance(spec, [])

    seed_vector = embeddings[seed_uuid]
    similarities = []
    for node_uuid, vector in embeddings.items():
        if node_uuid == seed_uuid:
            continue
        similarities.append((node_uuid, _cosine_similarity(seed_vector, vector)))
    similarities.sort(key=lambda pair: pair[1], reverse=True)
    top = similarities[:top_k]

    owners = await node_lookup(driver, [node_uuid for node_uuid, _ in top])
    shaped = []
    for node_uuid, sim in top:
        owner = owners.get(node_uuid)
        if owner is None:
            continue
        shaped.append(
            {
                "id": owner["owner_human_id"],
                "name": owner["owner_name"],
                "label": owner["resolved_label"],
                "similarity": round(sim, 4),
            }
        )
    return _with_provenance(spec, shaped)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _shape_rows(rows: list[dict], owners: dict[str, dict], score_field: str) -> list[dict]:
    shaped = []
    for row in rows:
        owner = owners.get(row["uuid"])
        if owner is None:
            continue
        shaped.append(
            {
                "id": owner["owner_human_id"],
                "name": owner["owner_name"],
                "label": owner["resolved_label"],
                "account_id": owner["account_id"],
                score_field: round(row[score_field], 4),
            }
        )
    return shaped


EDGE_CONFIDENCE = 0.6


async def run_risk_propagation(driver: AsyncDriver, seed_ids: list[str], max_hops: int = 3) -> dict:
    """Custom label-propagation variant (ARGUS_PLAN.md Phase 9 #6): risk radiates
    from seed nodes across any relationship, attenuating by hop distance and a
    flat edge-confidence factor — deliberately simple and auditable rather than
    a GDS black box, since the whole point is an analyst can see why."""
    async with driver.session() as session:
        seed_result = await session.run(
            """
            MATCH (n) WHERE n.person_id IN $seeds OR n.org_id IN $seeds OR n.account_id IN $seeds
            RETURN n.id AS uuid, coalesce(n.person_id, n.org_id, n.account_id, n.device_id, n.vehicle_id) AS human_id,
                   coalesce(n.name, n.account_id) AS name, labels(n)[0] AS label,
                   n.argus_score AS argus_score, n.argus_band AS argus_band
            """,
            seeds=seed_ids,
        )
        seeds = [dict(record) async for record in seed_result]
        if not seeds:
            return {"seeds": [], "propagated": []}

        # Seeds with no assessment are excluded rather than defaulted. The
        # previous `or 50.0` invented a starting value for any entity that had
        # no score, so an analyst could seed propagation from an entity ARGUS
        # knows nothing about and receive a confident-looking cascade computed
        # from a number nobody chose.
        usable = [s for s in seeds if s["argus_score"] is not None]
        unusable = [s for s in seeds if s["argus_score"] is None]
        if not usable:
            return {
                "seeds": [_seed_payload(s) for s in seeds],
                "unusable_seeds": [_seed_payload(s) for s in unusable],
                "propagated": [],
                "note": (
                    "None of the seed entities has an ARGUS assessment to propagate. "
                    "Propagation starts from an assessed score; there is nothing to start from."
                ),
            }

        frontier = {s["uuid"]: s["argus_score"] for s in usable}
        visited = set(frontier.keys())
        accumulated: dict[str, float] = {}

        for hop in range(1, max_hops + 1):
            if not frontier:
                break
            neighbor_result = await session.run(
                """
                MATCH (n)-[r]-(m)
                WHERE n.id IN $frontier_ids AND NOT m.id IN $visited
                  AND type(r) <> 'SAME_AS' 
                  AND any(l IN labels(m) WHERE l IN ['Person', 'Organization', 'Account', 'Device', 'Vehicle'])
                RETURN DISTINCT m.id AS uuid,
                       coalesce(m.person_id, m.org_id, m.account_id, m.device_id, m.vehicle_id) AS human_id,
                       coalesce(m.name, m.account_id, m.device_id, m.plate) AS name, labels(m)[0] AS label,
                       n.id AS source_uuid
                """,
                frontier_ids=list(frontier.keys()),
                visited=list(visited),
            )
            next_frontier: dict[str, float] = {}
            rows = [dict(record) async for record in neighbor_result]
            for row in rows:
                source_risk = frontier[row["source_uuid"]]
                delta = source_risk * (1 / hop) * EDGE_CONFIDENCE
                key = row["uuid"]
                accumulated[key] = accumulated.get(key, 0.0) + delta
                next_frontier[key] = max(next_frontier.get(key, 0.0), delta)
                visited.add(key)
            frontier = next_frontier

        uuids = list(accumulated.keys())
        detail_result = await session.run(
            """
            MATCH (n) WHERE n.id IN $ids
            RETURN n.id AS uuid, coalesce(n.person_id, n.org_id, n.account_id, n.device_id, n.vehicle_id) AS human_id,
                   coalesce(n.name, n.account_id, n.device_id, n.plate) AS name, labels(n)[0] AS label
            """,
            ids=uuids,
        )
        details = {row["uuid"]: dict(row) async for row in detail_result}

    propagated = [
        {
            "id": details[uuid]["human_id"],
            "name": details[uuid]["name"],
            "label": details[uuid]["label"],
            "propagated_risk": round(min(delta, 100.0), 1),
        }
        for uuid, delta in accumulated.items()
        if uuid in details
    ]
    propagated.sort(key=lambda p: p["propagated_risk"], reverse=True)

    return {
        "seeds": [_seed_payload(s) for s in usable],
        "unusable_seeds": [_seed_payload(s) for s in unusable],
        "propagated": propagated,
        "note": (
            "Propagated values are a distance-attenuated echo of the seeds' own assessment "
            "scores. They are not assessments: no evidence about the receiving entity was "
            "examined to produce them."
        ),
    }


def _seed_payload(seed: dict) -> dict:
    return {
        "id": seed["human_id"],
        "name": seed["name"],
        "label": seed["label"],
        "band": seed["argus_band"],
        "score": seed["argus_score"],
    }


async def run_cycle_detection(
    driver: AsyncDriver,
    min_length: int = 3,
    max_length: int = 6,
    limit: int = 25,
    min_retention: float = 0.85,
) -> list[dict]:
    """Circular money-movement paths (A -> B -> ... -> A) — the layering signature.

    This used to begin `WHERE any(r IN rels WHERE r.flagged = true)`, with a
    comment explaining that flagged transactions are "where real injected
    storylines live". That is precisely the problem: `flagged` is written by the
    scenario generator's storyline injector, so the detector was not finding
    laundering rings — it was filtering the graph down to the rings the
    generator had already labelled and then reporting them as a discovery. Every
    cycle it returned was guaranteed to be a plant, and every unplanted cycle
    was guaranteed to be invisible.

    The filter is now the property that actually distinguishes a laundering ring
    from an accounting coincidence: **value preservation**. Each hop must pass on
    at least `min_retention` of what arrived, and no hop may exceed it, which is
    the same test `app/assessment/detectors.py` applies for the funds-cycle
    signal. Cycles are found on their own merits, and whether one happens to be
    planted is a question for the evaluation harness, not for the query.

    Bounded by length and result count because cycle enumeration is
    combinatorially expensive.
    """
    # Variable-length relationship bounds must be literals in Cypher (not query
    # parameters) — safe to interpolate since both are typed ints, never raw
    # user input. `min_retention` is a parameter, as it can be.
    async with driver.session() as session:
        result = await session.run(
            f"""
            MATCH path = (a:Account)-[rels:TRANSACTED_WITH*{min_length}..{max_length}]->(a)
            WHERE all(
                      i IN range(0, size(rels) - 2)
                      WHERE rels[i].amount > 0
                        AND rels[i + 1].amount <= rels[i].amount
                        AND rels[i + 1].amount >= rels[i].amount * $min_retention
                  )
            WITH path, rels LIMIT $limit
            RETURN [n IN nodes(path) | n.account_id] AS account_ids,
                   [n IN nodes(path) | n.id] AS uuids,
                   length(path) AS length,
                   reduce(total = 0.0, r IN rels | total + r.amount) AS total_amount,
                   CASE WHEN head(rels).amount > 0
                        THEN last(rels).amount / head(rels).amount ELSE null END AS retention
            """,
            limit=limit,
            min_retention=min_retention,
        )
        rows = [dict(record) async for record in result]

    all_uuids = {uuid for row in rows for uuid in row["uuids"]}
    owners = await owner_lookup(driver, list(all_uuids))

    cycles = []
    for row in rows:
        members = [
            {
                "account_id": owners[uuid]["account_id"] if uuid in owners else None,
                "name": owners[uuid]["owner_name"] if uuid in owners else None,
                "label": owners[uuid]["resolved_label"] if uuid in owners else None,
                "id": owners[uuid]["owner_human_id"] if uuid in owners else None,
            }
            for uuid in row["uuids"]
        ]
        cycles.append(
            {
                "length": row["length"],
                "total_amount": round(row["total_amount"], 2),
                # What survived the loop. A ring that returns 97% of what set
                # out is a different claim from one that returns 12%, and the
                # previous version reported both as simply "a cycle".
                "retention": round(row["retention"], 4) if row["retention"] is not None else None,
                "members": members,
            }
        )
    return cycles
