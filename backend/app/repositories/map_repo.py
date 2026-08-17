"""Geospatial queries for the Map page (ARGUS_PLAN.md Phase 6, Page 4).

The map is a drill-down: World -> Region -> Country -> City -> Entity. The
region and country rollups here exist so the world view can be drawn from
aggregates rather than by shipping several thousand points to the client and
clustering them there — at world zoom the individual points aren't legible
anyway, and the aggregate is the thing the analyst is actually reading.
"""

from neo4j import AsyncDriver

from app.repositories.graph_repo import to_graph_node

# Kept in sync with generator/geography.py's REGION_CENTERS. Duplicated rather
# than imported because the generator is a separate deployable with its own
# virtualenv (see architecture.md) — the backend cannot import from it.
REGION_CENTERS: dict[str, tuple[float, float, float]] = {
    "South Asia": (21.0, 78.0, 4.0),
    "Middle East": (25.0, 51.0, 4.4),
    "Central Asia": (41.5, 63.0, 4.2),
    "Southeast Asia": (5.0, 108.0, 4.0),
    "East Asia": (28.0, 122.0, 4.0),
    "Europe": (48.5, 10.0, 3.8),
    "Africa": (5.0, 20.0, 3.2),
    "North America": (35.0, -90.0, 3.4),
    "South America": (-20.0, -60.0, 3.4),
    "Oceania": (-33.0, 148.0, 4.0),
}


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
    # `via` is optional and only set on circuitous routes, so it must be an
    # OPTIONAL MATCH — a plain MATCH would silently drop every normal shipment.
    query = """
    MATCH (s:Shipment)
    MATCH (origin:Location {id: s.origin_id})
    MATCH (dest:Location {id: s.destination_id})
    OPTIONAL MATCH (via:Location {id: s.via_id})
    RETURN s.shipment_id AS shipment_id, s.carrier AS carrier, s.status AS status,
           s.argus_band AS argus_band, s.argus_score AS argus_score,
           s.argus_coverage AS argus_coverage, s.lane AS lane,
           s.origin_region AS origin_region, s.destination_region AS destination_region,
           s.distance_km AS distance_km, s.detour_ratio AS detour_ratio,
           s.departure AS departure, s.arrival AS arrival, s.manifest AS manifest,
           origin.name AS origin_name, origin.city AS origin_city, origin.country AS origin_country,
           origin.lat AS origin_lat, origin.lng AS origin_lng,
           dest.name AS dest_name, dest.city AS dest_city, dest.country AS dest_country,
           dest.lat AS dest_lat, dest.lng AS dest_lng,
           via.name AS via_name, via.city AS via_city, via.country AS via_country,
           via.lat AS via_lat, via.lng AS via_lng
    LIMIT $limit
    """
    async with driver.session() as session:
        result = await session.run(query, limit=limit)
        return [dict(record) async for record in result]


async def get_region_rollup(driver: AsyncDriver) -> list[dict]:
    """Per-region aggregates for the world view, with map centers attached."""
    query = """
    MATCH (n)
    WHERE (n:Person OR n:Organization) AND n.region IS NOT NULL
    WITH n.region AS region,
         count(n) AS entity_count,
         // Counts, not an average. A mean over a region where most entities
         // could not be assessed at all describes nothing, and shading a map by
         // one is how a sparsely-collected region comes to look calm.
         sum(CASE WHEN n.argus_band = 'elevated' THEN 1 ELSE 0 END) AS elevated_count,
         sum(CASE WHEN n.argus_band IS NOT NULL
                   AND n.argus_band <> 'insufficient_evidence' THEN 1 ELSE 0 END) AS assessed_count,
         sum(CASE WHEN n:Organization THEN 1 ELSE 0 END) AS org_count,
         count(DISTINCT n.country) AS country_count
    RETURN region, entity_count, elevated_count, assessed_count, org_count, country_count
    ORDER BY entity_count DESC
    """
    async with driver.session() as session:
        result = await session.run(query)
        rows = [dict(record) async for record in result]

    # Routes ARGUS assessed as worth a look, attributed to both endpoints — a
    # divergent shipment is a signal about the regions at each end of it, not
    # just the origin.
    #
    # Counted from ARGUS's own band, not from the generator's `route_anomaly`
    # flag. The map used to render the answer key as "anomalous routes", which
    # is the audit's G-08 finding wearing a cartographic hat.
    anomaly_query = """
    MATCH (s:Shipment) WHERE s.argus_band IN ['elevated', 'notable']
    UNWIND [s.origin_region, s.destination_region] AS region
    RETURN region, count(*) AS flagged_routes
    """
    async with driver.session() as session:
        result = await session.run(anomaly_query)
        flagged = {r["region"]: r["flagged_routes"] async for r in result}

    for row in rows:
        center = REGION_CENTERS.get(row["region"])
        row["lat"], row["lng"], row["zoom"] = center if center else (0.0, 0.0, 3.0)
        row["flagged_routes"] = flagged.get(row["region"], 0)

    return rows


