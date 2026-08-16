"""The ingestion pipeline end to end, against real PostgreSQL and a real folder.

The acceptance criteria for this phase are mostly negative — what must *not*
happen — and they are asserted here directly: the same payload twice must not
create two observations, a malformed record must not be dropped, and a source
that goes quiet must not look like a world in which nothing happened.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from app.config import get_settings
from app.database.postgres import acquire, close_postgres, connect_postgres
from app.ingestion.connectors import INGEST_ROOT_ENV
from app.models.provenance import Reliability, Source, SourceType
from app.repositories import ingest_repo, provenance_repo
from app.services import ingest

pytestmark = pytest.mark.asyncio

# Since Phase 4, ingestion checks that a subject *exists* rather than only that
# its id has a recognised prefix, so these tests need a real node to point at.
#
# The fixture creates it rather than relying on one being there. Depending on
# seeded generator data made the whole file skip against a freshly migrated
# graph — which is exactly what CI has — and CI correctly treats a skipped
# integration test as a failure, because a green run that exercised nothing is
# worse than a red one.
#
# The id sits far outside the generator's allocations so it can never collide
# with, or be mistaken for, a real record.
SUBJECT = "PRS-9910001"
SUBJECT_MARKER = "argus-ingest-test"


@pytest_asyncio.fixture
async def feed(
    driver: AsyncDriver, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[dict]:
    """A registered source, a connector, and a drop folder — torn down after.

    Takes the graph from the shared `driver` fixture rather than calling the
    application's `connect_neo4j()`. That distinction is not cosmetic: the app
    driver reads `NEO4J_URI`/`NEO4J_PASSWORD`, which CI deliberately does not
    set for the test step — it sets `TEST_NEO4J_*`, which only the conftest
    fixture honours. Using the app driver meant every test in this file errored
    in CI while passing on any machine where both happened to be configured.
    """
    settings = get_settings()
    try:
        probe = await asyncpg.connect(dsn=settings.postgres_dsn, timeout=5)
    except Exception:
        pytest.skip("No PostgreSQL reachable; skipping ingestion integration tests")
    await probe.close()

    # The ingestion service resolves subjects through the process-wide driver,
    # so point that at the test graph for the duration.
    import app.database.neo4j as neo4j_module

    previous_driver = getattr(neo4j_module, "_driver", None)
    neo4j_module._driver = driver

    async with driver.session() as session:
        await session.run(
            """
            MERGE (p:Person {person_id: $ref})
            SET p.id = coalesce(p.id, randomUUID()),
                p.name = 'Ingest Fixture Subject',
                p.marker = $marker
            """,
            ref=SUBJECT,
            marker=SUBJECT_MARKER,
        )

    await connect_postgres()

    root = tmp_path / "ingest"
    directory = root / "feed"
    directory.mkdir(parents=True)
    monkeypatch.setenv(INGEST_ROOT_ENV, str(root))

    marker = uuid.uuid4().hex[:12]
    source_id = f"test.{marker}"
    connector_id = f"test-{marker}"

    await provenance_repo.register_source(
        Source(
            source_id=source_id,
            name=f"Test feed {marker}",
            source_type=SourceType.PARTNER,
            description="integration fixture",
            reliability=Reliability.C,
            reliability_basis="fixture",
            is_synthetic=False,
            independence_group=source_id,
            staleness_hours=24,
        )
    )
    await ingest_repo.upsert_connector(
        connector_id=connector_id,
        source_id=source_id,
        connector_type="filesystem",
        display_name=f"Test feed {marker}",
        config={"directory": "feed"},
        mapping={
            "content_type": "test.report",
            "subject_path": "entity_id",
            "occurred_at_path": "observed_at",
            "timezone": "UTC",
            "required_fields": ["entity_id"],
        },
        poll_interval_seconds=10,
    )

    try:
        yield {
            "source_id": source_id,
            "connector_id": connector_id,
            "directory": directory,
            "marker": marker,
        }
    finally:
        # Raw landing and the dead-letter queue are append-only by design, so
        # clearing them requires the admin role *and* disabling triggers — two
        # deliberate acts, which is exactly the cost the design intends.
        admin = await asyncpg.connect(dsn=settings.postgres_admin_dsn)
        try:
            async with admin.transaction():
                for table in ("raw_records", "ingest_failures", "observations",
                              "observation_subjects", "assertions", "assertion_evidence"):
                    await admin.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
                await admin.execute(
                    "DELETE FROM ingest_failures WHERE connector_id = $1", connector_id
                )
                await admin.execute("DELETE FROM raw_records WHERE connector_id = $1", connector_id)
                await admin.execute(
                    "DELETE FROM connector_field_stats WHERE connector_id = $1", connector_id
                )
                await admin.execute("DELETE FROM ingest_batches WHERE connector_id = $1", connector_id)
                await admin.execute("DELETE FROM connectors WHERE connector_id = $1", connector_id)
                await admin.execute(
                    """
                    DELETE FROM observation_subjects WHERE observation_id IN (
                        SELECT observation_id FROM observations WHERE source_id = $1
                    )
                    """,
                    source_id,
                )
                await admin.execute("DELETE FROM observations WHERE source_id = $1", source_id)
                await admin.execute("DELETE FROM sources WHERE source_id = $1", source_id)
                for table in ("raw_records", "ingest_failures", "observations",
                              "observation_subjects", "assertions", "assertion_evidence"):
                    await admin.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")
        finally:
            await admin.close()
        await close_postgres()
        async with driver.session() as session:
            await session.run(
                "MATCH (n {marker: $marker}) DETACH DELETE n", marker=SUBJECT_MARKER
            )
        neo4j_module._driver = previous_driver


def _write(directory: Path, name: str, records: list[dict]) -> None:
    (directory / name).write_text("\n".join(json.dumps(r) for r in records))


# ── The acceptance criteria ──────────────────────────────────────────────────


async def test_a_record_becomes_an_attributed_observation(feed: dict) -> None:
    _write(
        feed["directory"],
        "a.jsonl",
        [{"entity_id": SUBJECT, "observed_at": "2026-08-01T10:00:00Z", "note": "seen"}],
    )
    outcome = await ingest.run_connector(feed["connector_id"])
    assert outcome.new == 1 and outcome.failed == 0

    observations = await provenance_repo.observations_for_subject(SUBJECT)
    mine = [o for o in observations if o.source_id == feed["source_id"]]
    assert len(mine) == 1
    assert mine[0].payload["note"] == "seen"
    assert mine[0].source_is_synthetic is False
    # Declared timezone, so the instant is derivable and stated.
    assert mine[0].occurred_at is not None
    # The source never sent a collection time, and nothing invents one.
    assert mine[0].collected_at is None


async def test_the_same_payload_twice_yields_one_observation(feed: dict) -> None:
    """The phase's headline idempotency requirement.

    Without it, re-reading one file inflates every corroboration count derived
    from it — a single source starts looking like several.
    """
    record = [{"entity_id": SUBJECT, "observed_at": "2026-08-01T10:00:00Z"}]
    _write(feed["directory"], "a.jsonl", record)
    first = await ingest.run_connector(feed["connector_id"])

    # Same content, new file, and the cursor reset so the connector re-reads it.
    _write(feed["directory"], "b.jsonl", record)
    second = await ingest.run_connector(feed["connector_id"])

    assert first.new == 1
    assert second.new == 0
    assert second.duplicate == 1

    observations = await provenance_repo.observations_for_subject(SUBJECT)
    assert len([o for o in observations if o.source_id == feed["source_id"]]) == 1


async def test_a_malformed_record_lands_in_the_dlq_and_is_never_dropped(feed: dict) -> None:
    """The failure mode that matters most: a silent drop makes an intelligence
    gap invisible, because the analyst sees no data and concludes there was
    nothing to see."""
    _write(
        feed["directory"],
        "a.jsonl",
        [
            {"entity_id": SUBJECT, "observed_at": "2026-08-01T10:00:00Z"},
            {"observed_at": "2026-08-01T10:00:00Z"},  # no subject
            {"entity_id": "NOSUCH-0001", "observed_at": "2026-08-01T10:00:00Z"},
        ],
    )
    outcome = await ingest.run_connector(feed["connector_id"])
    assert outcome.new == 1
    assert outcome.failed == 2

    failures = await ingest_repo.list_failures(connector_id=feed["connector_id"])
    assert len(failures) == 2
    assert {f["stage"] for f in failures} == {"validate"}
    # Every rejection states a reason a human can act on.
    assert all(f["error_detail"] for f in failures)

    # And the payload is still there, which is what makes replay possible.
    for failure in failures:
        raw = await ingest_repo.get_raw(failure["raw_id"])
        assert raw is not None
        assert raw["status"] == "failed"


async def test_a_dead_lettered_record_can_be_replayed_after_the_mapping_is_fixed(
    feed: dict,
) -> None:
    """Why raw landing is worth its storage. The mapping was wrong; the fix is
    to correct it and replay. A pipeline that discarded its input could only be
    fixed going forward."""
    _write(feed["directory"], "a.jsonl", [{"ref": SUBJECT, "observed_at": "2026-08-01T10:00:00Z"}])
    outcome = await ingest.run_connector(feed["connector_id"])
    assert outcome.failed == 1

    failure = (await ingest_repo.list_failures(connector_id=feed["connector_id"]))[0]

    # The subject was under `ref`, not `entity_id`. Correct the mapping.
    await ingest_repo.upsert_connector(
        connector_id=feed["connector_id"],
        source_id=feed["source_id"],
        connector_type="filesystem",
        display_name="fixed",
        config={"directory": "feed"},
        mapping={
            "content_type": "test.report",
            "subject_path": "ref",
            "occurred_at_path": "observed_at",
            "timezone": "UTC",
        },
    )

    result = await ingest.replay_failure(failure["failure_id"], actor="user:test")
    assert result["succeeded"] is True

    observations = await provenance_repo.observations_for_subject(SUBJECT)
    assert any(o.source_id == feed["source_id"] for o in observations)

    resolved = await ingest_repo.list_failures(
        connector_id=feed["connector_id"], include_resolved=True
    )
    assert resolved[0]["resolved_at"] is not None
    assert resolved[0]["replay_count"] == 1


async def test_a_schema_change_is_detected(feed: dict) -> None:
    """A source that quietly starts emitting a new field does not error; the
    data just means something different from then on."""
    _write(feed["directory"], "a.jsonl", [{"entity_id": SUBJECT, "observed_at": "2026-08-01T10:00:00Z"}])
    await ingest.run_connector(feed["connector_id"])

    _write(
        feed["directory"],
        "b.jsonl",
        [{"entity_id": SUBJECT, "observed_at": "2026-08-02T10:00:00Z", "threat_level": "high"}],
    )
    outcome = await ingest.run_connector(feed["connector_id"])

    assert "threat_level" in outcome.new_fields
    assert any("schema change" in w for w in outcome.warnings)

    known = {f["field_path"] for f in await ingest_repo.known_fields(feed["connector_id"])}
    assert {"entity_id", "observed_at", "threat_level"} <= known


async def test_a_source_that_stops_producing_is_reported_as_stale(feed: dict) -> None:
    """A feed that goes silent looks exactly like a world in which nothing is
    happening. The only defence is an explicit expectation to measure against."""
    _write(feed["directory"], "a.jsonl", [{"entity_id": SUBJECT, "observed_at": "2026-08-01T10:00:00Z"}])
    await ingest.run_connector(feed["connector_id"])

    assert not [s for s in await ingest.stale_sources() if s["connector_id"] == feed["connector_id"]]

    # Age the last success past the source's declared 24h expectation.
    async with acquire() as conn:
        await conn.execute(
            "UPDATE connectors SET last_success_at = now() - interval '48 hours' WHERE connector_id = $1",
            feed["connector_id"],
        )

    stale = [s for s in await ingest.stale_sources() if s["connector_id"] == feed["connector_id"]]
    assert len(stale) == 1
    assert "against a declared expectation of 24h" in stale[0]["reason"]


async def test_a_source_with_no_declared_expectation_is_never_called_stale(feed: dict) -> None:
    """A made-up threshold produces made-up alerts. No declaration means no
    claim, rather than a default nobody chose."""
    async with acquire() as conn:
        await conn.execute(
            "UPDATE connectors SET last_success_at = now() - interval '400 days' WHERE connector_id = $1",
            feed["connector_id"],
        )
    # `sources` is INSERT/SELECT-only for the application role — a reliability
    # rating is not something the app may quietly rewrite — so changing one in a
    # test needs the admin connection. The privilege boundary holding here is
    # the point, not an inconvenience.
    admin = await asyncpg.connect(dsn=get_settings().postgres_admin_dsn)
    try:
        await admin.execute(
            "UPDATE sources SET staleness_hours = NULL WHERE source_id = $1", feed["source_id"]
        )
    finally:
        await admin.close()
    assert not [s for s in await ingest.stale_sources() if s["connector_id"] == feed["connector_id"]]


async def test_a_connector_failing_wholesale_is_quarantined_not_left_to_fill_the_dlq(
    feed: dict,
) -> None:
    records = [{"entity_id": "NOSUCH-0001", "observed_at": "2026-08-01T10:00:00Z"} for _ in range(25)]
    for index, record in enumerate(records):
        record["seq"] = index  # distinct content hashes
    _write(feed["directory"], "a.jsonl", records)

    outcome = await ingest.run_connector(feed["connector_id"])
    assert outcome.failed == 25
    assert any("Quarantined" in w or "quarantined" in w for w in outcome.warnings)

    row = await ingest_repo.get_connector(feed["connector_id"])
    assert row is not None
    assert row.quarantined_at is not None
    assert not row.is_runnable

    # And a quarantined connector actually stops, rather than merely being
    # labelled.
    again = await ingest.run_connector(feed["connector_id"])
    assert again.fetched == 0
    assert "quarantined" in (again.error or "")


async def test_a_broken_configuration_quarantines_rather_than_retrying(feed: dict) -> None:
    """No number of attempts conjures a missing directory, and a connector
    retrying a config error forever is noise that hides real failures."""
    await ingest_repo.upsert_connector(
        connector_id=feed["connector_id"],
        source_id=feed["source_id"],
        connector_type="filesystem",
        display_name="broken",
        config={"directory": "does-not-exist"},
        mapping={"content_type": "t", "subject_path": "entity_id"},
    )
    outcome = await ingest.run_connector(feed["connector_id"])
    assert outcome.error is not None

    row = await ingest_repo.get_connector(feed["connector_id"])
    assert row is not None and row.quarantined_at is not None


async def test_health_reports_what_actually_happened(feed: dict) -> None:
    _write(
        feed["directory"],
        "a.jsonl",
        [
            {"entity_id": SUBJECT, "observed_at": "2026-08-01T10:00:00Z"},
            {"observed_at": "2026-08-01T10:00:00Z"},
        ],
    )
    await ingest.run_connector(feed["connector_id"])

    rows = [r for r in await ingest_repo.health_rows() if r["connector_id"] == feed["connector_id"]]
    assert len(rows) == 1
    health = rows[0]
    assert health["records_24h"] == 2
    assert health["new_24h"] == 1
    assert health["failed_records_24h"] == 1
    assert health["open_failures"] == 1
    # Source reliability travels with the health row: a healthy feed rated E is
    # a different thing from a healthy feed rated A.
    assert health["source_reliability"] == "C"


async def test_one_connector_failing_leaves_others_untouched(feed: dict) -> None:
    """Isolation, asserted rather than assumed. Connectors never share a call
    stack or a transaction, so a broken feed cannot take a working one with it."""
    other_id = f"{feed['connector_id']}-b"
    await ingest_repo.upsert_connector(
        connector_id=other_id,
        source_id=feed["source_id"],
        connector_type="filesystem",
        display_name="broken sibling",
        config={"directory": "nowhere"},
        mapping={"content_type": "t", "subject_path": "entity_id"},
    )
    try:
        broken = await ingest.run_connector(other_id)
        assert broken.error is not None

        _write(
            feed["directory"], "a.jsonl", [{"entity_id": SUBJECT, "observed_at": "2026-08-01T10:00:00Z"}]
        )
        healthy = await ingest.run_connector(feed["connector_id"])
        assert healthy.new == 1
        assert healthy.error is None
    finally:
        # Batches are operational history: the application may write them and
        # never delete them. Cleanup is an admin act.
        admin = await asyncpg.connect(dsn=get_settings().postgres_admin_dsn)
        try:
            async with admin.transaction():
                # Even the superuser must disable the trigger first: the
                # dead-letter queue records what happened, and erasing it is
                # meant to take two deliberate acts.
                await admin.execute("ALTER TABLE ingest_failures DISABLE TRIGGER USER")
                await admin.execute(
                    "DELETE FROM ingest_failures WHERE connector_id = $1", other_id
                )
                await admin.execute("ALTER TABLE ingest_failures ENABLE TRIGGER USER")
                await admin.execute("DELETE FROM ingest_batches WHERE connector_id = $1", other_id)
                await admin.execute("DELETE FROM connectors WHERE connector_id = $1", other_id)
        finally:
            await admin.close()


async def test_a_subject_that_does_not_exist_is_dead_lettered_not_recorded(
    feed: dict,
) -> None:
    """A recognised prefix is not an existence check.

    `PRS-9999999` passes every Phase 3 validation and names nobody. Before
    subject resolution, this record landed as an observation about a person who
    does not exist: no error, no dead-letter entry, and it would never have
    appeared on any entity page. Silent loss inside a check that looked like it
    covered the case.
    """
    ghost = "PRS-9999999"
    _write(
        feed["directory"],
        "a.jsonl",
        [{"entity_id": ghost, "observed_at": "2026-08-01T10:00:00Z", "note": "seen"}],
    )
    outcome = await ingest.run_connector(feed["connector_id"])

    assert outcome.new == 0
    assert outcome.unresolved_subjects == 1
    assert await provenance_repo.observations_for_subject(ghost) == []

    failures = await ingest_repo.list_failures(connector_id=feed["connector_id"])
    assert len(failures) == 1
    # A stage of its own: the remedy for "ARGUS has never heard of this person"
    # is nothing like the remedy for a broken mapping.
    assert failures[0]["stage"] == "resolve"
    assert "UnresolvedSubject" in failures[0]["error_type"]
    # And the payload is kept, so the record can be replayed once the entity
    # exists or the mapping learns how to match it.
    assert failures[0]["raw_id"] is not None
