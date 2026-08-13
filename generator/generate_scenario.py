#!/usr/bin/env python3
"""ARGUS on-demand scenario generator (ARGUS_PLAN.md Phase 9).

Additively injects one new, self-contained storyline into the *live*
graph, reusing the exact same entity generators and storyline-injection
logic as the full world generator (generate_world.py) — this is "make the
invisible visible": the demo runs the real generation engine, not a fake
progress bar. New organizations/accounts/devices/documents/shipments are
created; existing low-risk Persons are reused as participants (fetched
from the live graph, matched by uuid, never re-created) so nothing
collides with or duplicates the 75K-node baseline world.

Usage:
    python generate_scenario.py --type shell_company_ring --complexity Medium --seed 42

Prints one `STAGE: ...` line per step (consumed by the backend as live
progress) and a final `RESULT_JSON: {...}` line with the scenario summary.
"""

import argparse
import json
import random
import sys

from faker import Faker
from neo4j import GraphDatabase

from generators.account_generator import generate_accounts
from generators.case_generator import generate_seed_cases
from generators.common import seed_locale_fakers
from generators.device_generator import generate_devices
from generators.document_generator import generate_documents
from generators.neo4j_writer import write_scenario
from generators.organization_generator import generate_organizations
from generators.risk_scorer import index_by_human_id, score_world
from generators.shipment_generator import ANOMALY_RISK, MANIFEST_GOODS, generate_shipments
from generators.storyline_generator import (
    StorylineResult,
    _communication_cluster,
    _document_forgery_ring,
    _identity_overlap,
    _money_routing_network,
    _shell_company_ring,
    _supply_chain_divergence,
)

HANDLERS = {
    "shell_company_ring": _shell_company_ring,
    "money_routing_network": _money_routing_network,
    "communication_cluster": _communication_cluster,
    "supply_chain_divergence": _supply_chain_divergence,
    "document_forgery_ring": _document_forgery_ring,
    "identity_overlap": _identity_overlap,
}

COMPLEXITY_SCALE = {
    "Low": {"orgs": 3, "persons": 6, "shipments": 4},
    "Medium": {"orgs": 6, "persons": 12, "shipments": 8},
    "High": {"orgs": 10, "persons": 20, "shipments": 14},
}

ID_PREFIX_BY_LABEL = {
    "ORG": ("Organization", "org_id"),
    "ACC": ("Account", "account_id"),
    "DEV": ("Device", "device_id"),
    "DOC": ("Document", "doc_id"),
    "SHP": ("Shipment", "shipment_id"),
    "TXN": (None, None),  # edge, not a node
    "COM": (None, None),  # edge, not a node
    "STL": ("Storyline", "storyline_id"),
    "CASE": ("Case", "case_id"),
}


def log_stage(message: str) -> None:
    print(f"STAGE: {message}", flush=True)


def _max_suffix(session, label: str, id_field: str) -> int:
    result = session.run(f"MATCH (n:{label}) RETURN max(n.{id_field}) AS max_id")
    record = result.single()
    max_id = record["max_id"] if record else None
    return int(max_id.split("-")[-1]) if max_id else 0


def _fetch_offsets(session) -> dict[str, int]:
    offsets = {}
    for prefix, (label, id_field) in ID_PREFIX_BY_LABEL.items():
        if label is None:
            # TXN/COM have no node label; use the highest existing tx/comm id
            # via a relationship property scan instead.
            rel_type = "TRANSACTED_WITH" if prefix == "TXN" else "COMMUNICATED_WITH"
            prop = "tx_id" if prefix == "TXN" else "comm_id"
            result = session.run(f"MATCH ()-[r:{rel_type}]->() RETURN max(r.{prop}) AS max_id")
            record = result.single()
            max_id = record["max_id"] if record else None
            offsets[prefix] = int(max_id.split("-")[-1]) if max_id else 0
        else:
            offsets[prefix] = _max_suffix(session, label, id_field)
    return offsets


def _fetch_existing_persons(session, count: int) -> list[dict]:
    result = session.run(
        """
        MATCH (p:Person) WHERE p.risk_score < 40
        RETURN p.id AS id, p.person_id AS person_id, p.name AS name, p.risk_score AS risk_score
        ORDER BY rand() LIMIT $count
        """,
        count=count,
    )
    return [dict(record) for record in result]


def _fetch_existing_locations(session) -> list[dict]:
    # lat/lng/region are required by the shipment generator's trade-lane model,
    # which routes between regions and measures detours geometrically.
    result = session.run(
        """
        MATCH (l:Location)
        RETURN l.id AS id, l.type AS type, l.lat AS lat, l.lng AS lng,
               l.region AS region, l.city AS city, l.country AS country
        """
    )
    return [dict(record) for record in result]


