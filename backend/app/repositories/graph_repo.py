"""Raw Cypher access to the graph.

Every lookup here resolves by human-readable ID (person_id, org_id, ...), each
of which is backed by a uniqueness constraint created in migration 001 (see
app/database/migrations/runner.py). Before that migration only the uuid was
constrained, so these were full label scans — while this docstring claimed they
were index-backed (audit B-09). Verified by EXPLAIN: NodeUniqueIndexSeek.

Keep it that way. If you add a lookup on a new property, add its index in a
migration in the same change.
"""

import logging

from neo4j import AsyncDriver

from app.repositories.entity_labels import ENTITY_LABELS, resolve_label

# Keyed by Neo4j label rather than by ID prefix. Used for a deterministic
# secondary sort: ordering by score alone leaves entities that tie — and with a
# score capped at a reference weight, many do — in whatever order the store
# happens to return, so two identical requests could paginate differently.
ENTITY_LABELS_BY_LABEL = {info.label: info for info in ENTITY_LABELS.values()}

logger = logging.getLogger(__name__)

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
    WHERE type(r) <> 'SAME_AS'
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
    WHERE type(r) <> 'SAME_AS'
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
        # ARGUS's own assessment, or None. It used to be `risk_score` read
        # straight off the node — the scenario generator's number, assigned
        # from storyline membership and rendered by every surface as though it
        # were a finding (audit G-08).
        #
        # None is returned for an entity type ARGUS does not assess and for one
        # it has not assessed yet, and the two are distinguished by `band`
        # rather than collapsed. The generator's value stays on the node,
        # reachable through provenance, which is where a source's claim
        # belongs.
        "assessment": _assessment_of(props),
        "properties": props,
    }


def _assessment_of(props: dict) -> dict | None:
    band = props.get("argus_band")
    if band is None:
        return None
    return {
        "band": band,
        # Absent rather than zero for an unassessable subject, all the way to
        # the client, so nothing downstream can sort it next to a subject that
        # was examined and scored zero.
        "score": props.get("argus_score"),
        "coverage": props.get("argus_coverage"),
        "model": props.get("argus_model"),
        "assessed_at": props.get("argus_assessed_at"),
    }


# `city` only exists on these labels; Vehicles and Devices are located through
# their owner rather than carrying coordinates of their own.
CITY_FILTERABLE_LABELS = ("Person", "Organization", "Location")


# The bands a caller may filter a browse by. `unassessed` is included and is
# not a synonym for "clean": it selects entities ARGUS has no opinion about,
# which is a real thing to want to look at.
BROWSABLE_BANDS = ("elevated", "notable", "routine", "insufficient_evidence", "unassessed")


def build_browse_filters(label: str, band: str | None, city: str | None) -> tuple[str, str]:
    """Cypher fragments for the browse filters, as (band_filter, city_filter).

    The filter is a band rather than a minimum score, because the score is a
    share of whatever could be evaluated for that subject and a threshold
    across mixed subject types compares numbers with different denominators.
    Filtering by band asks the question the analyst actually has: show me the
    ones worth looking at.

    It applies to every browsable label. Restricting it to Person/Organization
    once meant "High risk and above" silently returned every Location, Vehicle
    and Device on the page — unfiltered rows presented as matching the filter.
    Entity types ARGUS does not assess carry no band, so they match only
    `unassessed`, which is the honest answer including when it means no results.
    """
    if band is None:
        band_filter = ""
    elif band == "unassessed":
        band_filter = "AND n.argus_band IS NULL"
    else:
        band_filter = "AND n.argus_band = $band"
    city_filter = "AND n.city = $city" if city and label in CITY_FILTERABLE_LABELS else ""
    return band_filter, city_filter


async def list_entities(
    driver: AsyncDriver,
    entity_type: str,
    band: str | None = None,
    city: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict], int]:
    if entity_type not in BROWSABLE_LABELS:
        # Previously this silently fell back to "Person" for anything
        # unrecognised, so a UI facet for a non-browsable type returned a list
        # of people labelled as that type — wrong data presented as correct.
        raise ValueError(f"Unsupported entity type: {entity_type}")
    if band is not None and band not in BROWSABLE_BANDS:
        raise ValueError(f"Unsupported assessment band: {band}")
    label = entity_type
    band_filter, city_filter = build_browse_filters(label, band, city)

    count_query = f"MATCH (n:{label}) WHERE true {band_filter} {city_filter} RETURN count(n) AS total"
    # NULLS LAST, so entities ARGUS could not assess sort to the end rather
    # than to either extreme. Neo4j orders NULL last on DESC by default; it is
    # stated here because relying on it silently is how a subject with no score
    # ends up at the top of a queue.
    query = f"""
    MATCH (n:{label}) WHERE true {band_filter} {city_filter}
    RETURN n ORDER BY n.argus_score DESC, n.{ENTITY_LABELS_BY_LABEL[label].id_field}
    SKIP $skip LIMIT $limit
    """
    params = {"band": band, "city": city, "skip": (page - 1) * page_size, "limit": page_size}

    async with driver.session() as session:
        total_result = await session.run(count_query, params)
        total_record = await total_result.single()
        total = total_record["total"] if total_record else 0

        result = await session.run(query, params)
        nodes = [to_graph_node(dict(record["n"]), label) async for record in result]

    return nodes, total


