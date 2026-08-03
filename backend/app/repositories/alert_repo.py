"""Alerts are a filtered view over Incident nodes (High/Critical severity by
default) — there is no separate Alert node in the ontology (ARGUS_PLAN.md
Phase 7): the machine flags via Incident.severity, the analyst reviews and
updates Incident.status."""

from neo4j import AsyncDriver

ALERT_SEVERITIES = ["High", "Critical"]


async def list_alerts(
    driver: AsyncDriver, status: str | None, priority: str | None, page: int, page_size: int
) -> tuple[list[dict], int]:
    severities = [priority] if priority else ALERT_SEVERITIES
    status_filter = "AND i.status = $status" if status else ""
    params = {
        "severities": severities,
        "status": status,
        "skip": (page - 1) * page_size,
        "limit": page_size,
    }

    async with driver.session() as session:
        total_result = await session.run(
            f"MATCH (i:Incident) WHERE i.severity IN $severities {status_filter} RETURN count(i) AS total",
            **params,
        )
        total_record = await total_result.single()
        total = total_record["total"] if total_record else 0

        result = await session.run(
            f"""
            MATCH (i:Incident) WHERE i.severity IN $severities {status_filter}
            OPTIONAL MATCH (i)-[:INVOLVES]->(entity)
            WITH i, collect(DISTINCT {{label: labels(entity)[0], properties: entity}})[0..5] AS involved
            RETURN i, involved
            ORDER BY i.timestamp DESC SKIP $skip LIMIT $limit
            """,
            **params,
        )
        alerts = []
        async for record in result:
            alert = dict(record["i"])
            alert["involved_entities"] = [
                {"label": item["label"], "properties": dict(item["properties"])}
                for item in record["involved"]
                if item["label"]
            ]
            alerts.append(alert)

    return alerts, total


async def review_alert(driver: AsyncDriver, incident_id: str, new_status: str) -> dict | None:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (i:Incident {incident_id: $incident_id}) SET i.status = $status RETURN i",
            incident_id=incident_id,
            status=new_status,
        )
        record = await result.single()
        return dict(record["i"]) if record else None
