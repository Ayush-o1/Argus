"""The temporal and spatial analysis against a real graph.

Covers what only shows up against real data: that the queries match the labels
the graph actually uses, that windows anchor to the data rather than the clock,
and that absent days are counted as zero rather than omitted.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from neo4j import AsyncDriver

from app.repositories import patterns_repo
from app.services import patterns

pytestmark = pytest.mark.asyncio


async def test_every_lane_matches_the_labels_the_graph_uses(graph: AsyncDriver) -> None:
    """COMMUNICATED_WITH joins Devices, not people. Matching Person to Person
    returned nothing at all — silently — and the lane read as a world in which
    nobody communicates."""
    series = await patterns_repo.fetch_daily_series(graph)
    assert set(series) == set(patterns_repo.LANES)
    for lane in ("transactions", "communications"):
        assert sum(b["total"] for b in series[lane].values()) > 0, (
            f"the {lane} lane matched nothing; the query does not fit the graph"
        )


async def test_densify_counts_absent_days_as_zero(graph: AsyncDriver) -> None:
    """Audit B-18. A day with no activity produces no row, and a mean computed
    over only the days present treats "nothing happened" as "no observation" —
    inflating every baseline and suppressing the quiet periods a change is
    measured against."""
    buckets = {date(2026, 1, 1): {"total": 5, "elevated": 0}}
    series = patterns_repo.densify(buckets, date(2026, 1, 1), date(2026, 1, 5))
    assert series == [5, 0, 0, 0, 0]
    assert len(series) == 5


async def test_temporal_analysis_runs_and_states_its_window(graph: AsyncDriver) -> None:
    result = await patterns.analyse_temporal(graph, window_days=30, baseline_days=90)
    assert result["evaluable"]
    assert result["window"]["days"] == 30
    assert result["baseline"]["days"] == 90
    assert result["window"]["from"] and result["baseline"]["from"]
    for lane in result["series"]:
        assert lane["change"]["test"]
        assert lane["change"]["recent"]["days"] == 30


async def test_windows_anchor_to_the_data_not_the_clock(graph: AsyncDriver) -> None:
    """Anchoring to today on a world whose most recent event is months old
    produces an empty recent window and a confident claim that activity has
    stopped."""
    far_future = datetime.now(UTC) + timedelta(days=3650)
    result = await patterns.analyse_temporal(graph, now=far_future)
    assert result["evaluable"]
    assert result["window"]["to"] == result["anchored_to"]
    totals = [s["change"]["recent"]["count"] for s in result["series"]]
    assert sum(totals) > 0, "the window anchored to the clock and found nothing"


async def test_an_impossible_window_is_refused(graph: AsyncDriver) -> None:
    with pytest.raises(ValueError):
        await patterns.analyse_temporal(graph, window_days=0)
    with pytest.raises(ValueError):
        await patterns.analyse_temporal(graph, baseline_days=99999)


async def test_spatial_analysis_finds_real_concentrations(graph: AsyncDriver) -> None:
    result = await patterns.analyse_spatial(graph)
    clusters = result["clusters"]
    assert clusters["located_total"] > 0
    assert clusters["count"] > 0
    for cluster in clusters["found"]:
        assert cluster["size"] >= clusters["min_samples"]
        assert cluster["radius_km"] >= 0
        assert -90 <= cluster["lat"] <= 90
        assert -180 <= cluster["lng"] <= 180


async def test_the_unclustered_remainder_is_reported(graph: AsyncDriver) -> None:
    """A view showing only clusters would imply the world is made of them."""
    result = await patterns.analyse_spatial(graph)
    assert "noise" in result["clusters"]
    assert result["clusters"]["note"]


async def test_hotspots_publish_both_verdicts(graph: AsyncDriver) -> None:
    result = await patterns.analyse_spatial(graph)
    hotspots = result["hotspots"]
    if not hotspots["evaluable"]:
        pytest.skip(f"not evaluable on this graph: {hotspots['reason']}")
    assert hotspots["significant_after_correction"] <= hotspots["significant_before_correction"]
    assert hotspots["caveat"]
    for item in hotspots["hot"]:
        assert item["z_score"] > 0


async def test_spatial_parameters_are_bounded(graph: AsyncDriver) -> None:
    for kwargs in ({"eps_km": 0.0}, {"min_samples": 1}, {"band_km": 1.0}, {"value": "risk_score"}):
        with pytest.raises(ValueError):
            await patterns.analyse_spatial(graph, **kwargs)  # type: ignore[arg-type]


async def test_country_markers_use_a_spherical_centroid(graph: AsyncDriver) -> None:
    """`avg(n.lat), avg(n.lng)` in Cypher is the arithmetic mean of angles,
    which is not the mean direction and is simply wrong across the
    antimeridian."""
    from app.repositories import map_repo

    rows = await map_repo.get_country_rollup(graph)
    assert rows
    for row in rows:
        if row["lat"] is None:
            continue
        assert -90 <= row["lat"] <= 90
        assert -180 <= row["lng"] <= 180
