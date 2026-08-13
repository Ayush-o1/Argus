"""Raw Cypher access to the graph. Every query here is index-backed (see
generator/generators/neo4j_writer.py for the constraints/indexes created at
generation time) — no full graph scans in user-facing paths, per
ARGUS_PLAN.md Phase 15.
"""

from neo4j import AsyncDriver

from app.repositories.entity_labels import ENTITY_LABELS, resolve_label

MAX_NEIGHBORHOOD_NODES = 500

# Labels `list_entities` can page over. Location is included so the Search
# page's Location facet browses actual Locations (the fulltext index already
# covers it); Device is browse-only, since it carries no name to match on.
BROWSABLE_LABELS = ("Person", "Organization", "Location", "Vehicle", "Device")


async def get_node_by_human_id(driver: AsyncDriver, human_id: str) -> dict | None:
    """Returns a fully-shaped GraphNode dict (see to_graph_node), plus `degree`."""
    info = resolve_label(human_id)
    if info is None:
        return None

    query = f"""
    MATCH (n:{info.label} {{{info.id_field}: $human_id}})
    OPTIONAL MATCH (n)-[r]-()
    RETURN n, labels(n)[0] AS label, count(r) AS degree
    """
    async with driver.session() as session:
        result = await session.run(query, human_id=human_id)
        record = await result.single()
        if record is None:
            return None
        node = to_graph_node(dict(record["n"]), record["label"])
        node["degree"] = record["degree"]
        return node


async def get_one_hop_neighbors(driver: AsyncDriver, human_id: str, limit: int = 100) -> list[dict]:
    """Every relationship touching this node, either direction, with the other endpoint."""
    info = resolve_label(human_id)
    if info is None:
        return []

    query = f"""
    MATCH (n:{info.label} {{{info.id_field}: $human_id}})-[r]-(m)
    RETURN n, r, m, labels(m)[0] AS other_label, type(r) AS rel_type,
           startNode(r) = n AS outgoing
    LIMIT $limit
    """
    async with driver.session() as session:
        result = await session.run(query, human_id=human_id, limit=limit)
        return [
            {
                "rel": dict(record["r"]),
                "rel_type": record["rel_type"],
                "other": dict(record["m"]),
                "other_label": record["other_label"],
                "outgoing": record["outgoing"],
            }
            async for record in result
        ]


async def get_neighborhood(
    driver: AsyncDriver, human_id: str, depth: int = 1, limit: int = MAX_NEIGHBORHOOD_NODES
) -> dict:
    """BFS expansion done as repeated 1-hop queries (bounded, predictable cost)
    rather than a single variable-length Cypher pattern, which would risk
    exploding through hub nodes like high-degree Account/Device vertices."""
    info = resolve_label(human_id)
    if info is None:
        return {"nodes": [], "edges": []}

    seed = await get_node_by_human_id(driver, human_id)
    if seed is None:
        return {"nodes": [], "edges": []}

    nodes_by_id: dict[str, dict] = {human_id: seed}
    edges: list[dict] = []
    seen_edge_keys: set[tuple] = set()
    frontier = [human_id]

    for _hop in range(depth):
        next_frontier: list[str] = []
        for current_id in frontier:
            if len(nodes_by_id) >= limit:
                break
            for item in await get_one_hop_neighbors(driver, current_id, limit=limit):
                other_id = _human_id_of(item["other"], item["other_label"])
                if other_id is None:
                    continue
                if other_id not in nodes_by_id and len(nodes_by_id) < limit:
                    nodes_by_id[other_id] = to_graph_node(item["other"], item["other_label"])
                    next_frontier.append(other_id)

                src, dst = (current_id, other_id) if item["outgoing"] else (other_id, current_id)
                edge_key = (src, dst, item["rel_type"], item["rel"].get("tx_id") or item["rel"].get("comm_id") or "")
                if edge_key in seen_edge_keys:
                    continue
                seen_edge_keys.add(edge_key)
                edges.append(
                    {
                        "id": f"{src}->{item['rel_type']}->{dst}:{len(edges)}",
                        "source": src,
                        "target": dst,
                        "type": item["rel_type"],
                        "properties": item["rel"],
                    }
                )
        frontier = next_frontier
        if not frontier or len(nodes_by_id) >= limit:
            break

    return {"nodes": list(nodes_by_id.values()), "edges": edges}


def _human_id_of(props: dict, label: str) -> str | None:
    for info in ENTITY_LABELS.values():
        if info.label == label and info.id_field in props:
            return props[info.id_field]
    return None


def to_graph_node(props: dict, label: str) -> dict:
    info = next((i for i in ENTITY_LABELS.values() if i.label == label), None)
    human_id = props.get(info.id_field) if info else None
    name = props.get(info.name_field) if info else None
    return {
        "id": human_id,
        "uuid": props.get("id"),
        "label": label,
        "name": name or human_id or "Unknown",
        "risk_score": props.get("risk_score", 0.0),
        "properties": props,
    }


# `city` only exists on these labels; Vehicles and Devices are located through
# their owner rather than carrying coordinates of their own.
CITY_FILTERABLE_LABELS = ("Person", "Organization", "Location")


