"""Graph reads and writes for entity resolution.

Two responsibilities, and the split between them is the phase's central claim:

  * **Reading profiles.** The Cypher projection names only the properties the
    matcher is allowed to see. `risk_score`, `flags`, `community_ids` and
    `storyline_id` are not filtered out after the fetch — they are never
    selected, so no code path can accidentally reach them.

  * **Projecting decisions.** A `SAME_AS` relationship is written between two
    nodes that have been judged the same. It is a *projection*: the decision
    lives in `resolution_decisions` in Postgres, append-only, and this edge can
    be deleted and rebuilt from it at any time. Nothing here modifies an entity
    node, and there is no code in ARGUS that deletes one as part of a merge.
"""

from __future__ import annotations

from typing import Any

from neo4j import AsyncDriver

from app.repositories.entity_labels import resolve_label
from app.resolution.profile import (
    ID_FIELDS,
    SUPPORTED_TYPES,
    EntityProfile,
    allowed_source_keys,
    profile_from_node,
)


def _projection(entity_type: str) -> str:
    """The RETURN clause, built from the allowlist.

    Property names come from a module-level constant, never from a request, so
    this string interpolation cannot carry user input into Cypher.
    """
    keys = allowed_source_keys(entity_type)
    return ", ".join(f"n.{key} AS {key}" for key in keys)


async def fetch_profiles(
    driver: AsyncDriver, entity_type: str, *, limit: int = 5000, skip: int = 0
) -> list[EntityProfile]:
    if entity_type not in SUPPORTED_TYPES:
        raise ValueError(f"no match rules for entity type {entity_type!r}")

    query = f"""
    MATCH (n:{entity_type})
    WHERE n.{ID_FIELDS[entity_type]} IS NOT NULL
    RETURN {_projection(entity_type)}
    ORDER BY n.{ID_FIELDS[entity_type]}
    SKIP $skip LIMIT $limit
    """
    profiles: list[EntityProfile] = []
    async with driver.session() as session:
        result = await session.run(query, skip=skip, limit=limit)
        async for record in result:
            profile = profile_from_node(entity_type, dict(record))
            if profile is not None:
                profiles.append(profile)
    return profiles


async def fetch_profiles_by_refs(
    driver: AsyncDriver, entity_type: str, refs: list[str]
) -> dict[str, EntityProfile]:
    """Several profiles in one query, keyed by ref.

    Exists because the single-ref form was being called in a loop — once per
    candidate returned by the blocking index, on the ingestion path. A record
    whose blocking key matched 200 others cost 200 round trips, per record, per
    batch. Correct and unusably slow, which is the kind of defect that only
    shows up under a real feed.
    """
    if entity_type not in SUPPORTED_TYPES or not refs:
        return {}

    query = f"""
    MATCH (n:{entity_type})
    WHERE n.{ID_FIELDS[entity_type]} IN $refs
    RETURN {_projection(entity_type)}
    """
    profiles: dict[str, EntityProfile] = {}
    async with driver.session() as session:
        result = await session.run(query, refs=refs)
        async for record in result:
            profile = profile_from_node(entity_type, dict(record))
            if profile is not None:
                profiles[profile.ref] = profile
    return profiles


async def count_entities(driver: AsyncDriver, entity_type: str) -> int:
    if entity_type not in SUPPORTED_TYPES:
        return 0
    query = f"MATCH (n:{entity_type}) RETURN count(n) AS n"
    async with driver.session() as session:
        result = await session.run(query)
        record = await result.single()
    return int(record["n"]) if record else 0


async def fetch_profile(driver: AsyncDriver, ref: str) -> EntityProfile | None:
    """One profile by human id, or None if no such entity exists.

    None here is what closes a real gap: before this, a feed could record an
    observation whose subject was `PRS-9999999` and nothing in ARGUS would ever
    say that no such person existed. See `services/resolution.resolve_subject`.
    """
    info = resolve_label(ref)
    if info is None or info.label not in SUPPORTED_TYPES:
        return None

    entity_type = info.label
    query = f"""
    MATCH (n:{entity_type} {{{ID_FIELDS[entity_type]}: $ref}})
    RETURN {_projection(entity_type)}
    LIMIT 1
    """
    async with driver.session() as session:
        result = await session.run(query, ref=ref)
        record = await result.single()
    return profile_from_node(entity_type, dict(record)) if record else None


