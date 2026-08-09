"""Case CRUD and evidence linking (ARGUS_PLAN.md Phase 7)."""

import uuid
from datetime import UTC, datetime

from neo4j import AsyncDriver

from app.repositories.entity_labels import resolve_label


async def list_cases(driver: AsyncDriver, status: str | None, page: int, page_size: int) -> tuple[list[dict], int]:
    status_filter = "WHERE c.status = $status" if status else ""
    params = {"status": status, "skip": (page - 1) * page_size, "limit": page_size}

    async with driver.session() as session:
        total_result = await session.run(f"MATCH (c:Case) {status_filter} RETURN count(c) AS total", params)
        total_record = await total_result.single()
        total = total_record["total"] if total_record else 0

        result = await session.run(
            f"MATCH (c:Case) {status_filter} RETURN c ORDER BY c.opened_at DESC SKIP $skip LIMIT $limit",
            params,
        )
        cases = [dict(record["c"]) async for record in result]

    return cases, total


async def get_case(driver: AsyncDriver, case_id: str) -> dict | None:
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (c:Case {case_id: $case_id})
            OPTIONAL MATCH (c)-[:LINKED_TO]->(entity)
            RETURN c, collect(DISTINCT {label: labels(entity)[0], properties: entity}) AS linked_entities
            """,
            case_id=case_id,
        )
        record = await result.single()
        if record is None:
            return None
        case = dict(record["c"])
        case["linked_entities"] = [
            {"label": item["label"], "properties": dict(item["properties"])}
            for item in record["linked_entities"]
            if item["label"]
        ]
        return case


async def create_case(driver: AsyncDriver, title: str, priority: str, notes: str, next_seq: int) -> dict:
    now = datetime.now(UTC).isoformat()
    case = {
        "id": str(uuid.uuid4()),
        "case_id": f"CASE-{next_seq:04d}",
        "title": title,
        "status": "Draft",
        "priority": priority,
        "assigned_analyst": "Unassigned",
        "opened_at": now,
        "closed_at": None,
        "notes": notes,
        "storyline_id": None,
    }
    async with driver.session() as session:
        await session.run("CREATE (c:Case) SET c = $case", case=case)
    return case


async def update_case(driver: AsyncDriver, case_id: str, updates: dict) -> dict | None:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Case {case_id: $case_id}) SET c += $updates RETURN c",
            case_id=case_id,
            updates=updates,
        )
        record = await result.single()
        return dict(record["c"]) if record else None


async def add_entity_to_case(driver: AsyncDriver, case_id: str, entity_human_id: str, reason: str) -> bool:
    info = resolve_label(entity_human_id)
    if info is None:
        return False
    async with driver.session() as session:
        result = await session.run(
            f"""
            MATCH (c:Case {{case_id: $case_id}})
            MATCH (e:{info.label} {{{info.id_field}: $entity_id}})
            MERGE (c)-[r:LINKED_TO]->(e)
            SET r.reason = $reason, r.added_at = $added_at
            RETURN c
            """,
            case_id=case_id,
            entity_id=entity_human_id,
            reason=reason,
            added_at=datetime.now(UTC).isoformat(),
        )
        return await result.single() is not None


async def remove_entity_from_case(driver: AsyncDriver, case_id: str, entity_human_id: str) -> None:
    info = resolve_label(entity_human_id)
    if info is None:
        return
    async with driver.session() as session:
        await session.run(
            f"""
            MATCH (c:Case {{case_id: $case_id}})-[r:LINKED_TO]->(e:{info.label} {{{info.id_field}: $entity_id}})
            DELETE r
            """,
            case_id=case_id,
            entity_id=entity_human_id,
        )


async def next_case_sequence(driver: AsyncDriver) -> int:
    async with driver.session() as session:
        result = await session.run("MATCH (c:Case) RETURN count(c) AS total")
        record = await result.single()
        return (record["total"] if record else 0) + 1
