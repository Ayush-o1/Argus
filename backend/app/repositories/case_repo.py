"""Case CRUD and evidence linking (ARGUS_PLAN.md Phase 7)."""

import uuid
from datetime import UTC, datetime

from neo4j import AsyncDriver

from app.repositories.entity_labels import resolve_label

# Neo4j does not store null properties: `SET c.closed_at = null` removes the key
# rather than storing a null, so a reopened case came back with no `closed_at`
# key at all while a never-closed one had it only because it was written at
# creation. The API contract should not depend on that storage detail, so every
# case is normalised to carry the full field set on the way out.
_NULLABLE_CASE_FIELDS = ("closed_at", "storyline_id", "notes", "assigned_analyst")


def _shape_case(props: dict) -> dict:
    case = dict(props)
    for field in _NULLABLE_CASE_FIELDS:
        case.setdefault(field, None)
    return case


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
        cases = [_shape_case(record["c"]) async for record in result]

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
        case = _shape_case(record["c"])
        case["linked_entities"] = [
            {"label": item["label"], "properties": dict(item["properties"])}
            for item in record["linked_entities"]
            if item["label"]
        ]
        return case


async def create_case(driver: AsyncDriver, title: str, priority: str, notes: str) -> dict:
    """Allocates the next case_id and creates the case in one transaction.

    The previous implementation read `count(c) + 1` in one query and wrote in
    another (audit B-02). Two concurrent creates both read N and both wrote
    CASE-000(N+1); with no uniqueness constraint Neo4j accepted both, and
    `get_case`'s `.single()` then raised forever for that id — the case detail
    page was permanently broken. Counting was also simply wrong after any
    deletion.

    `MERGE` on the :IdSequence node takes a lock on it for the duration of the
    transaction, so concurrent allocations serialise on that lock and each
    observes the previous one's increment. The uniqueness constraint on
    Case.case_id (migration 001) is the backstop if this is ever bypassed.
    """
    now = datetime.now(UTC).isoformat()
    async with driver.session() as session:
        result = await session.run(
            # Zero-padded to 4 digits for display, but only while that is
            # lossless: past 9999 the number is emitted in full rather than
            # truncated to its last four digits, which would reintroduce
            # collisions at exactly the point they become likely.
            """
            MERGE (seq:IdSequence {prefix: 'CASE'})
            ON CREATE SET seq.value = $seed
            SET seq.value = seq.value + 1
            WITH seq.value AS next_seq
            CREATE (c:Case)
            SET c = $case,
                c.case_id = 'CASE-' + CASE
                    WHEN next_seq < 10000 THEN right('0000' + toString(next_seq), 4)
                    ELSE toString(next_seq)
                END
            RETURN c
            """,
            seed=await _sequence_seed(session),
            case={
                "id": str(uuid.uuid4()),
                "title": title,
                "status": "Draft",
                "priority": priority,
                "assigned_analyst": "Unassigned",
                "opened_at": now,
                "closed_at": None,
                "notes": notes,
                "storyline_id": None,
            },
        )
        record = await result.single()
        if record is None:  # pragma: no cover - CREATE always returns a row
            raise RuntimeError("Case creation returned no row")
        return _shape_case(record["c"])


async def _sequence_seed(session) -> int:
    """Initial counter value, used only when the :IdSequence node does not yet
    exist. Seeded from the highest existing case number so a graph populated by
    the generator (which writes CASE-0001..N directly) does not immediately
    collide with the constraint.

    Parses the numeric suffix rather than taking a string max: `max()` over
    strings is lexicographic, which breaks the moment the zero-padding width
    changes (audit B-22).
    """
    result = await session.run(
        """
        MATCH (c:Case)
        WHERE c.case_id STARTS WITH 'CASE-'
        RETURN max(toInteger(split(c.case_id, '-')[-1])) AS max_seq
        """
    )
    record = await result.single()
    return (record["max_seq"] or 0) if record else 0


# Fields an update request may change. `SET c += $map` with a caller-supplied
# map is one widened request model away from mass assignment — it would happily
# overwrite case_id, opened_at, or the uuid. Enumerating the writable fields
# means a new field has to be added deliberately in two places.
UPDATABLE_FIELDS = frozenset({"status", "priority", "notes", "assigned_analyst"})


async def update_case(driver: AsyncDriver, case_id: str, updates: dict) -> dict | None:
    """Applies a whitelisted set of field updates.

    Also maintains `closed_at`, which was declared in create_case and typed in
    the frontend but never written by any code path — a case could be Closed and
    still carry closed_at: null, so "when was this closed" had no answer.
    """
    rejected = set(updates) - UPDATABLE_FIELDS
    if rejected:
        raise ValueError(f"Fields are not updatable: {', '.join(sorted(rejected))}")
    if not updates:
        return await get_case(driver, case_id)

    # Only the whitelisted keys reach the query, and each is set by name.
    assignments = ", ".join(f"c.{field} = ${field}" for field in sorted(updates))

    closed_at_clause = ""
    if updates.get("status") == "Closed":
        closed_at_clause = ", c.closed_at = coalesce(c.closed_at, $now)"
    elif "status" in updates:
        # Reopening clears the closure timestamp; leaving a stale one would
        # claim the case was closed at a moment it demonstrably was not.
        closed_at_clause = ", c.closed_at = null"

    async with driver.session() as session:
        result = await session.run(
            f"MATCH (c:Case {{case_id: $case_id}}) SET {assignments}{closed_at_clause} RETURN c",
            case_id=case_id,
            now=datetime.now(UTC).isoformat(),
            **updates,
        )
        record = await result.single()
        return _shape_case(record["c"]) if record else None


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


