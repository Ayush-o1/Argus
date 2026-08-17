"""Risk assessment end to end, against a real Neo4j and a real PostgreSQL.

What a mock could not tell you, and these do: that the append-only triggers
refuse an edit the application never attempts, that the graph projection is
genuinely rebuildable from the ledger, and that a subject with no evidence
survives the whole round trip with a NULL score rather than a zero.

The tests seed their own small world rather than relying on the generated one,
so they assert the same thing on a developer's populated graph and on CI's
empty one. Everything they write is removed afterwards — including the
Postgres rows, which the application itself is not permitted to delete. A test
suite that quietly published thousands of assessments and assertions nobody ran
would be corrupting the record it exists to protect.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta

import asyncpg
import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from app.assessment.model import (
    BAND_ELEVATED,
    BAND_INSUFFICIENT,
    BAND_ROUTINE,
    default_model,
)
from app.config import get_settings
from app.repositories import assessment_graph_repo, assessment_repo
from app.services import assessment as service

pytestmark = pytest.mark.asyncio

BASE = datetime(2026, 3, 1, 9, 0, 0)
RING_SIZE = 6


@pytest_asyncio.fixture
async def pg_admin() -> AsyncIterator[asyncpg.Connection]:
    """Superuser connection, used only to undo what the tests wrote.

    The application role cannot delete an assessment and neither can the
    superuser without disabling the trigger first — which is the property under
    test in `test_assessments_are_append_only`, exercised here in reverse.
    """
    settings = get_settings()
    try:
        conn = await asyncpg.connect(dsn=settings.postgres_admin_dsn, timeout=5)
    except Exception:
        pytest.skip("No PostgreSQL reachable; skipping assessment integration test")
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def ledger(pg_admin: asyncpg.Connection) -> AsyncIterator[None]:
    """Records a high-water mark, then removes everything written above it."""
    from app.database.postgres import close_postgres, connect_postgres

    await connect_postgres()
    before_run = await pg_admin.fetchval("SELECT coalesce(max(run_id), 0) FROM assessment_runs")
    before_assertion = await pg_admin.fetchval("SELECT count(*) FROM assertions")
    started = await pg_admin.fetchval("SELECT now()")
    try:
        yield
    finally:
        async with pg_admin.transaction():
            for table, trigger in (
                ("assessment_signals", "assessment_signals_no_update"),
                ("assessments", "assessments_no_delete"),
                ("assessment_evaluations", "assessment_evaluations_no_delete"),
            ):
                await pg_admin.execute(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}")
            await pg_admin.execute(
                "DELETE FROM assessment_signals WHERE assessment_id IN "
                "(SELECT assessment_id FROM assessments WHERE run_id > $1)",
                before_run,
            )
            await pg_admin.execute("DELETE FROM assessments WHERE run_id > $1", before_run)
            await pg_admin.execute(
                "DELETE FROM assessment_evaluations WHERE run_id > $1", before_run
            )
            await pg_admin.execute("DELETE FROM assessment_runs WHERE run_id > $1", before_run)
            for table, trigger in (
                ("assessment_signals", "assessment_signals_no_update"),
                ("assessments", "assessments_no_delete"),
                ("assessment_evaluations", "assessment_evaluations_no_delete"),
            ):
                await pg_admin.execute(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}")

            # Assertions are append-only too, and this phase publishes them.
            # Supersession makes them a linked list, so the pointers into the
            # doomed rows have to be cleared before the rows can go — which
            # needs the content-immutability trigger down as well, since that
            # one permits `superseded_by` to be set but never unset.
            await pg_admin.execute("ALTER TABLE assertions DISABLE TRIGGER assertions_no_delete")
            await pg_admin.execute(
                "ALTER TABLE assertions DISABLE TRIGGER assertions_immutable_content"
            )
            await pg_admin.execute(
                "ALTER TABLE assertion_evidence DISABLE TRIGGER assertion_evidence_no_delete"
            )
            doomed = [
                row["assertion_id"]
                for row in await pg_admin.fetch(
                    "SELECT assertion_id FROM assertions WHERE asserted_at > $1", started
                )
            ]
            if doomed:
                await pg_admin.execute(
                    "UPDATE assertions SET superseded_by = NULL, superseded_at = NULL "
                    "WHERE superseded_by = ANY($1::uuid[])",
                    doomed,
                )
                await pg_admin.execute(
                    "DELETE FROM assertion_evidence WHERE assertion_id = ANY($1::uuid[])", doomed
                )
                await pg_admin.execute(
                    "DELETE FROM assertions WHERE assertion_id = ANY($1::uuid[])", doomed
                )
            # Retractions this run applied to pre-existing assertions are undone
            # too, so a test cannot leave a real finding marked as withdrawn.
            await pg_admin.execute(
                "UPDATE assertions SET retracted_at = NULL, retracted_by = NULL, "
                "retraction_reason = NULL WHERE retracted_at > $1",
                started,
            )
            await pg_admin.execute(
                "ALTER TABLE assertion_evidence ENABLE TRIGGER assertion_evidence_no_delete"
            )
            await pg_admin.execute(
                "ALTER TABLE assertions ENABLE TRIGGER assertions_immutable_content"
            )
            await pg_admin.execute("ALTER TABLE assertions ENABLE TRIGGER assertions_no_delete")

            remaining = await pg_admin.fetchval("SELECT count(*) FROM assertions")
            assert remaining == before_assertion, (
                "the test suite must leave the provenance store exactly as it found it"
            )
        await close_postgres()


@pytest_asyncio.fixture
async def world(graph: AsyncDriver, tag: str) -> str:
    """A ring of accounts moving money in a circle, plus two control subjects.

    Deliberately small and hand-built. Numbers chosen so the expected answer is
    readable from the fixture: six accounts, each hop retaining 95%, all inside
    a day.
    """
    async with graph.session() as session:
        await session.run(
            """
            CREATE (p:Person {person_id: $owner, name: 'Ring Holder', _test_tag: $tag})
            CREATE (q:Person {person_id: $bare, name: 'No Evidence', _test_tag: $tag})
            """,
            owner=f"PRS-9{tag[-6:]}",
            bare=f"PRS-8{tag[-6:]}",
            tag=tag,
        )
        for i in range(RING_SIZE):
            await session.run(
                """
                CREATE (a:Account {account_id: $account_id, offshore: false, _test_tag: $tag})
                """,
                account_id=f"ACC-9{tag[-5:]}{i}",
                tag=tag,
            )
        await session.run(
            """
            MATCH (p:Person {person_id: $owner}), (a:Account {account_id: $first})
            CREATE (p)-[:OWNS_ACCOUNT]->(a)
            """,
            owner=f"PRS-9{tag[-6:]}",
            first=f"ACC-9{tag[-5:]}0",
        )
        amount = 500_000.0
        for i in range(RING_SIZE):
            amount *= 0.95
            await session.run(
                """
                MATCH (a:Account {account_id: $src}), (b:Account {account_id: $dst})
                CREATE (a)-[:TRANSACTED_WITH {
                    tx_id: $tx_id, amount: $amount, timestamp: $timestamp
                }]->(b)
                """,
                src=f"ACC-9{tag[-5:]}{i}",
                dst=f"ACC-9{tag[-5:]}{(i + 1) % RING_SIZE}",
                tx_id=f"TXN-9{tag[-5:]}{i}",
                amount=round(amount, 2),
                timestamp=(BASE + timedelta(hours=3 * i)).isoformat(),
            )
    return tag


def owner_ref(tag: str) -> str:
    return f"PRS-9{tag[-6:]}"


def bare_ref(tag: str) -> str:
    return f"PRS-8{tag[-6:]}"


# ─────────────────────────────────────────────────────────────────────────────


async def test_a_planted_ring_is_found_and_explained(
    graph: AsyncDriver, world: str, ledger: None
) -> None:
    """The signal fires, and the finding names the accounts and the amounts.

    A band on its own is an opinion. The test asserts the working is there,
    because a finding an analyst cannot check is not reviewable, and an
    unreviewable finding is exactly what this phase replaced.
    """
    await service.run_assessment(graph, triggered_by="user:test", publish_assertions=False)

    owner = await assessment_repo.current_for_subject(owner_ref(world))
    assert owner is not None
    assert owner.band == BAND_ELEVATED
    assert owner.score == 100.0

    cycle = next(s for s in owner.signals if s["signal_id"] == "funds_cycle")
    assert cycle["evaluable"] is True
    assert cycle["magnitude"] == 1.0
    assert cycle["detail"]["hops"] == RING_SIZE
    assert len(cycle["detail"]["accounts"]) == RING_SIZE + 1
    assert f"ACC-9{world[-5:]}0" in cycle["detail"]["accounts"]
    assert "ring" in cycle["summary"].lower()


async def test_a_subject_with_no_evidence_survives_the_round_trip_unscored(
    graph: AsyncDriver, world: str, ledger: None, pg_admin: asyncpg.Connection
) -> None:
    """NULL, not 0, all the way into the column.

    Checked in the database rather than in Python, because a zero written here
    would let any future `ORDER BY score` sort an unexamined subject into the
    middle of the queue as though it had been cleared.
    """
    await service.run_assessment(graph, triggered_by="user:test", publish_assertions=False)

    row = await pg_admin.fetchrow(
        "SELECT band, score FROM assessment_current WHERE subject_ref = $1", bare_ref(world)
    )
    assert row is not None
    assert row["band"] == BAND_INSUFFICIENT
    assert row["score"] is None


async def test_the_database_refuses_a_band_and_score_that_disagree(
    pg_admin: asyncpg.Connection, ledger: None
) -> None:
    """The rule lives in a CHECK constraint, so it holds against any writer —
    including a future code path that has not been reviewed."""
    run_id = await pg_admin.fetchval(
        "INSERT INTO assessment_runs (model_version, model_fingerprint, triggered_by) "
        "VALUES ('test', 'test', 'pytest') RETURNING run_id"
    )
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await pg_admin.execute(
            """
            INSERT INTO assessments (
                run_id, subject_ref, subject_type, band, score,
                evidence_coverage, evaluable_weight, total_weight,
                model_version, model_fingerprint, computed_at
            ) VALUES ($1, 'PRS-TEST', 'Person', 'insufficient_evidence', 42.0,
                      0.1, 1, 10, 'test', 'test', now())
            """,
            run_id,
        )


async def test_assessments_are_append_only(
    graph: AsyncDriver, world: str, ledger: None, pg_admin: asyncpg.Connection
) -> None:
    """A dated claim that can be edited afterwards is not a record of what was
    believed. Enforced by trigger, so it holds even for the superuser."""
    await service.run_assessment(graph, triggered_by="user:test", publish_assertions=False)
    assert await pg_admin.fetchval("SELECT count(*) FROM assessments") > 0

    for statement in (
        "UPDATE assessments SET score = 1",
        "DELETE FROM assessments WHERE true",
    ):
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await pg_admin.execute(statement)


async def test_rerunning_appends_a_generation_rather_than_editing_one(
    graph: AsyncDriver, world: str, ledger: None
) -> None:
    await service.run_assessment(graph, triggered_by="user:test", publish_assertions=False)
    await service.run_assessment(graph, triggered_by="user:test", publish_assertions=False)

    history = await assessment_repo.history_for_subject(owner_ref(world))
    assert len(history) >= 2, "the earlier assessment must still be readable"

    current = await assessment_repo.current_for_subject(owner_ref(world))
    assert current is not None
    assert current.computed_at == max(h.computed_at for h in history)


async def test_the_graph_projection_is_rebuildable_from_the_ledger(
    graph: AsyncDriver, world: str, ledger: None
) -> None:
    """The claim that the graph properties are a cache, tested by destroying
    them and asking for them back.

    If this ever produced a different answer, one of the two stores would be
    lying and there would be no way to tell which.
    """
    await service.run_assessment(graph, triggered_by="user:test", publish_assertions=False)

    async def projected() -> dict:
        async with graph.session() as session:
            result = await session.run(
                "MATCH (n) WHERE n._test_tag = $tag AND n.argus_band IS NOT NULL "
                "RETURN n.person_id AS person, n.account_id AS account, n.argus_band AS band, "
                "n.argus_score AS score, n.argus_coverage AS coverage",
                tag=world,
            )
            return {
                (record["person"] or record["account"]): (
                    record["band"],
                    record["score"],
                    record["coverage"],
                )
                async for record in result
            }

    before = await projected()
    assert before, "the run should have projected onto the seeded nodes"

    cleared = await assessment_graph_repo.clear_projection(graph)
    assert cleared > 0
    assert await projected() == {}

    await service.rebuild_projection(graph)
    assert await projected() == before


async def test_the_projection_leaves_the_generators_number_untouched(
    graph: AsyncDriver, tag: str, ledger: None
) -> None:
    """The synthetic risk score is a source's claim, and provenance holds an
    assertion describing it. Overwriting it would make that assertion describe
    a value that no longer exists."""
    async with graph.session() as session:
        await session.run(
            "CREATE (p:Person {person_id: $ref, name: 'Keeps Its Score', "
            "risk_score: 73.5, _test_tag: $tag})",
            ref=f"PRS-7{tag[-6:]}",
            tag=tag,
        )

    await service.run_assessment(graph, triggered_by="user:test", publish_assertions=False)

    async with graph.session() as session:
        record = await (
            await session.run(
                "MATCH (p:Person {person_id: $ref}) RETURN p.risk_score AS generator, "
                "p.argus_band AS argus",
                ref=f"PRS-7{tag[-6:]}",
            )
        ).single()
    assert record is not None
    assert record["generator"] == 73.5, "the source's own claim must be preserved verbatim"
    assert record["argus"] == BAND_INSUFFICIENT


async def test_an_unassessable_subject_gets_no_projected_score(
    graph: AsyncDriver, world: str, ledger: None
) -> None:
    """Absent, not zero — so a Cypher `ORDER BY n.argus_score DESC` cannot rank
    a subject ARGUS never examined."""
    await service.run_assessment(graph, triggered_by="user:test", publish_assertions=False)

    async with graph.session() as session:
        record = await (
            await session.run(
                "MATCH (p:Person {person_id: $ref}) "
                "RETURN p.argus_band AS band, p.argus_score AS score",
                ref=bare_ref(world),
            )
        ).single()
    assert record is not None
    assert record["band"] == BAND_INSUFFICIENT
    assert record["score"] is None


async def test_findings_are_published_as_inferred_assertions(
    graph: AsyncDriver, world: str, ledger: None, pg_admin: asyncpg.Connection
) -> None:
    """What ARGUS believes has to reach provenance, or the entity page would
    show a conclusion the provenance tab could not account for."""
    model = default_model()
    outcome = await service.run_assessment(graph, triggered_by="user:test")
    assert outcome.assertions_published >= 1

    row = await pg_admin.fetchrow(
        """
        SELECT * FROM assertions
         WHERE subject_ref = $1 AND predicate = 'argus_risk_assessment'
         ORDER BY asserted_at DESC LIMIT 1
        """,
        owner_ref(world),
    )
    assert row is not None
    assert row["epistemic_kind"] == "inferred"
    assert row["reliability"] == "F", "one synthetic measurement is not a track record"
    assert row["method"] == model.method
    assert model.short_fingerprint in row["method"]
    assert row["asserted_by"] == "source:argus.derived"
    assert "recommendation to review" in row["note"]


async def test_a_routine_subject_is_not_asserted_about(
    graph: AsyncDriver, tag: str, ledger: None, pg_admin: asyncpg.Connection
) -> None:
    """`routine` is a real finding and it is not a belief about the subject.

    Publishing one assertion per unremarkable entity would bury the provenance
    store; the assessment itself stays readable through the assessment API.
    """
    async with graph.session() as session:
        await session.run(
            """
            CREATE (s:Shipment {shipment_id: $ref, detour_ratio: 1.0,
                origin_region: 'Europe', destination_region: 'East Asia',
                manifest: 'Textile rolls', declared_manifest: 'Textile rolls',
                _test_tag: $tag})
            """,
            ref=f"SHP-9{tag[-6:]}",
            tag=tag,
        )
    await service.run_assessment(graph, triggered_by="user:test")

    assessment = await assessment_repo.current_for_subject(f"SHP-9{tag[-6:]}")
    assert assessment is not None and assessment.band == BAND_ROUTINE

    count = await pg_admin.fetchval(
        "SELECT count(*) FROM assertions WHERE subject_ref = $1 AND predicate = $2",
        f"SHP-9{tag[-6:]}",
        "argus_risk_assessment",
    )
    assert count == 0


async def test_the_run_records_what_the_evidence_sweep_saw(
    graph: AsyncDriver, world: str, ledger: None
) -> None:
    """A run that saw fewer transfers than the last one produced different
    scores for a reason that has nothing to do with the subjects."""
    await service.run_assessment(graph, triggered_by="user:test", publish_assertions=False)

    run = await assessment_repo.latest_run()
    assert run is not None
    assert run.status == "complete"
    assert run.evidence_summary["transfers"] >= RING_SIZE
    assert run.evidence_summary["cycles_found"] >= 1
    assert run.search_truncated is False
    assert run.subjects_assessed == (
        run.elevated_count + run.notable_count + run.routine_count + run.insufficient_count
    ), "the bands must account for every subject assessed"


async def test_evaluation_reports_what_the_model_cannot_detect(
    graph: AsyncDriver, world: str, ledger: None
) -> None:
    """The report has to name the planted phenomena no admissible signal can
    reach, rather than quietly computing recall over the detectable subset."""
    await service.run_assessment(graph, triggered_by="user:test", publish_assertions=False)
    report = await service.run_evaluation(graph, triggered_by="user:test")

    undetectable = [row for row in report.per_storyline if not row.detectable]
    assert {row.storyline_type for row in undetectable} == {
        "identity_overlap",
        "document_forgery_ring",
    }
    for row in undetectable:
        assert row.note, "a zero recall has to come with the reason for it"
        assert row.reached_notable_or_better == 0

    assert report.model_fingerprint == default_model().fingerprint()
    assert any("synthetic world" in caveat for caveat in report.caveats)
    assert report.elevated.precision is None or 0.0 <= report.elevated.precision <= 1.0
