"""Integration tests for case_repo against a real Neo4j.

These pin audit B-02: `next_case_sequence` read `count(c) + 1` in one query and
wrote in another, with no uniqueness constraint behind it. Two concurrent
creates allocated the same case_id, Neo4j accepted both, and `get_case`'s
`.single()` then raised permanently for that id — the case detail page was
broken with no way to recover through the UI.
"""

from __future__ import annotations

import asyncio

import pytest
from neo4j import AsyncDriver

from app.repositories import case_repo

pytestmark = pytest.mark.asyncio


async def _cleanup_cases(driver: AsyncDriver, case_ids: list[str]) -> None:
    if not case_ids:
        return
    async with driver.session() as session:
        await session.run("MATCH (c:Case) WHERE c.case_id IN $ids DETACH DELETE c", ids=case_ids)


async def test_create_case_returns_a_persisted_case(graph: AsyncDriver) -> None:
    case = await case_repo.create_case(graph, "Integration probe", "Low", "notes")
    try:
        assert case["case_id"].startswith("CASE-")
        assert case["status"] == "Draft"
        assert case["closed_at"] is None

        fetched = await case_repo.get_case(graph, case["case_id"])
        assert fetched is not None
        assert fetched["title"] == "Integration probe"
    finally:
        await _cleanup_cases(graph, [case["case_id"]])


async def test_concurrent_creates_never_collide(graph: AsyncDriver) -> None:
    """The B-02 regression. Fails against the pre-migration implementation."""
    concurrency = 25
    cases = await asyncio.gather(
        *[case_repo.create_case(graph, f"Concurrent {i}", "Low", "") for i in range(concurrency)]
    )
    ids = [c["case_id"] for c in cases]
    try:
        assert len(set(ids)) == concurrency, f"duplicate case_ids allocated: {ids}"

        # Each must remain individually fetchable. A duplicate id makes
        # get_case's .single() raise, so this asserts the user-visible symptom
        # and not merely the underlying uniqueness.
        for case_id in ids:
            assert await case_repo.get_case(graph, case_id) is not None
    finally:
        await _cleanup_cases(graph, ids)


async def test_uniqueness_constraint_rejects_a_duplicate_case_id(graph: AsyncDriver) -> None:
    """The database itself must refuse a duplicate, independently of application
    logic — the constraint is the backstop if sequencing is ever bypassed."""
    case = await case_repo.create_case(graph, "Constraint probe", "Low", "")
    try:
        with pytest.raises(Exception) as exc_info:
            async with graph.session() as session:
                await session.run(
                    "CREATE (c:Case {case_id: $case_id, id: 'duplicate-probe'})",
                    case_id=case["case_id"],
                )
        assert "constraint" in str(exc_info.value).lower()
    finally:
        await _cleanup_cases(graph, [case["case_id"]])


async def test_update_case_rejects_fields_outside_the_whitelist(graph: AsyncDriver) -> None:
    """`SET c += $updates` would have accepted any key, including case_id and
    opened_at."""
    case = await case_repo.create_case(graph, "Whitelist probe", "Low", "")
    try:
        with pytest.raises(ValueError, match="not updatable"):
            await case_repo.update_case(graph, case["case_id"], {"case_id": "CASE-9999"})
        with pytest.raises(ValueError, match="not updatable"):
            await case_repo.update_case(graph, case["case_id"], {"opened_at": "1999-01-01"})

        unchanged = await case_repo.get_case(graph, case["case_id"])
        assert unchanged is not None
        assert unchanged["case_id"] == case["case_id"]
    finally:
        await _cleanup_cases(graph, [case["case_id"]])


async def test_closing_a_case_records_closed_at(graph: AsyncDriver) -> None:
    """`closed_at` was declared at creation and typed in the frontend but never
    written by any code path, so a closed case had no closure time."""
    case = await case_repo.create_case(graph, "Closure probe", "Low", "")
    try:
        closed = await case_repo.update_case(graph, case["case_id"], {"status": "Closed"})
        assert closed is not None
        assert closed["closed_at"] is not None

        # Reopening must clear it: a stale timestamp would assert the case was
        # closed at a moment it demonstrably was not.
        reopened = await case_repo.update_case(graph, case["case_id"], {"status": "Open"})
        assert reopened is not None
        assert reopened["closed_at"] is None
    finally:
        await _cleanup_cases(graph, [case["case_id"]])


async def test_update_case_returns_none_for_a_missing_case(graph: AsyncDriver) -> None:
    assert await case_repo.update_case(graph, "CASE-DOES-NOT-EXIST", {"status": "Open"}) is None
