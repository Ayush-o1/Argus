"""The alerting path against a real PostgreSQL.

Covers the properties that only exist once rows are actually written: dedup
against the unique key, the append-only triggers, the guarded state transition,
and the constraint that a dismissal carries a reason.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
import pytest_asyncio

from app.alerting.identity import alert_key
from app.config import get_settings
from app.repositories import alert_repo

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def pg_admin() -> AsyncIterator[asyncpg.Connection]:
    settings = get_settings()
    try:
        conn = await asyncpg.connect(dsn=settings.postgres_admin_dsn, timeout=5)
    except Exception:
        pytest.skip("No PostgreSQL reachable; skipping alerting integration test")
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def pool() -> AsyncIterator[None]:
    from app.database.postgres import close_postgres, connect_postgres

    try:
        await connect_postgres()
    except Exception:
        pytest.skip("No PostgreSQL reachable; skipping alerting integration test")
    try:
        yield
    finally:
        await close_postgres()


@pytest_asyncio.fixture
async def scratch(pg_admin: asyncpg.Connection, pool: None) -> AsyncIterator[dict]:
    """A run and a group to hang test alerts from, removed afterwards.

    Cleanup disables the append-only triggers, which is exactly the privilege
    the application does not have — the tests below assert it cannot.
    """
    tag = uuid.uuid4().hex[:8]
    run_id = await alert_repo.start_run(f"fp-{tag}", None, None)
    group_key = f"grp-{tag}"
    from app.database.postgres import acquire

    async with acquire() as conn:
        await alert_repo.upsert_group(conn, group_key, "scope", ["PRS-TEST"], "test group")

    keys: list[str] = []
    try:
        yield {"run_id": run_id, "group_key": group_key, "tag": tag, "keys": keys}
    finally:
        await pg_admin.execute("ALTER TABLE alert_transitions DISABLE TRIGGER USER")
        await pg_admin.execute("ALTER TABLE alert_occurrences DISABLE TRIGGER USER")
        try:
            if keys:
                await pg_admin.execute("DELETE FROM alert_transitions WHERE alert_key = ANY($1::text[])", keys)
                await pg_admin.execute("DELETE FROM alert_occurrences WHERE alert_key = ANY($1::text[])", keys)
                await pg_admin.execute("DELETE FROM alerts WHERE alert_key = ANY($1::text[])", keys)
            await pg_admin.execute("DELETE FROM alert_groups WHERE group_key = $1", group_key)
            await pg_admin.execute("DELETE FROM alert_runs WHERE run_id = $1", run_id)
        finally:
            await pg_admin.execute("ALTER TABLE alert_transitions ENABLE TRIGGER USER")
            await pg_admin.execute("ALTER TABLE alert_occurrences ENABLE TRIGGER USER")


async def _insert(
    scratch: dict, *, rule_id="test.rule", version=1, scope=("PRS-TEST",),
    priority=0.5, suppressed=False,
):
    from app.database.postgres import acquire

    key = alert_key(rule_id, version, tuple(scope))
    scratch["keys"].append(key)
    async with acquire() as conn:
        created, count = await alert_repo.upsert_alert(
            conn,
            alert_key=key, rule_id=rule_id, rule_version=version, scope=list(scope),
            group_key=scratch["group_key"], title="t", summary="s",
            priority=priority, priority_band="medium",
            priority_factors=json.dumps({}), evidence=json.dumps({}),
            suppressed=suppressed, suppressed_by="sup-1" if suppressed else None,
            run_id=scratch["run_id"],
        )
        await alert_repo.record_occurrence(conn, key, scratch["run_id"], priority, 0.5, 0.5)
    return key, created, count


async def test_first_insert_creates_and_repeat_only_counts(scratch: dict) -> None:
    key, created, count = await _insert(scratch)
    assert created is True and count == 1

    _, created_again, count_again = await _insert(scratch)
    assert created_again is False, "a repeat firing must not create a second row"
    assert count_again == 2

    row = await alert_repo.get_alert(key)
    assert row is not None and row["occurrence_count"] == 2


async def test_repeat_does_not_reset_analyst_state(scratch: dict) -> None:
    """The property that makes dedup safe: a re-run must not undo triage."""
    key, _, _ = await _insert(scratch)
    await alert_repo.apply_transition(
        alert_key=key, from_state="open", to_state="acknowledged", reason_code=None,
        note=None, actor_username="iris", actor_role="investigator", terminal=False,
    )
    await alert_repo.assign_alert(key, "iris")

    await _insert(scratch)

    row = await alert_repo.get_alert(key)
    assert row is not None
    assert row["state"] == "acknowledged", "a repeat firing reset the analyst's state"
    assert row["assigned_to"] == "iris"


async def test_occurrence_is_recorded_once_per_run(scratch: dict) -> None:
    key, _, _ = await _insert(scratch)
    await _insert(scratch)
    rows = await alert_repo.list_occurrences(key)
    assert len(rows) == 1, "the same run must not double-count an occurrence"


async def test_transition_writes_history_and_moves_the_alert(scratch: dict) -> None:
    key, _, _ = await _insert(scratch)
    updated = await alert_repo.apply_transition(
        alert_key=key, from_state="open", to_state="investigating", reason_code=None,
        note="taking a look", actor_username="iris", actor_role="investigator", terminal=False,
    )
    assert updated is not None and updated["state"] == "investigating"

    history = await alert_repo.list_transitions(key)
    assert history[-1]["to_state"] == "investigating"
    assert history[-1]["actor_username"] == "iris"


async def test_a_stale_transition_is_refused(scratch: dict) -> None:
    """Two analysts triaging concurrently: the second must not silently
    overwrite the first."""
    key, _, _ = await _insert(scratch)
    first = await alert_repo.apply_transition(
        alert_key=key, from_state="open", to_state="acknowledged", reason_code=None,
        note=None, actor_username="iris", actor_role="investigator", terminal=False,
    )
    assert first is not None

    stale = await alert_repo.apply_transition(
        alert_key=key, from_state="open", to_state="investigating", reason_code=None,
        note=None, actor_username="sam", actor_role="supervisor", terminal=False,
    )
    assert stale is None, "a transition from a state the alert has left must not apply"


async def test_dismissal_records_reason_and_closure(scratch: dict) -> None:
    key, _, _ = await _insert(scratch)
    updated = await alert_repo.apply_transition(
        alert_key=key, from_state="open", to_state="dismissed", reason_code="known_benign",
        note="explained by the data owner", actor_username="iris", actor_role="investigator",
        terminal=True,
    )
    assert updated is not None
    assert updated["dismissal_reason"] == "known_benign"
    assert updated["closed_at"] is not None


async def test_reopening_clears_the_closure_timestamp(scratch: dict) -> None:
    key, _, _ = await _insert(scratch)
    await alert_repo.apply_transition(
        alert_key=key, from_state="open", to_state="dismissed", reason_code="not_relevant",
        note=None, actor_username="iris", actor_role="investigator", terminal=True,
    )
    reopened = await alert_repo.apply_transition(
        alert_key=key, from_state="dismissed", to_state="open", reason_code=None,
        note="new evidence", actor_username="sam", actor_role="supervisor", terminal=False,
    )
    assert reopened is not None
    assert reopened["closed_at"] is None
    assert reopened["dismissal_reason"] is None


async def test_transitions_are_append_only_to_the_application(scratch: dict) -> None:
    key, _, _ = await _insert(scratch)
    await alert_repo.apply_transition(
        alert_key=key, from_state="open", to_state="acknowledged", reason_code=None,
        note=None, actor_username="iris", actor_role="investigator", terminal=False,
    )
    from app.database.postgres import acquire

    async with acquire() as conn:
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute("UPDATE alert_transitions SET to_state='open' WHERE alert_key=$1", key)
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute("DELETE FROM alert_transitions WHERE alert_key=$1", key)


async def test_the_application_cannot_delete_an_alert(scratch: dict) -> None:
    """An alert that turned out to be wrong is dismissed with a reason, which
    is a record. Deleting it is not."""
    key, _, _ = await _insert(scratch)
    from app.database.postgres import acquire

    async with acquire() as conn:
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute("DELETE FROM alerts WHERE alert_key=$1", key)


async def test_suppressed_alert_is_written_and_excluded_from_the_default_queue(scratch: dict) -> None:
    """Suppression hides; it does not prevent. The alert must still exist."""
    key, _, _ = await _insert(scratch, rule_id="test.suppressed", suppressed=True)

    default, _ = await alert_repo.list_alerts(page_size=200)
    assert key not in {a["alert_key"] for a in default}

    hidden, _ = await alert_repo.list_alerts(suppressed_only=True, page_size=200)
    assert key in {a["alert_key"] for a in hidden}, "a suppressed alert must remain one filter away"


async def test_suppression_can_be_created_and_revoked(pool: None) -> None:
    row = await alert_repo.create_suppression(
        rule_id="test.rule", subject_ref=None, reason_code="known_benign",
        note="a sufficiently long explanatory note", created_by="iris",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    sid = str(row["suppression_id"])
    try:
        active = await alert_repo.list_suppressions(active_only=True)
        assert sid in {str(s["suppression_id"]) for s in active}

        revoked = await alert_repo.revoke_suppression(sid, "sam")
        assert revoked is not None and revoked["revoked_by"] == "sam"

        again = await alert_repo.revoke_suppression(sid, "sam")
        assert again is None, "revoking twice must not succeed silently"

        active_after = await alert_repo.list_suppressions(active_only=True)
        assert sid not in {str(s["suppression_id"]) for s in active_after}
    finally:
        from app.database.postgres import acquire

        async with acquire() as conn:
            await conn.execute(
                "UPDATE alert_suppressions SET expires_at = created_at + interval '1 second' "
                "WHERE suppression_id = $1::uuid",
                sid,
            )


async def test_jsonb_columns_come_back_as_objects_not_text(scratch: dict) -> None:
    """asyncpg returns JSONB as text unless it is decoded.

    Without this the API serialises `priority_factors` as a JSON *string*, and a
    client asking whether it contains a key gets a substring search over text
    rather than a lookup — which does not raise on the server and surfaced only
    as a TypeError in the browser. A repository that returns a different type
    from the one its column declares is worth pinning.
    """
    key, _, _ = await _insert(scratch, rule_id="test.jsonb")

    row = await alert_repo.get_alert(key)
    assert row is not None
    assert isinstance(row["priority_factors"], dict), "priority_factors came back as text"
    assert isinstance(row["evidence"], dict), "evidence came back as text"

    listed, _ = await alert_repo.list_alerts(subject_ref="PRS-TEST", page_size=50)
    assert listed, "the alert should be listed under its subject"
    assert all(isinstance(a["priority_factors"], dict) for a in listed)


async def test_spread_is_computed_over_every_subject(pool: None) -> None:
    """B-04, on the surface that replaced the one it was found on.

    The old alert panel derived "N countries · crosses N regions" from a
    five-entity preview and printed it under a heading reading "Spread". The
    replacement has no preview to derive it from, and it states its basis.
    """
    from app.repositories.alert_findings_repo import spread_of

    context = {
        f"PRS-{i}": {"country": f"Country{i}", "region": f"Region{i % 3}"} for i in range(12)
    }
    spread = spread_of(context)
    assert spread["country_count"] == 12, "spread must count every subject, not a slice"
    assert spread["region_count"] == 3
    assert spread["subjects_total"] == 12
    assert spread["basis"] == "complete"


async def test_spread_reports_a_partial_basis_when_locations_are_missing(pool: None) -> None:
    """A missing country means "not recorded", not "not abroad"."""
    from app.repositories.alert_findings_repo import spread_of

    context = {
        "PRS-1": {"country": "India", "region": "South Asia"},
        "PRS-2": {"country": None, "region": None},
        "PRS-3": {"country": None, "region": None},
    }
    spread = spread_of(context)
    assert spread["basis"] == "partial"
    assert spread["subjects_located"] == 1
    assert spread["subjects_total"] == 3


async def test_queue_counts_add_up(scratch: dict) -> None:
    await _insert(scratch, rule_id="test.count.a")
    await _insert(scratch, rule_id="test.count.b")
    counts = await alert_repo.queue_counts()
    assert counts["total"] >= 2
    assert set(counts) >= {"total", "open", "acknowledged", "investigating", "resolved", "dismissed", "suppressed"}
