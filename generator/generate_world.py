#!/usr/bin/env python3
"""ARGUS synthetic world generator — main entry point.

Deterministic: the same --seed always produces the same world. See
ARGUS_PLAN.md Phase 8 for the full pipeline design and Phase 4 for the
world this produces (real Indian geography, entirely synthetic subjects).

Usage:
    python generate_world.py --seed 42          # refuses if the graph is populated
    python generate_world.py --seed 42 --wipe  # destructive: replaces the graph
"""

import argparse
import getpass
import logging
import os
import random
import time

from faker import Faker
from neo4j import GraphDatabase

from config import GeneratorConfig
from generators.account_generator import generate_accounts
from generators.case_generator import generate_seed_cases
from generators.common import seed_locale_fakers
from generators.communication_generator import generate_communications
from generators.device_generator import generate_devices
from generators.document_generator import generate_documents
from generators.event_generator import generate_events
from generators.neo4j_writer import write_world
from generators.organization_generator import generate_organizations
from generators.person_generator import generate_persons
from generators.relationship_generator import assign_directors, assign_employment
from generators.risk_scorer import index_by_human_id, score_world
from generators.shipment_generator import generate_shipments
from generators.storyline_generator import inject_storylines
from generators.transaction_generator import generate_baseline_transactions
from generators.vehicle_generator import generate_vehicles
from generators.world_generator import generate_locations

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("argus.generator")


def parse_args() -> GeneratorConfig:
    parser = argparse.ArgumentParser(description="Generate the ARGUS synthetic world.")
    parser.add_argument("--seed", type=int, default=42)
    # Credentials come from the environment rather than argv, which /proc and
    # `ps` expose to every local user (audit B-08).
    parser.add_argument("--neo4j-uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--neo4j-user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument(
        "--wipe",
        action="store_true",
        help="Delete the entire existing graph before writing. Destroys analyst-created cases.",
    )
    args = parser.parse_args()

    password = os.environ.get("NEO4J_PASSWORD") or getpass.getpass("Neo4j password: ")

    return GeneratorConfig(
        seed=args.seed,
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=password,
        wipe_existing=args.wipe,
    )


def step(label: str):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            start = time.time()
            result = fn(*args, **kwargs)
            logger.info("  ✓ %s (%.2fs)", label, time.time() - start)
            return result

        return wrapper

    return decorator


def build_world(cfg: GeneratorConfig) -> dict:
    rng = random.Random(cfg.seed)
    # Kept as the default/fallback Faker; per-region locales are resolved inside
    # the generators via `common.faker_for_region` so names match their place.
    faker = Faker("en_IN")
    faker.seed_instance(cfg.seed)
    seed_locale_fakers(cfg.seed)
    scale = cfg.scale

    logger.info("ARGUS world generation — seed %d", cfg.seed)
    logger.info("")

    logger.info("STAGE 1: World Foundation")
    locations = step("Locations")(generate_locations)(rng, scale.location_count)

    logger.info("STAGE 2: Organizations")
    orgs = step("Organizations")(generate_organizations)(rng, scale.org_count)

    logger.info("STAGE 3: Persons, directors, accounts, devices, vehicles")
    persons = step("Persons")(generate_persons)(rng, faker, scale.person_count)
    directs_edges = step("Director assignments")(assign_directors)(rng, persons, orgs)
    employment_edges = step("Employment assignments")(assign_employment)(rng, persons, orgs)
    accounts = step("Accounts")(generate_accounts)(rng, persons, orgs, scale.account_count)
    devices = step("Devices")(generate_devices)(rng, persons, scale.device_count)
    vehicles = step("Vehicles")(generate_vehicles)(rng, persons, orgs, scale.vehicle_count)

    logger.info("STAGE 4: Baseline transactions")
    transactions = step("Transactions")(generate_baseline_transactions)(rng, accounts, scale.transaction_count)

    logger.info("STAGE 5: Communications")
    communications = step("Communications")(generate_communications)(rng, persons, devices, scale.communication_count)

    logger.info("STAGE 6: Events and documents")
    events = step("Events")(generate_events)(rng, persons, locations, scale.event_count)
    documents = step("Documents")(generate_documents)(rng, persons, orgs, scale.document_count)

    logger.info("STAGE 7: Shipments")
    shipments = step("Shipments")(generate_shipments)(rng, locations, scale.shipment_count)

    world = {
        "persons": persons,
        "orgs": orgs,
        "locations": locations,
        "vehicles": vehicles,
        "devices": devices,
        "accounts": accounts,
        "transactions": transactions,
        "communications": communications,
        "events": events,
        "documents": documents,
        "shipments": shipments,
        "directs_edges": directs_edges,
        "employment_edges": employment_edges,
        "tx_counter": [len(transactions)],
        "comm_counter": [len(communications)],
    }

    logger.info("STAGE 8: Storyline injection")
    storyline_result = step("Storylines")(inject_storylines)(rng, world, scale.storyline_count)
    world["storylines"] = storyline_result.storylines
    world["incidents"] = storyline_result.incidents
    world["controls_edges"] = storyline_result.controls_edges
    world["shares_device_edges"] = storyline_result.shares_device_edges
    world["transactions"] = world["transactions"] + storyline_result.extra_transactions
    world["communications"] = world["communications"] + storyline_result.extra_communications

    logger.info("STAGE 9: Risk scoring")
    id_index = index_by_human_id(world)
    step("Risk scores")(score_world)(rng, world, id_index)
    for person in world["persons"]:
        if person["risk_score"] >= 80 and "flagged" not in person["flags"]:
            person["flags"].append("flagged")

    logger.info("STAGE 10: Seed cases")
    world["cases"] = step("Cases")(generate_seed_cases)(rng, world["storylines"], scale.storyline_count)

    return world


