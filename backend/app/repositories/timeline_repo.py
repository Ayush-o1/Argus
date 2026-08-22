"""Global temporal activity for the Timeline page.

Previously this returned a random sample — `ORDER BY flagged DESC, rand() LIMIT
800` — and the frontend computed "N days above 2σ of flagged volume" from it.
That was wrong three ways (audit B-03):

  1. `rand()` re-drew per request, so refreshing the page changed which days
     were bursts. Two analysts comparing notes saw different findings from the
     same query.
  2. `ORDER BY flagged DESC` took every flagged record first and filled the
     remainder randomly, so the flagged-to-baseline ratio in the sample bore no
     relation to the real one. The chart was labelled "Daily volume"; it was not
     volume.
  3. The frontend's mean was computed only over days that appeared in the
     payload. Days with no activity produced no row, so they were omitted rather
     than counted as zero, inflating the mean and suppressing real bursts
     (audit B-18).

The fix is to aggregate server-side over the whole population. Daily counts are
cheap to compute in Cypher and small to transmit — 180 days of buckets is a few
kilobytes, far less than 800 individual records were — so the sampling was never
buying anything.

Individual records are still returned for the scatter lane, but they are now
explicitly a bounded, ordered preview (`Basis.TRUNCATED`) rather than something
statistics are computed from.
"""

from __future__ import annotations

from datetime import date, timedelta

from neo4j import AsyncDriver

from app.models.aggregate import Aggregate

# Upper bound on individual records returned for the scatter lane. These drive a
# visual only — every number on the page comes from the day buckets.
DETAIL_LIMIT = 400


LANES = ("transactions", "communications", "events", "incidents")


def _empty_bucket(day: str) -> dict:
    bucket: dict = {"day": day, "total": 0, "source_reported": 0}
    for lane in LANES:
        bucket[lane] = 0
        bucket[f"{lane}_source_reported"] = 0
    return bucket


async def _daily_counts(driver: AsyncDriver) -> tuple[list[dict], dict[str, int]]:
    """Per-day totals across every transaction, communication, event and
    incident in the graph. Returns (buckets, population_totals).

    `substring(x.timestamp, 0, 10)` extracts the date from the stored ISO string
    rather than parsing it into a temporal type, and takes the day exactly as
    written.

    The generator now anchors the world in UTC (audit B-17 fixed in
    `generator/generators/common.py`), so for anything generated since, the day
    key is the UTC date — a stated convention rather than an inherited accident.

    A graph populated before that fix still holds naive local timestamps, and
    those are bucketed by their wall-clock date because no offset exists to
    honour; parsing them would invent a timezone the data does not carry. Both
    forms slice identically, so mixed data buckets consistently, but the older
    rows carry an ambiguity that only regenerating the world removes.
    """
    query = """
    CALL () {
        MATCH ()-[t:TRANSACTED_WITH]->()
        WHERE t.timestamp IS NOT NULL
        RETURN substring(t.timestamp, 0, 10) AS day,
               'transactions' AS lane,
               CASE WHEN t.flagged THEN 1 ELSE 0 END AS reported
        UNION ALL
        MATCH ()-[c:COMMUNICATED_WITH]->()
        WHERE c.timestamp IS NOT NULL
        RETURN substring(c.timestamp, 0, 10) AS day,
               'communications' AS lane,
               CASE WHEN c.flagged THEN 1 ELSE 0 END AS reported
        UNION ALL
        MATCH (e:Event)
        WHERE e.timestamp IS NOT NULL
        RETURN substring(e.timestamp, 0, 10) AS day,
               'events' AS lane,
               0 AS reported
        UNION ALL
        MATCH (i:Incident)
        WHERE i.timestamp IS NOT NULL
        RETURN substring(i.timestamp, 0, 10) AS day,
               'incidents' AS lane,
               1 AS reported
    }
    RETURN day, lane, count(*) AS total, sum(reported) AS source_reported
    ORDER BY day
    """
    async with driver.session() as session:
        result = await session.run(query)
        rows = [dict(record) async for record in result]

    by_day: dict[str, dict] = {}
    population: dict[str, int] = {"transactions": 0, "communications": 0, "events": 0, "incidents": 0}

    for row in rows:
        day = row["day"]
        bucket = by_day.setdefault(day, _empty_bucket(day))
        bucket["total"] += row["total"]
        bucket["source_reported"] += row["source_reported"]
        bucket[row["lane"]] += row["total"]
        # Kept per-lane, not just summed: the UI lets an analyst switch lanes
        # off, and a single pre-summed total cannot be apportioned back
        # afterwards. Without these the filtered flagged count would have to be
        # approximated, and approximating a figure the analyst reads as exact is
        # the failure this whole change exists to prevent.
        bucket[f"{row['lane']}_source_reported"] += row["source_reported"]
        population[row["lane"]] += row["total"]

    return list(by_day.values()), population


