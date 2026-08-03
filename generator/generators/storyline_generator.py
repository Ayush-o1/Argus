"""Stage 8: Storyline Injection.

Plants the deliberately-entangled entity clusters described in
ARGUS_PLAN.md Phase 4 ("The Synthetic Incidents"). Each storyline mutates
the already-generated world (flagging documents, adding transactions/
communications/edges) and produces one Incident record documenting what
was planted — this is ground truth, not detection. The independent
detection pass (Isolation Forest + z-score, ARGUS_PLAN.md Phase 10) is a
separate backend feature that rediscovers anomalous behavior from the
graph itself, without reading these labels.
"""

import random
from dataclasses import dataclass, field
from datetime import timedelta

from generators.common import new_id, new_uuid, random_datetime_between, WORLD_END, WORLD_START

SEVERITY_WEIGHTED = [("Low", 15), ("Medium", 35), ("High", 35), ("Critical", 15)]


@dataclass
class StorylineResult:
    storylines: list[dict] = field(default_factory=list)
    incidents: list[dict] = field(default_factory=list)
    extra_transactions: list[dict] = field(default_factory=list)
    extra_communications: list[dict] = field(default_factory=list)
    controls_edges: list[dict] = field(default_factory=list)
    shares_device_edges: list[dict] = field(default_factory=list)


def inject_storylines(rng: random.Random, world: dict, storyline_count: int) -> StorylineResult:
    result = StorylineResult()
    handlers = [
        _shell_company_ring,
        _money_routing_network,
        _communication_cluster,
        _supply_chain_divergence,
        _document_forgery_ring,
        _identity_overlap,
        _anomalous_transaction_burst,
    ]

    for i in range(storyline_count):
        handler = handlers[i % len(handlers)]
        handler(rng, world, result, i + 1)

    return result


def _severity(rng: random.Random) -> str:
    levels, weights = zip(*SEVERITY_WEIGHTED)
    return rng.choices(levels, weights=weights, k=1)[0]


def _make_storyline(
    rng: random.Random, storyline_type: str, index: int, severity: str, entity_ids: list[str], description: str
) -> dict:
    return {
        "id": new_uuid(),
        "storyline_id": new_id("STL", index),
        "type": storyline_type,
        "severity": severity,
        "discovery_difficulty": round(rng.uniform(0.15, 0.9), 2),
        "entity_ids": entity_ids,
        "description": description,
    }


def _make_incident(rng: random.Random, storyline: dict, index: int, incident_type: str) -> dict:
    return {
        "id": new_uuid(),
        "incident_id": new_id("INC", index),
        "type": incident_type,
        "severity": storyline["severity"],
        "timestamp": random_datetime_between(rng, WORLD_START, WORLD_END).isoformat(),
        "involved_entity_ids": storyline["entity_ids"],
        "description": storyline["description"],
        "status": "Open",
        "storyline_id": storyline["storyline_id"],
    }


def _shell_company_ring(rng: random.Random, world: dict, result: StorylineResult, index: int) -> None:
    orgs = [o for o in world["orgs"] if o["type"] in ("Shell", "Corporation")]
    persons = world["persons"]
    if len(orgs) < 3 or not persons:
        return

    ring_orgs = rng.sample(orgs, k=min(rng.randint(3, 8), len(orgs)))
    controllers = rng.sample(persons, k=min(rng.randint(1, 3), len(persons)))

    for org in ring_orgs:
        org["type"] = "Shell"
        org["risk_score"] = max(org["risk_score"], 55.0)

    for controller in controllers:
        for org in ring_orgs:
            result.controls_edges.append(
                {
                    "person_id": controller["id"],
                    "org_id": org["id"],
                    "confidence": round(rng.uniform(0.6, 0.95), 2),
                }
            )

    # Circular transactions between the ring's accounts, if any exist.
    accounts_by_org = {a["owner_id"]: a for a in world["accounts"] if a["owner_type"] == "Organization"}
    ring_accounts = [accounts_by_org[o["id"]] for o in ring_orgs if o["id"] in accounts_by_org]
    tx_ids = _inject_circular_transactions(rng, ring_accounts, world["tx_counter"], result, index)

    entity_ids = [o["org_id"] for o in ring_orgs] + [p["person_id"] for p in controllers]
    severity = _severity(rng)
    storyline = _make_storyline(
        rng,
        "shell_company_ring",
        index,
        severity,
        entity_ids,
        f"{len(ring_orgs)} organizations linked through {len(controllers)} shared controller(s) "
        f"and circular transaction routing.",
    )
    storyline["entity_ids"] += tx_ids
    result.storylines.append(storyline)
    result.incidents.append(_make_incident(rng, storyline, index, "FinancialCrime"))


