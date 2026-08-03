"""Stage 11: Index + Write to Neo4j.

Modeling note (v1 implementation refinement over the strict Phase 7
ontology): Transaction and Communication are written as *relationship*
properties on TRANSACTED_WITH / COMMUNICATED_WITH edges between Account and
Device nodes, rather than as their own intermediate nodes. At this
project's scale that's tens of thousands fewer nodes for identical query
power — every property survives on the edge, and the algorithms that
actually need this data (cycle detection, PageRank, communication density)
all operate on Account-Account / Device-Device edges directly. See
ARGUS_PLAN.md Phase 7 for the full ontology this refines.
"""

import logging

from neo4j import Driver

logger = logging.getLogger("argus.generator.writer")

BATCH_SIZE = 2000

# Which node label a human-readable ID prefix resolves to, for building
# generic entity-reference edges (Incident.involved_entity_ids, etc.).
# TXN/COM have no node label — they're edges — and are skipped.
LABEL_BY_PREFIX = {
    "PRS": "Person",
    "ORG": "Organization",
    "ACC": "Account",
    "DEV": "Device",
    "VEH": "Vehicle",
    "DOC": "Document",
    "SHP": "Shipment",
    "EVT": "Event",
    "LOC": "Location",
    "CASE": "Case",
}

NODE_SPECS = [
    ("Person", "persons", "person_id"),
    ("Organization", "orgs", "org_id"),
    ("Location", "locations", "location_id"),
    ("Vehicle", "vehicles", "vehicle_id"),
    ("Device", "devices", "device_id"),
    ("Account", "accounts", "account_id"),
    ("Event", "events", "event_id"),
    ("Shipment", "shipments", "shipment_id"),
    ("Document", "documents", "doc_id"),
    ("Incident", "incidents", "incident_id"),
    ("Case", "cases", "case_id"),
    ("Storyline", "storylines", "storyline_id"),
]


def write_world(driver: Driver, world: dict, wipe_existing: bool = True) -> None:
    with driver.session() as session:
        if wipe_existing:
            _wipe(session)
        _create_constraints(session)

        for label, world_key, _id_field in NODE_SPECS:
            _write_nodes(session, label, world.get(world_key, []))

        _write_owned_by(session, "OWNS_ACCOUNT", world["accounts"], "owner_id", "owner_type")
        _write_owned_by(session, "OWNS_VEHICLE", world["vehicles"], "registered_to", "owner_type")
        _write_simple_edges(session, "Person", "Device", "OWNS_DEVICE", world["devices"], "owner_id", "id")

        _write_relationship_rows(session, "Person", "Organization", "DIRECTS", world["directs_edges"], "person_id", "org_id")
        _write_relationship_rows(
            session, "Person", "Organization", "EMPLOYED_BY", world["employment_edges"], "person_id", "org_id"
        )
        _write_relationship_rows(
            session, "Person", "Organization", "CONTROLS", world["controls_edges"], "person_id", "org_id"
        )
        _write_relationship_rows(
            session, "Person", "Person", "SHARES_DEVICE", world["shares_device_edges"], "person_a_id", "person_b_id"
        )

        _write_transacted_with(session, world["transactions"])
        _write_communicated_with(session, world["communications"])
        _write_attended(session, world["events"])
        _write_occurred_at(session, world["events"])
        _write_document_edges(session, world["documents"])
        _write_entity_reference_edges(session, "Incident", "INVOLVES", world["incidents"], "involved_entity_ids")
        _write_entity_reference_edges(session, "Case", "LINKED_TO", world["cases"], "linked_entity_human_ids")

        _create_search_and_range_indexes(session)


def write_scenario(driver: Driver, world: dict) -> None:
    """Additive write for a single on-demand scenario (ARGUS_PLAN.md Phase 9,
    Scenario Generator): writes only the newly-created nodes/edges. Existing
    Person nodes referenced by uuid are MATCHed, never re-created via
    `_write_nodes`'s CREATE, so this can never collide with or duplicate
    anything already in the live graph. Locations/Vehicles/Events are
    likewise never populated by scenario generation and pass through as
    no-op empty lists."""
    with driver.session() as session:
        for label, world_key, _id_field in NODE_SPECS:
            if world_key == "persons":
                continue  # pre-existing — reused by reference only, never re-created
            _write_nodes(session, label, world.get(world_key, []))

        _write_owned_by(session, "OWNS_ACCOUNT", world.get("accounts", []), "owner_id", "owner_type")
        _write_simple_edges(session, "Person", "Device", "OWNS_DEVICE", world.get("devices", []), "owner_id", "id")
        _write_relationship_rows(
            session, "Person", "Organization", "CONTROLS", world.get("controls_edges", []), "person_id", "org_id"
        )
        _write_relationship_rows(
            session, "Person", "Person", "SHARES_DEVICE", world.get("shares_device_edges", []), "person_a_id", "person_b_id"
        )
        _write_transacted_with(session, world.get("transactions", []))
        _write_communicated_with(session, world.get("communications", []))
        _write_document_edges(session, world.get("documents", []))
        _write_entity_reference_edges(session, "Incident", "INVOLVES", world.get("incidents", []), "involved_entity_ids")
        _write_entity_reference_edges(session, "Case", "LINKED_TO", world.get("cases", []), "linked_entity_human_ids")


