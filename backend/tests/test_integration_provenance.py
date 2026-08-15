"""The provenance layer against a real PostgreSQL.

What is asserted here cannot be asserted against a mock, because the properties
belong to the database: immutability is a trigger, idempotency is a unique
constraint, and the bitemporal filter is SQL. A fake would agree with whatever
the code believed about itself, which is exactly the gap the audit found.

Test data is namespaced by a unique source id and subject prefix, and torn down
through the admin connection with triggers explicitly disabled — two deliberate
acts, which is precisely the cost the design intends removing a record to carry.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
import pytest_asyncio

from app.config import get_settings
from app.database.postgres import close_postgres, connect_postgres
from app.models.provenance import (
    Credibility,
    EpistemicKind,
    Rating,
    Reliability,
    Source,
    SourceType,
)
from app.repositories import provenance_repo

pytestmark = pytest.mark.asyncio


def _rating(reliability: Reliability, credibility: Credibility) -> Rating:
    return Rating(reliability=reliability, credibility=credibility)


@pytest_asyncio.fixture
async def pg_pool() -> AsyncIterator[None]:
    settings = get_settings()
    try:
        probe = await asyncpg.connect(dsn=settings.postgres_dsn, timeout=5)
    except Exception:
        pytest.skip("No PostgreSQL reachable; skipping provenance integration tests")
    await probe.close()

    await connect_postgres()
    try:
        yield
    finally:
        await close_postgres()


@pytest_asyncio.fixture
async def scope(pg_pool: None) -> AsyncIterator[str]:
    """A unique namespace for one test, cleaned up afterwards.

    Teardown runs as the admin role and disables the append-only triggers. That
    is deliberately awkward: if a test could tidy up through the application's
    own privileges, the immutability guarantee would be worth nothing.
    """
    marker = uuid.uuid4().hex[:12]
    yield marker

    settings = get_settings()
    conn = await asyncpg.connect(dsn=settings.postgres_admin_dsn)
    try:
        async with conn.transaction():
            for table in ("observations", "observation_subjects", "assertions", "assertion_evidence"):
                await conn.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
            await conn.execute(
                """
                DELETE FROM assertion_evidence WHERE assertion_id IN (
                    SELECT assertion_id FROM assertions WHERE subject_ref LIKE $1
                ) OR observation_id IN (
                    SELECT observation_id FROM observations WHERE source_id LIKE $2
                )
                """,
                f"%{marker}%",
                f"%{marker}%",
            )
            await conn.execute("DELETE FROM assertions WHERE subject_ref LIKE $1", f"%{marker}%")
            await conn.execute(
                """
                DELETE FROM observation_subjects WHERE observation_id IN (
                    SELECT observation_id FROM observations WHERE source_id LIKE $1
                )
                """,
                f"%{marker}%",
            )
            await conn.execute("DELETE FROM observations WHERE source_id LIKE $1", f"%{marker}%")
            await conn.execute("DELETE FROM sources WHERE source_id LIKE $1", f"%{marker}%")
            for table in ("observations", "observation_subjects", "assertions", "assertion_evidence"):
                await conn.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")
    finally:
        await conn.close()


async def _source(
    scope: str,
    suffix: str,
    *,
    reliability: Reliability = Reliability.B,
    group: str | None = None,
    synthetic: bool = False,
) -> str:
    source_id = f"test.{scope}.{suffix}"
    await provenance_repo.register_source(
        Source(
            source_id=source_id,
            name=f"Test source {suffix}",
            source_type=SourceType.OSINT,
            description="Integration test fixture",
            reliability=reliability,
            reliability_basis="Fixture",
            is_synthetic=synthetic,
            independence_group=group or source_id,
        )
    )
    return source_id


# ─────────────────────────────────────────────────────────────────────────────
# Immutability
# ─────────────────────────────────────────────────────────────────────────────


async def test_the_application_cannot_alter_or_delete_an_observation(scope: str) -> None:
    """An observation that can be edited after the fact is not evidence of
    anything. This is the property that justified putting the layer in Postgres
    rather than the graph, so it is asserted rather than assumed."""
    source_id = await _source(scope, "immutable")
    observation_id, created = await provenance_repo.record_observation(
        source_id=source_id,
        content_type="test.claim",
        payload={"country": "Canada"},
        subjects=[(f"PRS-{scope}", "Person")],
    )
    assert created

    settings = get_settings()
    conn = await asyncpg.connect(dsn=settings.postgres_dsn)
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "UPDATE observations SET content_type = 'edited' WHERE observation_id = $1",
                uuid.UUID(observation_id),
            )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "DELETE FROM observations WHERE observation_id = $1", uuid.UUID(observation_id)
            )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute("TRUNCATE observations")
    finally:
        await conn.close()


async def test_assertion_content_is_immutable_but_it_can_be_ended(scope: str) -> None:
    """A belief must be able to end — superseded or retracted — without its
    content becoming editable. Rewriting what was claimed, rather than recording
    that it was withdrawn, destroys the history a review depends on."""
    source_id = await _source(scope, "assertion-immutable")
    subject = f"PRS-{scope}"
    assertion_id = await provenance_repo.record_assertion(
        subject_ref=subject,
        subject_type="Person",
        predicate="country",
        object_value="Canada",
        epistemic_kind=EpistemicKind.REPORTED,
        rating=_rating(Reliability.B, Credibility.PROBABLY_TRUE),
        method="source-report",
        asserted_by=f"source:{source_id}",
    )

    settings = get_settings()
    conn = await asyncpg.connect(dsn=settings.postgres_dsn)
    try:
        # Each of these is a way of quietly rewriting history: changing the
        # claim, inflating either rating, or promoting an inference to an
        # observation. All must be refused.
        for statement in [
            """UPDATE assertions SET object_value = '"Mexico"'::jsonb WHERE assertion_id = $1""",
            "UPDATE assertions SET reliability = 'A' WHERE assertion_id = $1",
            "UPDATE assertions SET credibility = '1' WHERE assertion_id = $1",
            "UPDATE assertions SET epistemic_kind = 'observed' WHERE assertion_id = $1",
            "UPDATE assertions SET predicate = 'nationality' WHERE assertion_id = $1",
            "UPDATE assertions SET asserted_by = 'user:someone-else' WHERE assertion_id = $1",
        ]:
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.execute(statement, uuid.UUID(assertion_id))
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "DELETE FROM assertions WHERE assertion_id = $1", uuid.UUID(assertion_id)
            )
    finally:
        await conn.close()

    # Ending it is permitted, through the one supported path.
    assert await provenance_repo.retract_assertion(
        assertion_id, retracted_by="user:test", reason="source withdrew the claim"
    )


async def test_a_retraction_cannot_be_reversed(scope: str) -> None:
    """Un-retracting would let someone quietly restore a discredited belief. The
    supported move is to assert it again, which leaves both records visible."""
    source_id = await _source(scope, "no-unretract")
    assertion_id = await provenance_repo.record_assertion(
        subject_ref=f"PRS-{scope}",
        subject_type="Person",
        predicate="status",
        object_value="Wanted",
        epistemic_kind=EpistemicKind.REPORTED,
        rating=_rating(Reliability.C, Credibility.POSSIBLY_TRUE),
        method="source-report",
        asserted_by=f"source:{source_id}",
    )
    await provenance_repo.retract_assertion(
        assertion_id, retracted_by="user:test", reason="incorrect"
    )

    settings = get_settings()
    conn = await asyncpg.connect(dsn=settings.postgres_dsn)
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "UPDATE assertions SET retracted_at = NULL WHERE assertion_id = $1",
                uuid.UUID(assertion_id),
            )
    finally:
        await conn.close()

    # And the repository reports the second attempt as a no-op rather than
    # overwriting the recorded reason with a later one.
    assert not await provenance_repo.retract_assertion(
        assertion_id, retracted_by="user:other", reason="different reason"
    )
    stored = await provenance_repo.get_assertion(assertion_id)
    assert stored is not None
    assert stored.retraction_reason == "incorrect"


async def test_a_retraction_requires_a_reason(scope: str) -> None:
    source_id = await _source(scope, "reason-required")
    assertion_id = await provenance_repo.record_assertion(
        subject_ref=f"PRS-{scope}",
        subject_type="Person",
        predicate="status",
        object_value="Active",
        epistemic_kind=EpistemicKind.REPORTED,
        rating=_rating(Reliability.C, Credibility.POSSIBLY_TRUE),
        method="source-report",
        asserted_by=f"source:{source_id}",
    )
    with pytest.raises(provenance_repo.RetractionRefused):
        await provenance_repo.retract_assertion(assertion_id, retracted_by="user:x", reason="   ")


# ─────────────────────────────────────────────────────────────────────────────
# Idempotency
# ─────────────────────────────────────────────────────────────────────────────


async def test_the_same_payload_twice_yields_one_observation(scope: str) -> None:
    """Replaying a feed must not look like independent confirmation. Without
    this, re-ingesting one file would multiply every corroboration count derived
    from it."""
    source_id = await _source(scope, "idempotent")
    payload = {"country": "Canada", "city": "Toronto"}

    first_id, first_created = await provenance_repo.record_observation(
        source_id=source_id,
        content_type="test.claim",
        payload=payload,
        subjects=[(f"PRS-{scope}", "Person")],
    )
    # Same content, different key order — the canonical hash must not care.
    second_id, second_created = await provenance_repo.record_observation(
        source_id=source_id,
        content_type="test.claim",
        payload={"city": "Toronto", "country": "Canada"},
        subjects=[(f"PRS-{scope}", "Person")],
    )

    assert first_created and not second_created
    assert first_id == second_id
    assert len(await provenance_repo.observations_for_subject(f"PRS-{scope}")) == 1


async def test_two_sources_reporting_the_same_thing_are_two_observations(scope: str) -> None:
    """Deduplication is per source. Two sources independently saying the same
    thing is corroboration, and collapsing them would erase it."""
    source_a = await _source(scope, "dedup-a")
    source_b = await _source(scope, "dedup-b")
    payload = {"country": "Canada"}

    for source_id in (source_a, source_b):
        await provenance_repo.record_observation(
            source_id=source_id,
            content_type="test.claim",
            payload=payload,
            subjects=[(f"PRS-{scope}", "Person")],
        )

    assert len(await provenance_repo.observations_for_subject(f"PRS-{scope}")) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Corroboration and independence
# ─────────────────────────────────────────────────────────────────────────────


async def test_corroboration_counts_independent_groups_not_observations(scope: str) -> None:
    """Two feeds reprinting one wire service are one voice.

    This is the difference between "three sources agree" and "one source, quoted
    three times" — and it is the mechanism by which a single rumour otherwise
    comes to look like a corroborated pattern.
    """
    wire = await _source(scope, "wire", group=f"test.{scope}.wire-group")
    reprint = await _source(scope, "reprint", group=f"test.{scope}.wire-group")
    independent = await _source(scope, "independent")

    subject = f"PRS-{scope}"
    observation_ids = []
    for index, source_id in enumerate((wire, reprint, independent)):
        observation_id, _ = await provenance_repo.record_observation(
            source_id=source_id,
            content_type="test.claim",
            payload={"country": "Canada", "seq": index},
            subjects=[(subject, "Person")],
        )
        observation_ids.append(observation_id)

    assertion_id = await provenance_repo.record_assertion(
        subject_ref=subject,
        subject_type="Person",
        predicate="country",
        object_value="Canada",
        epistemic_kind=EpistemicKind.REPORTED,
        rating=_rating(Reliability.B, Credibility.PROBABLY_TRUE),
        method="source-report",
        asserted_by="user:test",
        evidence=[(oid, "supports") for oid in observation_ids],
    )

    assertion = await provenance_repo.get_assertion(assertion_id)
    assert assertion is not None
    assert assertion.corroboration is not None
    assert assertion.corroboration.supporting_observations == 3
    assert assertion.corroboration.independent_sources == 2, (
        "the wire service and its reprint must count once, not twice"
    )


async def test_contradicting_evidence_is_kept_against_the_assertion(scope: str) -> None:
    """An assertion whose counter-evidence was discarded looks better supported
    than it is."""
    supporting_source = await _source(scope, "for")
    opposing_source = await _source(scope, "against")
    subject = f"PRS-{scope}"

    for_id, _ = await provenance_repo.record_observation(
        source_id=supporting_source,
        content_type="test.claim",
        payload={"country": "Canada"},
        subjects=[(subject, "Person")],
    )
    against_id, _ = await provenance_repo.record_observation(
        source_id=opposing_source,
        content_type="test.claim",
        payload={"country": "Mexico"},
        subjects=[(subject, "Person")],
    )

    assertion_id = await provenance_repo.record_assertion(
        subject_ref=subject,
        subject_type="Person",
        predicate="country",
        object_value="Canada",
        epistemic_kind=EpistemicKind.ASSESSED,
        rating=_rating(Reliability.B, Credibility.DOUBTFUL),
        method="analyst-judgement",
        asserted_by="user:test",
        evidence=[(for_id, "supports"), (against_id, "contradicts")],
    )

    assertion = await provenance_repo.get_assertion(assertion_id)
    assert assertion is not None
    assert assertion.corroboration is not None
    assert assertion.corroboration.supporting_observations == 1
    assert assertion.corroboration.contradicting_observations == 1
    assert {e.stance for e in assertion.evidence} == {"supports", "contradicts"}


# ─────────────────────────────────────────────────────────────────────────────
# Conflict
# ─────────────────────────────────────────────────────────────────────────────


async def test_contradictory_assertions_are_both_returned_with_no_winner(scope: str) -> None:
    """The phase's defining behaviour.

    Two sources disagree about a person's country. A worse system picks the one
    with the better rating and shows a single value; the analyst then never
    learns there was a disagreement at all. Both must come back, and neither may
    be marked as preferred — including when one source is rated A1 and the other
    E5, which is the case most likely to tempt an automatic resolution.
    """
    strong = await _source(scope, "strong", reliability=Reliability.A)
    weak = await _source(scope, "weak", reliability=Reliability.E)
    subject = f"PRS-{scope}"

    await provenance_repo.record_assertion(
        subject_ref=subject,
        subject_type="Person",
        predicate="country",
        object_value="Canada",
        epistemic_kind=EpistemicKind.REPORTED,
        rating=_rating(Reliability.A, Credibility.CONFIRMED),
        method="source-report",
        asserted_by=f"source:{strong}",
    )
    await provenance_repo.record_assertion(
        subject_ref=subject,
        subject_type="Person",
        predicate="country",
        object_value="Mexico",
        epistemic_kind=EpistemicKind.REPORTED,
        rating=_rating(Reliability.E, Credibility.IMPROBABLE),
        method="source-report",
        asserted_by=f"source:{weak}",
    )

    conflicts = await provenance_repo.conflicts_for_subject(subject)
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.predicate == "country"
    assert {a.object_value for a in conflict.assertions} == {"Canada", "Mexico"}
    assert {a.rating.code for a in conflict.assertions} == {"A1", "E5"}
    assert not hasattr(conflict, "winner")


async def test_agreeing_assertions_are_not_a_conflict(scope: str) -> None:
    source_a = await _source(scope, "agree-a")
    source_b = await _source(scope, "agree-b")
    subject = f"PRS-{scope}"

    for source_id in (source_a, source_b):
        await provenance_repo.record_assertion(
            subject_ref=subject,
            subject_type="Person",
            predicate="country",
            object_value="Canada",
            epistemic_kind=EpistemicKind.REPORTED,
            rating=_rating(Reliability.B, Credibility.PROBABLY_TRUE),
            method="source-report",
            asserted_by=f"source:{source_id}",
        )

    assert await provenance_repo.conflicts_for_subject(subject) == []


async def test_superseding_an_assertion_ends_the_conflict(scope: str) -> None:
    """Correction is how a conflict is resolved — by a person, recorded — not by
    the system choosing. The superseded assertion stays retrievable."""
    source_id = await _source(scope, "supersede")
    subject = f"PRS-{scope}"

    first = await provenance_repo.record_assertion(
        subject_ref=subject,
        subject_type="Person",
        predicate="country",
        object_value="Canada",
        epistemic_kind=EpistemicKind.REPORTED,
        rating=_rating(Reliability.C, Credibility.POSSIBLY_TRUE),
        method="source-report",
        asserted_by=f"source:{source_id}",
    )
    second = await provenance_repo.record_assertion(
        subject_ref=subject,
        subject_type="Person",
        predicate="country",
        object_value="Mexico",
        epistemic_kind=EpistemicKind.REPORTED,
        rating=_rating(Reliability.B, Credibility.PROBABLY_TRUE),
        method="source-report",
        asserted_by=f"source:{source_id}",
        supersedes=first,
    )

    assert await provenance_repo.conflicts_for_subject(subject) == []
    current = await provenance_repo.assertions_for_subject(subject)
    assert [a.assertion_id for a in current] == [second]

    with_history = await provenance_repo.assertions_for_subject(subject, include_ended=True)
    assert {a.assertion_id for a in with_history} == {first, second}
    superseded = next(a for a in with_history if a.assertion_id == first)
    assert superseded.superseded_by == second
    assert not superseded.is_current


# ─────────────────────────────────────────────────────────────────────────────
# Bitemporality
# ─────────────────────────────────────────────────────────────────────────────


async def test_what_argus_believed_at_a_past_instant_is_answerable(scope: str) -> None:
    """Post-incident review turns on this question. Without it, the record shows
    only the conclusion eventually reached, never what was actually available to
    the person deciding at the time.
    """
    await _source(scope, "bitemporal")
    subject = f"PRS-{scope}"

    first = await provenance_repo.record_assertion(
        subject_ref=subject,
        subject_type="Person",
        predicate="threat_status",
        object_value="Low",
        epistemic_kind=EpistemicKind.ASSESSED,
        rating=_rating(Reliability.C, Credibility.POSSIBLY_TRUE),
        method="analyst-judgement",
        asserted_by="user:analyst-one",
    )

    stored = await provenance_repo.get_assertion(first)
    assert stored is not None
    before_change = stored.asserted_at + timedelta(milliseconds=1)

    second = await provenance_repo.record_assertion(
        subject_ref=subject,
        subject_type="Person",
        predicate="threat_status",
        object_value="High",
        epistemic_kind=EpistemicKind.ASSESSED,
        rating=_rating(Reliability.B, Credibility.PROBABLY_TRUE),
        method="analyst-judgement",
        asserted_by="user:analyst-two",
        supersedes=first,
    )

    past = await provenance_repo.assertions_for_subject(subject, as_of=before_change)
    assert [a.object_value for a in past] == ["Low"], (
        "as-of must return the belief held at that instant, not today's"
    )

    now = await provenance_repo.assertions_for_subject(subject)
    assert [a.object_value for a in now] == ["High"]

    # Before anything was asserted, ARGUS believed nothing — and says so rather
    # than falling back to the earliest record it happens to hold.
    earlier = stored.asserted_at - timedelta(hours=1)
    assert await provenance_repo.assertions_for_subject(subject, as_of=earlier) == []

    future = await provenance_repo.assertions_for_subject(
        subject, as_of=datetime.now(UTC) + timedelta(days=1)
    )
    assert [a.assertion_id for a in future] == [second]


async def test_a_retracted_assertion_is_still_visible_in_the_past(scope: str) -> None:
    """Reconstructing a past belief must include beliefs since withdrawn.
    Filtering them out would show a cleaner history than the one that happened,
    which is the opposite of what a review needs."""
    source_id = await _source(scope, "retracted-past")
    subject = f"PRS-{scope}"

    assertion_id = await provenance_repo.record_assertion(
        subject_ref=subject,
        subject_type="Person",
        predicate="affiliation",
        object_value="GroupX",
        epistemic_kind=EpistemicKind.REPORTED,
        rating=_rating(Reliability.D, Credibility.DOUBTFUL),
        method="source-report",
        asserted_by=f"source:{source_id}",
    )
    stored = await provenance_repo.get_assertion(assertion_id)
    assert stored is not None
    while_believed = stored.asserted_at + timedelta(milliseconds=1)

    await provenance_repo.retract_assertion(
        assertion_id, retracted_by="user:test", reason="source recanted"
    )

    assert await provenance_repo.assertions_for_subject(subject) == []
    past = await provenance_repo.assertions_for_subject(subject, as_of=while_believed)
    assert [a.object_value for a in past] == ["GroupX"]


async def test_observations_are_filtered_by_when_argus_learned_them(scope: str) -> None:
    source_id = await _source(scope, "obs-asof")
    subject = f"PRS-{scope}"

    observation_id, _ = await provenance_repo.record_observation(
        source_id=source_id,
        content_type="test.claim",
        payload={"country": "Canada"},
        subjects=[(subject, "Person")],
    )
    observation = await provenance_repo.get_observation(observation_id)
    assert observation is not None

    before = observation.recorded_at - timedelta(seconds=1)
    assert await provenance_repo.observations_for_subject(subject, as_of=before) == []
    after = observation.recorded_at + timedelta(seconds=1)
    assert len(await provenance_repo.observations_for_subject(subject, as_of=after)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Honest absence
# ─────────────────────────────────────────────────────────────────────────────


async def test_unknown_collection_time_stays_null(scope: str) -> None:
    """A source that never recorded when it collected something must not be
    given a plausible timestamp. `collected_at` has no default for exactly this
    reason: a fabricated instant is worse than a visible gap."""
    source_id = await _source(scope, "no-collection-time")
    observation_id, _ = await provenance_repo.record_observation(
        source_id=source_id,
        content_type="test.claim",
        payload={"country": "Canada"},
        subjects=[(f"PRS-{scope}", "Person")],
    )
    observation = await provenance_repo.get_observation(observation_id)
    assert observation is not None
    assert observation.collected_at is None
    assert observation.occurred_at is None
    assert observation.recorded_at is not None


async def test_attribute_provenance_reports_its_own_denominator(scope: str) -> None:
    """A bounded read must not look like a complete one.

    `attribute_provenance` resolves each field against a LIMITed window of
    observations. Without the total, a field whose only observation fell outside
    that window would come back `unattributed` — indistinguishable from a field
    nothing ever reported. One is a statement about the world; the other is a
    statement about a LIMIT clause, and Phase 0 exists because ARGUS used to
    render the second as the first.
    """
    from app.services.provenance import attribute_provenance

    source_id = await _source(scope, "denominator")
    subject = f"PRS-{scope}"

    for index in range(5):
        await provenance_repo.record_observation(
            source_id=source_id,
            content_type="test.claim",
            payload={"country": "Canada", "seq": index},
            subjects=[(subject, "Person")],
        )

    complete = await attribute_provenance(subject, {"country": "Canada"}, limit=50)
    assert complete.observations_total == 5
    assert complete.observations_examined == 5
    assert complete.complete
    assert complete.attributes["country"]["kind"] == "reported"

    truncated = await attribute_provenance(subject, {"country": "Canada"}, limit=2)
    assert truncated.observations_total == 5
    assert truncated.observations_examined == 2
    assert not truncated.complete, (
        "a partial read must report itself as partial, or the caller cannot tell "
        "an absent source from an unread one"
    )


async def test_a_modified_value_is_not_reported_as_sourced(scope: str) -> None:
    """An edit that inherits its original's provenance is a forgery.

    If the stored value no longer matches what the source said, the field is
    `modified` — the source is still shown, along with what it actually
    reported, so the divergence is visible rather than smoothed over.
    """
    from app.services.provenance import attribute_provenance

    source_id = await _source(scope, "modified")
    subject = f"PRS-{scope}"
    await provenance_repo.record_observation(
        source_id=source_id,
        content_type="test.claim",
        payload={"country": "Canada"},
        subjects=[(subject, "Person")],
    )

    matching = await attribute_provenance(subject, {"country": "Canada"})
    assert matching.attributes["country"]["kind"] == "reported"

    # The graph now says something the source never did.
    changed = await attribute_provenance(subject, {"country": "Mexico"})
    entry = changed.attributes["country"]
    assert entry["kind"] == "modified"
    assert entry["observations"][0]["reported_value"] == "Canada"
    assert entry["observations"][0]["matches_current_value"] is False

    # And a field no source mentioned at all is neither of those.
    unknown = await attribute_provenance(subject, {"shoe_size": 44})
    assert unknown.attributes["shoe_size"]["kind"] == "unattributed"
    assert unknown.attributes["shoe_size"]["observations"] == []


async def test_attribution_resolves_to_a_readable_name(scope: str) -> None:
    """Attribution nobody can read is not attribution.

    `asserted_by` stores a stable identifier so a rename cannot orphan a record,
    but the UI rendered it directly and an analyst judgement appeared as
    `user:b4e9468f-4dac-…`. Found in browser verification, not by any test: the
    API was returning exactly what it was asked for. The readable form is
    resolved on read rather than stored, so a rename tracks through without
    rewriting an immutable row.
    """
    source_id = await _source(scope, "attribution")
    subject = f"PRS-{scope}"

    from_source = await provenance_repo.record_assertion(
        subject_ref=subject,
        subject_type="Person",
        predicate="country",
        object_value="Canada",
        epistemic_kind=EpistemicKind.REPORTED,
        rating=_rating(Reliability.B, Credibility.PROBABLY_TRUE),
        method="source-report",
        asserted_by=f"source:{source_id}",
    )
    resolved = await provenance_repo.get_assertion(from_source)
    assert resolved is not None
    assert resolved.asserted_by == f"source:{source_id}"
    assert resolved.asserted_by_display == "Test source attribution"

    # An identifier with no matching row falls back to itself. Showing an empty
    # byline for a deleted user would erase the attribution entirely, which is
    # worse than showing the raw id.
    orphaned = await provenance_repo.record_assertion(
        subject_ref=subject,
        subject_type="Person",
        predicate="status",
        object_value="Unknown",
        epistemic_kind=EpistemicKind.ASSESSED,
        rating=_rating(Reliability.F, Credibility.CANNOT_BE_JUDGED),
        method="analyst-judgement",
        asserted_by="user:00000000-0000-0000-0000-000000000000",
    )
    fallback = await provenance_repo.get_assertion(orphaned)
    assert fallback is not None
    assert fallback.asserted_by_display == "user:00000000-0000-0000-0000-000000000000"


async def test_registering_a_source_never_overwrites_its_rating(scope: str) -> None:
    """A reliability rating is an analytic judgement. Re-registration on every
    boot must not silently change what every assertion resting on it means."""
    source_id = await _source(scope, "rating-stable", reliability=Reliability.B)
    await provenance_repo.register_source(
        Source(
            source_id=source_id,
            name="Renamed",
            source_type=SourceType.OSINT,
            description="Attempted overwrite",
            reliability=Reliability.A,
            reliability_basis="Should not take effect",
            is_synthetic=False,
            independence_group=source_id,
        )
    )
    stored = await provenance_repo.get_source(source_id)
    assert stored is not None
    assert stored.reliability is Reliability.B
    assert stored.name == "Test source rating-stable"
