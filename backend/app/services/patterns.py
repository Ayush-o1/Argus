"""Temporal and spatial analysis, assembled from the pure statistics.

Answers three questions the product could not answer before:

  - **Is this increase significant?** A rate comparison against a stated prior
    period, returning a rate ratio, a confidence interval and an exact p-value.
  - **Where is activity concentrated?** Density clustering over coordinates,
    plus Getis-Ord Gi* to say whether a concentration is more than the map being
    dense there anyway.
  - **What are the temporal patterns?** Trend, changepoint and weekly rhythm,
    each with a test and each declining to answer where the data cannot support
    one.

Every result carries its window and its baseline. That is not decoration: "N
days above 2σ" was the previous statistical claim in this product, and it was
uncheckable precisely because it never said what it was measured against.

Nothing is persisted. Assessment, correlation and alerting keep ledgers because
alerts and cases attach to their outputs; a trend is a description of the world
as it is now, and storing one would create a stale record that nothing depends
on. Runs are cheap — the whole analysis is a few hundred milliseconds — so it is
computed when asked and stamped with the moment it was computed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from neo4j import AsyncDriver

from app.geometry import centroid
from app.repositories import patterns_repo
from app.spatial.clustering import DEFAULT_EPS_KM, DEFAULT_MIN_SAMPLES, cluster_points
from app.spatial.hotspots import DEFAULT_BAND_KM, getis_ord
from app.temporal.significance import compare_rates, flag_unusual_days
from app.temporal.trend import find_changepoint, mann_kendall, weekly_seasonality

logger = logging.getLogger(__name__)

# Default comparison: the last 30 days against the 90 before them. A baseline
# longer than the window is deliberate — it makes the baseline rate the more
# precisely estimated of the two, which is the right way round when the question
# is whether the recent window departs from normal.
DEFAULT_WINDOW_DAYS = 30
DEFAULT_BASELINE_DAYS = 90

MAX_WINDOW_DAYS = 365
MAX_BASELINE_DAYS = 730


@dataclass(frozen=True)
class SeriesAnalysis:
    lane: str
    change: dict[str, Any]
    trend: dict[str, Any]
    changepoint: dict[str, Any]
    seasonality: dict[str, Any]
    daily: list[dict[str, Any]]
    unusual_days: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "change": self.change,
            "trend": self.trend,
            "changepoint": self.changepoint,
            "seasonality": self.seasonality,
            "daily": self.daily,
            "unusual_days": self.unusual_days,
            "unusual_note": (
                "Days tested against the rate implied by every other day, "
                "Benjamini-Hochberg corrected across the series. Not "
                "'above two standard deviations', which has no null hypothesis "
                "and whose threshold is inflated by the bursts it looks for."
            ),
        }


async def analyse_temporal(
    driver: AsyncDriver,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Change, trend, changepoint and seasonality for every lane."""
    if not 1 <= window_days <= MAX_WINDOW_DAYS:
        raise ValueError(f"window_days must be between 1 and {MAX_WINDOW_DAYS}.")
    if not 1 <= baseline_days <= MAX_BASELINE_DAYS:
        raise ValueError(f"baseline_days must be between 1 and {MAX_BASELINE_DAYS}.")

    now = now or datetime.now(UTC)
    series = await patterns_repo.fetch_daily_series(driver)

    # The window ends at the last day the data actually holds, not at today.
    # Anchoring to the wall clock on a world whose most recent event is months
    # old produces an empty recent window and a confident "activity has stopped".
    observed_days = sorted({d for lane in series.values() for d in lane})
    if not observed_days:
        return {
            "evaluable": False,
            "reason": "The graph holds no timestamped activity to analyse.",
            "computed_at": now.isoformat(),
        }
    last_day = observed_days[-1]

    recent_start = last_day - timedelta(days=window_days - 1)
    baseline_end = recent_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=baseline_days - 1)

    analyses: list[dict[str, Any]] = []
    for lane in patterns_repo.LANES:
        buckets = series.get(lane, {})

        recent = patterns_repo.densify(buckets, recent_start, last_day)
        baseline = patterns_repo.densify(buckets, baseline_start, baseline_end)

        change = compare_rates(
            sum(recent), float(len(recent)),
            sum(baseline), float(len(baseline)),
            recent_from=datetime.combine(recent_start, datetime.min.time(), tzinfo=UTC),
            recent_to=datetime.combine(last_day, datetime.min.time(), tzinfo=UTC),
            baseline_from=datetime.combine(baseline_start, datetime.min.time(), tzinfo=UTC),
            baseline_to=datetime.combine(baseline_end, datetime.min.time(), tzinfo=UTC),
        )

        full = patterns_repo.densify(buckets, baseline_start, last_day)
        values = [float(v) for v in full]

        weekday_counts: dict[int, int] = {}
        day = baseline_start
        for count in full:
            weekday_counts[day.weekday()] = weekday_counts.get(day.weekday(), 0) + count
            day += timedelta(days=1)

        # Which individual days depart from the rest of the series. Replaces
        # the client-side "days above mean + 2σ", which had no null hypothesis
        # and whose threshold was inflated by the very bursts it was looking
        # for. Measured on the same data, the old rule called 132 of 4,800
        # ordinary days a burst; this calls 1.
        unusual = {u.index: u for u in flag_unusual_days(full)}

        daily = []
        day = baseline_start
        for i, count in enumerate(full):
            flag = unusual.get(i)
            daily.append({
                "day": day.isoformat(),
                "count": count,
                "elevated": buckets.get(day, {}).get("elevated", 0),
                "in_window": day >= recent_start,
                "unusual": bool(flag and flag.significant),
                "unusual_direction": flag.direction if flag and flag.significant else None,
                "expected": flag.expected if flag else None,
                "p_value": flag.p_value if flag else None,
            })
            day += timedelta(days=1)

        analyses.append(
            SeriesAnalysis(
                lane=lane,
                change=change.as_dict(),
                trend=mann_kendall(values).as_dict(),
                changepoint=find_changepoint(values).as_dict(),
                seasonality=weekly_seasonality(weekday_counts).as_dict(),
                daily=daily,
                unusual_days=sum(1 for d in daily if d["unusual"]),
            ).as_dict()
        )

    return {
        "evaluable": True,
        "window": {
            "days": window_days,
            "from": recent_start.isoformat(),
            "to": last_day.isoformat(),
        },
        "baseline": {
            "days": baseline_days,
            "from": baseline_start.isoformat(),
            "to": baseline_end.isoformat(),
        },
        "anchored_to": last_day.isoformat(),
        "anchor_note": (
            "Windows end at the most recent day the data holds, not at today. "
            "Anchoring to the clock on a world whose last event is older would "
            "produce an empty window and a confident claim that activity stopped."
        ),
        "series": analyses,
        "computed_at": now.isoformat(),
    }


