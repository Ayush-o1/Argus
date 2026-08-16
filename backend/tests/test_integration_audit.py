"""The audit log's security properties, against a real PostgreSQL.

These assert the two claims the audit log makes:
  1. the application role cannot mutate it, and
  2. mutation performed anyway is detectable.

Both are enforced by the database, so only a real database can test them.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest

from app.config import get_settings
from app.services import audit

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def pg():
    """Application-role connection — the privileges the running API actually has."""
    settings = get_settings()
    try:
        conn = await asyncpg.connect(dsn=settings.postgres_dsn, timeout=5)
    except Exception:
        pytest.skip("No PostgreSQL reachable; skipping audit integration test")
    try:
        yield conn
    finally:
        await conn.close()


@pytest.fixture
async def intact_chain():
    """Skip tamper tests unless the chain is currently intact.

    These tests deliberately break the chain and then restore it. If a previous
    run left it broken, they would all fail for a reason unrelated to what they
    assert — so they check first and say so plainly rather than reporting a
    cascade of misleading failures.
    """
    from app.database.postgres import close_postgres, connect_postgres

    await connect_postgres()
    try:
        result = await audit.verify_chain()
        if not result.ok:
            pytest.skip(
                f"audit chain already broken before this test ({result.detail}); "
                "repair it before running tamper tests"
            )
        yield
    finally:
        await close_postgres()


@pytest.fixture
async def pg_admin():
    """Superuser connection, used only to clean up rows the app cannot delete."""
    settings = get_settings()
    try:
        conn = await asyncpg.connect(dsn=settings.postgres_admin_dsn, timeout=5)
    except Exception:
        pytest.skip("No PostgreSQL reachable; skipping audit integration test")
    try:
        yield conn
    finally:
        await conn.close()


async def test_application_role_may_insert_but_not_mutate(pg: asyncpg.Connection) -> None:
    """The core claim: compromising ARGUS does not let an attacker erase what
    they did."""
    granted = {
        r["privilege_type"]
        for r in await pg.fetch(
            """
            SELECT privilege_type FROM information_schema.role_table_grants
            WHERE grantee = current_user AND table_name = 'audit_events'
            """
        )
    }
    assert granted == {"INSERT", "SELECT"}, f"application role holds unexpected grants: {granted}"

    for statement in (
        "UPDATE audit_events SET action = 'tampered'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ):
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await pg.execute(statement)


async def test_triggers_block_mutation_even_for_the_superuser(pg_admin: asyncpg.Connection) -> None:
    """Privilege alone is not the only guard: the triggers apply to every role,
    so erasing a record takes two deliberate acts rather than one.

    The row is written first, and that is not incidental. `UPDATE` and `DELETE`
    triggers are `FOR EACH ROW`, so on an empty table they never fire and the
    statement succeeds trivially — the assertion passes or fails depending on
    whether the database happened to have data. Locally it always did; in CI,
    against a freshly migrated database, this test failed on every run from the
    moment the audit log was introduced.
    """
    from app.database.postgres import close_postgres, connect_postgres

    await connect_postgres()
    try:
        await audit.record(
            audit.AuditEvent(
                action=f"test.trigger.{uuid.uuid4().hex[:8]}",
                outcome="success",
                actor_username="pytest",
                resource_type="Probe",
                resource_id="trigger-guard",
            )
        )
    finally:
        await close_postgres()

    assert await pg_admin.fetchval("SELECT count(*) FROM audit_events") > 0

    for statement in (
        "UPDATE audit_events SET action = 'tampered'",
        "DELETE FROM audit_events WHERE true",
    ):
        with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
            await pg_admin.execute(statement)


async def test_recorded_events_chain_and_verify(
    pg_admin: asyncpg.Connection, intact_chain: None
) -> None:
    from app.database.postgres import close_postgres, connect_postgres

    await connect_postgres()
    try:
        marker = f"test.chain.{uuid.uuid4().hex[:8]}"
        for index in range(3):
            await audit.record(
                audit.AuditEvent(
                    action=marker,
                    outcome="success",
                    actor_username="pytest",
                    resource_type="Probe",
                    resource_id=str(index),
                )
            )

        rows = await pg_admin.fetch(
            "SELECT seq, prev_hash, entry_hash FROM audit_events WHERE action = $1 ORDER BY seq",
            marker,
        )
        assert len(rows) == 3
        # Each row's prev_hash must be its predecessor's entry_hash.
        for earlier, later in zip(rows, rows[1:], strict=False):
            assert later["prev_hash"] == earlier["entry_hash"]

        result = await audit.verify_chain()
        assert result.ok, result.detail
    finally:
        await close_postgres()


async def test_verification_detects_an_altered_row(
    pg_admin: asyncpg.Connection, intact_chain: None
) -> None:
    """Tamper-*evident*, not merely tamper-resistant.

    Alters a row the only way it can be altered — as superuser, with the trigger
    explicitly disabled — and asserts that verification notices.
    """
    from app.database.postgres import close_postgres, connect_postgres

    await connect_postgres()
    try:
        marker = f"test.tamper.{uuid.uuid4().hex[:8]}"
        await audit.record(
            audit.AuditEvent(
                action=marker, outcome="success", actor_username="pytest", resource_id="original"
            )
        )
        assert (await audit.verify_chain()).ok

        async with pg_admin.transaction():
            await pg_admin.execute("ALTER TABLE audit_events DISABLE TRIGGER audit_events_no_update")
            await pg_admin.execute(
                "UPDATE audit_events SET resource_id = 'tampered' WHERE action = $1", marker
            )
            await pg_admin.execute("ALTER TABLE audit_events ENABLE TRIGGER audit_events_no_update")

        result = await audit.verify_chain()
        assert not result.ok, "an altered row must break verification"
        assert result.first_broken_seq is not None
        assert "altered" in result.detail

        # Restore, so one test does not permanently fail every later run.
        async with pg_admin.transaction():
            await pg_admin.execute("ALTER TABLE audit_events DISABLE TRIGGER audit_events_no_update")
            await pg_admin.execute(
                "UPDATE audit_events SET resource_id = 'original' WHERE action = $1", marker
            )
            await pg_admin.execute("ALTER TABLE audit_events ENABLE TRIGGER audit_events_no_update")

        assert (await audit.verify_chain()).ok, "restoring the value must repair the chain"
    finally:
        await close_postgres()


async def test_verification_detects_a_removed_row(
    pg_admin: asyncpg.Connection, intact_chain: None
) -> None:
    from app.database.postgres import close_postgres, connect_postgres

    await connect_postgres()
    try:
        marker = f"test.remove.{uuid.uuid4().hex[:8]}"
        for index in range(3):
            await audit.record(
                audit.AuditEvent(
                    action=marker, outcome="success", actor_username="pytest", resource_id=str(index)
                )
            )

        middle = await pg_admin.fetchval(
            "SELECT seq FROM audit_events WHERE action = $1 ORDER BY seq OFFSET 1 LIMIT 1", marker
        )
        row = await pg_admin.fetchrow("SELECT * FROM audit_events WHERE seq = $1", middle)

        async with pg_admin.transaction():
            await pg_admin.execute("ALTER TABLE audit_events DISABLE TRIGGER audit_events_no_delete")
            await pg_admin.execute("DELETE FROM audit_events WHERE seq = $1", middle)
            await pg_admin.execute("ALTER TABLE audit_events ENABLE TRIGGER audit_events_no_delete")

        result = await audit.verify_chain()
        assert not result.ok, "a removed row must break the chain"
        assert "removed or reordered" in result.detail

        # Restore for subsequent runs. `seq` must be reinserted explicitly:
        # letting BIGSERIAL assign a fresh one puts the row at the end of the
        # log rather than back where it was, and the chain stays broken. That is
        # the property working — a deleted entry cannot be quietly slipped back
        # into place — so the test has to restore the exact row, position
        # included.
        columns = list(row.keys())
        placeholders = ", ".join(f"${i + 1}" for i in range(len(columns)))
        await pg_admin.execute(
            f"INSERT INTO audit_events ({', '.join(columns)}) VALUES ({placeholders})",
            *[row[c] for c in columns],
        )
        assert (await audit.verify_chain()).ok, "restoring the exact row must repair the chain"
    finally:
        await close_postgres()


async def test_audit_log_filters_combine_and_ignore_blanks(pg: asyncpg.Connection) -> None:
    """The audit listing's filters, against a real database.

    Covers the endpoint's query directly. It was previously assembled with
    f-strings — safely, but in a shape that made safety a matter of reading the
    loop rather than of the code's form. Rewriting it to static SQL is only an
    improvement if the behaviour it replaced is pinned, and nothing pinned it.
    """
    from app.api.routes.admin import read_audit_log
    from app.database.postgres import close_postgres, connect_postgres

    marker = f"test.filter.{uuid.uuid4().hex[:8]}"
    other = f"test.other.{uuid.uuid4().hex[:8]}"

    await connect_postgres()
    try:
        for index in range(3):
            await audit.record(
                audit.AuditEvent(
                    action=marker,
                    outcome="success",
                    actor_username="filter-probe",
                    resource_type="Probe",
                    resource_id=f"res-{index}",
                )
            )
        await audit.record(
            audit.AuditEvent(
                action=other,
                outcome="success",
                actor_username="someone-else",
                resource_type="Probe",
                resource_id="res-0",
            )
        )
    finally:
        await close_postgres()

    # Called directly rather than over HTTP, so FastAPI's `Query(...)` defaults
    # are never resolved — every parameter has to be passed explicitly.
    async def read(
        action: str | None = None,
        resource_id: str | None = None,
        actor_username: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ):
        return await read_audit_log(
            action=action,
            resource_id=resource_id,
            actor_username=actor_username,
            page=page,
            page_size=page_size,
            conn=pg,
            _=None,  # type: ignore[arg-type]
        )

    by_action = await read(action=marker)
    assert by_action.meta is not None and by_action.meta.total == 3
    assert {row["action"] for row in by_action.data} == {marker}

    # Filters combine with AND rather than OR.
    combined = await read(action=marker, resource_id="res-0")
    assert combined.meta is not None and combined.meta.total == 1

    # A filter that matches nothing returns nothing, not everything.
    assert (await read(action=marker, actor_username="someone-else")).meta.total == 0  # type: ignore[union-attr]

    # A blank filter means "no filter", not "match the empty string" — the
    # behaviour the previous `if value:` guard gave, preserved deliberately.
    blank = await read(action="", resource_id="")
    unfiltered = await read()
    assert blank.meta is not None and unfiltered.meta is not None
    assert blank.meta.total == unfiltered.meta.total > 0

    # Paging returns distinct rows, newest first.
    page1 = await read(action=marker, page=1, page_size=2)
    page2 = await read(action=marker, page=2, page_size=2)
    assert len(page1.data) == 2 and len(page2.data) == 1
    assert {r["seq"] for r in page1.data}.isdisjoint({r["seq"] for r in page2.data})
    assert page1.data[0]["seq"] > page1.data[1]["seq"]
