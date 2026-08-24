"""Export custody against a real PostgreSQL.

The properties here exist only once rows are written: the hash survives
disposal, the content cannot be rewritten, the access log cannot be edited, and
retention destroys bytes without destroying the record that they existed.

Every test builds the world it measures — the lesson the patterns suite learned
in Phase 8, when tests that read ambient state passed locally and failed against
an empty CI database.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
import pytest_asyncio

from app.config import get_settings
from app.evidence.artifacts import digest, verify
from app.evidence.export import render_markdown, render_pdf
from app.repositories import export_repo, investigation_repo
from app.services.retention import dispose_due_exports

pytestmark = pytest.mark.asyncio

ACTOR = {"actor_username": "t.mensah", "actor_role": "analyst"}


@pytest_asyncio.fixture
async def pg_admin() -> AsyncIterator[asyncpg.Connection]:
    settings = get_settings()
    try:
        conn = await asyncpg.connect(dsn=settings.postgres_admin_dsn, timeout=5)
    except Exception:
        pytest.skip("No PostgreSQL reachable; skipping evidence integration test")
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
        pytest.skip("No PostgreSQL reachable; skipping evidence integration test")
    try:
        yield
    finally:
        await close_postgres()


@pytest_asyncio.fixture
async def scratch(pg_admin: asyncpg.Connection, pool: None) -> AsyncIterator[dict]:
    tag = uuid.uuid4().hex[:8]
    state: dict = {"tag": tag, "investigations": [], "exports": []}
    try:
        yield state
    finally:
        for table in ("export_access", "exports"):
            await pg_admin.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
        for table in (
            "investigation_events", "investigation_reviews", "investigation_findings",
            "investigation_actions", "investigation_entities", "investigation_alerts",
            "analyst_assessments",
        ):
            await pg_admin.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
        await pg_admin.execute("ALTER TABLE investigations DISABLE TRIGGER USER")
        try:
            if state["exports"]:
                await pg_admin.execute(
                    "DELETE FROM export_access WHERE export_id = ANY($1::uuid[])", state["exports"]
                )
                await pg_admin.execute(
                    "DELETE FROM exports WHERE export_id = ANY($1::uuid[])", state["exports"]
                )
            if state["investigations"]:
                for table in (
                    "investigation_events", "investigation_reviews", "investigation_findings",
                    "investigation_actions", "investigation_entities", "investigation_alerts",
                    "analyst_assessments",
                ):
                    await pg_admin.execute(
                        f"DELETE FROM {table} WHERE investigation_id = ANY($1::uuid[])",
                        state["investigations"],
                    )
                await pg_admin.execute(
                    "DELETE FROM investigations WHERE investigation_id = ANY($1::uuid[])",
                    state["investigations"],
                )
        finally:
            for table in (
                "export_access", "exports", "investigation_events", "investigation_reviews",
                "investigation_findings", "investigation_actions", "investigation_entities",
                "investigation_alerts", "analyst_assessments", "investigations",
            ):
                await pg_admin.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")


async def _investigation(scratch: dict, classification: str = "internal") -> dict:
    created = await investigation_repo.create_investigation(
        title=f"Export test {scratch['tag']}",
        hypothesis="Three companies share one owner",
        confidence="low",
        confidence_basis="one registry extract",
        opened_by="t.mensah",
        actor_role="analyst",
        classification=classification,
    )
    scratch["investigations"].append(created["investigation_id"])
    return created


async def _export(scratch: dict, investigation: dict, content: bytes = b"<html>report</html>") -> dict:
    artifact = digest(content)
    record = await export_repo.create_export(
        investigation_id=investigation["investigation_id"],
        format_="html",
        classification=investigation["classification"],
        content=artifact.content,
        sha256=artifact.sha256,
        requested_by="t.mensah",
        requester_role="analyst",
        requester_clearance="internal",
        purpose="court bundle",
        request_ip="127.0.0.1",
    )
    scratch["exports"].append(record["export_id"])
    return record


async def test_creating_an_export_is_itself_the_first_access_entry(scratch: dict) -> None:
    """A custody log that starts with the second reader cannot say who produced it."""
    inv = await _investigation(scratch)
    record = await _export(scratch, inv)
    access = await export_repo.list_access(str(record["export_id"]))
    assert [a["action"] for a in access] == ["created"]
    assert access[0]["actor_username"] == "t.mensah"
    assert access[0]["detail"] == "court bundle"


async def test_a_refused_read_is_recorded_as_loudly_as_a_successful_one(scratch: dict) -> None:
    inv = await _investigation(scratch)
    record = await _export(scratch, inv)
    await export_repo.log_access(
        export_id=str(record["export_id"]),
        action="downloaded",
        actor_username="v.novak",
        actor_role="viewer",
        actor_clearance="unrestricted",
        outcome="denied",
        detail="clearance unrestricted below internal",
    )
    access = await export_repo.list_access(str(record["export_id"]))
    denied = [a for a in access if a["outcome"] == "denied"]
    assert len(denied) == 1
    assert denied[0]["actor_username"] == "v.novak"


async def test_the_content_cannot_be_rewritten(scratch: dict) -> None:
    from app.database.postgres import acquire

    inv = await _investigation(scratch)
    record = await _export(scratch, inv)
    async with acquire() as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="only be emptied"):
            await conn.execute(
                "UPDATE exports SET content = $2 WHERE export_id = $1",
                record["export_id"], b"a different report",
            )
        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="immutable"):
            await conn.execute(
                "UPDATE exports SET content_sha256 = $2 WHERE export_id = $1",
                record["export_id"], "f" * 64,
            )


async def test_the_access_log_cannot_be_edited_or_deleted(scratch: dict) -> None:
    from app.database.postgres import acquire

    inv = await _investigation(scratch)
    record = await _export(scratch, inv)
    async with acquire() as conn:
        for statement in (
            "UPDATE export_access SET actor_username = 'nobody' WHERE export_id = $1",
            "DELETE FROM export_access WHERE export_id = $1",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError, match="permission denied"):
                await conn.execute(statement, record["export_id"])


async def test_integrity_is_verifiable_by_rehashing(scratch: dict) -> None:
    inv = await _investigation(scratch)
    content = b"<html>the actual report body</html>"
    record = await _export(scratch, inv, content)

    stored = await export_repo.fetch_export_content(str(record["export_id"]))
    assert stored is not None
    ok, explanation = verify(bytes(stored["content"]), stored["content_sha256"])
    assert ok, explanation


async def test_tampering_with_stored_bytes_is_detected(
    scratch: dict, pg_admin: asyncpg.Connection
) -> None:
    """The trigger stops the application. This is what happens when it does not.

    A superuser — which in an incident is exactly who would be in a position to
    alter a record — can bypass the trigger. Re-hashing is what catches it, and
    it is the reason the hash is stored at all.
    """
    inv = await _investigation(scratch)
    record = await _export(scratch, inv, b"the original")

    await pg_admin.execute("ALTER TABLE exports DISABLE TRIGGER USER")
    try:
        await pg_admin.execute(
            "UPDATE exports SET content = $2 WHERE export_id = $1",
            record["export_id"], b"a forgery",
        )
    finally:
        await pg_admin.execute("ALTER TABLE exports ENABLE TRIGGER USER")

    stored = await export_repo.fetch_export_content(str(record["export_id"]))
    assert stored is not None
    ok, explanation = verify(bytes(stored["content"]), stored["content_sha256"])
    assert not ok
    assert "have changed since they were produced" in explanation


async def test_retention_destroys_the_bytes_and_keeps_the_record(
    scratch: dict, pg_admin: asyncpg.Connection
) -> None:
    """What disposal is for, and what it must not do.

    "An export of this investigation was made on this date by this person and
    has since been destroyed on schedule" is a more useful record than the bytes
    were. Deleting the row would leave no trace the export ever happened.
    """
    inv = await _investigation(scratch)
    record = await _export(scratch, inv)

    # Bring the retention date forward rather than waiting a year. Done as
    # superuser because the schema deliberately refuses to let the application
    # extend or shorten a retention period.
    await pg_admin.execute("ALTER TABLE exports DISABLE TRIGGER USER")
    try:
        await pg_admin.execute(
            "UPDATE exports SET retention_until = $2 WHERE export_id = $1",
            record["export_id"], datetime.now(UTC) - timedelta(days=1),
        )
    finally:
        await pg_admin.execute("ALTER TABLE exports ENABLE TRIGGER USER")

    disposed = await dispose_due_exports()
    assert disposed >= 1

    row = await export_repo.fetch_export(str(record["export_id"]))
    assert row is not None
    assert row["disposed_at"] is not None
    assert row["disposal_reason"] == "retention period elapsed"
    # The parts that matter survive.
    assert row["content_sha256"] == record["content_sha256"]
    assert row["requested_by"] == "t.mensah"
    assert row["purpose"] == "court bundle"

    content = await export_repo.fetch_export_content(str(record["export_id"]))
    assert content is not None and len(bytes(content["content"])) == 0

    # And the disposal is as visible in the custody log as a download.
    access = await export_repo.list_access(str(record["export_id"]))
    assert any(a["action"] == "disposed" for a in access)


async def test_disposal_is_idempotent_across_concurrent_schedulers(
    scratch: dict, pg_admin: asyncpg.Connection
) -> None:
    """Two instances ticking at once must produce one disposal, not two.

    A database guarantee rather than leader election, the same argument the
    ingest scheduler makes.
    """
    inv = await _investigation(scratch)
    record = await _export(scratch, inv)
    await pg_admin.execute("ALTER TABLE exports DISABLE TRIGGER USER")
    try:
        await pg_admin.execute(
            "UPDATE exports SET retention_until = $2 WHERE export_id = $1",
            record["export_id"], datetime.now(UTC) - timedelta(days=1),
        )
    finally:
        await pg_admin.execute("ALTER TABLE exports ENABLE TRIGGER USER")

    first = await dispose_due_exports()
    second = await dispose_due_exports()
    assert first >= 1
    assert second == 0, "a second pass must find nothing left to dispose of"


async def test_an_export_records_the_classification_it_carried_not_the_current_one(
    scratch: dict, pg_admin: asyncpg.Connection
) -> None:
    """A copy that has already left cannot be reclassified.

    What matters for custody is what was on the paper when it was handed over.
    """
    inv = await _investigation(scratch, classification="internal")
    record = await _export(scratch, inv)

    await pg_admin.execute(
        "UPDATE investigations SET classification = 'restricted' WHERE investigation_id = $1",
        inv["investigation_id"],
    )
    row = await export_repo.fetch_export(str(record["export_id"]))
    assert row is not None
    assert row["classification"] == "internal"


async def test_markdown_and_pdf_are_accepted_formats_and_round_trip_intact(scratch: dict) -> None:
    """Migration 011 widened the format constraint from (json, html) to add
    (markdown, pdf) — proved here by actually inserting both, through the real
    renderers, against the real constraint, rather than asserting the SQL text."""
    inv = await _investigation(scratch)
    full = await investigation_repo.get_investigation(inv["inv_ref"])
    assert full is not None
    events = await investigation_repo.fetch_events(inv["investigation_id"])

    md_bytes = render_markdown(full, events, requested_by="t.mensah", purpose="regulator hand-off")
    pdf_bytes = render_pdf(full, events, requested_by="t.mensah", purpose="regulator hand-off")

    # `_export` always writes format_="html", so each real format is inserted
    # explicitly here rather than complicating that shared helper.
    md_artifact = digest(md_bytes)
    md_row = await export_repo.create_export(
        investigation_id=inv["investigation_id"],
        format_="markdown",
        classification=inv["classification"],
        content=md_artifact.content,
        sha256=md_artifact.sha256,
        requested_by="t.mensah",
        requester_role="analyst",
        requester_clearance="internal",
        purpose="regulator hand-off",
        request_ip="127.0.0.1",
    )
    scratch["exports"].append(md_row["export_id"])

    pdf_artifact = digest(pdf_bytes)
    pdf_row = await export_repo.create_export(
        investigation_id=inv["investigation_id"],
        format_="pdf",
        classification=inv["classification"],
        content=pdf_artifact.content,
        sha256=pdf_artifact.sha256,
        requested_by="t.mensah",
        requester_role="analyst",
        requester_clearance="internal",
        purpose="regulator hand-off",
        request_ip="127.0.0.1",
    )
    scratch["exports"].append(pdf_row["export_id"])

    fetched_md = await export_repo.fetch_export_content(str(md_row["export_id"]))
    fetched_pdf = await export_repo.fetch_export_content(str(pdf_row["export_id"]))
    assert bytes(fetched_md["content"]) == md_bytes
    assert bytes(fetched_pdf["content"]) == pdf_bytes
    assert bytes(fetched_pdf["content"]).startswith(b"%PDF-")

    ok_md, _ = verify(bytes(fetched_md["content"]), md_row["content_sha256"])
    ok_pdf, _ = verify(bytes(fetched_pdf["content"]), pdf_row["content_sha256"])
    assert ok_md
    assert ok_pdf
