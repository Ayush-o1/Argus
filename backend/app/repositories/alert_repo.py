"""Alerts are a filtered view over Incident nodes (High/Critical severity by
default) — there is no separate Alert node in the ontology: the machine flags
via Incident.severity, the analyst reviews and updates Incident.status.

Geographic spread is computed here, over *every* entity an incident involves,
rather than in the UI over the handful of entities that happened to be
returned. Previously the query truncated involved entities to five with
`collect(...)[0..5]` and returned no total, and AlertDetail then derived
"N countries · Crosses N regions · Affected (N)" from that slice (audit B-04).
An incident touching thirty entities across twelve countries reported three
countries and five affected — a truncation presented as a complete finding,
under a section header reading "Spread".

The five-entity preview is still returned, because the panel only has room to
list a few, but it now travels with the totals it is a preview *of*.
"""

from neo4j import AsyncDriver

from app.models.aggregate import Aggregate

ALERT_SEVERITIES = ["High", "Critical"]

# How many involved entities to include for display. The count and the spread
# figures are computed over all of them regardless.
INVOLVED_PREVIEW_LIMIT = 5


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
        "preview_limit": INVOLVED_PREVIEW_LIMIT,
    }

    async with driver.session() as session:
        total_result = await session.run(
            f"MATCH (i:Incident) WHERE i.severity IN $severities {status_filter} RETURN count(i) AS total",
            params,
        )
        total_record = await total_result.single()
        total = total_record["total"] if total_record else 0

        result = await session.run(
            f"""
            MATCH (i:Incident) WHERE i.severity IN $severities {status_filter}
            WITH i ORDER BY i.timestamp DESC SKIP $skip LIMIT $limit

            // Aggregate over every involved entity before taking a preview, so
            // the spread figures describe the incident rather than the slice.
            OPTIONAL MATCH (i)-[:INVOLVES]->(entity)
            WITH i,
                 collect(DISTINCT entity) AS entities,
                 count(DISTINCT entity) AS involved_total,
                 count(DISTINCT entity.country) AS country_count,
                 count(DISTINCT entity.region) AS region_count,
                 collect(DISTINCT entity.country) AS countries,
                 collect(DISTINCT entity.region) AS regions,
                 max(entity.risk_score) AS peak_risk

            RETURN i,
                   involved_total,
                   country_count,
                   region_count,
                   [c IN countries WHERE c IS NOT NULL] AS countries,
                   [r IN regions WHERE r IS NOT NULL] AS regions,
                   peak_risk,
                   [e IN entities[0..$preview_limit] | {{label: labels(e)[0], properties: e}}] AS involved
            """,
            params,
        )

        alerts = []
        async for record in result:
            alert = dict(record["i"])
            involved_total = record["involved_total"] or 0
            preview = [
                {"label": item["label"], "properties": dict(item["properties"])}
                for item in record["involved"]
                if item["label"]
            ]

            coverage = (
                Aggregate.complete(involved_total, population=involved_total, method="count")
                if involved_total <= len(preview)
                else Aggregate.truncated(
                    len(preview), population=involved_total, examined=len(preview), method="first-n"
                )
            )
            alert["involved_entities"] = preview
            alert["involved_coverage"] = coverage.model_dump(mode="json")

            # Computed across all involved entities, so these stand on their own
            # regardless of how many are previewed above.
            alert["spread"] = {
                "involved_total": involved_total,
                "country_count": record["country_count"] or 0,
                "region_count": record["region_count"] or 0,
                # Bounded for display; country_count remains the authority.
                "countries": sorted(record["countries"])[:8],
                "regions": sorted(record["regions"]),
                "peak_risk": record["peak_risk"],
            }
            alerts.append(alert)

    return alerts, total


async def list_related_alerts(driver: AsyncDriver, incident_id: str, limit: int = 50) -> list[dict]:
    """Every alert sharing this incident's storyline, across the whole graph.

    The UI previously derived this by filtering the currently-loaded page of
    alerts (audit B-29), so related alerts outside the first 100 were invisible
    while the panel stated "treat as one investigation" — a page-scoped result
    presented as a complete set.
    """
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (source:Incident {incident_id: $incident_id})
            WHERE source.storyline_id IS NOT NULL
            MATCH (other:Incident {storyline_id: source.storyline_id})
            WHERE other.incident_id <> source.incident_id
            RETURN other ORDER BY other.timestamp DESC LIMIT $limit
            """,
            incident_id=incident_id,
            limit=limit,
        )
        return [dict(record["other"]) async for record in result]


async def review_alert(driver: AsyncDriver, incident_id: str, new_status: str) -> dict | None:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (i:Incident {incident_id: $incident_id}) SET i.status = $status RETURN i",
            incident_id=incident_id,
            status=new_status,
        )
        record = await result.single()
        return dict(record["i"]) if record else None