async def analyse_spatial(
    driver: AsyncDriver,
    *,
    eps_km: float = DEFAULT_EPS_KM,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    band_km: float = DEFAULT_BAND_KM,
    value: str = "elevated_count",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Density clusters over coordinates, and Gi* over per-country counts."""
    if not 1.0 <= eps_km <= 2000.0:
        raise ValueError("eps_km must be between 1 and 2000.")
    if not 2 <= min_samples <= 500:
        raise ValueError("min_samples must be between 2 and 500.")
    if not 10.0 <= band_km <= 5000.0:
        raise ValueError("band_km must be between 10 and 5000.")
    if value not in ("elevated_count", "entity_count", "assessed_count"):
        raise ValueError("value must be elevated_count, entity_count or assessed_count.")

    now = now or datetime.now(UTC)

    points = await patterns_repo.fetch_located_entities(driver)
    clusters, noise = cluster_points(points, eps_km=eps_km, min_samples=min_samples)

    rows = await patterns_repo.fetch_location_values(driver)
    locations: list[dict[str, Any]] = []
    for row in rows:
        positions = [(float(p[0]), float(p[1])) for p in (row.get("positions") or []) if p]
        centre = centroid(positions)
        if centre is None:
            continue
        locations.append({
            "key": row["country"],
            "region": row["region"],
            "lat": centre[0],
            "lng": centre[1],
            "value": float(row.get(value) or 0),
            "entity_count": int(row.get("entity_count") or 0),
            "elevated_count": int(row.get("elevated_count") or 0),
            "assessed_count": int(row.get("assessed_count") or 0),
        })

    report = getis_ord(locations, band_km=band_km)
    by_key = {loc["key"]: loc for loc in locations}
    enriched = report.as_dict()
    for group in ("hot", "cold", "all"):
        for item in enriched[group]:
            source = by_key.get(item["key"], {})
            item["region"] = source.get("region")
            item["entity_count"] = source.get("entity_count")
            item["elevated_count"] = source.get("elevated_count")
            item["assessed_count"] = source.get("assessed_count")

    return {
        "clusters": {
            "found": [c.as_dict() for c in clusters],
            "count": len(clusters),
            "noise": noise,
            "located_total": len([p for p in points if p.get("lat") is not None]),
            "eps_km": eps_km,
            "min_samples": min_samples,
            "note": (
                f"{noise} located entities belong to no concentration at all. They are "
                "reported rather than dropped: a view showing only clusters would imply "
                "the world is made entirely of them."
            ),
            "method": "DBSCAN on great-circle distance",
        },
        "hotspots": enriched,
        "value_measured": value,
        "computed_at": now.isoformat(),
        "postgis_note": (
            "Computed in-process rather than in PostGIS. At this scale a full "
            "haversine scan is milliseconds and a spatial index would have nothing "
            "to accelerate. The trigger for revisiting is roughly a million located "
            "entities, or a query needing polygon containment rather than point "
            "proximity."
        ),
    }
