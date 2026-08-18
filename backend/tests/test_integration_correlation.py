"""Correlation end to end, against a real Neo4j and a real PostgreSQL.

What a mock could not tell you, and these do: that the append-only triggers
refuse an edit the application never attempts, that the cluster projection is
genuinely rebuildable from the ledger, that the `ref_a < ref_b` constraint
really does stop a pair being stored twice, and that a dimension which could
not be evaluated survives the whole round trip with a NULL magnitude rather
than a zero.

The tests seed their own small world rather than relying on the generated one,
so they assert the same thing on a developer's populated graph and on CI's empty
one. Everything they write is removed afterwards — including the Postgres rows,
which the application itself is not permitted to delete. A suite that quietly
published links nobody ran would be corrupting the record it exists to protect.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta

import asyncpg
import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from app.config import get_settings
from app.correlation.model import TIER_ESTABLISHED, TIER_PROBABLE, default_model
from app.repositories import correlation_graph_repo, correlation_repo
from app.services import correlation as service

pytestmark = pytest.mark.asyncio

BASE = datetime(2026, 3, 1, 9, 0, 0)


@pytest_asyncio.fixture
async def pg_admin() -> AsyncIterator[asyncpg.Connection]:
    """Superuser connection, used only to undo what the tests wrote.

    The application role cannot delete a link and neither can the superuser
    without disabling the trigger first — which is the property under test in
    `test_links_are_append_only`, exercised here in reverse.
    """
    settings = get_settings()
    try:
        conn = await asyncpg.connect(dsn=settings.postgres_admin_dsn, timeout=5)
    except Exception:
        pytest.skip("No PostgreSQL reachable; skipping correlation integration test")
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def ledger(pg_admin: asyncpg.Connection) -> AsyncIterator[None]:
    """Records a high-water mark, then removes everything written above it."""
    from app.database.postgres import close_postgres, connect_postgres

    await connect_postgres()
    before_run = await pg_admin.fetchval("SELECT coalesce(max(run_id), 0) FROM correlation_runs")
    before_assertion = await pg_admin.fetchval("SELECT count(*) FROM assertions")
    started = await pg_admin.fetchval("SELECT now()")
    triggers = (
        ("correlation_link_dimensions", "correlation_link_dimensions_no_update"),
        ("correlation_links", "correlation_links_no_delete"),
        ("correlation_clusters", "correlation_clusters_no_delete"),
        ("correlation_evaluations", "correlation_evaluations_no_delete"),
    )
    try:
        yield
    finally:
        async with pg_admin.transaction():
            for table, trigger in triggers:
                await pg_admin.execute(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}")
            await pg_admin.execute(
                "DELETE FROM correlation_link_dimensions WHERE link_id IN "
                "(SELECT link_id FROM correlation_links WHERE run_id > $1)",
                before_run,
            )
            await pg_admin.execute("DELETE FROM correlation_links WHERE run_id > $1", before_run)
            await pg_admin.execute(
                "DELETE FROM correlation_cluster_members WHERE cluster_id IN "
                "(SELECT cluster_id FROM correlation_clusters WHERE run_id > $1)",
                before_run,
            )
            await pg_admin.execute(
                "DELETE FROM correlation_clusters WHERE run_id > $1", before_run
            )
            await pg_admin.execute(
                "DELETE FROM correlation_evaluations WHERE run_id > $1", before_run
            )
            await pg_admin.execute("DELETE FROM correlation_runs WHERE run_id > $1", before_run)
            for table, trigger in triggers:
                await pg_admin.execute(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}")

            # Assertions are append-only too, and this phase publishes them.
            # Supersession makes them a linked list, so pointers into the doomed
            # rows have to be cleared first — which needs the content-immutability
            # trigger down as well, since that one permits `superseded_by` to be
            # set but never unset.
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


def refs(tag: str) -> tuple[str, str, str]:
    short = tag[-6:]
    return (f"PRS-A{short}", f"PRS-B{short}", f"PRS-C{short}")


@pytest_asyncio.fixture
async def world(graph: AsyncDriver, tag: str) -> str:
    """Three people connected two ways each, plus the structure to see it.

    Deliberately small and hand-built, so the expected answer is readable from
    the fixture: A pays B directly, A and B call each other, B and C do the
    same. C is joined only through B, which makes the B–C link a bridge and the
    cluster's fragility measurable.
    """
    a, b, c = refs(tag)
    short = tag[-5:]
    async with graph.session() as session:
        await session.run(
            """
            UNWIND $people AS ref
            CREATE (p:Person {person_id: ref, name: ref, _test_tag: $tag, lat: 19.07, lng: 72.87})
            """,
            people=[a, b, c],
            tag=tag,
        )
        await session.run(
            """
            UNWIND $rows AS row
            CREATE (acc:Account {account_id: row.account, offshore: false, _test_tag: $tag})
            WITH acc, row
            MATCH (p:Person {person_id: row.owner})
            CREATE (p)-[:OWNS_ACCOUNT]->(acc)
            """,
            rows=[
                {"owner": a, "account": f"ACC-A{short}"},
                {"owner": b, "account": f"ACC-B{short}"},
                {"owner": c, "account": f"ACC-C{short}"},
            ],
            tag=tag,
        )
        await session.run(
            """
            UNWIND $rows AS row
            MATCH (src:Account {account_id: row.src}), (dst:Account {account_id: row.dst})
            CREATE (src)-[:TRANSACTED_WITH {
                tx_id: row.tx_id, amount: row.amount, timestamp: row.timestamp
            }]->(dst)
            """,
            rows=[
                {
                    "src": f"ACC-A{short}",
                    "dst": f"ACC-B{short}",
                    "tx_id": f"TXN-1{short}",
                    "amount": 500_000.0,
                    "timestamp": BASE.isoformat(),
                },
                {
                    "src": f"ACC-B{short}",
                    "dst": f"ACC-C{short}",
                    "tx_id": f"TXN-2{short}",
                    "amount": 470_000.0,
                    "timestamp": (BASE + timedelta(days=1)).isoformat(),
                },
            ],
        )
        await session.run(
            """
            UNWIND $people AS ref
            MATCH (p:Person {person_id: ref})
            CREATE (p)-[:OWNS_DEVICE]->(:Device {device_id: 'DEV-' + ref, _test_tag: $tag})
            """,
            people=[a, b, c],
            tag=tag,
        )
        await session.run(
            """
            UNWIND $rows AS row
            MATCH (:Person {person_id: row.a})-[:OWNS_DEVICE]->(da:Device)
            MATCH (:Person {person_id: row.b})-[:OWNS_DEVICE]->(db:Device)
            CREATE (da)-[:COMMUNICATED_WITH {comm_id: row.comm_id, timestamp: row.timestamp}]->(db)
            """,
            rows=[
                {"a": x, "b": y, "comm_id": f"COM-{i}{short}", "timestamp": (BASE + timedelta(hours=i)).isoformat()}
                for i, (x, y) in enumerate(
                    [(a, b), (b, a), (a, b), (b, c), (c, b), (b, c)]
                )
            ],
        )
    return tag


def _seed(ref: str) -> dict:
    return {
        "subject_ref": ref,
        "subject_type": "Person",
        "band": "notable",
        "score": 40.0,
        "signal_ids": ["funds_cycle"],
    }


async def _anchor_seeds(tag: str) -> list[dict]:
    """Anchors as the assessment ledger would supply them.

    Built here rather than by running the assessor, so a correlation failure
    cannot be mistaken for an assessment failure. What matters to correlation is
    only that a subject fired a signal; which signal is Phase 5's business.
    """
    return [_seed(ref) for ref in refs(tag)]


@pytest_asyncio.fixture
async def scoped(monkeypatch: pytest.MonkeyPatch, world: str):
    """Point the anchor query at this test's subjects instead of the real ledger.

    Without this, `run_correlation` reads whatever the developer's last
    assessment run produced and correlates the entire generated world — which
    on a populated machine is thousands of anchors and takes minutes, while on
    CI's empty graph it is nothing at all. The same test would then be measuring
    two completely different things depending on where it ran.

    Patched at the repository boundary so everything downstream of it — the
    service, the evidence sweep, blocking, scoring, storage, projection — is the
    real code path.
    """
    from app.repositories import assessment_repo

    scoped_refs = list(refs(world))

    def use(extra: list[str] | None = None) -> None:
        chosen = scoped_refs + list(extra or [])

        async def anchors_for_correlation(limit: int) -> list[dict]:
            return [_seed(ref) for ref in chosen][:limit]

        async def count_anchors_for_correlation() -> int:
            return len(chosen)

        monkeypatch.setattr(
            assessment_repo, "anchors_for_correlation", anchors_for_correlation
        )
        monkeypatch.setattr(
            assessment_repo, "count_anchors_for_correlation", count_anchors_for_correlation
        )

    use()
    return use


# ─────────────────────────────────────────────────────────────────────────────


async def test_the_correlator_finds_a_chain_and_explains_it(
    graph: AsyncDriver, world: str, ledger: None
) -> None:
    from app.correlation.candidates import generate
    from app.correlation.dimensions import build_context
    from app.correlation.linking import link_pair

    a, b, c = refs(world)
    model = default_model()
    evidence = await correlation_graph_repo.fetch_correlation_evidence(
        graph, await _anchor_seeds(world)
    )
    ctx = build_context(evidence, model)
    proposed = generate(ctx)

    assert (a, b) in proposed.pairs
    link = link_pair(ctx, evidence.anchors[a], evidence.anchors[b])
    assert link is not None
    assert link.tier in (TIER_ESTABLISHED, TIER_PROBABLE)

    fired = {o.dimension_id for o in link.fired}
    assert "funds_path" in fired
    assert "communication" in fired
    # The reasons are named in the basis, not merely counted.
    assert any("hop" in o.summary for o in link.fired)


async def test_the_correlator_never_sees_a_planted_edge(
    graph: AsyncDriver, world: str, tag: str, ledger: None, scoped
) -> None:
    """The guarantee, exercised rather than inspected.

    A `CONTROLS` edge and a `SHARES_DEVICE` edge are added between two subjects
    with nothing else between them. If any dimension could see either, the pair
    would be linked. None can, so it is not.
    """
    a, _b, c = refs(world)
    short = tag[-6:]
    lonely_x, lonely_y = f"PRS-X{short}", f"PRS-Y{short}"
    async with graph.session() as session:
        await session.run(
            """
            CREATE (x:Person {person_id: $x, name: 'X', _test_tag: $tag})
            CREATE (y:Person {person_id: $y, name: 'Y', _test_tag: $tag})
            CREATE (o:Organization {org_id: $org, name: 'O', _test_tag: $tag})
            CREATE (x)-[:CONTROLS]->(o)
            CREATE (y)-[:CONTROLS]->(o)
            CREATE (x)-[:SHARES_DEVICE]->(y)
            """,
            x=lonely_x,
            y=lonely_y,
            org=f"ORG-Z{short}",
            tag=tag,
        )

    scoped([lonely_x, lonely_y])
    seeds = await _anchor_seeds(world) + [_seed(lonely_x), _seed(lonely_y)]
    evidence = await correlation_graph_repo.fetch_correlation_evidence(graph, seeds)

    # The edges exist in the graph and are simply invisible to the evidence.
    assert lonely_x in evidence.anchors
    assert not [af for af in evidence.affiliations if af.person_ref in (lonely_x, lonely_y)]
    assert not [t for t in evidence.contacts if t.person_a in (lonely_x, lonely_y)]

    outcome = await service.run_correlation(
        graph, triggered_by="test", publish_assertions=False
    )
    assert outcome.run_id
    links = await correlation_repo.list_current_links(limit=1000)
    joined = {(link.ref_a, link.ref_b) for link in links}
    ordered = (lonely_x, lonely_y) if lonely_x <= lonely_y else (lonely_y, lonely_x)
    assert ordered not in joined, (
        "two subjects joined only by planted edges were correlated — a dimension "
        "is reading the answer key"
    )
    assert a != c


async def test_a_run_is_stored_and_read_back_whole(
    graph: AsyncDriver, world: str, ledger: None, scoped
) -> None:
    outcome = await service.run_correlation(
        graph, triggered_by="test", publish_assertions=False
    )
    assert outcome.links_recorded > 0

    links = await correlation_repo.list_current_links(limit=100)
    assert links
    for link in links:
        assert link.ref_a < link.ref_b, "pairs must be stored in a stable order"
        assert link.dimensions, "a link with no working shown is an assertion of authority"
        assert 0.0 <= link.strength <= 1.0
        assert 0.0 <= link.coverage <= 1.0


async def test_an_unevaluable_dimension_survives_with_a_null_magnitude(
    graph: AsyncDriver, world: str, ledger: None, scoped
) -> None:
    """The three-state discipline, all the way to the database and back. A zero
    here would say "we looked and they were far apart" about a pair whose
    distance was never computed."""
    await service.run_correlation(graph, triggered_by="test", publish_assertions=False)
    links = await correlation_repo.list_current_links(limit=100)

    unevaluable = [
        dimension
        for link in links
        for dimension in link.dimensions
        if not dimension["evaluable"]
    ]
    assert unevaluable, "expected at least one dimension to be unevaluable in this small world"
    for dimension in unevaluable:
        assert dimension["magnitude"] is None
        assert dimension["summary"], "an unevaluable dimension must still say why"


async def test_the_cluster_projection_is_rebuildable_from_the_ledger(
    graph: AsyncDriver, world: str, ledger: None, scoped
) -> None:
    """The proof that the graph properties are a cache and not a second source
    of truth: clear them, rebuild from the ledger, and land in the same place.

    The comparison is against the *ledger's* current memberships rather than
    against whatever the graph happened to be carrying. Those can differ — a
    previous generation may have marked subjects this one does not — and it is
    the ledger that decides, which is exactly what makes the properties a cache.
    """
    await service.run_correlation(graph, triggered_by="test", publish_assertions=False)
    expected = len(await correlation_repo.all_current_clusters_for_projection())

    async with graph.session() as session:
        result = await session.run(
            "MATCH (n) WHERE n.argus_cluster IS NOT NULL RETURN count(n) AS n"
        )
        record = await result.single()
        assert (record["n"] if record else 0) == expected, (
            "a completed run must leave the graph carrying exactly the current memberships"
        )

    rebuilt = await service.rebuild_projection(graph)
    assert rebuilt["cleared"] == expected
    assert rebuilt["written"] == expected


async def test_links_are_append_only(
    graph: AsyncDriver, world: str, ledger: None, scoped, pg_admin: asyncpg.Connection
) -> None:
    """Enforced by the database, so it holds even when the caller is the
    application. A link that can be edited after the fact is not a record of
    what was believed."""
    await service.run_correlation(graph, triggered_by="test", publish_assertions=False)
    link_id = await pg_admin.fetchval(
        "SELECT link_id FROM correlation_links ORDER BY computed_at DESC LIMIT 1"
    )
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await pg_admin.execute(
            "UPDATE correlation_links SET strength = 0.99 WHERE link_id = $1", link_id
        )
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await pg_admin.execute("DELETE FROM correlation_links WHERE link_id = $1", link_id)


async def test_a_pair_cannot_be_stored_in_both_orders(
    graph: AsyncDriver, world: str, ledger: None, pg_admin: asyncpg.Connection
) -> None:
    """Otherwise every count on every correlation surface would silently
    double."""
    run_id = await pg_admin.fetchval(
        "INSERT INTO correlation_runs (model_version, model_fingerprint, triggered_by) "
        "VALUES ('test@v1', 'test', 'test') RETURNING run_id"
    )
    with pytest.raises(asyncpg.CheckViolationError):
        await pg_admin.execute(
            """
            INSERT INTO correlation_links (
                run_id, ref_a, ref_b, type_a, type_b, strength, tier, coverage,
                evaluable_dimensions, applicable_dimensions, model_version,
                model_fingerprint, computed_at
            ) VALUES ($1, 'ZZZ', 'AAA', 'Person', 'Person', 0.8, 'probable', 0.8,
                      6, 7, 'test@v1', 'test', now())
            """,
            run_id,
        )


async def test_a_dimension_cannot_be_unevaluable_and_carry_a_magnitude(
    graph: AsyncDriver, world: str, ledger: None, pg_admin: asyncpg.Connection
) -> None:
    run_id = await pg_admin.fetchval(
        "INSERT INTO correlation_runs (model_version, model_fingerprint, triggered_by) "
        "VALUES ('test@v1', 'test', 'test') RETURNING run_id"
    )
    link_id = await pg_admin.fetchval(
        """
        INSERT INTO correlation_links (
            run_id, ref_a, ref_b, type_a, type_b, strength, tier, coverage,
            evaluable_dimensions, applicable_dimensions, model_version,
            model_fingerprint, computed_at
        ) VALUES ($1, 'AAA', 'ZZZ', 'Person', 'Person', 0.8, 'probable', 0.8,
                  6, 7, 'test@v1', 'test', now())
        RETURNING link_id
        """,
        run_id,
    )
    with pytest.raises(asyncpg.CheckViolationError):
        await pg_admin.execute(
            """
            INSERT INTO correlation_link_dimensions (
                link_id, dimension_id, family, evaluable, magnitude, summary
            ) VALUES ($1, 'proximity', 'spatial', false, 0.0, 'x')
            """,
            link_id,
        )


async def test_a_failed_run_leaves_the_previous_generation_standing(
    graph: AsyncDriver, world: str, ledger: None, scoped
) -> None:
    """A transient database outage must not turn into a silent claim that
    nothing is connected."""
    await service.run_correlation(graph, triggered_by="test", publish_assertions=False)
    good = await correlation_repo.latest_complete_run()
    assert good is not None
    before = await correlation_repo.list_current_links(limit=1000)
    assert before

    class Broken:
        def session(self, *args, **kwargs):
            raise RuntimeError("graph unavailable")

    with pytest.raises(RuntimeError):
        await service.run_correlation(Broken(), triggered_by="test", publish_assertions=False)  # type: ignore[arg-type]

    failed = await correlation_repo.latest_run()
    assert failed is not None
    assert failed.status == "failed"
    assert "graph unavailable" in (failed.error or "")

    # The current view still resolves to the last *complete* run.
    still = await correlation_repo.latest_complete_run()
    assert still is not None and still.run_id == good.run_id
    assert len(await correlation_repo.list_current_links(limit=1000)) == len(before)


async def test_a_world_with_no_findings_is_a_completed_run_of_zero(
    graph: AsyncDriver, ledger: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not an error. A world where ARGUS has found nothing has nothing to
    correlate, and recording that is more honest than failing and leaving no
    record that the question was asked."""
    from app.repositories import assessment_repo

    async def no_anchors(limit: int) -> list[dict]:
        return []

    async def none_available() -> int:
        return 0

    monkeypatch.setattr(assessment_repo, "anchors_for_correlation", no_anchors)
    monkeypatch.setattr(assessment_repo, "count_anchors_for_correlation", none_available)

    outcome = await service.run_correlation(
        graph, triggered_by="test", publish_assertions=False
    )
    assert outcome.anchors == 0
    assert outcome.links_recorded == 0

    run = await correlation_repo.latest_run()
    assert run is not None
    assert run.status == "complete"
    assert "nothing to correlate" in run.evidence_summary.get("note", "")


