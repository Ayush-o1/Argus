"""Stage 4: Baseline transaction history.

Generates plausible day-to-day account activity. Deliberate anomalies
(bursts, circular routing) are injected separately and explicitly by
storyline_generator.py (Stage 8) so they carry storyline attribution and
can be evaluated against the anomaly detector as a real detection problem
rather than baked directly into "normal" traffic.
"""

import random

from generators.common import new_id, new_uuid, random_datetime_between, WORLD_END, WORLD_START

TX_TYPE_WEIGHTED = [("Wire", 40), ("Cash", 35), ("Crypto", 10), ("Escrow", 15)]

# Most accounts transact a handful of times over the window; a long tail
# transacts much more often. This keeps per-account baselines meaningful so
# a later burst reads as a genuine deviation rather than noise.
TX_PER_ACCOUNT_WEIGHTED = [(3, 40), (8, 35), (20, 20), (45, 5)]


def generate_baseline_transactions(rng: random.Random, accounts: list[dict], target_count: int) -> list[dict]:
    if len(accounts) < 2:
        return []

    transactions: list[dict] = []
    counter = 0
    account_ids = [a["id"] for a in accounts]
    counts, count_weights = zip(*TX_PER_ACCOUNT_WEIGHTED)
    types, type_weights = zip(*TX_TYPE_WEIGHTED)

    # Cycle through accounts as many times as needed (rather than a single
    # pass) so the actual output lands at target_count rather than whatever
    # one pass of per-account baselines happens to sum to.
    while len(transactions) < target_count:
        account = accounts[len(transactions) % len(accounts)]
        num_tx = rng.choices(counts, weights=count_weights, k=1)[0]
        for _ in range(num_tx):
            if len(transactions) >= target_count:
                break
            counter += 1
            to_account = rng.choice(account_ids)
            while to_account == account["id"]:
                to_account = rng.choice(account_ids)

            amount = _baseline_amount(rng, account)
            transactions.append(
                {
                    "id": new_uuid(),
                    "tx_id": new_id("TXN", counter),
                    "from_account": account["id"],
                    "to_account": to_account,
                    "amount": amount,
                    "currency": "INR",
                    "type": rng.choices(types, weights=type_weights, k=1)[0],
                    "timestamp": random_datetime_between(rng, WORLD_START, WORLD_END).isoformat(),
                    "description": "Routine transfer",
                    "flagged": False,
                    "risk_score": 0.0,
                    "storyline_id": None,
                }
            )

    return transactions


def _baseline_amount(rng: random.Random, account: dict) -> float:
    base_by_class = {"Low": 5_000, "Medium": 25_000, "High": 150_000, "Extreme": 800_000}
    base = base_by_class.get(account["balance_class"], 10_000)
    return round(rng.uniform(base * 0.1, base * 1.2), 2)
