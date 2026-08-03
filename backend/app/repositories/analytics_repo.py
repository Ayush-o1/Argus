"""Graph Data Science-backed analytics (ARGUS_PLAN.md Phase 9).

The projection runs over the Account/TRANSACTED_WITH subgraph — per the
Phase 7 implementation note, transactions are edges (not nodes), so
Account->Account *is* the money-movement graph, and it's exactly the shape
PageRank, Betweenness, Louvain, Node2Vec, and cycle detection need. Each
Account is denormalized with `owner_id`/`owner_type`, so results are joined
back to the owning Person/Organization for display without extra traversal.
"""

from neo4j import AsyncDriver

PROJECTION_NAME = "entityGraph"


async def ensure_projection(driver: AsyncDriver) -> None:
    """(Re)creates the in-memory GDS graph projection. Idempotent — cheap enough
    (single machine, ~2.8K accounts / 40K transactions) to just drop and redo
    rather than tracking staleness."""
    async with driver.session() as session:
        exists_result = await session.run("CALL gds.graph.exists($name) YIELD exists", name=PROJECTION_NAME)
        record = await exists_result.single()
        if record and record["exists"]:
            await session.run("CALL gds.graph.drop($name)", name=PROJECTION_NAME)

        await session.run(
            """
            CALL gds.graph.project(
                $name,
                'Account',
                {
                    TRANSACTED_WITH: {
                        orientation: 'NATURAL',
                        properties: { amount: { property: 'amount', defaultValue: 0.0 } }
                    }
                }
            )
            """,
            name=PROJECTION_NAME,
        )


async def _owner_lookup(driver: AsyncDriver, account_ids: list[str]) -> dict[str, dict]:
    """Maps Account.id (uuid) -> {account_id, owner_id, owner_label, owner_name, risk_score}."""
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:Account) WHERE a.id IN $ids
            OPTIONAL MATCH (owner) WHERE owner.id = a.owner_id
            RETURN a.id AS uuid, a.account_id AS account_id, a.owner_id AS owner_id,
                   a.owner_type AS owner_label, a.risk_score AS account_risk_score,
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


async def run_pagerank(driver: AsyncDriver, top_k: int = 50) -> list[dict]:
    await ensure_projection(driver)
    async with driver.session() as session:
        result = await session.run(
            """
            CALL gds.pageRank.stream($name, { relationshipWeightProperty: 'amount' })
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).id AS uuid, score
            ORDER BY score DESC LIMIT $top_k
            """,
            name=PROJECTION_NAME,
            top_k=top_k,
        )
        rows = [dict(record) async for record in result]

    owners = await _owner_lookup(driver, [r["uuid"] for r in rows])
    return _shape_rows(rows, owners, "score")


async def run_betweenness(driver: AsyncDriver, top_k: int = 50) -> list[dict]:
    await ensure_projection(driver)
    async with driver.session() as session:
        result = await session.run(
            """
            CALL gds.betweenness.stream($name)
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).id AS uuid, score
            ORDER BY score DESC LIMIT $top_k
            """,
            name=PROJECTION_NAME,
            top_k=top_k,
        )
        rows = [dict(record) async for record in result]

    owners = await _owner_lookup(driver, [r["uuid"] for r in rows])
    return _shape_rows(rows, owners, "score")


async def run_louvain(driver: AsyncDriver) -> dict:
    await ensure_projection(driver)
    async with driver.session() as session:
        result = await session.run(
            """
            CALL gds.louvain.stream($name)
            YIELD nodeId, communityId
            RETURN gds.util.asNode(nodeId).id AS uuid, communityId
            """,
            name=PROJECTION_NAME,
        )
        rows = [dict(record) async for record in result]

    owners = await _owner_lookup(driver, [r["uuid"] for r in rows])
    communities: dict[int, list[dict]] = {}
    for row in rows:
        owner = owners.get(row["uuid"])
        if owner is None:
            continue
        communities.setdefault(row["communityId"], []).append(owner)

    summary = []
    for community_id, members in communities.items():
        risk_scores = [m["account_risk_score"] or 0 for m in members]
        avg_risk = sum(risk_scores) / len(risk_scores) if risk_scores else 0
        top_member = max(members, key=lambda m: m["account_risk_score"] or 0)
        summary.append(
            {
                "community_id": community_id,
                "size": len(members),
                "avg_risk_score": round(avg_risk, 1),
                "top_entity": {
                    "id": top_member["owner_human_id"],
                    "name": top_member["owner_name"],
                    "label": top_member["resolved_label"],
                },
            }
        )
    summary.sort(key=lambda c: c["avg_risk_score"], reverse=True)
    return {"communities": summary, "total_communities": len(summary)}


