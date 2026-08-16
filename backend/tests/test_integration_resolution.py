"""Entity resolution against a real PostgreSQL and a real Neo4j.

The properties asserted here are the ones a mock cannot tell you about: that
the database refuses to rewrite a decision, that a merge leaves both entity
nodes untouched, that reversal is an INSERT rather than an edit, and that the
graph projection can be thrown away and re-derived from the ledger.

Test entities are created with ids far outside the generator's range and are
removed afterwards. The ledger is append-only, so clearing it requires the
admin role *and* disabling a trigger — the privilege boundary is doing its job,
and cleanup is deliberately an administrative act.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from app.config import get_settings
from app.database.postgres import acquire, close_postgres, connect_postgres
from app.repositories import resolution_graph_repo as graph_repo
from app.repositories import resolution_repo as repo
from app.resolution.profile import EntityProfile
from app.resolution.scoring import compare
from app.services import resolution

pytestmark = pytest.mark.asyncio

# Well clear of the generator's allocations, so a test can never collide with
# — or be mistaken for — a real record. The *attributes* are equally invented:
# an earlier version of this fixture copied a real person's name and phone,
# which made probes match her too and coupled the tests to production data.
BASE = 9_900_000
MARKER = "argus-resolution-test"

_LEDGER_TABLES = ("resolution_decisions", "resolution_labels", "resolution_evaluations")


def ref(offset: int) -> str:
    return f"PRS-{BASE + offset:07d}"


@pytest_asyncio.fixture
async def stack(driver: AsyncDriver) -> AsyncIterator[AsyncDriver]:
    """A real Postgres and a real Neo4j, with every test artefact removed after."""
    settings = get_settings()
    try:
        probe = await asyncpg.connect(dsn=settings.postgres_dsn, timeout=5)
    except Exception:
        pytest.skip("No PostgreSQL reachable; skipping resolution integration tests")
    await probe.close()

    await connect_postgres()

    # The service reaches for the process-wide driver; point it at the test one.
    import app.database.neo4j as neo4j_module

    previous = getattr(neo4j_module, "_driver", None)
    neo4j_module._driver = driver

    # Evaluations are published measurements in an append-only table. A test
    # that persists one and never removes it leaves the environment claiming a
    # report nobody ran, so the high-water mark is captured here and anything
    # above it is cleared at teardown.
    async with acquire() as conn:
        evaluation_mark = (
            await conn.fetchval(
                "SELECT coalesce(max(evaluation_id), 0) FROM resolution_evaluations"
            )
        ) or 0

    refs = [ref(i) for i in range(12)]
    async with driver.session() as session:
        await session.run(
            """
            UNWIND $rows AS row
            CREATE (p:Person)
            SET p = row, p.marker = $marker
            """,
            rows=[
                {
                    "person_id": refs[0], "id": str(uuid.uuid4()), "name": "Wilhelmina Ashgrove",
                    "dob": "1988-04-23", "phone": "+1 6470009911", "city": "Thunder Bay",
                    "state": "Ontario", "country": "Canada", "nationality": "Canada",
                    "occupation": "Logistics Manager", "gender": "Female",
                    "lat": 43.672958, "lng": -79.300179,
                },
                {
                    "person_id": refs[1], "id": str(uuid.uuid4()), "name": "W. Ashgrove",
                    "dob": "1988-04-23", "phone": "16470009911", "city": "Thunder Bay",
                    "state": "Ontario", "country": "Canada", "nationality": "Canada",
                    "occupation": "Logistics Manager", "gender": "Female",
                    "lat": 43.672958, "lng": -79.300179,
                },
                # Deliberately a *different* phone from refs[0] and refs[1]:
                # this is the record a feed can be resolved onto unambiguously,
                # while refs[0]/refs[1] share a number and so are ambiguous
                # with each other by design.
                {
                    "person_id": refs[2], "id": str(uuid.uuid4()), "name": "Wilhelmina R Ashgrove",
                    "dob": "1988-04-23", "phone": "+1 555000222", "city": "Thunder Bay",
                    "state": "Ontario", "country": "Canada", "nationality": "Canada",
                    "occupation": "Logistics Manager", "gender": "Female",
                },
                {
                    "person_id": refs[3], "id": str(uuid.uuid4()), "name": "Berenike Falkenrath",
                    "dob": "1951-12-05", "phone": "+234 9670001122", "city": "Lagos",
                    "state": "Lagos", "country": "Nigeria", "nationality": "Nigeria",
                    "occupation": "Retail Shop Owner", "gender": "Female",
                },
            ],
            marker=MARKER,
        )

    try:
        yield driver
    finally:
        async with driver.session() as session:
            await session.run("MATCH (n {marker: $marker}) DETACH DELETE n", marker=MARKER)

        admin = await asyncpg.connect(dsn=settings.postgres_admin_dsn)
        try:
            async with admin.transaction():
                for table in _LEDGER_TABLES:
                    await admin.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
                await admin.execute(
                    "DELETE FROM resolution_decisions WHERE left_ref = ANY($1::text[]) "
                    "OR right_ref = ANY($1::text[])",
                    refs,
                )
                await admin.execute(
                    "DELETE FROM resolution_labels WHERE left_ref = ANY($1::text[]) "
                    "OR right_ref = ANY($1::text[])",
                    refs,
                )
                await admin.execute(
                    "DELETE FROM resolution_evaluations WHERE evaluation_id > $1",
                    evaluation_mark,
                )
                for table in _LEDGER_TABLES:
                    await admin.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")
                await admin.execute(
                    "DELETE FROM resolution_candidates WHERE left_ref = ANY($1::text[]) "
                    "OR right_ref = ANY($1::text[])",
                    refs,
                )
                await admin.execute(
                    "DELETE FROM resolution_cluster_members WHERE ref = ANY($1::text[])", refs
                )
                await admin.execute(
                    "DELETE FROM resolution_clusters WHERE canonical_ref = ANY($1::text[])", refs
                )
                await admin.execute(
                    "DELETE FROM resolution_canonical_pins WHERE ref = ANY($1::text[])", refs
                )
                await admin.execute(
                    "DELETE FROM resolution_blocking_index WHERE ref = ANY($1::text[])", refs
                )
        finally:
            await admin.close()

        # Rebuild before tearing the pool down: the cluster projection is
        # derived, and leaving it describing deleted test records would make the
        # next run's counts wrong.
        await resolution.rebuild_clusters()
        neo4j_module._driver = previous
        await close_postgres()


async def _snapshot(driver: AsyncDriver, person_ref: str) -> dict:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (p:Person {person_id: $ref}) RETURN properties(p) AS props", ref=person_ref
        )
        record = await result.single()
    return dict(record["props"]) if record else {}


# ── The central guarantee ────────────────────────────────────────────────────


async def test_a_merge_never_destroys_either_record(stack: AsyncDriver) -> None:
    """The acceptance criterion, asserted byte-for-byte on both nodes.

    Nothing in the resolution feature writes to an entity node, so this holds
    by construction rather than by care — but it is the claim the whole phase
    rests on, so it is checked rather than argued.
    """
    before_left = await _snapshot(stack, ref(0))
    before_right = await _snapshot(stack, ref(1))

    await resolution.decide(
        left_ref=ref(0), right_ref=ref(1), verdict="same",
        actor="user:test", actor_kind="analyst", rationale="same phone and date of birth",
    )

    assert await _snapshot(stack, ref(0)) == before_left
    assert await _snapshot(stack, ref(1)) == before_right


async def test_a_merge_is_reversible_and_both_decisions_survive(stack: AsyncDriver) -> None:
    merge = await resolution.decide(
        left_ref=ref(0), right_ref=ref(1), verdict="same",
        actor="user:test", actor_kind="analyst", rationale="looks like the same person",
    )
    await resolution.reverse_decision(
        merge["decision_id"], actor="user:supervisor", actor_kind="analyst",
        rationale="different people; the phone is a shared office line",
    )

    history = await repo.decision_history(ref(0), ref(1))
    assert [d.verdict for d in history] == ["same", "different"]
    assert history[1].reverses_decision_id == history[0].decision_id
    # The original is untouched — "merged then un-merged" is a different record
    # from "never merged", and only the append-only form can tell them apart.
    assert history[0].rationale == "looks like the same person"

    current = await repo.current_decision(ref(0), ref(1))
    assert current is not None and current.verdict == "different"

    # And both records are still there.
    assert await graph_repo.entity_exists(stack, ref(0))
    assert await graph_repo.entity_exists(stack, ref(1))


async def test_reversal_removes_the_graph_projection_only(stack: AsyncDriver) -> None:
    merge = await resolution.decide(
        left_ref=ref(0), right_ref=ref(1), verdict="same",
        actor="user:test", actor_kind="analyst", rationale="same phone",
    )
    assert await graph_repo.same_as_neighbours(stack, ref(0))

    await resolution.reverse_decision(
        merge["decision_id"], actor="user:test", actor_kind="analyst", rationale="mistaken",
    )
    assert await graph_repo.same_as_neighbours(stack, ref(0)) == []
    assert await graph_repo.entity_exists(stack, ref(1))


async def test_the_decision_ledger_refuses_to_be_rewritten(stack: AsyncDriver) -> None:
    """Enforced by the database for every role, not by the application."""
    result = await resolution.decide(
        left_ref=ref(0), right_ref=ref(1), verdict="same",
        actor="user:test", actor_kind="analyst", rationale="same phone",
    )
    async with acquire() as conn:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "UPDATE resolution_decisions SET verdict = 'different' WHERE decision_id = $1",
                result["decision_id"],
            )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn.execute(
                "DELETE FROM resolution_decisions WHERE decision_id = $1",
                result["decision_id"],
            )


async def test_reversing_a_superseded_decision_is_refused(stack: AsyncDriver) -> None:
    """Otherwise two people racing to undo each other produce a ledger whose
    current state depends on who committed last."""
    merge = await resolution.decide(
        left_ref=ref(0), right_ref=ref(1), verdict="same",
        actor="user:a", actor_kind="analyst", rationale="same phone",
    )
    await resolution.reverse_decision(
        merge["decision_id"], actor="user:b", actor_kind="analyst", rationale="no",
    )
    with pytest.raises(resolution.DecisionRefused, match="no longer the current"):
        await resolution.reverse_decision(
            merge["decision_id"], actor="user:c", actor_kind="analyst", rationale="again",
        )


async def test_a_decision_must_state_a_reason(stack: AsyncDriver) -> None:
    with pytest.raises(resolution.DecisionRefused, match="state its reason"):
        await resolution.decide(
            left_ref=ref(0), right_ref=ref(1), verdict="same",
            actor="user:test", actor_kind="analyst", rationale="   ",
        )


async def test_a_record_cannot_be_resolved_against_itself(stack: AsyncDriver) -> None:
    with pytest.raises(resolution.DecisionRefused, match="against itself"):
        await resolution.decide(
            left_ref=ref(0), right_ref=ref(0), verdict="same",
            actor="user:test", actor_kind="analyst", rationale="x",
        )


async def test_identity_is_never_resolved_across_entity_types(stack: AsyncDriver) -> None:
    with pytest.raises(resolution.DecisionRefused, match="different entity types"):
        await resolution.decide(
            left_ref=ref(0), right_ref="ORG-0000001", verdict="same",
            actor="user:test", actor_kind="analyst", rationale="x",
        )


async def test_the_pair_is_stored_in_one_canonical_order(stack: AsyncDriver) -> None:
    """Without this, (A,B) and (B,A) become two decisions that can contradict."""
    await resolution.decide(
        left_ref=ref(1), right_ref=ref(0), verdict="same",
        actor="user:test", actor_kind="analyst", rationale="same phone",
    )
    assert await repo.current_decision(ref(0), ref(1)) is not None
    assert await repo.current_decision(ref(1), ref(0)) is not None
    assert len(await repo.decision_history(ref(1), ref(0))) == 1


# ── Clusters ─────────────────────────────────────────────────────────────────


async def test_clusters_close_transitively_and_flag_a_contradiction(
    stack: AsyncDriver,
) -> None:
    for left, right in ((ref(0), ref(1)), (ref(1), ref(2))):
        await resolution.decide(
            left_ref=left, right_ref=right, verdict="same",
            actor="user:test", actor_kind="analyst", rationale="same phone and dob",
        )
    cluster = await repo.cluster_for_ref(ref(0))
    assert cluster is not None
    assert set(cluster["members"]) == {ref(0), ref(1), ref(2)}
    assert cluster["contested"] is False

    # Now contradict the chain. ARGUS must not silently drop a link to make the
    # cluster consistent again.
    await resolution.decide(
        left_ref=ref(0), right_ref=ref(2), verdict="different",
        actor="user:test", actor_kind="analyst", rationale="different national records",
    )
    contested = await repo.cluster_for_ref(ref(0))
    assert contested is not None
    assert contested["contested"] is True
    assert ref(0) in contested["contested_reason"]
    assert set(contested["members"]) == {ref(0), ref(1), ref(2)}


async def test_a_cluster_states_how_its_canonical_record_was_chosen(
    stack: AsyncDriver,
) -> None:
    await resolution.decide(
        left_ref=ref(0), right_ref=ref(1), verdict="same",
        actor="user:test", actor_kind="analyst", rationale="same phone",
    )
    cluster = await repo.cluster_for_ref(ref(0))
    assert cluster is not None
    assert cluster["canonical_ref"] in cluster["members"]
    assert cluster["canonical_basis"]


async def test_an_analyst_pin_overrides_the_canonical_rule(stack: AsyncDriver) -> None:
    await resolution.decide(
        left_ref=ref(0), right_ref=ref(1), verdict="same",
        actor="user:test", actor_kind="analyst", rationale="same phone",
    )
    await repo.pin_canonical(ref(1), pinned_by="user:test", reason="richer record")
    await resolution.rebuild_clusters()
    cluster = await repo.cluster_for_ref(ref(0))
    assert cluster is not None
    assert cluster["canonical_ref"] == ref(1)
    assert "pinned" in cluster["canonical_basis"]


# ── The projection is derived, not authoritative ─────────────────────────────


async def test_the_graph_projection_can_be_thrown_away_and_rebuilt(
    stack: AsyncDriver,
) -> None:
    """If Postgres and the graph ever disagree, Postgres wins. Asserted rather
    than described, so "the graph is a projection" is a testable claim."""
    await resolution.decide(
        left_ref=ref(0), right_ref=ref(1), verdict="same",
        actor="user:test", actor_kind="analyst", rationale="same phone",
    )
    async with stack.session() as session:
        await session.run("MATCH ()-[r:SAME_AS]-() DELETE r")
    assert await graph_repo.same_as_neighbours(stack, ref(0)) == []

    await resolution.rebuild_projection()
    assert await graph_repo.same_as_neighbours(stack, ref(0))


# ── Runs, candidates and the review queue ────────────────────────────────────


async def test_a_run_records_candidates_with_their_full_comparison(
    stack: AsyncDriver,
) -> None:
    await resolution.run_matcher(["Person"], triggered_by="test", apply_auto=False)
    candidate = await repo.get_candidate_for_pair(ref(0), ref(1))
    assert candidate is not None
    assert candidate.band in ("auto", "review")
    assert candidate.blocking_keys
    # Every attribute the model looked at, including the ones it could not
    # compare — a review screen must be able to argue both ways.
    verdicts = {c["verdict"] for c in candidate.comparisons}
    assert "agree" in verdicts


async def test_an_auto_merge_is_attributed_to_the_matcher_not_a_person(
    stack: AsyncDriver,
) -> None:
    outcome = await resolution.run_matcher(["Person"], triggered_by="test", apply_auto=True)
    assert outcome.auto_merged >= 1
    decision = await repo.current_decision(ref(0), ref(1))
    assert decision is not None
    assert decision.verdict == "same"
    assert decision.decided_by_kind == "matcher"
    assert decision.decided_by == resolution.MATCHER_ACTOR
    assert decision.model_fingerprint


async def test_a_later_run_does_not_reopen_a_decided_pair(stack: AsyncDriver) -> None:
    """Otherwise the queue grows back every night and analyst work is discarded."""
    await resolution.run_matcher(["Person"], triggered_by="test", apply_auto=False)
    candidate = await repo.get_candidate_for_pair(ref(0), ref(1))
    assert candidate is not None
    await resolution.decide(
        left_ref=ref(0), right_ref=ref(1), verdict="different",
        actor="user:test", actor_kind="analyst", rationale="shared office line",
        candidate_id=candidate.candidate_id,
    )
    await resolution.run_matcher(["Person"], triggered_by="test", apply_auto=True)
    reread = await repo.get_candidate_for_pair(ref(0), ref(1))
    assert reread is not None and reread.status == "decided"
    current = await repo.current_decision(ref(0), ref(1))
    assert current is not None and current.verdict == "different"


async def test_deciding_closes_the_candidate_and_records_a_label(
    stack: AsyncDriver,
) -> None:
    """Analyst decisions are the only ground truth ARGUS gets about its own
    population, so each one becomes a label for the evaluation report."""
    await resolution.run_matcher(["Person"], triggered_by="test", apply_auto=False)
    candidate = await repo.get_candidate_for_pair(ref(0), ref(1))
    assert candidate is not None
    await resolution.decide(
        left_ref=ref(0), right_ref=ref(1), verdict="same",
        actor="user:test", actor_kind="analyst", rationale="same phone and dob",
        candidate_id=candidate.candidate_id,
    )
    assert (await repo.get_candidate(candidate.candidate_id)).status == "decided"  # type: ignore[union-attr]
    labelled = {(row["left_ref"], row["right_ref"]) for row in await repo.labels("analyst")}
    assert (ref(0), ref(1)) in labelled


# ── Subject resolution: the gap this phase closed in ingestion ───────────────


async def test_a_subject_id_that_names_nothing_is_reported_as_unknown(
    stack: AsyncDriver,
) -> None:
    """`PRS-9999999` has a valid prefix and names nobody.

    Phase 3 checked only the prefix, so a feed could record observations
    against a person who does not exist — no error, no dead-letter entry, and
    the observation would never appear on any entity page.
    """
    outcome = await resolution.resolve_subject("PRS-9999999")
    assert outcome.status == "unknown"
    assert outcome.resolved is False


async def test_an_existing_subject_resolves_directly(stack: AsyncDriver) -> None:
    outcome = await resolution.resolve_subject(ref(0))
    assert outcome.status == "known"
    assert outcome.ref == ref(0)


async def test_an_unrecognised_prefix_is_distinguished_from_a_missing_record(
    stack: AsyncDriver,
) -> None:
    assert (await resolution.resolve_subject("XYZ-1")).status == "unsupported"


async def test_an_unknown_id_with_matching_attributes_resolves_to_the_existing_record(
    stack: AsyncDriver,
) -> None:
    """The payoff: a feed that does not know ARGUS's ids can still be attached
    to the right entity, and the record says it was attached by matching."""
    await resolution.run_matcher(["Person"], triggered_by="test", apply_auto=False)
    outcome = await resolution.resolve_subject(
        "PRS-9999998",
        attributes={
            "name": "Wilhelmina R Ashgrove", "date_of_birth": "1988-04-23", "phone": "+1 555000222",
            "city": "Thunder Bay", "state": "Ontario", "country": "Canada",
            "nationality": "Canada", "occupation": "Logistics Manager", "gender": "Female",
        },
        origin="test-feed",
    )
    assert outcome.status == "matched"
    assert outcome.ref == ref(2)
    assert "Resolved to" in outcome.detail


async def test_a_weak_attribute_match_is_not_resolved_but_names_its_candidates(
    stack: AsyncDriver,
) -> None:
    """A dead-letter entry saying "unknown subject" is useless. One naming the
    plausible matches and what agreed is something an analyst can act on."""
    await resolution.run_matcher(["Person"], triggered_by="test", apply_auto=False)
    outcome = await resolution.resolve_subject(
        "PRS-9999997",
        attributes={"name": "Wilhelmina Ashgrove", "city": "Thunder Bay"},
        origin="test-feed",
    )
    assert outcome.resolved is False
    assert outcome.status in ("ambiguous", "unknown")


async def test_a_record_about_a_genuinely_new_person_stays_unresolved(
    stack: AsyncDriver,
) -> None:
    """Ingestion must not invent an entity, however confident it feels."""
    await resolution.run_matcher(["Person"], triggered_by="test", apply_auto=False)
    outcome = await resolution.resolve_subject(
        "PRS-9999996",
        attributes={
            "name": "Ingeborg Solheim", "date_of_birth": "1943-11-02",
            "phone": "+47 22334455", "city": "Bergen", "country": "Norway",
        },
        origin="test-feed",
    )
    assert outcome.resolved is False
    assert outcome.ref is None


# ── Evaluation ───────────────────────────────────────────────────────────────


async def test_an_evaluation_is_published_against_its_exact_model(
    stack: AsyncDriver,
) -> None:
    reports = await resolution.run_evaluation(entity_type="Person", sample=200, persist=True)
    assert set(reports) == {"synthetic", "analyst"}
    assert reports["synthetic"]["overall"]["pairs"] > 0
    published = await repo.recent_evaluations(5)
    assert any(row["dataset"] == "synthetic" for row in published)
    assert all(row["model_fingerprint"] for row in published)


async def test_the_matcher_never_reads_a_label(stack: AsyncDriver) -> None:
    """A pair labelled `same` must score exactly as it would unlabelled."""
    left = EntityProfile(
        ref=ref(0), entity_type="Person", attributes={"name": "Wilhelmina Ashgrove"}
    )
    right = EntityProfile(
        ref=ref(1), entity_type="Person", attributes={"name": "Wilhelmina Ashgrove"}
    )
    before = compare(left, right).score
    async with acquire() as conn:
        await repo.add_label(
            conn, entity_type="Person", left_ref=ref(0), right_ref=ref(1),
            is_same=True, origin="synthetic", note="test",
        )
    assert compare(left, right).score == before


async def test_matching_both_halves_of_an_existing_merge_is_not_ambiguous(
    stack: AsyncDriver,
) -> None:
    """Several strong matches are only ambiguous if they are different entities.

    Found in runtime verification: a feed matched both records of a pair the
    matcher had merged minutes earlier, and ARGUS dead-lettered it as
    "ambiguous" — contradicting its own conclusion that the two are one entity,
    and refusing to place a record it had everything it needed to place.
    """
    await resolution.decide(
        left_ref=ref(0), right_ref=ref(1), verdict="same",
        actor="user:test", actor_kind="analyst", rationale="same phone and date of birth",
    )
    await resolution.run_matcher(["Person"], triggered_by="test", apply_auto=False)

    outcome = await resolution.resolve_subject(
        "PRS-9999995",
        attributes={
            "name": "Wilhelmina Ashgrove", "date_of_birth": "1988-04-23", "phone": "+1 6470009911",
            "city": "Thunder Bay", "state": "Ontario", "country": "Canada",
            "nationality": "Canada", "occupation": "Logistics Manager", "gender": "Female",
        },
        origin="test-feed",
    )
    assert outcome.status == "matched"
    cluster = await repo.cluster_for_ref(ref(0))
    assert cluster is not None
    assert outcome.ref == cluster["canonical_ref"]
    # And it says which cluster, and how the representative was chosen.
    assert "already resolved to a single entity" in outcome.detail


async def test_two_unrelated_strong_matches_stay_ambiguous(stack: AsyncDriver) -> None:
    """The control for the test above: without a merge joining them, two equally
    strong matches mean none of them is a safe answer."""
    await resolution.run_matcher(["Person"], triggered_by="test", apply_auto=False)
    outcome = await resolution.resolve_subject(
        "PRS-9999994",
        attributes={
            "name": "Wilhelmina Ashgrove", "date_of_birth": "1988-04-23", "phone": "+1 6470009911",
            "city": "Thunder Bay", "state": "Ontario", "country": "Canada",
            "nationality": "Canada", "occupation": "Logistics Manager", "gender": "Female",
        },
        origin="test-feed",
    )
    assert outcome.status == "ambiguous"
    assert outcome.ref is None
    assert len(outcome.candidates) >= 2


async def test_an_analyst_can_record_a_merge_the_matcher_never_proposed(
    stack: AsyncDriver,
) -> None:
    """The escape hatch for blocking's one silent failure.

    A pair no blocking key brings together is never scored and appears nowhere
    as something ARGUS declined to consider, so a person who finds it by hand
    has to be able to record it.
    """
    # These two share no blocking key at all — different name, dob and city.
    assert await repo.get_candidate_for_pair(ref(0), ref(3)) is None
    result = await resolution.decide(
        left_ref=ref(0), right_ref=ref(3), verdict="same",
        actor="user:test", actor_kind="analyst",
        rationale="Confirmed by a partner service: one person, two national registrations.",
    )
    assert result["verdict"] == "same"
    cluster = await repo.cluster_for_ref(ref(0))
    assert cluster is not None and ref(3) in cluster["members"]


async def test_a_merge_does_not_become_a_connection_in_the_domain_graph(
    stack: AsyncDriver,
) -> None:
    """SAME_AS is a statement about records, not a relationship between them.

    Found in browser verification: after a merge, the entity profile showed
    "Connections — Person 1", which reads as "this person is connected to
    another person" when the claim is that they *are* one person. The same
    edge would have inflated node degree and, worse, let shortest-path route a
    connection *through* an identity assertion — manufacturing a link between
    two entities that the graph never contained.
    """
    from app.repositories import entity_repo
    from app.repositories import graph_repo as domain_graph

    before_summary = await entity_repo.get_connection_summary(stack, ref(0))
    before_node = await domain_graph.get_node_by_human_id(stack, ref(0))

    await resolution.decide(
        left_ref=ref(0), right_ref=ref(1), verdict="same",
        actor="user:test", actor_kind="analyst", rationale="same phone and date of birth",
    )
    # The projected edge exists...
    assert await graph_repo.same_as_neighbours(stack, ref(0))
    # ...and changes nothing about how the domain graph reads.
    assert await entity_repo.get_connection_summary(stack, ref(0)) == before_summary
    after_node = await domain_graph.get_node_by_human_id(stack, ref(0))
    assert after_node is not None and before_node is not None
    assert after_node["degree"] == before_node["degree"]

    neighbours = await domain_graph.get_one_hop_neighbors(stack, ref(0))
    assert all(n["rel_type"] != "SAME_AS" for n in neighbours)


async def test_a_path_is_never_routed_through_an_identity_assertion(
    stack: AsyncDriver,
) -> None:
    """The most damaging version of the same mistake: two entities appearing
    connected because a merge sits between them."""
    from app.repositories import graph_repo as domain_graph

    await resolution.decide(
        left_ref=ref(0), right_ref=ref(1), verdict="same",
        actor="user:test", actor_kind="analyst", rationale="same phone",
    )
    path = await domain_graph.shortest_path(stack, ref(0), ref(1))
    assert path is None
