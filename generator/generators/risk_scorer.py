"""Stage 9: Risk Scoring.

Deterministic, rule-based, and fully explainable — every point on every
score traces to a specific fact (storyline membership, a flagged
transaction, a shared device...). This is the generator's *initial* score
and a one-hop propagation pass; the interactive, multi-hop Risk
Propagation algorithm analysts can trigger from any seed node (ARGUS_PLAN.md
Phase 9) is a separate, on-demand backend feature that runs live against
the full graph.
"""

import random

SEVERITY_POINTS = {"Critical": 40.0, "High": 28.0, "Medium": 16.0, "Low": 8.0}
PROPAGATION_FACTOR = 0.35  # fraction of a flagged neighbor's score that propagates one hop


def index_by_human_id(world: dict) -> dict[str, dict]:
    """Maps every human-readable ID (PRS-..., ORG-..., ACC-..., ...) to its node dict."""
    index: dict[str, dict] = {}
    id_fields = {
        "persons": "person_id",
        "orgs": "org_id",
        "accounts": "account_id",
        "devices": "device_id",
        "transactions": "tx_id",
        "communications": "comm_id",
        "documents": "doc_id",
        "shipments": "shipment_id",
        "events": "event_id",
    }
    for key, id_field in id_fields.items():
        for node in world.get(key, []):
            index[node[id_field]] = node
    return index


def score_world(rng: random.Random, world: dict, id_index: dict[str, dict]) -> None:
    """Mutates risk_score / risk_factors in place across every entity list."""
    _add_factor_lists(world)
    _score_storylines(world, id_index)
    _score_shell_orgs(world)
    _score_flagged_documents(world, id_index)
    _propagate_from_orgs_to_directors(world)
    _propagate_from_shared_devices(world)
    _add_baseline_noise(rng, world)
    _clamp_scores(world)


def _add_factor_lists(world: dict) -> None:
    for key in ("persons", "orgs"):
        for node in world.get(key, []):
            node.setdefault("risk_factors", [])


def _bump(node: dict, points: float, factor: str) -> None:
    node["risk_score"] = min(100.0, node.get("risk_score", 0.0) + points)
    if "risk_factors" in node and factor not in node["risk_factors"]:
        node["risk_factors"].append(factor)


def _score_storylines(world: dict, id_index: dict[str, dict]) -> None:
    for storyline in world.get("storylines", []):
        points = SEVERITY_POINTS[storyline["severity"]]
        factor = f"Linked to {storyline['type'].replace('_', ' ')} ({storyline['severity']})"
        for human_id in storyline["entity_ids"]:
            node = id_index.get(human_id)
            if node is not None:
                _bump(node, points, factor)


def _score_shell_orgs(world: dict) -> None:
    for org in world.get("orgs", []):
        if org["type"] == "Shell":
            _bump(org, 10.0, "Registered as a shell company")


def _score_flagged_documents(world: dict, id_index: dict[str, dict]) -> None:
    for doc in world.get("documents", []):
        if not doc.get("flagged"):
            continue
        subject = next(
            (p for p in world["persons"] if p["id"] == doc["subject_id"]),
            None,
        )
        if subject is not None:
            _bump(subject, 15.0, f"Subject of a flagged document ({doc['inconsistency_type']})")


def _propagate_from_orgs_to_directors(world: dict) -> None:
    orgs_by_id = {o["id"]: o for o in world["orgs"]}
    persons_by_id = {p["id"]: p for p in world["persons"]}

    for edge in world.get("directs_edges", []) + world.get("controls_edges", []):
        org = orgs_by_id.get(edge["org_id"])
        person = persons_by_id.get(edge["person_id"])
        if org is None or person is None or org["risk_score"] <= 0:
            continue
        propagated = org["risk_score"] * PROPAGATION_FACTOR * edge.get("confidence", 1.0)
        if propagated > 1.0:
            _bump(person, propagated, f"Connected to flagged organization {org['name']}")


def _propagate_from_shared_devices(world: dict) -> None:
    persons_by_id = {p["id"]: p for p in world["persons"]}
    for edge in world.get("shares_device_edges", []):
        a = persons_by_id.get(edge["person_a_id"])
        b = persons_by_id.get(edge["person_b_id"])
        if a is None or b is None:
            continue
        higher, lower = (a, b) if a["risk_score"] >= b["risk_score"] else (b, a)
        propagated = higher["risk_score"] * PROPAGATION_FACTOR
        if propagated > 1.0:
            _bump(lower, propagated, "Shares a device with a higher-risk individual")


def _add_baseline_noise(rng: random.Random, world: dict) -> None:
    """A little variance so scores aren't suspiciously round for untouched entities."""
    for key in ("persons", "orgs"):
        for node in world.get(key, []):
            if node["risk_score"] == 0.0:
                node["risk_score"] = round(rng.uniform(0, 6), 1)


def _clamp_scores(world: dict) -> None:
    for key in (
        "persons",
        "orgs",
        "accounts",
        "devices",
        "transactions",
        "communications",
        "documents",
        "shipments",
    ):
        for node in world.get(key, []):
            node["risk_score"] = round(min(100.0, max(0.0, node.get("risk_score", 0.0))), 1)
