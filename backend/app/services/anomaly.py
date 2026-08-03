"""Statistical / ML anomaly detection (ARGUS_PLAN.md Phase 10, Local Feature 1).

A separate, independent pass from the generator's storyline injector — it
does not read `flagged`/`storyline_id`, it engineers behavioral features per
account (transaction volume, amount, burst density) from the raw transaction
timestamps and scores outliers two ways:

- Isolation Forest (unsupervised, trained fresh on this world's own feature
  matrix — no labels, no external data).
- A z-score baseline against the account population as a fully explainable
  cross-check.

An account is flagged only when both methods agree, which is a real (if
small-scale) precision/recall story, not a re-statement of the ground truth.
"""

from datetime import datetime

from neo4j import AsyncDriver
from sklearn.ensemble import IsolationForest

from app.repositories.analytics_repo import owner_lookup

BURST_WINDOW_SECONDS = 6 * 60 * 60  # 6 hours, per ARGUS_PLAN.md Phase 10 example


def _max_burst_count(timestamps: list[datetime], window_seconds: int) -> int:
    """Max number of transactions falling within any `window_seconds` span —
    a sliding window over sorted timestamps, O(n)."""
    if not timestamps:
        return 0
    ts = sorted(timestamps)
    left = 0
    best = 1
    for right in range(len(ts)):
        while (ts[right] - ts[left]).total_seconds() > window_seconds:
            left += 1
        best = max(best, right - left + 1)
    return best


async def _account_features(driver: AsyncDriver) -> list[dict]:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:Account)-[t:TRANSACTED_WITH]-()
            WITH a, collect(t.timestamp) AS timestamps, count(t) AS tx_count, sum(t.amount) AS total_amount
            WHERE tx_count >= 3
            RETURN a.id AS uuid, timestamps, tx_count, total_amount
            """
        )
        rows = [dict(record) async for record in result]

    features = []
    for row in rows:
        timestamps = [datetime.fromisoformat(t) for t in row["timestamps"]]
        burst = _max_burst_count(timestamps, BURST_WINDOW_SECONDS)
        features.append(
            {
                "uuid": row["uuid"],
                "tx_count": row["tx_count"],
                "total_amount": row["total_amount"] or 0.0,
                "max_burst_count": burst,
            }
        )
    return features


def _zscore(value: float, mean: float, std: float) -> float:
    return (value - mean) / std if std > 0 else 0.0


async def detect_transaction_anomalies(driver: AsyncDriver, z_threshold: float = 3.0) -> list[dict]:
    features = await _account_features(driver)
    if len(features) < 10:
        return []

    matrix = [[f["tx_count"], f["total_amount"], f["max_burst_count"]] for f in features]

    forest = IsolationForest(n_estimators=200, contamination="auto", random_state=42)
    predictions = forest.fit_predict(matrix)

    burst_values = [f["max_burst_count"] for f in features]
    burst_mean = sum(burst_values) / len(burst_values)
    burst_std = (sum((v - burst_mean) ** 2 for v in burst_values) / len(burst_values)) ** 0.5

    anomalies = []
    for feature, is_outlier, in zip(features, predictions, strict=True):
        z = _zscore(feature["max_burst_count"], burst_mean, burst_std)
        if is_outlier == -1 and z >= z_threshold:
            anomalies.append(
                {
                    **feature,
                    "burst_baseline_mean": round(burst_mean, 2),
                    "burst_baseline_std": round(burst_std, 2),
                    "z_score": round(z, 2),
                }
            )

    anomalies.sort(key=lambda a: a["z_score"], reverse=True)

    owners = await owner_lookup(driver, [a["uuid"] for a in anomalies])
    shaped = []
    for a in anomalies:
        owner = owners.get(a["uuid"])
        if owner is None:
            continue
        shaped.append(
            {
                "id": owner["owner_human_id"],
                "name": owner["owner_name"],
                "label": owner["resolved_label"],
                "account_id": owner["account_id"],
                "tx_count": a["tx_count"],
                "total_amount": round(a["total_amount"], 2),
                "max_burst_count": a["max_burst_count"],
                "burst_window_hours": BURST_WINDOW_SECONDS // 3600,
                "burst_baseline_mean": a["burst_baseline_mean"],
                "burst_baseline_std": a["burst_baseline_std"],
                "z_score": a["z_score"],
            }
        )
    return shaped