def _wipe(session) -> None:
    logger.info("Wiping existing graph...")
    session.run("MATCH (n) CALL { WITH n DETACH DELETE n } IN TRANSACTIONS OF 5000 ROWS")


def _create_constraints(session) -> None:
    for label, _world_key, _id_field in NODE_SPECS:
        session.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE")


def _create_search_and_range_indexes(session) -> None:
    session.run(
        "CREATE FULLTEXT INDEX entity_name IF NOT EXISTS "
        "FOR (n:Person|Organization|Location|Vehicle) ON EACH [n.name]"
    )
    session.run("CREATE INDEX person_risk IF NOT EXISTS FOR (n:Person) ON (n.risk_score)")
    session.run("CREATE INDEX org_risk IF NOT EXISTS FOR (n:Organization) ON (n.risk_score)")
    session.run("CREATE INDEX person_city IF NOT EXISTS FOR (n:Person) ON (n.city)")
    session.run("CREATE INDEX event_time IF NOT EXISTS FOR (n:Event) ON (n.timestamp)")
    session.run("CREATE INDEX incident_status IF NOT EXISTS FOR (n:Incident) ON (n.status, n.severity)")


def _chunks(rows: list[dict], size: int = BATCH_SIZE):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _write_nodes(session, label: str, rows: list[dict]) -> None:
    if not rows:
        return
    for batch in _chunks(rows):
        session.run(f"UNWIND $rows AS row CREATE (n:{label}) SET n = row", rows=batch)
    logger.info("Wrote %d :%s nodes", len(rows), label)


def _write_owned_by(session, rel_type: str, rows: list[dict], owner_key: str, owner_type_key: str) -> None:
    """Splits rows by owner_type (Person/Organization) so each batch can MATCH a fixed label.
    `rows` are the target nodes themselves (accounts/vehicles) — each already has its own
    `id`, so the target side matches on `row.id` directly."""
    target_label = "Account" if rel_type == "OWNS_ACCOUNT" else "Vehicle"
    for owner_label in ("Person", "Organization"):
        subset = [r for r in rows if r[owner_type_key] == owner_label]
        if not subset:
            continue
        for batch in _chunks(subset):
            session.run(
                f"""
                UNWIND $rows AS row
                MATCH (owner:{owner_label} {{id: row.{owner_key}}})
                MATCH (target:{target_label} {{id: row.id}})
                CREATE (owner)-[:{rel_type}]->(target)
                """,
                rows=batch,
            )
        logger.info("Wrote %d %s edges (%s -> %s)", len(subset), rel_type, owner_label, target_label)


def _write_simple_edges(session, from_label: str, to_label: str, rel_type: str, rows: list[dict], from_key: str, to_key: str) -> None:
    if not rows:
        return
    for batch in _chunks(rows):
        session.run(
            f"""
            UNWIND $rows AS row
            MATCH (a:{from_label} {{id: row.{from_key}}})
            MATCH (b:{to_label} {{id: row.{to_key}}})
            CREATE (a)-[:{rel_type}]->(b)
            """,
            rows=batch,
        )
    logger.info("Wrote %d %s edges (%s -> %s)", len(rows), rel_type, from_label, to_label)


def _write_relationship_rows(session, from_label: str, to_label: str, rel_type: str, rows: list[dict], from_key: str, to_key: str) -> None:
    if not rows:
        return
    for batch in _chunks(rows):
        session.run(
            f"""
            UNWIND $rows AS row
            MATCH (a:{from_label} {{id: row.{from_key}}})
            MATCH (b:{to_label} {{id: row.{to_key}}})
            CREATE (a)-[r:{rel_type}]->(b)
            SET r = row
            """,
            rows=batch,
        )
    logger.info("Wrote %d :%s edges", len(rows), rel_type)


