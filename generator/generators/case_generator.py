"""Seeds a handful of Cases from the generated storylines, so /cases has real
data to show before an analyst manually opens one. See ARGUS_PLAN.md Phase 7.
"""

import random
from datetime import timedelta

from generators.common import new_id, new_uuid, random_datetime_between, WORLD_END, WORLD_START

ANALYSTS = ["A. Krishnan", "M. Deshpande", "R. Fernandes", "S. Bhattacharya", "N. Iyer"]

CASE_TITLES_BY_TYPE = {
    "shell_company_ring": "Operation Shell Trace",
    "money_routing_network": "Operation Layered Transfer",
    "communication_cluster": "Operation Silent Wire",
    "supply_chain_divergence": "Operation Diverted Cargo",
    "document_forgery_ring": "Operation Forged Seal",
    "identity_overlap": "Operation Mirror Identity",
    "anomalous_transaction_burst": "Operation Sudden Spike",
}

STATUS_WEIGHTED = [("Open", 45), ("UnderReview", 30), ("Closed", 20), ("Draft", 5)]
PRIORITY_BY_SEVERITY = {"Critical": "Critical", "High": "High", "Medium": "Medium", "Low": "Low"}


def generate_seed_cases(rng: random.Random, storylines: list[dict], target_count: int) -> list[dict]:
    if not storylines:
        return []

    chosen = rng.sample(storylines, k=min(target_count, len(storylines)))
    statuses, status_weights = zip(*STATUS_WEIGHTED)
    cases: list[dict] = []

    for i, storyline in enumerate(chosen, start=1):
        opened = random_datetime_between(rng, WORLD_START, WORLD_END)
        status = rng.choices(statuses, weights=status_weights, k=1)[0]
        closed = opened + timedelta(days=rng.randint(3, 40)) if status == "Closed" else None

        cases.append(
            {
                "id": new_uuid(),
                "case_id": new_id("CASE", i),
                "title": f"{CASE_TITLES_BY_TYPE.get(storyline['type'], 'Operation Untitled')} — {storyline['storyline_id']}",
                "status": status,
                "priority": PRIORITY_BY_SEVERITY[storyline["severity"]],
                "assigned_analyst": rng.choice(ANALYSTS),
                "opened_at": opened.isoformat(),
                "closed_at": closed.isoformat() if closed else None,
                "linked_entity_human_ids": storyline["entity_ids"],
                "notes": f"Auto-seeded from storyline {storyline['storyline_id']} ({storyline['type']}): "
                f"{storyline['description']}",
                "storyline_id": storyline["storyline_id"],
            }
        )

    return cases
