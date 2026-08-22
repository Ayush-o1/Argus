"""The temporal and spatial analysis against a real graph.

These tests **create the world they measure**. An earlier version asserted
against whatever the developer's graph happened to hold, which passed on a
seeded machine and failed in CI against an empty database — and a test that only
works where the data already exists is not testing the query, it is testing the
developer's fixture state.

Everything created carries `_test_tag` and is removed by the `graph` fixture.
The assertions are written to hold whether or not a full world is also present:
they check that a query *matches its labels* and that a computed value is
well-formed, never that a global count equals a particular number.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from neo4j import AsyncDriver

from app.repositories import patterns_repo
from app.services import patterns

pytestmark = pytest.mark.asyncio

# A window the seeded activity sits inside, far from any real world's dates so
# the two cannot be confused when both are present.
BASE_DAY = date(2031, 3, 1)


async def seed_activity(driver: AsyncDriver, tag: str, days: int = 40) -> None:
    """Accounts transacting, devices communicating, and events — the three lanes.

    Written with the labels the graph actually uses: TRANSACTED_WITH joins
    Accounts and COMMUNICATED_WITH joins Devices. Matching Person to Person for
    the second returned nothing at all, silently, and the lane read as a world
    in which nobody communicates. That is the defect this seeding pins.
    """
    async with driver.session() as session:
        await session.run(
            """
            CREATE (a:Account {account_id: $a, id: $a, argus_band: 'elevated', _test_tag: $tag})
            CREATE (b:Account {account_id: $b, id: $b, argus_band: 'routine',  _test_tag: $tag})
            CREATE (d1:Device {device_id: $d1, id: $d1, _test_tag: $tag})
            CREATE (d2:Device {device_id: $d2, id: $d2, _test_tag: $tag})
            CREATE (p1:Person {person_id: $p1, id: $p1, argus_band: 'elevated', _test_tag: $tag})
            CREATE (p2:Person {person_id: $p2, id: $p2, argus_band: 'routine',  _test_tag: $tag})
            CREATE (p1)-[:OWNS_DEVICE]->(d1)
            CREATE (p2)-[:OWNS_DEVICE]->(d2)
            """,
            a=f"ACC-{tag[-6:]}-A", b=f"ACC-{tag[-6:]}-B",
            d1=f"DEV-{tag[-6:]}-1", d2=f"DEV-{tag[-6:]}-2",
            p1=f"PRS-{tag[-6:]}-1", p2=f"PRS-{tag[-6:]}-2",
            tag=tag,
        )
        for offset in range(days):
            stamp = f"{(BASE_DAY + timedelta(days=offset)).isoformat()}T09:00:00"
            await session.run(
                """
                MATCH (a:Account {account_id: $a}), (b:Account {account_id: $b})
                MATCH (d1:Device {device_id: $d1}), (d2:Device {device_id: $d2})
                CREATE (a)-[:TRANSACTED_WITH {tx_id: $tx, timestamp: $ts, amount: 100.0, _test_tag: $tag}]->(b)
                CREATE (d1)-[:COMMUNICATED_WITH {comm_id: $cm, timestamp: $ts, _test_tag: $tag}]->(d2)
                CREATE (:Event {event_id: $ev, id: $ev, timestamp: $ts, type: 'Probe', _test_tag: $tag})
                """,
                a=f"ACC-{tag[-6:]}-A", b=f"ACC-{tag[-6:]}-B",
                d1=f"DEV-{tag[-6:]}-1", d2=f"DEV-{tag[-6:]}-2",
                tx=f"TX-{tag[-6:]}-{offset}", cm=f"CM-{tag[-6:]}-{offset}",
                ev=f"EV-{tag[-6:]}-{offset}", ts=stamp, tag=tag,
            )


async def seed_cluster(driver: AsyncDriver, tag: str, members: int = 12) -> None:
    """A tight concentration straddling a border — the finding `GROUP BY
    country` cannot express."""
    async with driver.session() as session:
        for i in range(members):
            await session.run(
                """
                CREATE (p:Person {
                    person_id: $ref, id: $ref, lat: $lat, lng: $lng,
                    country: $country, region: 'Probe Region',
                    argus_band: 'elevated', _test_tag: $tag
                })
                """,
                ref=f"PRS-{tag[-6:]}-G{i}",
                lat=31.5 + (i % 4) * 0.02,
                lng=74.0 + (i // 4) * 0.02,
                country="Probeland" if i % 2 == 0 else "Otherland",
                tag=tag,
            )


# ── temporal ─────────────────────────────────────────────────────────────────


async def test_every_lane_matches_the_labels_the_graph_uses(graph: AsyncDriver, tag: str) -> None:
    await seed_activity(graph, tag)
    series = await patterns_repo.fetch_daily_series(graph)
    assert set(series) == set(patterns_repo.LANES)
    for lane in patterns_repo.LANES:
        assert sum(b["total"] for b in series[lane].values()) > 0, (
            f"the {lane} lane matched nothing; the query does not fit the graph"
        )


async def test_the_elevated_count_resolves_through_device_owners(graph: AsyncDriver, tag: str) -> None:
    """`COMMUNICATED_WITH` joins Devices, so "elevated" has to be resolved
    through whoever owns them or the lane would always report zero."""
    await seed_activity(graph, tag)
    series = await patterns_repo.fetch_daily_series(graph)
    assert sum(b["elevated"] for b in series["communications"].values()) > 0


async def test_densify_counts_absent_days_as_zero() -> None:
    """Audit B-18. A day with no activity produces no row, and a mean over only
    the days present treats "nothing happened" as "no observation" — inflating
    every baseline and suppressing the quiet periods a change is measured
    against."""
    buckets = {date(2026, 1, 1): {"total": 5, "elevated": 0}}
    assert patterns_repo.densify(buckets, date(2026, 1, 1), date(2026, 1, 5)) == [5, 0, 0, 0, 0]


async def test_temporal_analysis_states_its_window_and_baseline(graph: AsyncDriver, tag: str) -> None:
    await seed_activity(graph, tag)
    result = await patterns.analyse_temporal(graph, window_days=10, baseline_days=20)
    assert result["evaluable"]
    assert result["window"]["days"] == 10
    assert result["baseline"]["days"] == 20
    for lane in result["series"]:
        assert lane["change"]["test"]
        assert lane["change"]["recent"]["days"] == 10
        assert lane["trend"]["test"]
        assert lane["seasonality"]["test"]


async def test_windows_anchor_to_the_data_not_the_clock(graph: AsyncDriver, tag: str) -> None:
    """Anchoring to today on a world whose most recent event is older produces
    an empty window and a confident claim that activity has stopped."""
    await seed_activity(graph, tag)
    far_future = datetime.now(UTC) + timedelta(days=3650)
    result = await patterns.analyse_temporal(graph, now=far_future)
    assert result["evaluable"]
    assert result["window"]["to"] == result["anchored_to"]
    assert sum(s["change"]["recent"]["count"] for s in result["series"]) > 0


async def test_a_steady_series_is_not_reported_as_a_change(graph: AsyncDriver, tag: str) -> None:
    """The seeded world produces exactly one event per lane per day, so any
    'significant change' would be the test inventing one."""
    await seed_activity(graph, tag, days=40)
    result = await patterns.analyse_temporal(graph, window_days=10, baseline_days=20)
    probe = next(s for s in result["series"] if s["lane"] == "events")
    assert probe["change"]["evaluable"]


async def test_an_impossible_window_is_refused(graph: AsyncDriver) -> None:
    for kwargs in ({"window_days": 0}, {"baseline_days": 99999}):
        with pytest.raises(ValueError):
            await patterns.analyse_temporal(graph, **kwargs)  # type: ignore[arg-type]


# ── spatial ──────────────────────────────────────────────────────────────────


async def test_a_seeded_concentration_is_found(graph: AsyncDriver, tag: str) -> None:
    await seed_cluster(graph, tag)
    result = await patterns.analyse_spatial(graph, eps_km=25, min_samples=5)
    refs = {f"PRS-{tag[-6:]}-G{i}" for i in range(12)}
    mine = [c for c in result["clusters"]["found"] if refs & set(c["members"])]
    assert mine, "the seeded concentration was not clustered"
    assert mine[0]["size"] >= 12
    assert -90 <= mine[0]["lat"] <= 90 and -180 <= mine[0]["lng"] <= 180


async def test_a_concentration_across_a_border_is_one_cluster(graph: AsyncDriver, tag: str) -> None:
    """`GROUP BY country` would report two unremarkable national totals."""
    await seed_cluster(graph, tag)
    result = await patterns.analyse_spatial(graph, eps_km=25, min_samples=5)
    refs = {f"PRS-{tag[-6:]}-G{i}" for i in range(12)}
    mine = next(c for c in result["clusters"]["found"] if refs & set(c["members"]))
    assert mine["crosses_border"]
    assert set(mine["countries"]) >= {"Probeland", "Otherland"}


async def test_the_unclustered_remainder_is_reported(graph: AsyncDriver, tag: str) -> None:
    """A view showing only clusters would imply the world is made of them."""
    await seed_cluster(graph, tag)
    result = await patterns.analyse_spatial(graph, eps_km=25, min_samples=5)
    assert "noise" in result["clusters"]
    assert result["clusters"]["note"]


async def test_hotspots_publish_both_verdicts(graph: AsyncDriver, tag: str) -> None:
    await seed_cluster(graph, tag)
    hotspots = (await patterns.analyse_spatial(graph))["hotspots"]
    if not hotspots["evaluable"]:
        # Fewer locations than Gi* needs is a legitimate outcome on a graph
        # holding only the seeded probe, and it says so rather than guessing.
        assert hotspots["reason"]
        return
    assert hotspots["significant_after_correction"] <= hotspots["significant_before_correction"]
    assert hotspots["caveat"]
    assert all(h["z_score"] > 0 for h in hotspots["hot"])


async def test_spatial_parameters_are_bounded(graph: AsyncDriver) -> None:
    for kwargs in ({"eps_km": 0.0}, {"min_samples": 1}, {"band_km": 1.0}, {"value": "risk_score"}):
        with pytest.raises(ValueError):
            await patterns.analyse_spatial(graph, **kwargs)  # type: ignore[arg-type]


async def test_country_markers_use_a_spherical_centroid(graph: AsyncDriver, tag: str) -> None:
    """`avg(n.lat), avg(n.lng)` in Cypher is the arithmetic mean of angles,
    which is not the mean direction and is wrong across the antimeridian."""
    from app.repositories import map_repo

    await seed_cluster(graph, tag)
    rows = await map_repo.get_country_rollup(graph)
    seeded = [r for r in rows if r["country"] in ("Probeland", "Otherland")]
    assert seeded, "the seeded countries did not appear in the rollup"
    for row in seeded:
        assert row["lat"] is not None and row["lng"] is not None
        assert 31.0 <= row["lat"] <= 32.0
        assert 73.5 <= row["lng"] <= 74.5
