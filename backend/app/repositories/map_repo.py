"""Geospatial queries for the Map page (ARGUS_PLAN.md Phase 6, Page 4)."""

from neo4j import AsyncDriver

from app.repositories.graph_repo import to_graph_node


async def get_map_entities(driver: AsyncDriver, entity_type: str | None = None, limit: int = 10_000) -> list[dict]:
    labels = [entity_type] if entity_type in ("Person", "Organization") else ["Person", "Organization"]
    results: list[dict] = []

    async with driver.session() as session:
        for label in labels:
            result = await session.run(
                f"MATCH (n:{label}) WHERE n.lat IS NOT NULL RETURN n LIMIT $limit",
                limit=limit,
            )
            async for record in result:
                node = to_graph_node(dict(record["n"]), label)
                results.append(node)

    return results


async def get_map_shipments(driver: AsyncDriver, limit: int = 1200) -> list[dict]:
    query = """
    MATCH (s:Shipment)
    MATCH (origin:Location {id: s.origin_id})
    MATCH (dest:Location {id: s.destination_id})
    RETURN s.shipment_id AS shipment_id, s.carrier AS carrier, s.status AS status,
           s.route_anomaly AS route_anomaly, s.risk_score AS risk_score,
           origin.name AS origin_name, origin.city AS origin_city, origin.lat AS origin_lat, origin.lng AS origin_lng,
           dest.name AS dest_name, dest.city AS dest_city, dest.lat AS dest_lat, dest.lng AS dest_lng
    LIMIT $limit
    """
    async with driver.session() as session:
        result = await session.run(query, limit=limit)
        return [dict(record) async for record in result]
