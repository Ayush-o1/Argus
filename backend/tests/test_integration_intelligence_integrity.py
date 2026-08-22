"""Integration tests pinning the audit's headline finding: surfaces that
presented partial data as complete findings.

Each test builds a graph shaped to expose one specific misstatement, then
asserts the API reports the truth. They are written so that reverting the fix
makes them fail with a message naming the wrong claim, rather than a bare
assertion error.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from app.repositories import dashboard_repo, timeline_repo

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def pg_pool() -> AsyncIterator[None]:
    """Just the connection pool. `get_dashboard_summary` reads the alerting
    tables for its queue figures, so it needs Postgres even where the test is
    about the graph."""
    from app.database.postgres import close_postgres, connect_postgres

    try:
        await connect_postgres()
    except Exception:
        pytest.skip("No PostgreSQL reachable; skipping dashboard integrity test")
    try:
        yield
    finally:
        await close_postgres()


@pytest_asyncio.fixture
async def pg_alerting() -> AsyncIterator[dict]:
    """A run and a group to hang probe alerts from, removed afterwards."""
    import uuid

    import asyncpg

    from app.config import get_settings
    from app.database.postgres import acquire, close_postgres, connect_postgres
    from app.repositories import alert_repo

    try:
        await connect_postgres()
        admin = await asyncpg.connect(dsn=get_settings().postgres_admin_dsn, timeout=5)
    except Exception:
        pytest.skip("No PostgreSQL reachable; skipping alerting integrity test")

    tag = uuid.uuid4().hex[:8]
    run_id = await alert_repo.start_run(f"probe-{tag}", None, None)
    group_key = f"grp-{tag}"
    async with acquire() as conn:
        await alert_repo.upsert_group(conn, group_key, "scope", ["PRS-PROBE"], "probe group")

    state = {"run_id": run_id, "group_key": group_key, "keys": []}
    try:
        yield state
    finally:
        await admin.execute("ALTER TABLE alert_transitions DISABLE TRIGGER USER")
        await admin.execute("ALTER TABLE alert_occurrences DISABLE TRIGGER USER")
        try:
            keys = state["keys"]
            if keys:
                await admin.execute("DELETE FROM alert_transitions WHERE alert_key = ANY($1::text[])", keys)
                await admin.execute("DELETE FROM alert_occurrences WHERE alert_key = ANY($1::text[])", keys)
                await admin.execute("DELETE FROM alerts WHERE alert_key = ANY($1::text[])", keys)
            await admin.execute("DELETE FROM alert_groups WHERE group_key = $1", group_key)
            await admin.execute("DELETE FROM alert_runs WHERE run_id = $1", run_id)
        finally:
            await admin.execute("ALTER TABLE alert_transitions ENABLE TRIGGER USER")
            await admin.execute("ALTER TABLE alert_occurrences ENABLE TRIGGER USER")
            await admin.close()
            await close_postgres()


async def _seed_alert(state: dict, *, rule_id: str, scope: list[str]) -> str:
    import json

    from app.alerting.identity import alert_key
    from app.database.postgres import acquire
    from app.repositories import alert_repo

    key = alert_key(rule_id, 1, tuple(scope))
    state["keys"].append(key)
    async with acquire() as conn:
        await alert_repo.upsert_alert(
            conn,
            alert_key=key, rule_id=rule_id, rule_version=1, scope=scope,
            group_key=state["group_key"], title="probe", summary="probe",
            priority=0.5, priority_band="medium",
            priority_factors=json.dumps({}), evidence=json.dumps({}),
            suppressed=False, suppressed_by=None, run_id=state["run_id"],
        )
    return key


# ── B-04 and B-29, on the system that now owns alerting ─────────────────────
#
# The original two tests pinned these properties against `alert_repo.list_alerts`
# and `list_related_alerts`, which read `Incident` nodes. Phase 7 replaced that
# path entirely, so those tests could not be kept as written — and the second was
# pinning a fix built on the answer key: "related alerts" matched on
# `source.storyline_id`, the generator's own label. Making a planted result
# complete is not the same as making it discovered.
#
# The properties themselves still matter and are pinned here against the alerting
# tables. Neither is weakened: the first still fails if a preview is presented as
# a total, and the second still fails if relatedness is scoped to a page.


async def test_alert_scope_carries_every_subject_not_a_preview(pg_alerting: dict) -> None:
    """B-04, restated. The defect was a five-entity preview whose spread figures
    were derived from the preview and labelled as the alert's reach."""
    from app.repositories import alert_repo

    subjects = [f"PRS-SPREAD-{i:02d}" for i in range(12)]
    key = await _seed_alert(pg_alerting, rule_id="probe.spread", scope=subjects)

    row = await alert_repo.get_alert(key)
    assert row is not None
    assert len(row["scope"]) == 12, (
        f"scope holds {len(row['scope'])} subjects; an alert that truncates its "
        "own scope understates its reach exactly as the spread preview did"
    )
    assert set(row["scope"]) == set(subjects)