def _money_routing_network(rng: random.Random, world: dict, result: StorylineResult, index: int) -> None:
    accounts = world["accounts"]
    if len(accounts) < 4:
        return

    chain_len = min(rng.randint(4, 7), len(accounts))
    chain = rng.sample(accounts, k=chain_len)
    amount = rng.uniform(200_000, 2_000_000)
    start = random_datetime_between(rng, WORLD_START, WORLD_END)

    tx_ids: list[str] = []
    for hop, (src, dst) in enumerate(zip(chain, chain[1:] + chain[:1])):
        world["tx_counter"][0] += 1
        hop_amount = round(amount * rng.uniform(0.92, 0.99), 2)  # a cut taken at each hop
        tx_id = new_id("TXN", world["tx_counter"][0])
        tx_ids.append(tx_id)
        result.extra_transactions.append(
            {
                "id": new_uuid(),
                "tx_id": tx_id,
                "from_account": src["id"],
                "to_account": dst["id"],
                "amount": hop_amount,
                "currency": "INR",
                "type": "Wire",
                "timestamp": (start + timedelta(hours=hop * rng.uniform(1, 6))).isoformat(),
                "description": "Fund transfer",
                "flagged": True,
                "risk_score": 70.0,
                "storyline_id": new_id("STL", index),
            }
        )
        amount = hop_amount

    severity = _severity(rng)
    storyline = _make_storyline(
        rng,
        "money_routing_network",
        index,
        severity,
        [a["account_id"] for a in chain] + tx_ids,
        f"Funds routed through a {chain_len}-account chain across multiple banks, "
        f"each hop retaining a small cut — a classic layering pattern.",
    )
    result.storylines.append(storyline)
    result.incidents.append(_make_incident(rng, storyline, index, "FinancialCrime"))


def _communication_cluster(rng: random.Random, world: dict, result: StorylineResult, index: int) -> None:
    devices_by_owner: dict[str, list[str]] = {}
    for d in world["devices"]:
        devices_by_owner.setdefault(d["owner_id"], []).append(d["id"])

    eligible_persons = [p for p in world["persons"] if p["id"] in devices_by_owner]
    if len(eligible_persons) < 5:
        return

    cluster = rng.sample(eligible_persons, k=min(rng.randint(5, 10), len(eligible_persons)))
    start = random_datetime_between(rng, WORLD_START, WORLD_END)
    comm_ids: list[str] = []

    for _ in range(rng.randint(30, 80)):
        a, b = rng.sample(cluster, k=2)
        world["comm_counter"][0] += 1
        comm_id = new_id("COM", world["comm_counter"][0])
        comm_ids.append(comm_id)
        result.extra_communications.append(
            {
                "id": new_uuid(),
                "comm_id": comm_id,
                "from_device": rng.choice(devices_by_owner[a["id"]]),
                "to_device": rng.choice(devices_by_owner[b["id"]]),
                "type": rng.choice(["Call", "Encrypted", "SMS"]),
                "timestamp": (start + timedelta(minutes=rng.uniform(0, 60 * 48))).isoformat(),
                "duration_seconds": rng.randint(30, 900),
                "flagged": True,
                "storyline_id": new_id("STL", index),
            }
        )

    severity = _severity(rng)
    storyline = _make_storyline(
        rng,
        "communication_cluster",
        index,
        severity,
        [p["person_id"] for p in cluster] + comm_ids,
        f"{len(cluster)} individuals with an unusually dense communication pattern "
        f"over a 48-hour window.",
    )
    result.storylines.append(storyline)
    result.incidents.append(_make_incident(rng, storyline, index, "CommunicationAnomaly"))


def _supply_chain_divergence(rng: random.Random, world: dict, result: StorylineResult, index: int) -> None:
    anomalous = [s for s in world["shipments"] if s["route_anomaly"]]
    if not anomalous:
        return

    group = rng.sample(anomalous, k=min(rng.randint(1, 4), len(anomalous)))
    storyline_id = new_id("STL", index)
    for shipment in group:
        shipment["risk_score"] = max(shipment["risk_score"], 60.0)

    severity = _severity(rng)
    storyline = _make_storyline(
        rng,
        "supply_chain_divergence",
        index,
        severity,
        [s["shipment_id"] for s in group],
        f"{len(group)} shipment(s) whose logged route diverges from the manifested itinerary.",
    )
    result.storylines.append(storyline)
    result.incidents.append(_make_incident(rng, storyline, index, "Trafficking"))


def _document_forgery_ring(rng: random.Random, world: dict, result: StorylineResult, index: int) -> None:
    documents = world["documents"]
    if len(documents) < 3:
        return

    group = rng.sample(documents, k=min(rng.randint(3, 6), len(documents)))
    inconsistency_types = ["issuer_subject_mismatch", "duplicate_serial", "backdated_issue"]

    for doc in group:
        doc["flagged"] = True
        doc["inconsistency_type"] = rng.choice(inconsistency_types)
        doc["storyline_id"] = new_id("STL", index)

    severity = _severity(rng)
    storyline = _make_storyline(
        rng,
        "document_forgery_ring",
        index,
        severity,
        [d["doc_id"] for d in group],
        f"{len(group)} document(s) with issuer/subject inconsistencies suggesting coordinated forgery.",
    )
    result.storylines.append(storyline)
    result.incidents.append(_make_incident(rng, storyline, index, "DocumentForgery"))