def _write_transacted_with(session, transactions: list[dict]) -> None:
    if not transactions:
        return
    for batch in _chunks(transactions):
        session.run(
            """
            UNWIND $rows AS row
            MATCH (a:Account {id: row.from_account})
            MATCH (b:Account {id: row.to_account})
            CREATE (a)-[r:TRANSACTED_WITH]->(b)
            SET r = row
            """,
            rows=batch,
        )
    logger.info("Wrote %d :TRANSACTED_WITH edges", len(transactions))


def _write_communicated_with(session, communications: list[dict]) -> None:
    if not communications:
        return
    for batch in _chunks(communications):
        session.run(
            """
            UNWIND $rows AS row
            MATCH (a:Device {id: row.from_device})
            MATCH (b:Device {id: row.to_device})
            CREATE (a)-[r:COMMUNICATED_WITH]->(b)
            SET r = row
            """,
            rows=batch,
        )
    logger.info("Wrote %d :COMMUNICATED_WITH edges", len(communications))


def _write_attended(session, events: list[dict]) -> None:
    rows = [{"event_id": e["id"], "person_id": pid} for e in events for pid in e["participant_ids"]]
    if not rows:
        return
    for batch in _chunks(rows):
        session.run(
            """
            UNWIND $rows AS row
            MATCH (p:Person {id: row.person_id})
            MATCH (e:Event {id: row.event_id})
            CREATE (p)-[:ATTENDED]->(e)
            """,
            rows=batch,
        )
    logger.info("Wrote %d :ATTENDED edges", len(rows))


def _write_occurred_at(session, events: list[dict]) -> None:
    rows = [{"event_id": e["id"], "location_id": e["location_id"]} for e in events]
    if not rows:
        return
    for batch in _chunks(rows):
        session.run(
            """
            UNWIND $rows AS row
            MATCH (e:Event {id: row.event_id})
            MATCH (l:Location {id: row.location_id})
            CREATE (e)-[:OCCURRED_AT]->(l)
            """,
            rows=batch,
        )
    logger.info("Wrote %d :OCCURRED_AT edges", len(rows))


def _write_document_edges(session, documents: list[dict]) -> None:
    issued_to = [{"doc_id": d["id"], "subject_id": d["subject_id"]} for d in documents]
    for batch in _chunks(issued_to):
        session.run(
            """
            UNWIND $rows AS row
            MATCH (doc:Document {id: row.doc_id})
            MATCH (p:Person {id: row.subject_id})
            CREATE (doc)-[:ISSUED_TO]->(p)
            """,
            rows=batch,
        )

    for issuer_label in ("Person", "Organization"):
        subset = [
            {"doc_id": d["id"], "issuer_id": d["issuer_id"]}
            for d in documents
            if d["issuer_type"] == issuer_label and d["issuer_id"] is not None
        ]
        for batch in _chunks(subset):
            session.run(
                f"""
                UNWIND $rows AS row
                MATCH (doc:Document {{id: row.doc_id}})
                MATCH (issuer:{issuer_label} {{id: row.issuer_id}})
                CREATE (doc)-[:ISSUED_BY]->(issuer)
                """,
                rows=batch,
            )
    logger.info("Wrote ISSUED_TO / ISSUED_BY edges for %d documents", len(documents))


def _write_entity_reference_edges(session, from_label: str, rel_type: str, rows: list[dict], human_ids_field: str) -> None:
    """Resolves human-readable IDs (PRS-.../ORG-.../...) to node-backed edges,
    grouped by target label so each batch can MATCH a fixed label. IDs with
    no node-backed label (TXN-..., COM-...) are skipped — they remain
    visible as plain strings on the source node's own properties."""
    by_target_label: dict[str, list[dict]] = {}
    for row in rows:
        for human_id in row[human_ids_field]:
            prefix = human_id.split("-")[0]
            label = LABEL_BY_PREFIX.get(prefix)
            if label is None:
                continue
            by_target_label.setdefault(label, []).append({"from_id": row["id"], "target_human_id": human_id})

    id_field_by_label = {label: id_field for label, _world_key, id_field in NODE_SPECS}
    for label, edge_rows in by_target_label.items():
        id_field = id_field_by_label[label]
        for batch in _chunks(edge_rows):
            session.run(
                f"""
                UNWIND $rows AS row
                MATCH (a:{from_label} {{id: row.from_id}})
                MATCH (b:{label} {{{id_field}: row.target_human_id}})
                CREATE (a)-[:{rel_type}]->(b)
                """,
                rows=batch,
            )
        logger.info("Wrote %d :%s edges (%s -> %s)", len(edge_rows), rel_type, from_label, label)