async def get_country_rollup(driver: AsyncDriver, region: str | None = None) -> list[dict]:
    """Per-country aggregates, optionally scoped to one region (drill-down step 2)."""
    query = """
    MATCH (n)
    WHERE (n:Person OR n:Organization) AND n.country IS NOT NULL
      AND ($region IS NULL OR n.region = $region)
    WITH n.country AS country, n.country_code AS country_code, n.region AS region,
         count(n) AS entity_count,
         sum(CASE WHEN n.argus_band = 'elevated' THEN 1 ELSE 0 END) AS elevated_count,
         sum(CASE WHEN n.argus_band IS NOT NULL
                   AND n.argus_band <> 'insufficient_evidence' THEN 1 ELSE 0 END) AS assessed_count,
         avg(n.lat) AS lat, avg(n.lng) AS lng
    RETURN country, country_code, region, entity_count, elevated_count, assessed_count, lat, lng
    ORDER BY entity_count DESC
    """
    async with driver.session() as session:
        result = await session.run(query, region=region)
        return [dict(record) async for record in result]


async def get_corridors(driver: AsyncDriver) -> list[dict]:
    """Trade lanes aggregated from actual shipments, with their anomaly share.

    Direction is collapsed (A->B and B->A are one corridor) because an analyst
    reading the world view is asking "how much moves between these regions",
    not "how much moves eastbound".
    """
    query = """
    MATCH (s:Shipment)
    WHERE s.origin_region IS NOT NULL AND s.destination_region IS NOT NULL
      AND s.origin_region <> s.destination_region
    WITH CASE WHEN s.origin_region < s.destination_region
              THEN s.origin_region ELSE s.destination_region END AS a,
         CASE WHEN s.origin_region < s.destination_region
              THEN s.destination_region ELSE s.origin_region END AS b,
         s
    RETURN a AS from_region, b AS to_region,
           count(s) AS shipment_count,
           sum(CASE WHEN s.argus_band IN ['elevated', 'notable'] THEN 1 ELSE 0 END) AS flagged_count,
           sum(CASE WHEN s.argus_band IS NULL THEN 1 ELSE 0 END) AS unassessed_count
    ORDER BY shipment_count DESC
    """
    async with driver.session() as session:
        result = await session.run(query)
        rows = [dict(record) async for record in result]

    for row in rows:
        from_c = REGION_CENTERS.get(row["from_region"], (0.0, 0.0, 3.0))
        to_c = REGION_CENTERS.get(row["to_region"], (0.0, 0.0, 3.0))
        row["from_lat"], row["from_lng"] = from_c[0], from_c[1]
        row["to_lat"], row["to_lng"] = to_c[0], to_c[1]
        # The denominator excludes shipments ARGUS has not assessed, so the
        # rate is a share of what was actually examined rather than a share of
        # everything that exists — the two differ sharply before a run.
        examined = row["shipment_count"] - row["unassessed_count"]
        row["examined_count"] = examined
        row["flagged_rate"] = round(row["flagged_count"] / examined, 3) if examined else None

    return rows