async def entity_exists(driver: AsyncDriver, ref: str) -> bool:
    info = resolve_label(ref)
    if info is None:
        return False
    query = f"MATCH (n:{info.label} {{{info.id_field}: $ref}}) RETURN count(n) > 0 AS found"
    async with driver.session() as session:
        result = await session.run(query, ref=ref)
        record = await result.single()
    return bool(record["found"]) if record else False


async def project_same_as(
    driver: AsyncDriver,
    *,
    entity_type: str,
    left_ref: str,
    right_ref: str,
    decision_id: int,
    decided_by: str,
    score: float | None,
) -> bool:
    """Write the SAME_AS edge for a merge decision.

    Undirected in meaning; stored in the canonical (left, right) direction so
    there is exactly one edge per pair. Traversals should match it without a
    direction.

    Returns False if either node is missing — a decision can legitimately name
    a record that no longer exists in the graph, and the ledger entry stands on
    its own regardless of whether the projection could be written.
    """
    if entity_type not in ID_FIELDS:
        return False
    id_field = ID_FIELDS[entity_type]
    query = f"""
    MATCH (a:{entity_type} {{{id_field}: $left}})
    MATCH (b:{entity_type} {{{id_field}: $right}})
    MERGE (a)-[r:SAME_AS]-(b)
      ON CREATE SET r.created_at = datetime()
    SET r.decision_id = $decision_id,
        r.decided_by = $decided_by,
        r.score = $score,
        r.updated_at = datetime()
    RETURN count(r) AS n
    """
    async with driver.session() as session:
        result = await session.run(
            query,
            left=left_ref,
            right=right_ref,
            decision_id=decision_id,
            decided_by=decided_by,
            score=score,
        )
        record = await result.single()
    return bool(record and record["n"])


async def remove_same_as(
    driver: AsyncDriver, *, entity_type: str, left_ref: str, right_ref: str
) -> bool:
    """Drop the projected edge. The decision that created it is untouched.

    This is the whole of what "un-merge" does to the graph, and it is why
    reversal costs nothing: no node was changed, no property was overwritten,
    and no record was absorbed into another.
    """
    if entity_type not in ID_FIELDS:
        return False
    id_field = ID_FIELDS[entity_type]
    query = f"""
    MATCH (a:{entity_type} {{{id_field}: $left}})-[r:SAME_AS]-(b:{entity_type} {{{id_field}: $right}})
    DELETE r
    RETURN count(r) AS n
    """
    async with driver.session() as session:
        result = await session.run(query, left=left_ref, right=right_ref)
        record = await result.single()
    return bool(record and record["n"])


async def same_as_count(driver: AsyncDriver) -> int:
    async with driver.session() as session:
        result = await session.run("MATCH ()-[r:SAME_AS]->() RETURN count(r) AS n")
        record = await result.single()
    return int(record["n"]) if record else 0


async def rebuild_same_as(
    driver: AsyncDriver, pairs: list[tuple[str, str, str, int, str, float | None]]
) -> dict[str, int]:
    """Discard every projected edge and re-derive it from the ledger.

    Exists so the graph can be proved to be a function of the decisions rather
    than an accumulation of them: if the projection ever disagrees with
    Postgres, this makes Postgres win. `pairs` is
    (entity_type, left, right, decision_id, decided_by, score).
    """
    async with driver.session() as session:
        await session.run("MATCH ()-[r:SAME_AS]-() DELETE r")

    written = 0
    for entity_type, left, right, decision_id, decided_by, score in pairs:
        if await project_same_as(
            driver,
            entity_type=entity_type,
            left_ref=left,
            right_ref=right,
            decision_id=decision_id,
            decided_by=decided_by,
            score=score,
        ):
            written += 1
    return {"requested": len(pairs), "written": written, "missing": len(pairs) - written}


async def same_as_neighbours(driver: AsyncDriver, ref: str) -> list[dict[str, Any]]:
    """Records joined to this one by a projected merge, for the entity profile."""
    info = resolve_label(ref)
    if info is None or info.label not in SUPPORTED_TYPES:
        return []
    id_field = ID_FIELDS[info.label]
    query = f"""
    MATCH (a:{info.label} {{{id_field}: $ref}})-[r:SAME_AS]-(b:{info.label})
    RETURN b.{id_field} AS ref, r.decision_id AS decision_id, r.score AS score,
           r.decided_by AS decided_by
    ORDER BY ref
    """
    async with driver.session() as session:
        result = await session.run(query, ref=ref)
        return [dict(record) async for record in result]
