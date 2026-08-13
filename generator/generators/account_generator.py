"""Stage 3 (cont'd): Bank accounts, owned by persons and organizations.

Not every person or organization has a tracked account — same as the real
world, and as ARGUS_PLAN.md Phase 4's counts imply (fewer accounts than
persons). Owners are drawn in shuffled order and given 1-4 (person) or 1-3
(org) accounts until the target count is reached.
"""

import random
from datetime import date, timedelta

from config import SYNTHETIC_BANKS, SYNTHETIC_BANKS_BY_REGION
from generators.common import new_id, new_uuid

ACCOUNT_TYPE_WEIGHTED_PERSON = [("Checking", 55), ("Savings", 35), ("Crypto", 10)]
ACCOUNT_TYPE_WEIGHTED_ORG = [("Corporate", 70), ("Shell", 15), ("Escrow", 15)]
BALANCE_CLASS_WEIGHTED = [("Low", 40), ("Medium", 35), ("High", 20), ("Extreme", 5)]


def generate_accounts(
    rng: random.Random, persons: list[dict], orgs: list[dict], target_count: int, id_offset: int = 0
) -> list[dict]:
    accounts: list[dict] = []
    counter = id_offset

    owners = [(p["id"], "Person", p.get("region")) for p in persons] + [
        (o["id"], "Organization", o.get("region")) for o in orgs
    ]
    rng.shuffle(owners)

    types_cls, type_w_cls = zip(*BALANCE_CLASS_WEIGHTED)

    for owner_uuid, owner_type, owner_region in owners:
        if len(accounts) >= target_count:
            break
        num_accounts = rng.randint(1, 4) if owner_type == "Person" else rng.randint(1, 3)
        type_pool = ACCOUNT_TYPE_WEIGHTED_PERSON if owner_type == "Person" else ACCOUNT_TYPE_WEIGHTED_ORG
        types, type_weights = zip(*type_pool)

        for _ in range(num_accounts):
            if len(accounts) >= target_count:
                break
            counter += 1
            opened = date.today() - timedelta(days=rng.randint(60, 365 * 15))
            bank, offshore = _pick_bank(rng, owner_region)
            accounts.append(
                {
                    "id": new_uuid(),
                    "account_id": new_id("ACC", counter),
                    "bank": bank,
                    "offshore": offshore,
                    "type": rng.choices(types, weights=type_weights, k=1)[0],
                    "balance_class": rng.choices(types_cls, weights=type_w_cls, k=1)[0],
                    "status": "Active",
                    "owner_id": owner_uuid,
                    "owner_type": owner_type,
                    "opened_date": opened.isoformat(),
                    "risk_score": 0.0,
                }
            )

    return accounts


# Most account holders bank where they live. The minority who don't are exactly
# what a cross-border investigation looks for, so the deviation is recorded as a
# queryable property rather than being lost in an otherwise-uniform bank pool.
OFFSHORE_ACCOUNT_RATE = 0.14


def _pick_bank(rng: random.Random, owner_region: str | None) -> tuple[str, bool]:
    local_pool = SYNTHETIC_BANKS_BY_REGION.get(owner_region or "", [])
    if not local_pool:
        return rng.choice(SYNTHETIC_BANKS), False
    if rng.random() < OFFSHORE_ACCOUNT_RATE:
        # Draw from banks outside the holder's own region, so the flag means
        # what it says rather than sometimes landing back on a local bank.
        foreign = [b for b in SYNTHETIC_BANKS if b not in local_pool]
        if foreign:
            return rng.choice(foreign), True
    return rng.choice(local_pool), False
