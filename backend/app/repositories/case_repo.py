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
            OPTIONAL MATCH (c)-[link:LINKED_TO]->(entity)
            WHERE link.removed_at IS NULL
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


async def create_case(
    driver: AsyncDriver, title: str, priority: str, notes: str, opened_by: str = 'unknown'
) -> dict:
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
            # Seven-digit zero padding, matching the generator's new_id() format
            # (generator/generators/common.py). The backend previously used four,
            # so the same graph held CASE-0000001 and CASE-0105 — two formats for
            # one identifier type, which sorts wrongly and reads as a data-quality
            # fault. Past 9,999,999 the number is emitted in full rather than
            # truncated, which would reintroduce collisions exactly when they
            # become likely.
            """
            MERGE (seq:IdSequence {prefix: 'CASE'})
            ON CREATE SET seq.value = $seed
            // Take whichever is higher: the counter, or the highest case_id
            // actually in the graph. The two can diverge — the generator writes
            // cases directly with its own numbering, and a restore or manual
            // intervention can move one without the other. When the counter
            // fell behind, every create failed the uniqueness constraint with
            // no recovery path. Reconciling here makes the counter self-healing
            // while staying monotonic, so ids are never reused.
            SET seq.value = CASE WHEN $seed > seq.value THEN $seed ELSE seq.value END + 1
            WITH seq.value AS next_seq
            CREATE (c:Case)
            SET c = $case,
                c.case_id = 'CASE-' + CASE
                    WHEN next_seq < 10000000 THEN right('0000000' + toString(next_seq), 7)
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
                "opened_by": opened_by,
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
    """The highest case number currently in the graph.

    Used both to seed the counter on first use and to reconcile it on every
    allocation, because the generator writes cases directly with its own
    numbering and can leave the counter behind.

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


async def add_entity_to_case(
    driver: AsyncDriver, case_id: str, entity_human_id: str, reason: str, added_by: str = 'unknown'
) -> bool:
    info = resolve_label(entity_human_id)
    if info is None:
        return False
    async with driver.session() as session:
        result = await session.run(
            f"""
            MATCH (c:Case {{case_id: $case_id}})
            MATCH (e:{info.label} {{{info.id_field}: $entity_id}})
            MERGE (c)-[r:LINKED_TO]->(e)
            SET r.reason = $reason,
                r.added_at = $added_at,
                r.added_by = $added_by,
                // Re-linking previously removed evidence clears the tombstone
                // rather than leaving a link that claims to be both live and
                // removed.
                r.removed_at = null,
                r.removed_by = null,
                r.removal_reason = null
            RETURN c
            """,
            case_id=case_id,
            entity_id=entity_human_id,
            reason=reason,
            added_by=added_by,
            added_at=datetime.now(UTC).isoformat(),
        )
        return await result.single() is not None


async def remove_entity_from_case(
    driver: AsyncDriver, case_id: str, entity_human_id: str, removed_by: str = "unknown", reason: str = ""
) -> bool:
    """Tombstone an evidence link. Returns whether a live link was found.

    Previously this issued `DELETE r`, so the fact that a piece of evidence had
    ever been linked — and who removed it, and why — vanished with it (audit
    G-11). In an investigation that history is itself evidence, and its removal
    is exactly the action an audit trail exists to capture.
    """
    info = resolve_label(entity_human_id)
    if info is None:
        return False
    async with driver.session() as session:
        result = await session.run(
            f"""
            MATCH (c:Case {{case_id: $case_id}})-[r:LINKED_TO]->(e:{info.label} {{{info.id_field}: $entity_id}})
            WHERE r.removed_at IS NULL
            SET r.removed_at = $removed_at, r.removed_by = $removed_by, r.removal_reason = $reason
            RETURN r
            """,
            case_id=case_id,
            entity_id=entity_human_id,
            removed_at=datetime.now(UTC).isoformat(),
            removed_by=removed_by,
            reason=reason,
        )
        return await result.single() is not None


