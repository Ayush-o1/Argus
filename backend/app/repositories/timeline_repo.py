"""Global temporal activity for the Timeline page (ARGUS_PLAN.md Phase 6, Page 5).

Plots flagged activity (the "signal") against a bounded baseline sample
(the "noise") rather than all ~60K generated events/transactions/
communications, which would be unrenderable and uninformative at once —
the point of this page is spotting bursts, not exhaustive enumeration.
"""

from neo4j import AsyncDriver


async def get_global_timeline(driver: AsyncDriver, baseline_sample: int = 300, flagged_limit: int = 500) -> dict:
    async with driver.session() as session:
        tx_result = await session.run(
            """
            MATCH ()-[t:TRANSACTED_WITH]->()
            WITH t, t.flagged AS flagged
            ORDER BY flagged DESC, rand()
            LIMIT $limit
            RETURN t.tx_id AS id, t.timestamp AS timestamp, t.amount AS amount,
                   t.type AS subtype, flagged AS flagged, t.storyline_id AS storyline_id
            """,
            limit=flagged_limit + baseline_sample,
        )
        transactions = [dict(record) async for record in tx_result]

        comm_result = await session.run(
            """
            MATCH ()-[c:COMMUNICATED_WITH]->()
            WITH c, c.flagged AS flagged
            ORDER BY flagged DESC, rand()
            LIMIT $limit
            RETURN c.comm_id AS id, c.timestamp AS timestamp, c.duration_seconds AS duration_seconds,
                   c.type AS subtype, flagged AS flagged, c.storyline_id AS storyline_id
            """,
            limit=flagged_limit + baseline_sample,
        )
        communications = [dict(record) async for record in comm_result]

        event_result = await session.run(
            """
            MATCH (e:Event)
            WITH e, rand() AS r
            ORDER BY r
            LIMIT $limit
            RETURN e.event_id AS id, e.timestamp AS timestamp, e.type AS subtype,
                   false AS flagged, e.storyline_id AS storyline_id
            """,
            limit=baseline_sample,
        )
        events = [dict(record) async for record in event_result]

        incident_result = await session.run(
            """
            MATCH (i:Incident)
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