def build_scenario(scenario_type: str, complexity: str, seed: int, driver) -> dict:
    rng = random.Random(seed)
    Faker("en_IN").seed_instance(seed)
    seed_locale_fakers(seed)
    scale = COMPLEXITY_SCALE[complexity]

    with driver.session() as session:
        offsets = _fetch_offsets(session)
        persons = _fetch_existing_persons(session, scale["persons"])
        locations = _fetch_existing_locations(session) if scenario_type == "supply_chain_divergence" else []

    if len(persons) < 2:
        raise RuntimeError("Not enough existing low-risk persons in the graph to build this scenario.")
    log_stage(f"Selected {len(persons)} existing persons")

    world: dict = {
        "persons": persons,
        "orgs": [],
        "devices": [],
        "accounts": [],
        "documents": [],
        "shipments": [],
        "directs_edges": [],
        "controls_edges": [],
        "shares_device_edges": [],
        "tx_counter": [offsets["TXN"]],
        "comm_counter": [offsets["COM"]],
    }

    if scenario_type == "shell_company_ring":
        world["orgs"] = generate_organizations(rng, scale["orgs"], id_offset=offsets["ORG"])
        # _shell_company_ring only draws from Shell/Corporation-typed orgs;
        # with a small on-demand batch the natural type distribution isn't
        # guaranteed to produce 3+, so force it for this scenario's own orgs.
        for org in world["orgs"]:
            org["type"] = rng.choice(["Corporation", "Shell"])
        log_stage(f"Organizations created ({len(world['orgs'])})")
        # target_count set to the per-owner max (3) * owner count so every org
        # is guaranteed at least one account — see account_generator's
        # owner-by-owner loop, which only stops early once target_count is hit.
        world["accounts"] = generate_accounts(
            rng, [], world["orgs"], len(world["orgs"]) * 3, id_offset=offsets["ACC"]
        )
        log_stage(f"Accounts created ({len(world['accounts'])})")

    if scenario_type == "money_routing_network":
        world["accounts"] = generate_accounts(rng, persons, [], max(len(persons), 4), id_offset=offsets["ACC"])
        log_stage(f"Accounts created ({len(world['accounts'])})")

    if scenario_type in ("communication_cluster", "identity_overlap"):
        world["devices"] = generate_devices(rng, persons, len(persons) * 2, id_offset=offsets["DEV"])
        log_stage(f"Devices created ({len(world['devices'])})")

    if scenario_type == "document_forgery_ring":
        world["documents"] = generate_documents(rng, persons, [], max(6, len(persons)), id_offset=offsets["DOC"])
        log_stage(f"Documents forged ({len(world['documents'])})")

    if scenario_type == "supply_chain_divergence":
        if len(locations) < 2:
            raise RuntimeError("Not enough existing locations in the graph to build this scenario.")
        world["shipments"] = generate_shipments(rng, locations, scale["shipments"], id_offset=offsets["SHP"])
        # Force a couple of the storyline's shipments to diverge. anomaly_kind
        # has to be set alongside route_anomaly: the map explains *why* a route
        # was flagged by looking that field up, so flipping the boolean alone
        # produced flagged arcs that could offer no reasoning for the flag.
        for shipment in rng.sample(world["shipments"], k=min(2, len(world["shipments"]))):
            shipment["route_anomaly"] = True
            shipment["anomaly_kind"] = "manifest_shift"
            shipment["declared_manifest"] = [
                good for good in MANIFEST_GOODS if good not in shipment["manifest"]
            ][: len(shipment["manifest"])]
            shipment["risk_score"] = ANOMALY_RISK["manifest_shift"]
        log_stage(f"Shipments created ({len(world['shipments'])})")

    log_stage("Building graph relationships...")
    result = StorylineResult()
    HANDLERS[scenario_type](rng, world, result, offsets["STL"] + 1)

    if not result.storylines:
        raise RuntimeError("Could not construct this storyline from the current graph state — try a different type.")

    world["storylines"] = result.storylines
    world["incidents"] = result.incidents
    world["transactions"] = result.extra_transactions
    world["communications"] = result.extra_communications

    id_index = index_by_human_id(world)
    score_world(rng, world, id_index)

    world["cases"] = generate_seed_cases(rng, result.storylines, 1, id_offset=offsets["CASE"])

    log_stage("Writing to graph...")
    write_scenario(driver, world)

    storyline = result.storylines[0]
    key_entity_human_id = storyline["entity_ids"][0]
    key_entity = id_index.get(key_entity_human_id, {})

    return {
        "storyline_id": storyline["storyline_id"],
        "type": storyline["type"],
        "severity": storyline["severity"],
        "description": storyline["description"],
        "case_id": world["cases"][0]["case_id"] if world["cases"] else None,
        "key_entity_id": key_entity.get("person_id") or key_entity.get("org_id") or key_entity_human_id,
        "key_entity_name": key_entity.get("name", key_entity_human_id),
        "node_counts": {
            "organizations": len(world["orgs"]),
            "accounts": len(world["accounts"]),
            "devices": len(world["devices"]),
            "documents": len(world["documents"]),
            "shipments": len(world["shipments"]),
            "transactions": len(world["transactions"]),
            "communications": len(world["communications"]),
        },
        "seed": seed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one on-demand ARGUS scenario into the live graph.")
    parser.add_argument("--type", required=True, choices=list(HANDLERS))
    parser.add_argument("--complexity", default="Medium", choices=list(COMPLEXITY_SCALE))
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="argus_dev_password")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else random.randint(1, 1_000_000)

    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password))
    try:
        driver.verify_connectivity()
        summary = build_scenario(args.type, args.complexity, seed, driver)
        print("RESULT_JSON: " + json.dumps(summary))
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a job error, not a crash
        print("RESULT_JSON: " + json.dumps({"error": str(exc)}))
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
