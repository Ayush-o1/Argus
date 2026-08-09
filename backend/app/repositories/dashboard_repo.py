"""Aggregate queries for the Dashboard (ARGUS_PLAN.md Phase 6, Page 1).

Not part of the original Phase 13 endpoint list — added because a real
command-center dashboard needs a handful of cheap aggregate reads rather
than the frontend fanning out N separate list calls just to compute totals.
"""

from neo4j import AsyncDriver

RISK_BUCKETS = [
    ("Critical", 80, 100),
    ("High", 60, 80),
    ("Medium", 35, 60),
    ("Low", 0, 35),
]


async def get_dashboard_summary(driver: AsyncDriver) -> dict:
    async with driver.session() as session:
        # Every MATCH after the first must be OPTIONAL: once a preceding WITH has
        # collapsed the stream to an aggregated row, a plain MATCH that finds zero
        # matches (e.g. zero active Cases after an analyst closes them all, or zero
        # open High/Critical Incidents after all alerts are closed) drops the row
        # count to zero for the rest of the query — .single() then returns None and
        # every downstream `counts["..."]` lookup raises. OPTIONAL MATCH keeps the
        # row alive with a 0 count instead. Confirmed via direct Cypher reproduction.
        counts = await (
            await session.run(
                """
                MATCH (p:Person) WITH count(p) AS persons
                OPTIONAL MATCH (o:Organization) WITH persons, count(o) AS orgs
                OPTIONAL MATCH ()-[t:TRANSACTED_WITH]->() WITH persons, orgs, count(t) AS transactions
                OPTIONAL MATCH (p2:Person) WHERE p2.risk_score >= 80
                WITH persons, orgs, transactions, count(p2) AS flagged
                OPTIONAL MATCH (a:Case) WHERE a.status IN ['Open', 'UnderReview']
                WITH persons, orgs, transactions, flagged, count(a) AS active_cases
                OPTIONAL MATCH (i:Incident) WHERE i.status = 'Open' AND i.severity IN ['High', 'Critical']
                RETURN persons, orgs, transactions, flagged, active_cases, count(i) AS open_alerts
                """
            )
        ).single()

        avg_risk_record = await (
            await session.run("MATCH (p:Person) RETURN avg(p.risk_score) AS avg_risk")
        ).single()

        risk_distribution = []
        for label, low, high in RISK_BUCKETS:
            record = await (
                await session.run(
                    "MATCH (p:Person) WHERE p.risk_score >= $low AND p.risk_score < $high RETURN count(p) AS count",
                    low=low,
                    high=high,
                )
            ).single()
            risk_distribution.append({"level": label, "count": record["count"]})

        recent_incidents_result = await session.run(
            """
            MATCH (i:Incident)
            RETURN i.incident_id AS incident_id, i.type AS type, i.severity AS severity,
                   i.timestamp AS timestamp, i.description AS description
            ORDER BY i.timestamp DESC LIMIT 6
            """
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

    return {
        "total_persons": counts["persons"],
        "total_organizations": counts["orgs"],
        "total_transactions": counts["transactions"],
        "flagged_entities": counts["flagged"],
        "active_cases": counts["active_cases"],
        "open_alerts": counts["open_alerts"],
        "avg_risk_score": round(avg_risk_record["avg_risk"] or 0.0, 1),
        "risk_distribution": risk_distribution,
        "recent_incidents": recent_incidents,
        "recent_cases": recent_cases,
    }