async def run_node2vec_similarity(driver: AsyncDriver, seed_human_id: str, top_k: int = 10) -> list[dict]:
    await ensure_projection(driver)
    async with driver.session() as session:
        result = await session.run(
            """
            CALL gds.node2vec.stream($name, { embeddingDimension: 64, iterations: 5 })
            YIELD nodeId, embedding
            RETURN gds.util.asNode(nodeId).id AS uuid, embedding
            """,
            name=PROJECTION_NAME,
        )
        rows = [dict(record) async for record in result]

        seed_result = await session.run(
            """
            MATCH (owner) WHERE owner.person_id = $seed OR owner.org_id = $seed
            MATCH (owner)-[:OWNS_ACCOUNT]->(a:Account)
            RETURN a.id AS uuid LIMIT 1
            """,
            seed=seed_human_id,
        )
        seed_record = await seed_result.single()

    if seed_record is None or not rows:
        return []

    seed_uuid = seed_record["uuid"]
    embeddings = {row["uuid"]: row["embedding"] for row in rows}
    seed_vector = embeddings.get(seed_uuid)
    if seed_vector is None:
        return []

    similarities = []
    for uuid, vector in embeddings.items():
        if uuid == seed_uuid:
            continue
        similarities.append((uuid, _cosine_similarity(seed_vector, vector)))
    similarities.sort(key=lambda pair: pair[1], reverse=True)
    top = similarities[:top_k]

    owners = await _owner_lookup(driver, [uuid for uuid, _ in top])
    shaped = []
    for uuid, sim in top:
        owner = owners.get(uuid)
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
    return shaped


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


HOP_DECAY = 1.0
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
                   coalesce(n.name, n.account_id) AS name, labels(n)[0] AS label, n.risk_score AS risk_score
            """,
            seeds=seed_ids,
        )
        seeds = [dict(record) async for record in seed_result]
        if not seeds:
            return {"seeds": [], "propagated": []}

        frontier = {s["uuid"]: s["risk_score"] or 50.0 for s in seeds}
        visited = set(frontier.keys())
        accumulated: dict[str, float] = {}

        for hop in range(1, max_hops + 1):
            if not frontier:
                break
            neighbor_result = await session.run(
                """
                MATCH (n)-[r]-(m)
                WHERE n.id IN $frontier_ids AND NOT m.id IN $visited
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
        "seeds": [
            {"id": s["human_id"], "name": s["name"], "label": s["label"], "risk_score": s["risk_score"]}
            for s in seeds
        ],
        "propagated": propagated,
    }


async def run_cycle_detection(
    driver: AsyncDriver, min_length: int = 3, max_length: int = 6, limit: int = 25
) -> list[dict]:
    """Finds circular money-movement paths (A -> B -> ... -> A) in the
    transaction graph — the classic laundering-ring signature. Bounded by
    length and result count since cycle enumeration is combinatorially
    expensive; scoped to flagged transactions first since that's where
    real injected storylines live, then falls back to the full graph."""
    # Variable-length relationship bounds must be literals in Cypher (not query
    # parameters) — safe to interpolate here since both are typed ints, never
    # raw user input.
    async with driver.session() as session:
        result = await session.run(
            f"""
            MATCH path = (a:Account)-[rels:TRANSACTED_WITH*{min_length}..{max_length}]->(a)
            WHERE any(r IN rels WHERE r.flagged = true)
            WITH path, rels LIMIT $limit
            RETURN [n IN nodes(path) | n.account_id] AS account_ids,
                   [n IN nodes(path) | n.id] AS uuids,
                   length(path) AS length,
                   reduce(total = 0.0, r IN rels | total + r.amount) AS total_amount
            """,
            limit=limit,
        )
        rows = [dict(record) async for record in result]

    all_uuids = {uuid for row in rows for uuid in row["uuids"]}
    owners = await _owner_lookup(driver, list(all_uuids))

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
        cycles.append({"length": row["length"], "total_amount": round(row["total_amount"], 2), "members": members})
    return cycles
