"""Data for the temporal and spatial statistics.

Two shapes only: a daily count series, and a set of located points. Everything
in `app/temporal/` and `app/spatial/` is a pure function over one of those, so
this module is the whole of Phase 8's contact with the database.

**Nothing here reads a planted field.** The counts are of events that happened;
the "elevated" series counts activity touching subjects *ARGUS* assessed, from
`argus_band`, which is the assessment phase's own output projected onto the
graph. `flagged` and `storyline_id` do not appear.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from neo4j import AsyncDriver

__all__ = [
    "LANES",
    "fetch_daily_series",
    "fetch_located_entities",
    "fetch_location_values",
]

LANES: tuple[str, ...] = ("transactions", "communications", "events")

# Counting only events, not incidents: an `Incident` node is written by the
# scenario generator to summarise a storyline it planted, so a lane of them is a
# count of the answer key over time. The timeline still displays them, labelled
# as reported by their source; they are not a series statistics are run on.
_DAILY = """
CALL () {
    MATCH (a:Account)-[t:TRANSACTED_WITH]->(b:Account)
    WHERE t.timestamp IS NOT NULL
    RETURN substring(t.timestamp, 0, 10) AS day,
           'transactions' AS lane,
           CASE WHEN a.argus_band = 'elevated' OR b.argus_band = 'elevated'
                THEN 1 ELSE 0 END AS elevated
    UNION ALL
    // COMMUNICATED_WITH joins Devices, not people. Matching Person to Person
    // here returns nothing at all — silently, and the lane reads as a world
    // where nobody talks. The owners are resolved so "elevated" means what it
    // does in every other lane: ARGUS's assessment of the people involved.
    MATCH (d1:Device)-[c:COMMUNICATED_WITH]->(d2:Device)
    WHERE c.timestamp IS NOT NULL
    OPTIONAL MATCH (p:Person)-[:OWNS_DEVICE]->(d1)
    OPTIONAL MATCH (q:Person)-[:OWNS_DEVICE]->(d2)
    RETURN substring(c.timestamp, 0, 10) AS day,
           'communications' AS lane,
           CASE WHEN p.argus_band = 'elevated' OR q.argus_band = 'elevated'
                THEN 1 ELSE 0 END AS elevated
    UNION ALL
    MATCH (e:Event)
    WHERE e.timestamp IS NOT NULL
    RETURN substring(e.timestamp, 0, 10) AS day,
           'events' AS lane,
           0 AS elevated
}
RETURN day, lane, count(*) AS total, sum(elevated) AS elevated
ORDER BY day
"""


async def fetch_daily_series(driver: AsyncDriver) -> dict[str, dict[date, dict[str, int]]]:
    """Per-lane, per-day counts across the whole population.

    Aggregated in the database rather than sampled. The timeline once drew a
    random 800 records per request and computed statistics from them; a day
    bucket is a few bytes and there is no reason to estimate something this
    cheap to count (audit B-03).
    """
    async with driver.session() as session:
        result = await session.run(_DAILY)
        rows = [dict(record) async for record in result]

    series: dict[str, dict[date, dict[str, int]]] = {lane: {} for lane in LANES}
    for row in rows:
        lane = row["lane"]
        if lane not in series:
            continue
        try:
            day = date.fromisoformat(row["day"])
        except (TypeError, ValueError):
            continue
        series[lane][day] = {
            "total": int(row["total"] or 0),
            "elevated": int(row["elevated"] or 0),
        }
    return series


def densify(
    buckets: dict[date, dict[str, int]], start: date, end: date, key: str = "total"
) -> list[int]:
    """A contiguous day-by-day series, with absent days as zero.

    The single most consequential line in this module. A day on which nothing
    happened produces no row, and a statistic computed over only the days that
    appear treats "nothing happened" as "no observation" — which inflates every
    mean and suppresses exactly the quiet periods a change is measured against.
    That was audit B-18, and it is why every series here is densified before any
    test touches it.
    """
    out: list[int] = []
    day = start
    while day <= end:
        out.append(buckets.get(day, {}).get(key, 0))
        day += timedelta(days=1)
    return out


_LOCATED = """
MATCH (n)
WHERE (n:Person OR n:Organization)
  AND n.lat IS NOT NULL AND n.lng IS NOT NULL
RETURN coalesce(n.person_id, n.org_id) AS ref,
       labels(n)[0] AS label,
       n.lat AS lat, n.lng AS lng,
       n.country AS country, n.region AS region,
       n.argus_band AS band
"""


async def fetch_located_entities(driver: AsyncDriver, limit: int = 20_000) -> list[dict[str, Any]]:
    """Every entity with coordinates, for density clustering."""
    async with driver.session() as session:
        result = await session.run(f"{_LOCATED} LIMIT $limit", limit=limit)
        return [dict(record) async for record in result]


# One row per country: a position computed from its members and the counts to
# test. The position is a placeholder here — `avg(lat)` is wrong on a sphere —
# and is replaced by a proper spherical centroid in the service. It is selected
# only so a country with no computable centroid still appears.
_LOCATION_VALUES = """
MATCH (n)
WHERE (n:Person OR n:Organization)
  AND n.country IS NOT NULL AND n.lat IS NOT NULL AND n.lng IS NOT NULL
RETURN n.country AS country,
       n.region AS region,
       collect([n.lat, n.lng])[0..2000] AS positions,
       count(n) AS entity_count,
       sum(CASE WHEN n.argus_band = 'elevated' THEN 1 ELSE 0 END) AS elevated_count,
       sum(CASE WHEN n.argus_band IS NOT NULL
                 AND n.argus_band <> 'insufficient_evidence' THEN 1 ELSE 0 END) AS assessed_count
"""


async def fetch_location_values(driver: AsyncDriver) -> list[dict[str, Any]]:
    """Per-country counts with member positions, for the hotspot statistic."""
    async with driver.session() as session:
        result = await session.run(_LOCATION_VALUES)
        return [dict(record) async for record in result]


def window_bounds(days: int, now: datetime | None = None) -> tuple[date, date]:
    """The inclusive day range covering the last `days` days."""
    end = (now or datetime.now(UTC)).date()
    return end - timedelta(days=days - 1), end
