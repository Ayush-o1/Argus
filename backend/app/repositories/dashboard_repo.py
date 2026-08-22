"""Aggregate queries for the Dashboard (ARGUS_PLAN.md Phase 6, Page 1).

Not part of the original Phase 13 endpoint list — added because a real
command-center dashboard needs a handful of cheap aggregate reads rather
than the frontend fanning out N separate list calls just to compute totals.
"""

from datetime import UTC, datetime, timedelta

from neo4j import AsyncDriver

from app.repositories import alert_repo

# Window for the dashboard's "recent activity" figure. Must match the label the
# UI renders, which reads it from the response rather than hardcoding it.
RECENT_WINDOW_DAYS = 7

# How many incidents to return for display. Deliberately separate from any
# counting query — this list is never a source for aggregates.
RECENT_INCIDENT_PREVIEW = 6

# The bands ARGUS's own assessor produces, plus the bucket for everyone it has
# not assessed. `unassessed` is listed here rather than being dropped because
# the four bands do not cover the population: a person with no accounts and no
# device is not low-risk, and a distribution that omitted them would present an
# opinion about a fraction of the world as an opinion about all of it.
#
# This replaces a distribution computed from `Person.risk_score` — the scenario
# generator's own number, assigned from storyline membership. The dashboard was
# reporting the answer key back as a finding (audit G-08).
ASSESSMENT_BANDS = ("elevated", "notable", "routine", "insufficient_evidence", "unassessed")


async def get_dashboard_summary(driver: AsyncDriver) -> dict:
    async with driver.session() as session:
        # Every MATCH after the first must be OPTIONAL: once a preceding WITH has
        # collapsed the stream to an aggregated row, a plain MATCH that finds zero
        # matches (e.g. zero active Cases after an analyst closes them all, or zero
        # open High/Critical Incidents after all alerts are closed) drops the row
        # count to zero for the rest of the query — .single() then returns None and
        # every downstream `counts["..."]` lookup raises. OPTIONAL MATCH keeps the
        # row alive with a 0 count instead. Confirmed via direct Cypher reproduction.
        counts_row = await (
            await session.run(
                """
                MATCH (p:Person) WITH count(p) AS persons
                OPTIONAL MATCH (o:Organization) WITH persons, count(o) AS orgs
                OPTIONAL MATCH ()-[t:TRANSACTED_WITH]->() WITH persons, orgs, count(t) AS transactions
                OPTIONAL MATCH (p2:Person) WHERE p2.argus_band = 'elevated'
                WITH persons, orgs, transactions, count(p2) AS elevated
                OPTIONAL MATCH (a:Case) WHERE a.status IN ['Open', 'UnderReview']
                RETURN persons, orgs, transactions, elevated, count(a) AS active_cases
                """
            )
        ).single()
        assert counts_row is not None, "aggregate query always returns exactly one row"

        # One grouped query rather than a count per band. The previous form ran
        # a query per bucket, and the buckets were half-open ranges over a
        # score, which is why a boundary mistake once dropped every entity at
        # exactly 100 from the distribution while the totals still looked
        # plausible. Grouping makes the counts sum to the population by
        # construction.
        band_result = await session.run(
            """
            MATCH (p:Person)
            RETURN coalesce(p.argus_band, 'unassessed') AS band, count(p) AS count
            """
        )
        counts = {record["band"]: record["count"] async for record in band_result}
        assessment_distribution = [
            {"band": band, "count": counts.get(band, 0)} for band in ASSESSMENT_BANDS
        ]

        # Counted over every incident, not over the six-row display list below.
        #
        # SituationBrief previously derived "N alerts are open, M of them
        # critical" by filtering `recent_incidents` — a LIMIT 6 list — while N
        # came from a full count. The two numbers were joined in one sentence as
        # though they shared a denominator, so M could never exceed 6 no matter
        # what the graph contained (audit B-05). The figure labelled
        # "Incidents · 7d" was capped the same way.
        period_result = await (
            await session.run(
                """
                OPTIONAL MATCH (r:Incident) WHERE r.timestamp >= $since
                RETURN count(r) AS incidents_in_window,
                       sum(CASE WHEN r.severity = 'Critical' THEN 1 ELSE 0 END) AS critical_in_window
                """,
                since=(datetime.now(UTC) - timedelta(days=RECENT_WINDOW_DAYS)).isoformat(),
            )
        ).single()
        assert period_result is not None, "aggregate query always returns exactly one row"

        recent_incidents_result = await session.run(
            """
            MATCH (i:Incident)
            RETURN i.incident_id AS incident_id, i.type AS type, i.severity AS severity,
                   i.timestamp AS timestamp, i.description AS description
            ORDER BY i.timestamp DESC LIMIT $limit
            """,
            limit=RECENT_INCIDENT_PREVIEW,
        )
        recent_incidents = [dict(record) async for record in recent_incidents_result]

        recent_cases_result = await session.run(
            """
            MATCH (c:Case)
            RETURN c.case_id AS case_id, c.title AS title, c.status AS status,
                   c.priority AS priority, c.opened_at AS opened_at
            ORDER BY c.opened_at DESC LIMIT 6
            """
        )
        recent_cases = [dict(record) async for record in recent_cases_result]

    alert_counts = await alert_repo.queue_counts()
    high_priority_open = await alert_repo.count_open_high_priority()

    return {
        "total_persons": counts_row["persons"],
        "total_organizations": counts_row["orgs"],
        "total_transactions": counts_row["transactions"],
        # Renamed from `flagged_entities`, and it is not a rename only. The old
        # figure counted people the generator had marked; this one counts
        # people ARGUS assessed as warranting review, which is a different
        # claim about a different thing.
        "elevated_entities": counts_row["elevated"],
        "active_cases": counts_row["active_cases"],
        # Alerts ARGUS raised, from the alerting tables — not open High/Critical
        # `Incident` nodes, which is what this counted until Phase 7. Those are
        # written by the scenario generator, one per storyline, so the dashboard
        # was reporting the answer key's size and calling it the queue.
        "open_alerts": alert_counts.get("open", 0),
        "high_priority_open_alerts": high_priority_open,
        # Incidents are kept, and are no longer called alerts. In this world they
        # are records reported by a source (the generator, registered and rated),
        # which is a different thing from something ARGUS concluded. Labelling
        # them as alerts is what made them a defect; reporting them as what they
        # are is not.
        "incidents_in_window": period_result["incidents_in_window"] or 0,
        "critical_incidents_in_window": period_result["critical_in_window"] or 0,
        "window_days": RECENT_WINDOW_DAYS,
        # No average. A mean over a population where most subjects could not be
        # assessed at all is not a summary of anything, and putting one on a
        # dashboard invites exactly the false authority this phase removed.
        "assessment_distribution": assessment_distribution,
        "assessed_persons": sum(
            row["count"] for row in assessment_distribution if row["band"] != "unassessed"
        ),
        # A display list only. Nothing derives a count from this.
        "recent_incidents": recent_incidents,
        "recent_cases": recent_cases,
    }
