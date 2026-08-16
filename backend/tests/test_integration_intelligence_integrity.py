"""Integration tests pinning the audit's headline finding: surfaces that
presented partial data as complete findings.

Each test builds a graph shaped to expose one specific misstatement, then
asserts the API reports the truth. They are written so that reverting the fix
makes them fail with a message naming the wrong claim, rather than a bare
assertion error.
"""

from __future__ import annotations

import pytest
from neo4j import AsyncDriver

from app.repositories import alert_repo, dashboard_repo, timeline_repo

pytestmark = pytest.mark.asyncio


async def _make_incident_with_entities(
    driver: AsyncDriver, tag: str, incident_id: str, countries: list[str], regions: list[str]
) -> None:
    """One Incident involving len(countries) Persons, one per country."""
    async with driver.session() as session:
        await session.run(
            """
            CREATE (i:Incident {
                incident_id: $incident_id, type: 'ProbeType', severity: 'Critical',
                status: 'Open', timestamp: '2026-06-01T00:00:00', description: 'probe',
                id: $uuid, _test_tag: $tag
            })
            """,
            incident_id=incident_id,
            uuid=f"{incident_id}-uuid",
            tag=tag,
        )
        for idx, (country, region) in enumerate(zip(countries, regions, strict=True)):
            await session.run(
                """
                MATCH (i:Incident {incident_id: $incident_id})
                CREATE (p:Person {
                    person_id: $person_id, name: $name, country: $country, region: $region,
                    risk_score: 90.0, id: $uuid, _test_tag: $tag
                })
                CREATE (i)-[:INVOLVES]->(p)
                """,
                incident_id=incident_id,
                person_id=f"PRS-{tag[-6:]}-{idx:03d}",
                name=f"Probe Person {idx}",
                country=country,
                region=region,
                uuid=f"{incident_id}-person-{idx}",
                tag=tag,
            )


async def test_alert_spread_counts_every_involved_entity(graph: AsyncDriver, tag: str) -> None:
    """B-04. Twelve involved entities across twelve countries; the preview holds
    five. Deriving spread from the preview reported five countries."""
    countries = [f"Country{i:02d}" for i in range(12)]
    regions = [f"Region{i % 4}" for i in range(12)]
    incident_id = f"INC-{tag[-8:]}"
    await _make_incident_with_entities(graph, tag, incident_id, countries, regions)

    alerts, _ = await alert_repo.list_alerts(graph, None, None, 1, 200)
    alert = next(a for a in alerts if a["incident_id"] == incident_id)

    spread = alert["spread"]
    assert spread["involved_total"] == 12, "involved_total must count every entity, not the preview"
    assert spread["country_count"] == 12, (
        f"country_count is {spread['country_count']}; deriving it from the "
        f"{len(alert['involved_entities'])}-entity preview understates the alert's reach"
    )
    assert spread["region_count"] == 4

    # The preview stays bounded, and says so.
    assert len(alert["involved_entities"]) == alert_repo.INVOLVED_PREVIEW_LIMIT
    coverage = alert["involved_coverage"]
    assert coverage["basis"] == "truncated"
    assert coverage["examined"] == alert_repo.INVOLVED_PREVIEW_LIMIT
    assert coverage["population"] == 12


async def test_alert_coverage_is_complete_when_nothing_is_truncated(graph: AsyncDriver, tag: str) -> None:
    incident_id = f"INC-{tag[-8:]}"
    await _make_incident_with_entities(graph, tag, incident_id, ["India", "UAE"], ["South Asia", "Middle East"])

    alerts, _ = await alert_repo.list_alerts(graph, None, None, 1, 200)
    alert = next(a for a in alerts if a["incident_id"] == incident_id)

    assert alert["involved_coverage"]["basis"] == "complete"
    assert alert["spread"]["country_count"] == 2


async def test_related_alerts_are_found_beyond_the_first_page(graph: AsyncDriver, tag: str) -> None:
    """B-29. The UI filtered the loaded page, so a related alert outside it was
    invisible while the panel claimed to identify one investigation."""
    storyline = f"STL-{tag[-8:]}"
    async with graph.session() as session:
        for idx in range(3):
            await session.run(
                """
                CREATE (i:Incident {
                    incident_id: $incident_id, type: 'ProbeType', severity: 'High',
                    status: 'Open', timestamp: $ts, description: 'probe',
                    storyline_id: $storyline, id: $uuid, _test_tag: $tag
                })
                """,
                incident_id=f"INC-{tag[-6:]}-{idx}",
                ts=f"2026-06-0{idx + 1}T00:00:00",
                storyline=storyline,
                uuid=f"{tag}-rel-{idx}",
                tag=tag,
            )

    related = await alert_repo.list_related_alerts(graph, f"INC-{tag[-6:]}-0")
    assert len(related) == 2
    assert all(r["storyline_id"] == storyline for r in related)
    assert all(r["incident_id"] != f"INC-{tag[-6:]}-0" for r in related), "must exclude the source alert"


async def test_related_alerts_empty_without_a_storyline(graph: AsyncDriver, tag: str) -> None:
    async with graph.session() as session:
        await session.run(
            """
            CREATE (i:Incident {
                incident_id: $incident_id, type: 'Solo', severity: 'High', status: 'Open',
                timestamp: '2026-06-01T00:00:00', description: 'probe', id: $uuid, _test_tag: $tag
            })
            """,
            incident_id=f"INC-{tag[-8:]}",
            uuid=f"{tag}-solo",
            tag=tag,
        )
    assert await alert_repo.list_related_alerts(graph, f"INC-{tag[-8:]}") == []


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


async def test_dashboard_critical_count_is_not_capped_by_the_preview(graph: AsyncDriver, tag: str) -> None:
    """B-05. The headline sentence put a full count and a six-row sample in one
    clause, so the critical figure could never exceed the preview length."""
    async with graph.session() as session:
        for idx in range(8):
            await session.run(
                """
                CREATE (i:Incident {
                    incident_id: $incident_id, type: 'ProbeType', severity: 'Critical',
                    status: 'Open', timestamp: '2026-06-01T00:00:00', description: 'probe',
                    id: $uuid, _test_tag: $tag
                })
                """,
                incident_id=f"INC-{tag[-6:]}-{idx}",
                uuid=f"{tag}-crit-{idx}",
                tag=tag,
            )

    summary = await dashboard_repo.get_dashboard_summary(graph)
    preview_len = len(summary["recent_incidents"])

    assert summary["critical_open_alerts"] >= 8, (
        f"critical_open_alerts is {summary['critical_open_alerts']} with 8 critical open incidents "
        f"present; a value bounded by the {preview_len}-row preview means it is being derived from it"
    )
    assert summary["critical_open_alerts"] <= summary["open_alerts"]