# Characters that carry meaning in the Lucene query grammar the fulltext index
# parses. Left unescaped, a search for a name containing an apostrophe-adjacent
# quote or a bracket raised a ParseException that surfaced as an unhandled 500,
# and input like `a* OR b*` was executed as operators rather than matched as
# text — the caller controlled the query grammar, not just the terms (audit B-11).
_LUCENE_SPECIAL = r'+-&|!(){}[]^"~*?:\/'


def escape_lucene(text: str) -> str:
    """Escape Lucene syntax so user input is matched as literal text.

    Backslash is escaped by the same pass because it is itself the escape
    character — handling it separately would double-escape everything after it.
    """
    out: list[str] = []
    for char in text:
        if char in _LUCENE_SPECIAL:
            out.append("\\")
        out.append(char)
    return "".join(out)


# Lucene's boolean keywords are reserved as bare uppercase words, not as
# characters, so character escaping does not neutralise them: searching for the
# literal text "AND" still raised a parse error. Lowercasing removes the
# operator meaning while preserving matching, because the index analyser
# lowercases tokens on both sides anyway.
_LUCENE_KEYWORDS = frozenset({"AND", "OR", "NOT", "TO"})

# Below this length, edit-distance matching matches almost anything, so short
# terms are matched exactly.
_MIN_FUZZY_LENGTH = 3


def build_fulltext_query(query_text: str) -> str:
    """Build a Lucene query that matches the input as literal text.

    The fuzzy operator is applied per term rather than to the whole string: it
    binds to a single term in Lucene, so `foo bar~` made only the last word
    fuzzy while appearing to apply to both.
    """
    parts: list[str] = []
    for raw in query_text.split():
        if not raw:
            continue
        term = raw.lower() if raw in _LUCENE_KEYWORDS else raw
        escaped = escape_lucene(term)
        # Length is measured on the original term: escaping inflates the string
        # with backslashes, which would otherwise push a two-character input
        # past the fuzzy threshold and match half the graph.
        parts.append(f"{escaped}~" if len(term) >= _MIN_FUZZY_LENGTH else escaped)
    return " ".join(parts)


async def search_entities(driver: AsyncDriver, query_text: str, limit: int = 20) -> list[dict]:
    if not query_text.strip():
        return []

    lucene_query = build_fulltext_query(query_text)
    if not lucene_query:
        return []

    cypher = """
    CALL db.index.fulltext.queryNodes('entity_name', $query_text) YIELD node, score
    RETURN node, labels(node)[0] AS label, score
    ORDER BY score DESC
    LIMIT $limit
    """
    async with driver.session() as session:
        result = await session.run(cypher, query_text=lucene_query, limit=limit)
        return [to_graph_node(dict(record["node"]), record["label"]) async for record in result]


async def shortest_path(driver: AsyncDriver, from_id: str, to_id: str) -> dict | None:
    from_info, to_info = resolve_label(from_id), resolve_label(to_id)
    if from_info is None or to_info is None:
        return None

    query = f"""
    MATCH (a:{from_info.label} {{{from_info.id_field}: $from_id}})
    MATCH (b:{to_info.label} {{{to_info.id_field}: $to_id}})
    MATCH path = shortestPath((a)-[rels*..8]-(b))
    WHERE none(rel IN rels WHERE type(rel) = 'SAME_AS')
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
    """Default Graph Explorer view when no seed entity is chosen: the persons
    and organizations ARGUS assessed most highly, plus their immediate
    neighbours — a genuinely interesting starting point rather than an
    arbitrary slice.

    Seeded from `argus_score`, not from the generator's `risk_score`. Seeding
    the explorer from the answer key meant the default view was a tour of the
    planted storylines, which looked like the platform finding things."""
    query = """
    MATCH (seed) WHERE (seed:Person OR seed:Organization) AND seed.argus_score > 0
    WITH seed ORDER BY seed.argus_score DESC LIMIT $seed_limit
    MATCH (seed)-[r]-(m)
    WHERE type(r) <> 'SAME_AS'
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

            # `to_graph_node` yields id=None for any label absent from
            # ENTITY_LABELS. Keying on that collapsed every such node into one
            # entry and left edges pointing at a node id that does not exist
            # (audit B-28). Unreachable with today's labels; a trap for the next
            # one added.
            if seed_node["id"] is None or other_node["id"] is None:
                logger.warning(
                    "skipping node with unmapped label in overview subgraph",
                    extra={"seed_label": record["seed_label"], "other_label": record["other_label"]},
                )
                continue

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
