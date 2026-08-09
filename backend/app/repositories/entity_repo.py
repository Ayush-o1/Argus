"""Entity-specific queries that go beyond generic graph traversal: connection
summaries and activity timelines for the Entity Profile page (ARGUS_PLAN.md
Phase 6)."""

from neo4j import AsyncDriver

from app.repositories.entity_labels import resolve_label


async def get_connection_summary(driver: AsyncDriver, human_id: str) -> dict[str, int]:
    """Counts of directly-connected nodes grouped by label, e.g. {"Account": 3, "Device": 2}."""
    info = resolve_label(human_id)
    if info is None:
        return {}

    query = f"""
    MATCH (n:{info.label} {{{info.id_field}: $human_id}})-[]-(m)
    RETURN labels(m)[0] AS label, count(DISTINCT m) AS count
    """
    async with driver.session() as session:
        result = await session.run(query, human_id=human_id)
        return {record["label"]: record["count"] async for record in result}


async def get_related_cases(driver: AsyncDriver, human_id: str) -> list[dict]:
    """Cases this entity is linked to, for the Entity Profile's cross-page
    navigation (ARGUS_PLAN.md Phase 7) — reverses case_repo.add_entity_to_case's
    Case-[:LINKED_TO]->Entity direction."""
    info = resolve_label(human_id)
    if info is None:
        return []

    query = f"""
    MATCH (c:Case)-[:LINKED_TO]->(n:{info.label} {{{info.id_field}: $human_id}})
    RETURN c ORDER BY c.opened_at DESC
    """
    async with driver.session() as session:
        result = await session.run(query, human_id=human_id)
        return [dict(record["c"]) async for record in result]


async def get_related_alerts(driver: AsyncDriver, human_id: str, limit: int = 20) -> list[dict]:
    """Alerts (high/critical Incidents) this entity is involved in — reverses
    alert_repo.list_alerts's Incident-[:INVOLVES]->Entity direction."""
    info = resolve_label(human_id)
    if info is None:
        return []

    query = f"""
    MATCH (i:Incident)-[:INVOLVES]->(n:{info.label} {{{info.id_field}: $human_id}})
    RETURN i ORDER BY i.timestamp DESC LIMIT $limit
    """
    async with driver.session() as session:
        result = await session.run(query, human_id=human_id, limit=limit)
        return [dict(record["i"]) async for record in result]


async def get_entity_timeline(driver: AsyncDriver, human_id: str, limit: int = 200) -> list[dict]:
    info = resolve_label(human_id)
    if info is None or info.label not in ("Person", "Organization"):
        return []

    events_query = f"""
    MATCH (n:{info.label} {{{info.id_field}: $human_id}})-[:ATTENDED]->(e:Event)-[:OCCURRED_AT]->(l:Location)
    RETURN 'Event' AS kind, e.type AS subtype, e.timestamp AS timestamp,
           {{event_id: e.event_id, location: l.name, city: l.city}} AS details
    """
    tx_query = f"""
    MATCH (n:{info.label} {{{info.id_field}: $human_id}})-[:OWNS_ACCOUNT]->(a:Account)
    MATCH (a)-[t:TRANSACTED_WITH]-(other:Account)
    RETURN 'Transaction' AS kind, t.type AS subtype, t.timestamp AS timestamp,
           {{tx_id: t.tx_id, amount: t.amount, currency: t.currency, flagged: t.flagged,
             from_account: a.account_id, other_account: other.account_id}} AS details
    """
    comm_query = f"""
    MATCH (n:{info.label} {{{info.id_field}: $human_id}})-[:OWNS_DEVICE]->(d:Device)
    MATCH (d)-[c:COMMUNICATED_WITH]-(other:Device)
    RETURN 'Communication' AS kind, c.type AS subtype, c.timestamp AS timestamp,
           {{comm_id: c.comm_id, duration_seconds: c.duration_seconds, flagged: c.flagged}} AS details
    """

    queries = [events_query, tx_query, comm_query] if info.label == "Person" else [tx_query]

    items: list[dict] = []
    async with driver.session() as session:
        for query in queries:
            result = await session.run(query, human_id=human_id)
            async for record in result:
                items.append(
                    {
                        "kind": record["kind"],
                        "subtype": record["subtype"],
                        "timestamp": record["timestamp"],
                        "details": record["details"],
                    }
                )

    items.sort(key=lambda x: x["timestamp"], reverse=True)
    return items[:limit]