async def test_ground_truth_is_reachable_only_through_its_own_function(
    graph: AsyncDriver, world: str, tag: str, ledger: None
) -> None:
    """The evaluation path can read storylines. Nothing else does, and this
    asserts the function works — so the isolation elsewhere is a real boundary
    rather than an absence of capability."""
    async with graph.session() as session:
        await session.run(
            """
            CREATE (s:Storyline {
                storyline_id: $sid, type: 'money_routing_network',
                entity_ids: $entities, _test_tag: $tag
            })
            """,
            sid=f"STL-T{tag[-6:]}",
            entities=list(refs(world)),
            tag=tag,
        )

    truth = await correlation_graph_repo.fetch_correlation_ground_truth(graph)
    planted = [row for row in truth if set(refs(world)).issubset(set(row[1]))]
    assert planted, "the evaluation path must be able to read ground truth"
    assert planted[0][0] == "money_routing_network"


async def test_an_account_and_its_holder_are_folded_into_one_subject(
    graph: AsyncDriver, world: str, tag: str, ledger: None
) -> None:
    """Both are findings, but they are one subject seen twice.

    Their counterparties, transfers and timing are identical by construction, so
    keeping both would report every financial link twice — once under the
    account and once under whoever holds it. Against the live graph that was
    8,730 duplicated links and made `Account-Person` the largest category of
    "discovery" in the system.
    """
    a, _b, _c = refs(world)
    short = tag[-5:]
    account = f"ACC-A{short}"

    seeds = await _anchor_seeds(world) + [
        {
            "subject_ref": account,
            "subject_type": "Account",
            "band": "notable",
            "score": 40.0,
            "signal_ids": ["offshore_banking"],
        }
    ]
    evidence = await correlation_graph_repo.fetch_correlation_evidence(graph, seeds)

    assert account in evidence.folded_accounts
    assert account not in evidence.anchors
    assert a in evidence.anchors, "the holder keeps the finding"