def build_browse_filters(label: str, risk_min: float, city: str | None) -> tuple[str, str]:
    """Cypher fragments for the browse filters, as (risk_filter, city_filter).

    The risk filter applies to every browsable label. Restricting it to
    Person/Organization meant "High risk and above" silently returned every
    Location, Vehicle and Device on the page — unfiltered rows presented as
    matching the filter. All five labels carry a non-null risk_score, so
    applying it uniformly is simply the honest answer, including when that
    answer is no results at all.
    """
    risk_filter = "AND n.risk_score >= $risk_min" if risk_min > 0 else ""
    city_filter = "AND n.city = $city" if city and label in CITY_FILTERABLE_LABELS else ""
    return risk_filter, city_filter


async def list_entities(
    driver: AsyncDriver,
    entity_type: str,
    risk_min: float = 0,
    city: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    if entity_type not in BROWSABLE_LABELS:
        # Previously this silently fell back to "Person" for anything
        # unrecognised, so a UI facet for a non-browsable type returned a list
        # of people labelled as that type — wrong data presented as correct.
        raise ValueError(f"Unsupported entity type: {entity_type}")
    label = entity_type
    risk_filter, city_filter = build_browse_filters(label, risk_min, city)

    count_query = f"MATCH (n:{label}) WHERE true {risk_filter} {city_filter} RETURN count(n) AS total"
    query = f"""
    MATCH (n:{label}) WHERE true {risk_filter} {city_filter}
    RETURN n ORDER BY n.risk_score DESC SKIP $skip LIMIT $limit
    """
    params = {"risk_min": risk_min, "city": city, "skip": (page - 1) * page_size, "limit": page_size}

    async with driver.session() as session:
        total_result = await session.run(count_query, params)
        total_record = await total_result.single()
        total = total_record["total"] if total_record else 0

        result = await session.run(query, params)
        nodes = [to_graph_node(dict(record["n"]), label) async for record in result]

    return nodes, total


async def search_entities(driver: AsyncDriver, query_text: str, limit: int = 20) -> list[dict]:
    if not query_text.strip():
        return []
    cypher = """
    CALL db.index.fulltext.queryNodes('entity_name', $query_text + '~') YIELD node, score
    RETURN node, labels(node)[0] AS label, score
    ORDER BY score DESC
    LIMIT $limit
    """
    async with driver.session() as session:
        result = await session.run(cypher, query_text=query_text, limit=limit)
        return [to_graph_node(dict(record["node"]), record["label"]) async for record in result]


async def shortest_path(driver: AsyncDriver, from_id: str, to_id: str) -> dict | None:
    from_info, to_info = resolve_label(from_id), resolve_label(to_id)
    if from_info is None or to_info is None:
        return None

    query = f"""
    MATCH (a:{from_info.label} {{{from_info.id_field}: $from_id}})
    MATCH (b:{to_info.label} {{{to_info.id_field}: $to_id}})
    MATCH path = shortestPath((a)-[*..8]-(b))
    RETURN path
    """
    async with driver.session() as session:
        result = await session.run(query, from_id=from_id, to_id=to_id)
        record = await result.single()
        if record is None:
            return None
        path = record["path"]
        nodes = [to_graph_node(dict(n), list(n.labels)[0]) for n in path.nodes]
        edges = [
            {
                "id": f"path-{i}",
                "source": _human_id_of(dict(rel.start_node), list(rel.start_node.labels)[0]),
                "target": _human_id_of(dict(rel.end_node), list(rel.end_node.labels)[0]),
                "type": rel.type,
                "properties": dict(rel),
            }
            for i, rel in enumerate(path.relationships)
        ]
        return {"nodes": nodes, "edges": edges, "length": len(path.relationships)}


async def get_overview_subgraph(driver: AsyncDriver, seed_limit: int = 25, edge_limit: int = 400) -> dict:
    """Default Graph Explorer view when no seed entity is chosen: the
    highest-risk persons and organizations plus their immediate neighbors —
    a genuinely interesting starting point rather than an arbitrary slice."""
    query = """
    MATCH (seed) WHERE (seed:Person OR seed:Organization) AND seed.risk_score > 0
    WITH seed ORDER BY seed.risk_score DESC LIMIT $seed_limit
    MATCH (seed)-[r]-(m)
    RETURN seed, r, m, labels(seed)[0] AS seed_label, labels(m)[0] AS other_label,
           type(r) AS rel_type, startNode(r) = seed AS outgoing
    LIMIT $edge_limit
    """
    nodes_by_id: dict[str, dict] = {}
    edges: list[dict] = []
    seen_edge_keys: set[tuple] = set()

    async with driver.session() as session:
        result = await session.run(query, seed_limit=seed_limit, edge_limit=edge_limit)
        async for record in result:
            seed_node = to_graph_node(dict(record["seed"]), record["seed_label"])
            other_node = to_graph_node(dict(record["m"]), record["other_label"])
            nodes_by_id.setdefault(seed_node["id"], seed_node)
            nodes_by_id.setdefault(other_node["id"], other_node)

            src, dst = (
                (seed_node["id"], other_node["id"]) if record["outgoing"] else (other_node["id"], seed_node["id"])
            )
            rel_props = dict(record["r"])
            edge_key = (src, dst, record["rel_type"], rel_props.get("tx_id") or rel_props.get("comm_id") or "")
            if edge_key in seen_edge_keys:
                continue
            seen_edge_keys.add(edge_key)
            edges.append(
                {
                    "id": f"{src}->{record['rel_type']}->{dst}:{len(edges)}",
                    "source": src,
                    "target": dst,
                    "type": record["rel_type"],
                    "properties": rel_props,
                }
            )

    return {"nodes": list(nodes_by_id.values()), "edges": edges}