def print_summary(world: dict) -> None:
    logger.info("")
    logger.info("World summary:")
    for key in (
        "persons", "orgs", "locations", "vehicles", "devices", "accounts",
        "transactions", "communications", "events", "documents", "shipments",
        "storylines", "incidents", "cases",
    ):
        logger.info("  %-16s %d", key, len(world.get(key, [])))
    logger.info("  %-16s %d", "directs_edges", len(world["directs_edges"]))
    logger.info("  %-16s %d", "employment_edges", len(world["employment_edges"]))
    logger.info("  %-16s %d", "controls_edges", len(world["controls_edges"]))
    logger.info("  %-16s %d", "shares_device_edges", len(world["shares_device_edges"]))


def _guard_existing_graph(driver, wipe_requested: bool) -> None:
    """Refuse to write into a populated graph unless --wipe was passed explicitly.

    Wiping used to be the default, so the documented command for populating a
    world also silently deleted every analyst-created Case, with no confirmation
    and no backup (audit B-24). Inverting the default alone would trade that for
    a wall of uniqueness-constraint violations on the second run, so this states
    the situation and the two ways out instead.
    """
    with driver.session() as session:
        record = session.run("MATCH (n) RETURN count(n) AS total").single()
        existing = record["total"] if record else 0

    if existing == 0 or wipe_requested:
        return

    analyst_cases = 0
    with driver.session() as session:
        record = session.run(
            "MATCH (c:Case) WHERE c.storyline_id IS NULL RETURN count(c) AS total"
        ).single()
        analyst_cases = record["total"] if record else 0

    raise SystemExit(
        f"\nRefusing to write: the graph already contains {existing:,} nodes"
        + (f", including {analyst_cases} analyst-created case(s)" if analyst_cases else "")
        + ".\n\n"
        "  To replace it entirely (destructive, and it will delete those cases):\n"
        "      python3 generate_world.py --seed 42 --wipe\n\n"
        "  To add a storyline to the existing world instead (non-destructive):\n"
        "      python3 generate_scenario.py --type shell_company_ring\n\n"
        "  Back up first with:\n"
        "      docker compose stop neo4j && docker run --rm \\\n"
        "        -v argus_neo4j_data:/data -v \"$PWD/backups\":/backups neo4j:5-community \\\n"
        "        neo4j-admin database dump neo4j --to-path=/backups\n"
    )


def main() -> None:
    cfg = parse_args()

    # Connect and check *before* spending ~15s generating a world we may refuse
    # to write.
    driver = GraphDatabase.driver(cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password))
    try:
        driver.verify_connectivity()
        _guard_existing_graph(driver, cfg.wipe_existing)
    except Exception:
        driver.close()
        raise

    world = build_world(cfg)
    print_summary(world)

    logger.info("")
    logger.info("STAGE 11: Writing to Neo4j (%s)", cfg.neo4j_uri)
    try:
        start = time.time()
        if cfg.wipe_existing:
            logger.warning("  --wipe given: deleting the existing graph before writing")
        write_world(driver, world, wipe_existing=cfg.wipe_existing)
        logger.info("  ✓ Write complete (%.2fs)", time.time() - start)
    finally:
        driver.close()

    logger.info("")
    logger.info("Done. Open Neo4j Browser at http://localhost:7474 to explore the world.")


if __name__ == "__main__":
    main()