async def test_an_account_whose_holder_is_not_a_finding_stays_a_subject(
    graph: AsyncDriver, world: str, tag: str, ledger: None
) -> None:
    """Folding is about avoiding duplication, not about demoting accounts. Where
    the holder is not itself a finding, the account is the only subject ARGUS
    has an opinion about and must remain correlatable."""
    short = tag[-5:]
    account = f"ACC-C{short}"
    seeds = [
        {
            "subject_ref": account,
            "subject_type": "Account",
            "band": "notable",
            "score": 40.0,
            "signal_ids": ["offshore_banking"],
        }
    ]
    evidence = await correlation_graph_repo.fetch_correlation_evidence(graph, seeds)

    assert evidence.folded_accounts == set()
    assert account in evidence.anchors


async def test_ground_truth_follows_the_same_folding(
    graph: AsyncDriver, world: str, tag: str, ledger: None
) -> None:
    """A storyline naming a chain of accounts names subjects correlation folded
    away. Without following the fold, the money-routing storyline reported a
    recall of zero against a run that had in fact linked every holder."""
    holders = await correlation_graph_repo.fetch_account_holders(graph)
    a, b, _c = refs(world)
    short = tag[-5:]
    assert holders.get(f"ACC-A{short}") == a
    assert holders.get(f"ACC-B{short}") == b


