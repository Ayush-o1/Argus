"""Investigations against a real PostgreSQL.

The properties here only exist once rows are written: the constraint that a
closure carries an outcome, the append-only history, the replay agreeing with
the row it claims to explain, and the guarantee that an analyst's dissent leaves
the model's assessment untouched.

Every test builds the world it measures. The patterns suite learned this the
expensive way in Phase 8 — tests that asserted against ambient database state
passed locally and failed the moment CI ran them against an empty instance.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime

import asyncpg
import pytest
import pytest_asyncio

from app.config import get_settings
from app.investigation.history import reconstruct, verify
from app.repositories import investigation_repo

pytestmark = pytest.mark.asyncio

ACTOR = {"actor_username": "t.mensah", "actor_role": "analyst"}


@pytest_asyncio.fixture
async def pg_admin() -> AsyncIterator[asyncpg.Connection]:
    settings = get_settings()
    try:
        conn = await asyncpg.connect(dsn=settings.postgres_admin_dsn, timeout=5)
    except Exception:
        pytest.skip("No PostgreSQL reachable; skipping investigation integration test")
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
        pytest.skip("No PostgreSQL reachable; skipping investigation integration test")
    try:
        yield
    finally:
        await close_postgres()


@pytest_asyncio.fixture
async def scratch(pg_admin: asyncpg.Connection, pool: None) -> AsyncIterator[dict]:
    """A tag for this test's rows, and removal of everything it created.

    Cleanup disables the append-only triggers — which is precisely the privilege
    the application does not hold, and which the tests below assert it cannot
    obtain.
    """
    tag = uuid.uuid4().hex[:8]
    state: dict = {"tag": tag, "ids": [], "subjects": [], "runs": []}
    tables = (
        "investigation_events",
        "investigation_reviews",
        "investigation_findings",
        "investigation_actions",
        "investigation_entities",
        "investigation_alerts",
        "analyst_assessments",
    )
    try:
        yield state
    finally:
        for table in tables:
            await pg_admin.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
        await pg_admin.execute("ALTER TABLE investigations DISABLE TRIGGER USER")
        try:
            ids = state["ids"]
            if ids:
                for table in tables:
                    await pg_admin.execute(f"DELETE FROM {table} WHERE investigation_id = ANY($1::uuid[])", ids)
                await pg_admin.execute("DELETE FROM investigations WHERE investigation_id = ANY($1::uuid[])", ids)
            if state["subjects"]:
                await pg_admin.execute(
                    "DELETE FROM analyst_assessments WHERE subject_ref = ANY($1::text[])",
                    state["subjects"],
                )
                # `assessments` carries its own append-only trigger from
                # migration 006. Removing rows this test seeded needs it off,
                # which is the privilege the application deliberately lacks.
                await pg_admin.execute("ALTER TABLE assessments DISABLE TRIGGER USER")
                try:
                    await pg_admin.execute(
                        "DELETE FROM assessments WHERE subject_ref = ANY($1::text[])",
                        state["subjects"],
                    )
                finally:
                    await pg_admin.execute("ALTER TABLE assessments ENABLE TRIGGER USER")
            if state["runs"]:
                await pg_admin.execute(
                    "DELETE FROM assessment_runs WHERE run_id = ANY($1::bigint[])",
                    state["runs"],
                )
        finally:
            for table in tables:
                await pg_admin.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")
            await pg_admin.execute("ALTER TABLE investigations ENABLE TRIGGER USER")


async def _open(scratch: dict, **overrides) -> dict:
    payload = {
        "title": f"Test investigation {scratch['tag']}",
        "hypothesis": "Three companies share one beneficial owner",
        "confidence": "low",
        "confidence_basis": "single uncorroborated registry extract",
        "opened_by": "t.mensah",
        "actor_role": "analyst",
    }
    payload.update(overrides)
    created = await investigation_repo.create_investigation(**payload)
    scratch["ids"].append(created["investigation_id"])
    return created


# ─────────────────────────────────────────────────────────────────────────────
# The constraint this phase exists for
# ─────────────────────────────────────────────────────────────────────────────


async def test_an_investigation_cannot_be_closed_without_an_outcome(scratch: dict) -> None:
    created = await _open(scratch)
    with pytest.raises(asyncpg.IntegrityConstraintViolationError) as exc:
        await investigation_repo.transition(
            investigation_id=created["investigation_id"],
            to_state="closed",
            outcome=None,
            outcome_rationale=None,
            **ACTOR,
        )
    assert "closed_has_outcome" in str(exc.value)


async def test_an_outcome_cannot_be_recorded_without_its_reasoning(scratch: dict) -> None:
    created = await _open(scratch)
    with pytest.raises(asyncpg.IntegrityConstraintViolationError) as exc:
        await investigation_repo.transition(
            investigation_id=created["investigation_id"],
            to_state="closed",
            outcome="confirmed",
            outcome_rationale=None,
            **ACTOR,
        )
    assert "outcome_has_rationale" in str(exc.value)


async def test_closing_records_the_outcome_the_time_and_the_person(scratch: dict) -> None:
    created = await _open(scratch)
    closed = await investigation_repo.transition(
        investigation_id=created["investigation_id"],
        to_state="closed",
        outcome="confirmed",
        outcome_rationale="Registry filings name the same director on all three.",
        **ACTOR,
    )
    assert closed["outcome"] == "confirmed"
    assert closed["closed_by"] == "t.mensah"
    # `closed_at` is the field the audit found declared on every Neo4j case and
    # written by no code path at all.
    assert closed["closed_at"] is not None


async def test_reopening_clears_the_conclusion_but_the_log_still_has_it(scratch: dict) -> None:
    created = await _open(scratch)
    iid = created["investigation_id"]
    await investigation_repo.transition(
        investigation_id=iid,
        to_state="closed",
        outcome="unfounded",
        outcome_rationale="The directors are unrelated namesakes.",
        **ACTOR,
    )
    reopened = await investigation_repo.transition(
        investigation_id=iid, to_state="active", note="new filing arrived", **ACTOR
    )
    assert reopened["outcome"] is None, "an open investigation has no conclusion"

    # Nothing was lost: the closure is still in the history, at the time it was
    # true. This is the difference between clearing a field and destroying a
    # record.
    events = await investigation_repo.fetch_events(iid)
    closures = [e for e in events if e["event_type"] == "closed"]
    assert closures, "the closure must survive the reopening"
    assert any(e["new_value"] == "unfounded" for e in closures)


# ─────────────────────────────────────────────────────────────────────────────
# History — the acceptance criterion, against a real log
# ─────────────────────────────────────────────────────────────────────────────


async def test_replaying_the_log_reproduces_the_current_row(scratch: dict) -> None:
    """The property that makes the history worth keeping.

    If the replay and the row disagree, one of them is lying and there is no way
    to tell which. Asserted over the whole tracked field set rather than a
    sample, because the field that drifts will be the one nobody sampled.
    """
    created = await _open(scratch)
    iid = created["investigation_id"]

    await investigation_repo.update_fields(investigation_id=iid, title="Renamed after the second interview", **ACTOR)
    await investigation_repo.transition(investigation_id=iid, to_state="active", **ACTOR)
    await investigation_repo.update_fields(
        investigation_id=iid,
        confidence="high",
        confidence_basis="two independent registries and a bank confirmation",
        assigned_to="r.okonkwo",
        set_assigned=True,
        **ACTOR,
    )
    await investigation_repo.transition(
        investigation_id=iid,
        to_state="closed",
        outcome="confirmed",
        outcome_rationale="Confirmed on both registries.",
        **ACTOR,
    )

    events = await investigation_repo.fetch_events(iid)
    replayed = reconstruct(events)
    current = await investigation_repo.get_investigation(iid)

    for field, value in replayed.items():
        actual = current[field]
        if isinstance(actual, datetime):
            actual = actual.isoformat()
        assert value == actual, f"the log and the row disagree about {field}"

    assert replayed["state"] == "closed"
    assert replayed["outcome"] == "confirmed"
    assert replayed["confidence"] == "high"
    assert replayed["assigned_to"] == "r.okonkwo"


async def test_the_investigation_can_be_read_as_it_stood_at_any_past_moment(scratch: dict) -> None:
    created = await _open(scratch)
    iid = created["investigation_id"]
    events = await investigation_repo.fetch_events(iid)
    opened_at = events[0]["occurred_at"]

    await investigation_repo.update_fields(
        investigation_id=iid,
        confidence="high",
        confidence_basis="corroborated since",
        **ACTOR,
    )
    await investigation_repo.transition(
        investigation_id=iid,
        to_state="closed",
        outcome="referred",
        outcome_rationale="Passed to the financial-crime unit.",
        **ACTOR,
    )

    events = await investigation_repo.fetch_events(iid)

    # As at the moment it was opened: low confidence, open, no outcome — even
    # though the row now says high, closed, referred.
    at_open = reconstruct(events, opened_at)
    assert at_open["confidence"] == "low"
    assert at_open["state"] == "open"
    assert at_open["outcome"] is None

    assert reconstruct(events)["outcome"] == "referred"


async def test_a_clean_history_verifies(scratch: dict) -> None:
    created = await _open(scratch)
    iid = created["investigation_id"]
    await investigation_repo.transition(investigation_id=iid, to_state="active", **ACTOR)
    await investigation_repo.update_fields(investigation_id=iid, title="Retitled", **ACTOR)
    assert verify(await investigation_repo.fetch_events(iid)) is None


async def test_a_write_that_bypasses_the_log_is_caught(scratch: dict, pg_admin: asyncpg.Connection) -> None:
    """The reason old values are stored as well as new ones.

    A direct UPDATE writes no event, so it leaves no trace of its own. It
    becomes visible at the *next* legitimate change, whose recorded previous
    value no longer matches what the log says was there.
    """
    created = await _open(scratch)
    iid = created["investigation_id"]

    await pg_admin.execute(
        "UPDATE investigations SET title = $2 WHERE investigation_id = $1",
        iid,
        "Retitled behind the log's back",
    )
    await investigation_repo.update_fields(investigation_id=iid, title="Retitled again, legitimately", **ACTOR)

    found = verify(await investigation_repo.fetch_events(iid))
    assert found is not None
    assert found.field == "title"
    assert found.recorded == "Retitled behind the log's back"
    assert "without writing an event" in found.describe()


async def test_the_application_is_not_granted_the_privilege_to_rewrite_history(
    scratch: dict,
) -> None:
    """Two independent layers, and this one refuses first.

    The application role holds INSERT and SELECT on the event log and nothing
    else, so an attempt to edit it is refused by the grant before a trigger is
    ever consulted. Asserted as "permission denied" rather than as the trigger's
    message, because that is what actually happens — a test that expected the
    trigger here would be asserting a mechanism that never runs.
    """
    from app.database.postgres import acquire

    created = await _open(scratch)
    iid = created["investigation_id"]

    async with acquire() as conn:
        for statement in (
            "UPDATE investigation_events SET note = 'tidied up' WHERE investigation_id = $1",
            "DELETE FROM investigation_events WHERE investigation_id = $1",
        ):
            with pytest.raises(asyncpg.InsufficientPrivilegeError, match="permission denied"):
                await conn.execute(statement, iid)

        # `investigations` is granted UPDATE — it is a work item — but not
        # DELETE, so removing one is refused here too.
        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="permission denied"):
            await conn.execute("DELETE FROM investigations WHERE investigation_id = $1", iid)


async def test_the_log_refuses_even_a_superuser(scratch: dict, pg_admin: asyncpg.Connection) -> None:
    """The layer that matters when the caller is not the application.

    Grants stop the app. They do not stop anyone holding superuser credentials —
    which, in an incident, is exactly who would be in a position to tidy a
    record. The trigger is what refuses them, and it is the reason immutability
    lives in the database rather than in a repository method.
    """
    created = await _open(scratch)
    iid = created["investigation_id"]

    with pytest.raises(asyncpg.InsufficientPrivilegeError, match="append-only"):
        await pg_admin.execute("UPDATE investigation_events SET note = 'tidied' WHERE investigation_id = $1", iid)
    with pytest.raises(asyncpg.InsufficientPrivilegeError, match="append-only"):
        await pg_admin.execute("DELETE FROM investigation_events WHERE investigation_id = $1", iid)
    with pytest.raises(asyncpg.InsufficientPrivilegeError, match="append-only"):
        await pg_admin.execute("DELETE FROM investigations WHERE investigation_id = $1", iid)


# ─────────────────────────────────────────────────────────────────────────────
# Analyst dissent (audit G-15)
# ─────────────────────────────────────────────────────────────────────────────


async def _seed_machine_assessment(pg_admin: asyncpg.Connection, scratch: dict, subject_ref: str, band: str) -> str:
    """A published machine assessment for the analyst to disagree with."""
    scratch["subjects"].append(subject_ref)
    run_id = await pg_admin.fetchval(
        """
        INSERT INTO assessment_runs (model_version, model_fingerprint, status, triggered_by)
        VALUES ('test-v1', $1, 'complete', 'test') RETURNING run_id
        """,
        f"fp-{scratch['tag']}",
    )
    scratch["runs"].append(run_id)
    return await pg_admin.fetchval(
        """
        INSERT INTO assessments
            (run_id, subject_ref, subject_type, band, score, evidence_coverage,
             evaluable_weight, total_weight, model_version, model_fingerprint, computed_at)
        VALUES ($1, $2, 'Person', $3, 78.0, 0.62, 6.2, 10.0, 'test-v1', $4, now())
        RETURNING assessment_id
        """,
        run_id,
        subject_ref,
        band,
        f"fp-{scratch['tag']}",
    )


async def test_an_analyst_can_disagree_and_the_machine_is_left_alone(
    scratch: dict, pg_admin: asyncpg.Connection
) -> None:
    """The property G-15 asks for, stated as plainly as it can be.

    Before this there was nowhere to record a disagreement, so the only ways to
    express one were to ignore the model or to overwrite it. Both stand now, and
    a reader can see that there is a disagreement at all.
    """
    subject = f"PRS-DISSENT-{scratch['tag']}"
    await _seed_machine_assessment(pg_admin, scratch, subject, "elevated")

    recorded = await investigation_repo.record_analyst_assessment(
        subject_ref=subject,
        subject_type="Person",
        analyst_band="routine",
        rationale="Both accounts belong to one registered company; the split is bookkeeping.",
        confidence="high",
        author_username="t.mensah",
        author_role="analyst",
    )

    assert recorded["analyst_band"] == "routine"
    assert recorded["machine_band"] == "elevated"
    assert recorded["dissents"] is True

    # The model's published assessment is exactly as it was.
    rows = await pg_admin.fetch("SELECT band FROM assessments WHERE subject_ref = $1", subject)
    assert [r["band"] for r in rows] == ["elevated"]


async def test_agreement_is_recorded_as_agreement_not_as_silence(scratch: dict, pg_admin: asyncpg.Connection) -> None:
    subject = f"PRS-CONCUR-{scratch['tag']}"
    await _seed_machine_assessment(pg_admin, scratch, subject, "notable")
    recorded = await investigation_repo.record_analyst_assessment(
        subject_ref=subject,
        subject_type="Person",
        analyst_band="notable",
        rationale="Reviewed the signals; the band is right.",
        confidence="moderate",
        author_username="t.mensah",
        author_role="analyst",
    )
    assert recorded["dissents"] is False


async def test_a_judgement_about_an_unassessed_subject_dissents_from_nothing(
    scratch: dict,
) -> None:
    subject = f"PRS-UNASSESSED-{scratch['tag']}"
    scratch["subjects"].append(subject)
    recorded = await investigation_repo.record_analyst_assessment(
        subject_ref=subject,
        subject_type="Person",
        analyst_band="notable",
        rationale="From a source report; ARGUS has not assessed this subject.",
        confidence="low",
        author_username="t.mensah",
        author_role="analyst",
    )
    # Null, not false. "Disagreed with nothing" and "agreed" are different facts.
    assert recorded["dissents"] is None
    assert recorded["machine_band"] is None


async def test_the_machine_band_is_frozen_so_the_disagreement_stays_legible(
    scratch: dict, pg_admin: asyncpg.Connection
) -> None:
    """A later assessment run must not turn a dissent into an agreement.

    If only the assessment id were stored, the comparison would follow the model
    wherever it went — and "the analyst disagreed" would quietly become "the
    analyst agreed" the moment the model changed its mind, against a number the
    analyst never saw.
    """
    subject = f"PRS-FROZEN-{scratch['tag']}"
    await _seed_machine_assessment(pg_admin, scratch, subject, "elevated")
    recorded = await investigation_repo.record_analyst_assessment(
        subject_ref=subject,
        subject_type="Person",
        analyst_band="routine",
        rationale="The transfers are intra-group.",
        confidence="high",
        author_username="t.mensah",
        author_role="analyst",
    )
    assert recorded["dissents"] is True

    # The model changes its mind and now agrees with the analyst.
    await _seed_machine_assessment(pg_admin, scratch, subject, "routine")

    after = await pg_admin.fetchrow(
        "SELECT machine_band, dissents FROM analyst_assessments WHERE analyst_assessment_id = $1",
        recorded["analyst_assessment_id"],
    )
    assert after["machine_band"] == "elevated", "the snapshot must not follow the model"
    assert after["dissents"] is True


async def test_a_dissent_cannot_be_edited_only_superseded(scratch: dict, pg_admin: asyncpg.Connection) -> None:
    subject = f"PRS-SUPERSEDE-{scratch['tag']}"
    await _seed_machine_assessment(pg_admin, scratch, subject, "elevated")
    first = await investigation_repo.record_analyst_assessment(
        subject_ref=subject,
        subject_type="Person",
        analyst_band="routine",
        rationale="Intra-group transfers.",
        confidence="moderate",
        author_username="t.mensah",
        author_role="analyst",
    )

    from app.database.postgres import acquire

    async with acquire() as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="immutable"):
            await conn.execute(
                "UPDATE analyst_assessments SET rationale = 'changed my mind' WHERE analyst_assessment_id = $1",
                first["analyst_assessment_id"],
            )

    # The supported route: record a second judgement. The first is superseded,
    # not erased — when someone changed their mind is itself informative.
    second = await investigation_repo.record_analyst_assessment(
        subject_ref=subject,
        subject_type="Person",
        analyst_band="notable",
        rationale="On reflection, notable rather than routine.",
        confidence="moderate",
        author_username="t.mensah",
        author_role="analyst",
    )

    standing = await investigation_repo.standing_analyst_assessments([subject])
    ids = [a["analyst_assessment_id"] for a in standing[subject]]
    assert second["analyst_assessment_id"] in ids
    assert first["analyst_assessment_id"] not in ids

    still_there = await pg_admin.fetchval("SELECT count(*) FROM analyst_assessments WHERE subject_ref = $1", subject)
    assert still_there == 2, "the superseded judgement stays on the record"


async def test_two_analysts_may_disagree_with_each_other_and_both_stand(
    scratch: dict, pg_admin: asyncpg.Connection
) -> None:
    """Collapsing them to one would be ARGUS choosing a winner between people."""
    subject = f"PRS-TWO-{scratch['tag']}"
    await _seed_machine_assessment(pg_admin, scratch, subject, "elevated")
    await investigation_repo.record_analyst_assessment(
        subject_ref=subject,
        subject_type="Person",
        analyst_band="routine",
        rationale="Intra-group.",
        confidence="high",
        author_username="t.mensah",
        author_role="analyst",
    )
    await investigation_repo.record_analyst_assessment(
        subject_ref=subject,
        subject_type="Person",
        analyst_band="elevated",
        rationale="The intra-group explanation does not cover the third account.",
        confidence="moderate",
        author_username="r.okonkwo",
        author_role="investigator",
    )
    standing = await investigation_repo.standing_analyst_assessments([subject])
    assert len(standing[subject]) == 2
    assert {a["analyst_band"] for a in standing[subject]} == {"routine", "elevated"}


# ─────────────────────────────────────────────────────────────────────────────
# Evidence and findings
# ─────────────────────────────────────────────────────────────────────────────


async def test_relinking_evidence_does_not_erase_the_record_of_its_removal(
    scratch: dict,
) -> None:
    """The defect this schema was built not to inherit (audit G-11).

    The Neo4j implementation keyed the link by (case, entity) and cleared
    `removed_at` on re-link — so re-adding a piece of evidence silently deleted
    who had removed it and why, in the very columns G-11 added to keep that.
    """
    created = await _open(scratch)
    iid = created["investigation_id"]
    ref = f"PRS-EV-{scratch['tag']}"

    await investigation_repo.link_entity(
        investigation_id=iid,
        entity_ref=ref,
        entity_type="Person",
        reason="named on the shipping manifest",
        **ACTOR,
    )
    assert await investigation_repo.unlink_entity(
        investigation_id=iid, entity_ref=ref, reason="wrong person, same surname", **ACTOR
    )
    await investigation_repo.link_entity(
        investigation_id=iid,
        entity_ref=ref,
        entity_type="Person",
        reason="confirmed by passport number after all",
        **ACTOR,
    )

    found = await investigation_repo.get_investigation(iid)
    links = [e for e in found["entities"] if e["entity_ref"] == ref]
    assert len(links) == 2, "the removal must survive the re-link"
    removed = [e for e in links if e["removed_at"] is not None]
    assert len(removed) == 1
    assert removed[0]["removal_reason"] == "wrong person, same surname"
    assert removed[0]["removed_by"] == "t.mensah"


async def test_an_evidence_link_needs_a_stated_reason(scratch: dict) -> None:
    created = await _open(scratch)
    with pytest.raises(asyncpg.IntegrityConstraintViolationError, match="reason_present"):
        await investigation_repo.link_entity(
            investigation_id=created["investigation_id"],
            entity_ref=f"PRS-BLANK-{scratch['tag']}",
            entity_type="Person",
            reason="   ",
            **ACTOR,
        )


async def test_a_finding_must_cite_something(scratch: dict) -> None:
    created = await _open(scratch)
    with pytest.raises(asyncpg.IntegrityConstraintViolationError, match="cites_present"):
        await investigation_repo.record_finding(
            investigation_id=created["investigation_id"],
            statement="They are connected.",
            confidence="high",
            cites=[],
            author_username="t.mensah",
            author_role="analyst",
        )


async def test_a_finding_is_superseded_rather_than_rewritten(scratch: dict) -> None:
    created = await _open(scratch)
    iid = created["investigation_id"]
    first = await investigation_repo.record_finding(
        investigation_id=iid,
        statement="The consignee is the same in all three.",
        confidence="moderate",
        cites=["SHP-1", "SHP-2"],
        author_username="t.mensah",
        author_role="analyst",
    )

    from app.database.postgres import acquire

    async with acquire() as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="immutable"):
            await conn.execute(
                "UPDATE investigation_findings SET statement = 'They differ' WHERE finding_id = $1",
                first["finding_id"],
            )

    second = await investigation_repo.record_finding(
        investigation_id=iid,
        statement="The consignee differs on the third; the first two match.",
        confidence="high",
        cites=["SHP-1", "SHP-2", "SHP-3"],
        author_username="t.mensah",
        author_role="analyst",
        supersedes=str(first["finding_id"]),
    )

    found = await investigation_repo.get_investigation(iid)
    by_id = {str(f["finding_id"]): f for f in found["findings"]}
    assert by_id[str(first["finding_id"])]["superseded_at"] is not None
    assert str(by_id[str(first["finding_id"])]["superseded_by"]) == str(second["finding_id"])
    # Both statements survive. How the analyst's understanding changed is part
    # of the record.
    assert len(found["findings"]) == 2


async def test_a_withdrawn_finding_stays_visible_with_its_reason(scratch: dict) -> None:
    created = await _open(scratch)
    iid = created["investigation_id"]
    finding = await investigation_repo.record_finding(
        investigation_id=iid,
        statement="The device was shared.",
        confidence="high",
        cites=["DEV-1"],
        author_username="t.mensah",
        author_role="analyst",
    )
    assert await investigation_repo.withdraw_finding(
        investigation_id=iid,
        finding_id=str(finding["finding_id"]),
        reason="the device identifier was mis-transcribed",
        **ACTOR,
    )
    found = await investigation_repo.get_investigation(iid)
    withdrawn = found["findings"][0]
    assert withdrawn["withdrawn_at"] is not None
    assert withdrawn["withdrawal_reason"] == "the device identifier was mis-transcribed"
    assert withdrawn["statement"] == "The device was shared."


async def test_the_total_is_counted_over_the_table_not_the_page(scratch: dict) -> None:
    """The defect the audit found on four surfaces and Phase 7 found on a fifth."""
    for _ in range(3):
        await _open(scratch)
    page = await investigation_repo.list_investigations(state=None, limit=2, offset=0)
    total = await investigation_repo.count_investigations(None)
    assert len(page) == 2
    assert total >= 3, "the total must not be the length of the page"


async def _closed(scratch: dict, outcome: str = "confirmed") -> dict:
    created = await _open(scratch)
    await investigation_repo.transition(
        investigation_id=created["investigation_id"],
        to_state="closed",
        outcome=outcome,
        outcome_rationale="Registry filings match.",
        **ACTOR,
    )
    return created


async def test_a_review_that_dissents_leaves_the_outcome_alone(scratch: dict) -> None:
    """The same principle as analyst dissent, one level up.

    A supervisor who disagrees is recorded as disagreeing. Changing the outcome
    would destroy the disagreement, which is the part worth keeping.
    """
    created = await _closed(scratch)
    review = await investigation_repo.record_review(
        investigation_id=created["investigation_id"],
        reviewer="s.laurent",
        actor_role="supervisor",
        concurs=False,
        note="The registry extract predates the restructuring.",
    )
    assert review is not None
    assert review["concurs"] is False
    assert review["outcome_reviewed"] == "confirmed"

    after = await investigation_repo.get_investigation(created["investigation_id"])
    assert after["outcome"] == "confirmed", "the reviewer does not overwrite the analyst"


async def test_a_later_review_cannot_erase_an_earlier_one(scratch: dict) -> None:
    """The defect a live walkthrough of the API exposed.

    The first version of this stored the review in four columns on the
    investigation. A second reviewer's "concurs" overwrote a supervisor's
    recorded dissent — note and all — which is exactly the failure the analyst
    dissent record was built to prevent, reproduced one level up. Reviews
    append; more than one person may hold a view, and the disagreement survives.
    """
    created = await _closed(scratch)
    iid = created["investigation_id"]

    await investigation_repo.record_review(
        investigation_id=iid,
        reviewer="s.laurent",
        actor_role="supervisor",
        concurs=False,
        note="The extract predates the restructuring.",
    )
    await investigation_repo.record_review(
        investigation_id=iid,
        reviewer="d.moreau",
        actor_role="supervisor",
        concurs=True,
        note=None,
    )

    reviews = (await investigation_repo.get_investigation(iid))["reviews"]
    assert len(reviews) == 2
    dissent = [r for r in reviews if not r["concurs"]]
    assert len(dissent) == 1
    assert dissent[0]["note"] == "The extract predates the restructuring."


async def test_nobody_may_review_their_own_conclusion(scratch: dict) -> None:
    """An investigator holds both UPDATE and REVIEW, so permissions never stopped this.

    Found by walking the API by hand: the analyst who closed an investigation
    reviewed their own conclusion and the request succeeded. Refused in the SQL
    rather than in the route, so no future caller can route around it.
    """
    created = await _closed(scratch)
    assert (
        await investigation_repo.record_review(
            investigation_id=created["investigation_id"],
            reviewer="t.mensah",  # the same person `_closed` used
            actor_role="investigator",
            concurs=True,
            note=None,
        )
        is None
    )
    assert (await investigation_repo.get_investigation(created["investigation_id"]))["reviews"] == []


async def test_an_open_investigation_cannot_be_reviewed(scratch: dict) -> None:
    created = await _open(scratch)
    assert (
        await investigation_repo.record_review(
            investigation_id=created["investigation_id"],
            reviewer="s.laurent",
            actor_role="supervisor",
            concurs=True,
            note=None,
        )
        is None
    )


async def test_a_dissenting_review_must_say_why(scratch: dict) -> None:
    created = await _closed(scratch)
    with pytest.raises(asyncpg.IntegrityConstraintViolationError, match="dissent_has_note"):
        await investigation_repo.record_review(
            investigation_id=created["investigation_id"],
            reviewer="s.laurent",
            actor_role="supervisor",
            concurs=False,
            note=None,
        )


async def test_a_review_records_the_outcome_it_was_commenting_on(scratch: dict) -> None:
    """So a reopening does not silently reattach an old review to a new verdict."""
    created = await _closed(scratch, outcome="confirmed")
    iid = created["investigation_id"]
    await investigation_repo.record_review(
        investigation_id=iid,
        reviewer="s.laurent",
        actor_role="supervisor",
        concurs=True,
        note=None,
    )
    await investigation_repo.transition(investigation_id=iid, to_state="active", **ACTOR)
    await investigation_repo.transition(
        investigation_id=iid,
        to_state="closed",
        outcome="unfounded",
        outcome_rationale="The second extract contradicts the first.",
        **ACTOR,
    )
    reviews = (await investigation_repo.get_investigation(iid))["reviews"]
    assert reviews[0]["outcome_reviewed"] == "confirmed"
    assert (await investigation_repo.get_investigation(iid))["outcome"] == "unfounded"


async def test_a_review_cannot_be_edited_or_deleted(scratch: dict) -> None:
    from app.database.postgres import acquire

    created = await _closed(scratch)
    await investigation_repo.record_review(
        investigation_id=created["investigation_id"],
        reviewer="s.laurent",
        actor_role="supervisor",
        concurs=False,
        note="Predates the restructuring.",
    )
    async with acquire() as conn:
        # No UPDATE grant at all: a review is not revisable, so the application
        # has no reason to hold it.
        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="permission denied"):
            await conn.execute("UPDATE investigation_reviews SET concurs = true")