async def test_group_counts_every_alert_not_the_returned_page(pg_alerting: dict) -> None:
    """B-29, restated. Relatedness must be computed over the whole alert set,
    not over whichever page a client happened to load — and without reading a
    planted storyline to do it."""
    from app.repositories import alert_repo

    for i in range(7):
        await _seed_alert(pg_alerting, rule_id=f"probe.group.{i}", scope=[f"PRS-GRP-{i:02d}"])

    rollup = await alert_repo.group_rollup(limit=200)
    row = next(g for g in rollup if g["group_key"] == pg_alerting["group_key"])
    assert row["alert_count"] == 7, (
        f"group reports {row['alert_count']} of 7 alerts; a count scoped to a "
        "page is the defect this pins"
    )

    listed, total = await alert_repo.list_alerts(
        group_key=pg_alerting["group_key"], page=1, page_size=3
    )
    assert len(listed) == 3, "page size must still bound what is returned"
    assert total == 7, "the total must describe the group, not the page"


async def test_an_alert_in_no_group_reports_nothing_related(pg_alerting: dict) -> None:
    """The empty case, which must be empty rather than nearest-neighbour."""
    from app.repositories import alert_repo

    listed, total = await alert_repo.list_alerts(group_key="grp-does-not-exist", page_size=50)
    assert listed == [] and total == 0


async def test_dashboard_open_alerts_come_from_argus_not_the_generator(
    graph: AsyncDriver, pg_alerting: dict
) -> None:
    """The dashboard counted open High/Critical `Incident` nodes as its alert
    figure. Those are written by the generator, one per storyline, so the number
    was the answer key's size presented as the queue."""
    from app.repositories import alert_repo

    summary = await dashboard_repo.get_dashboard_summary(graph)
    counts = await alert_repo.queue_counts()
    assert summary["open_alerts"] == counts["open"], (
        "dashboard open_alerts must equal the alerting tables' open count"
    )
    assert summary["high_priority_open_alerts"] <= summary["open_alerts"], (
        "the high-priority figure must share open_alerts' denominator (B-05)"
    )


async def test_timeline_is_deterministic_and_complete(graph: AsyncDriver) -> None:
    """B-03. `rand()` sampling made identical requests return different data, so
    burst findings changed between refreshes."""
    first = await timeline_repo.get_global_timeline(graph)
    second = await timeline_repo.get_global_timeline(graph)

    assert first["buckets"] == second["buckets"], "identical requests must return identical day buckets"
    assert first["totals"]["by_lane"] == second["totals"]["by_lane"]

    totals = first["totals"]["records"]
    assert totals["basis"] == "complete"
    assert totals["value"] == sum(first["totals"]["by_lane"].values())