def _zero_fill(buckets: list[dict]) -> list[dict]:
    """Insert explicit zero buckets for days with no activity.

    A day with nothing in it is a real observation about the timeline, and
    omitting it is what let the previous implementation compute its mean over
    only the non-empty days (audit B-18). Statistics downstream depend on this
    series being contiguous.
    """
    if not buckets:
        return []

    ordered = sorted(buckets, key=lambda b: b["day"])
    start = date.fromisoformat(ordered[0]["day"])
    end = date.fromisoformat(ordered[-1]["day"])
    existing = {b["day"]: b for b in ordered}

    filled: list[dict] = []
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        filled.append(existing.get(key, _empty_bucket(key)))
        cursor += timedelta(days=1)
    return filled


async def _detail_records(driver: AsyncDriver) -> dict[str, list[dict]]:
    """A bounded, deterministically-ordered preview for the scatter lane.

    Ordered by timestamp rather than `rand()` so the same request returns the
    same records. These are explicitly a preview: nothing on the page computes a
    statistic from them.
    """
    async with driver.session() as session:
        tx_result = await session.run(
            """
            MATCH ()-[t:TRANSACTED_WITH]->()
            WHERE t.timestamp IS NOT NULL
            RETURN t.tx_id AS id, t.timestamp AS timestamp, t.amount AS amount,
                   t.type AS subtype, coalesce(t.flagged, false) AS source_reported
            ORDER BY t.timestamp DESC
            LIMIT $limit
            """,
            limit=DETAIL_LIMIT,
        )
        transactions = [dict(record) async for record in tx_result]

        comm_result = await session.run(
            """
            MATCH ()-[c:COMMUNICATED_WITH]->()
            WHERE c.timestamp IS NOT NULL
            RETURN c.comm_id AS id, c.timestamp AS timestamp,
                   c.duration_seconds AS duration_seconds, c.type AS subtype,
                   coalesce(c.flagged, false) AS source_reported
            ORDER BY c.timestamp DESC
            LIMIT $limit
            """,
            limit=DETAIL_LIMIT,
        )
        communications = [dict(record) async for record in comm_result]

        event_result = await session.run(
            """
            MATCH (e:Event)
            WHERE e.timestamp IS NOT NULL
            RETURN e.event_id AS id, e.timestamp AS timestamp, e.type AS subtype,
                   false AS source_reported
            ORDER BY e.timestamp DESC
            LIMIT $limit
            """,
            limit=DETAIL_LIMIT,
        )
        events = [dict(record) async for record in event_result]

        # Incidents are returned in full: there are tens of them, not thousands,
        # and they are the page's primary signal rather than background volume.
        incident_result = await session.run(
            """
            MATCH (i:Incident)
            WHERE i.timestamp IS NOT NULL
            RETURN i.incident_id AS id, i.timestamp AS timestamp, i.type AS subtype,
                   i.severity AS severity, i.description AS description
            ORDER BY i.timestamp DESC
            """
        )
        incidents = [dict(record) async for record in incident_result]

    return {
        "transactions": transactions,
        "communications": communications,
        "events": events,
        "incidents": incidents,
    }


async def get_global_timeline(driver: AsyncDriver) -> dict:
    buckets, population = await _daily_counts(driver)
    filled = _zero_fill(buckets)
    details = await _detail_records(driver)

    total_records = sum(population.values())
    total_reported = sum(b["source_reported"] for b in filled)

    def preview(lane: str) -> dict:
        records = details[lane]
        pop = population[lane]
        # Incidents are complete; the other lanes are a bounded head of an
        # ordered list, which is a truncation and not a sample.
        agg = (
            Aggregate.complete(len(records), population=pop, method="all")
            if lane == "incidents" or len(records) >= pop
            else Aggregate.truncated(len(records), population=pop, examined=len(records), method="top-by-time")
        )
        return {"records": records, "coverage": agg.model_dump(mode="json")}

    return {
        # Every figure the UI renders comes from here, and every one covers the
        # whole population.
        "buckets": filled,
        "day_count": len(filled),
        "totals": {
            "records": Aggregate.complete(total_records, population=total_records, method="count").model_dump(
                mode="json"
            ),
            # Not "flagged". This counts records whose *source* marked them, and
            # in this world that source is the scenario generator marking the
            # storylines it planted. Presented as a finding it is the answer key;
            # presented as what it is — a claim by a rated source — it is a fact
            # about collection, and worth showing beside ARGUS's own view.
            "source_reported": Aggregate.complete(
                total_reported, population=total_records, method="count"
            ).model_dump(mode="json"),
            "by_lane": {lane: population[lane] for lane in population},
        },
        # Individual records, for the scatter visual only.
        "detail": {lane: preview(lane) for lane in ("transactions", "communications", "events", "incidents")},
    }