def _identity_overlap(rng: random.Random, world: dict, result: StorylineResult, index: int) -> None:
    devices = world["devices"]
    persons = world["persons"]
    if not devices or len(persons) < 2:
        return

    device = rng.choice(devices)
    others = [p for p in persons if p["id"] != device["owner_id"]]
    sharers = rng.sample(others, k=min(rng.randint(1, 2), len(others)))
    owner_person = next((p for p in persons if p["id"] == device["owner_id"]), None)
    if owner_person is None:
        return

    for sharer in sharers:
        result.shares_device_edges.append(
            {
                "person_a_id": owner_person["id"],
                "person_b_id": sharer["id"],
                "device_id": device["device_id"],
                "period": f"{WORLD_START.date().isoformat()}..{WORLD_END.date().isoformat()}",
            }
        )

    severity = _severity(rng)
    storyline = _make_storyline(
        rng,
        "identity_overlap",
        index,
        severity,
        [owner_person["person_id"]] + [s["person_id"] for s in sharers] + [device["device_id"]],
        f"{len(sharers)} additional individual(s) sharing a device with its registered owner.",
    )
    result.storylines.append(storyline)
    result.incidents.append(_make_incident(rng, storyline, index, "CommunicationAnomaly"))


def _anomalous_transaction_burst(rng: random.Random, world: dict, result: StorylineResult, index: int) -> None:
    accounts = world["accounts"]
    if len(accounts) < 2:
        return

    target = rng.choice(accounts)
    other_accounts = [a for a in accounts if a["id"] != target["id"]]
    if not other_accounts:
        return

    base_by_class = {"Low": 5_000, "Medium": 25_000, "High": 150_000, "Extreme": 800_000}
    base = base_by_class.get(target["balance_class"], 10_000)
    burst_start = random_datetime_between(rng, WORLD_START, WORLD_END)
    num_tx = rng.randint(15, 50)
    tx_ids: list[str] = []

    for _ in range(num_tx):
        world["tx_counter"][0] += 1
        tx_id = new_id("TXN", world["tx_counter"][0])
        tx_ids.append(tx_id)
        result.extra_transactions.append(
            {
                "id": new_uuid(),
                "tx_id": tx_id,
                "from_account": target["id"],
                "to_account": rng.choice(other_accounts)["id"],
                "amount": round(base * rng.uniform(3, 8), 2),
                "currency": "INR",
                "type": rng.choice(["Wire", "Crypto"]),
                "timestamp": (burst_start + timedelta(minutes=rng.uniform(0, 360))).isoformat(),
                "description": "Transfer",
                "flagged": True,
                "risk_score": 80.0,
                "storyline_id": new_id("STL", index),
            }
        )

    severity = _severity(rng)
    storyline = _make_storyline(
        rng,
        "anomalous_transaction_burst",
        index,
        severity,
        [target["account_id"]] + tx_ids,
        f"{num_tx} transactions in a 6-hour window on account {target['account_id']}, "
        f"several times its typical velocity.",
    )
    result.storylines.append(storyline)
    result.incidents.append(_make_incident(rng, storyline, index, "FinancialCrime"))


def _inject_circular_transactions(
    rng: random.Random, accounts: list[dict], tx_counter: list, result: StorylineResult, index: int
) -> list[str]:
    """A -> B -> C -> ... -> A, each hop retaining a small cut. Classic laundering shape."""
    if len(accounts) < 3:
        return []

    amount = rng.uniform(300_000, 1_500_000)
    start = random_datetime_between(rng, WORLD_START, WORLD_END)
    tx_ids: list[str] = []

    for hop, (src, dst) in enumerate(zip(accounts, accounts[1:] + accounts[:1])):
        tx_counter[0] += 1
        tx_id = new_id("TXN", tx_counter[0])
        tx_ids.append(tx_id)
        hop_amount = round(amount * rng.uniform(0.9, 0.98), 2)
        result.extra_transactions.append(
            {
                "id": new_uuid(),
                "tx_id": tx_id,
                "from_account": src["id"],
                "to_account": dst["id"],
                "amount": hop_amount,
                "currency": "INR",
                "type": "Wire",
                "timestamp": (start + timedelta(hours=hop * rng.uniform(2, 10))).isoformat(),
                "description": "Inter-company settlement",
                "flagged": True,
                "risk_score": 75.0,
                "storyline_id": new_id("STL", index),
            }
        )
        amount = hop_amount

    return tx_ids