async def test_timeline_day_series_is_contiguous(graph: AsyncDriver, tag: str) -> None:
    """B-18. Days with no activity were omitted, so the mean was computed over
    non-empty days only, inflating it and suppressing genuine bursts.

    The gap is created here rather than borrowed from whatever the graph
    happens to hold. Two events three days apart guarantee two empty days in
    between, so zero-filling is actually exercised — where previously the test
    skipped itself on a graph with too little spread, which against a freshly
    migrated database meant it never ran at all.
    """
    from datetime import date, timedelta

    async with graph.session() as session:
        await session.run(
            """
            UNWIND $stamps AS stamp
            CREATE (e:Event {event_id: 'EVT-' + stamp, type: 'test', timestamp: stamp,
                             flagged: false, _test_tag: $tag})
            """,
            stamps=["2019-03-01T09:00:00", "2019-03-04T09:00:00"],
            tag=tag,
        )

    buckets = (await timeline_repo.get_global_timeline(graph))["buckets"]
    assert len(buckets) >= 4, "the seeded events must produce a spread to check"

    days = [date.fromisoformat(b["day"]) for b in buckets]
    expected = [days[0] + timedelta(days=i) for i in range((days[-1] - days[0]).days + 1)]
    assert days == expected, "day series must be zero-filled and contiguous"

    # The two days between the seeded events must be present and empty — the
    # exact case B-18 was about.
    seeded = {b["day"]: b for b in buckets}
    for empty_day in ("2019-03-02", "2019-03-03"):
        assert empty_day in seeded, f"{empty_day} was omitted instead of zero-filled"
        assert seeded[empty_day]["total"] == 0


async def test_timeline_bucket_totals_equal_lane_totals(graph: AsyncDriver) -> None:
    """Each bucket's `total` must equal the sum of its lanes — the invariant the
    UI relies on when it recomputes totals for the active lane filter."""
    for bucket in (await timeline_repo.get_global_timeline(graph))["buckets"]:
        lane_sum = bucket["transactions"] + bucket["communications"] + bucket["events"] + bucket["incidents"]
        assert bucket["total"] == lane_sum, f"bucket {bucket['day']} totals disagree with its lanes"


async def test_timeline_lane_flagged_counts_are_exact(graph: AsyncDriver) -> None:
    """Per-lane flagged counts must sum to the day's flagged total.

    The UI computes the flagged figure for the active lane filter from these. If
    they were approximated — or apportioned from a single summed total — the
    number an analyst reads as exact would be an estimate.
    """
    lanes = ("transactions", "communications", "events", "incidents")
    for bucket in (await timeline_repo.get_global_timeline(graph))["buckets"]:
        lane_flagged_sum = sum(bucket[f"{lane}_flagged"] for lane in lanes)
        assert lane_flagged_sum == bucket["flagged"], (
            f"day {bucket['day']}: lane flagged counts sum to {lane_flagged_sum} "
            f"but the day total is {bucket['flagged']}"
        )
        for lane in lanes:
            assert bucket[f"{lane}_flagged"] <= bucket[lane], (
                f"day {bucket['day']}: {lane} has more flagged than total records"
            )


async def test_dashboard_incident_counts_are_not_capped_by_the_preview(
    graph: AsyncDriver, tag: str, pg_pool: None
) -> None:
    """B-05. The headline sentence put a full count and a six-row sample in one
    clause, so the figure could never exceed the preview length.

    The field this originally pinned — `critical_open_alerts` — counted open
    High/Critical `Incident` nodes and was named as though it described the
    alert queue. Phase 7 split those apart: `open_alerts` now comes from the
    alerting tables, and the incident figures are reported as incidents. The
    property is unchanged and is pinned here on the figures that remain.
    """
    recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    async with graph.session() as session:
        for idx in range(8):
            await session.run(
                """
                CREATE (i:Incident {
                    incident_id: $incident_id, type: 'ProbeType', severity: 'Critical',
                    status: 'Open', timestamp: $ts, description: 'probe',
                    id: $uuid, _test_tag: $tag
                })
                """,
                incident_id=f"INC-{tag[-6:]}-{idx}",
                ts=recent,
                uuid=f"{tag}-crit-{idx}",
                tag=tag,
            )

    summary = await dashboard_repo.get_dashboard_summary(graph)
    preview_len = len(summary["recent_incidents"])

    assert summary["critical_incidents_in_window"] >= 8, (
        f"critical_incidents_in_window is {summary['critical_incidents_in_window']} with 8 "
        f"critical incidents in the window; a value bounded by the {preview_len}-row "
        "preview means it is being derived from it"
    )
    assert summary["critical_incidents_in_window"] <= summary["incidents_in_window"]