async def test_a_subject_that_leaves_every_cluster_loses_its_projection(
    graph: AsyncDriver, world: str, tag: str, ledger: None, scoped
) -> None:
    """The cache must not assert a membership the ledger no longer holds.

    `project_clusters` only sets properties, so without an explicit clear a
    subject grouped last run and grouped nowhere now would keep its old
    `argus_cluster` — the same defect as the stale assertions Phase 5 found,
    moved from the record into the cache.
    """
    a, _b, _c = refs(world)
    await service.run_correlation(graph, triggered_by="test", publish_assertions=False)

    async with graph.session() as session:
        result = await session.run(
            "MATCH (n:Person {person_id: $ref}) RETURN n.argus_cluster AS cluster", ref=a
        )
        record = await result.single()
        assert record is not None and record["cluster"] is not None, (
            "expected this fixture's subjects to form a cluster"
        )

    # Re-run against a single anchor: no pair, so no link, so no cluster.
    scoped()
    from app.repositories import assessment_repo

    async def only_one(limit: int) -> list[dict]:
        return [_seed(a)]

    async def one_available() -> int:
        return 1

    import pytest as _pytest

    monkeypatch = _pytest.MonkeyPatch()
    monkeypatch.setattr(assessment_repo, "anchors_for_correlation", only_one)
    monkeypatch.setattr(assessment_repo, "count_anchors_for_correlation", one_available)
    try:
        await service.run_correlation(graph, triggered_by="test", publish_assertions=False)
    finally:
        monkeypatch.undo()

    async with graph.session() as session:
        result = await session.run(
            "MATCH (n:Person {person_id: $ref}) RETURN n.argus_cluster AS cluster", ref=a
        )
        record = await result.single()
        assert record is not None and record["cluster"] is None, (
            "the graph still claims a cluster membership the ledger has dropped"
        )
