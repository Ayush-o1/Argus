"""Density clustering and the hotspot statistic.

The findings under test are the ones string grouping cannot produce: a
concentration that straddles a border, and a concentration that is more than the
map being dense there anyway.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.geometry import centroid, haversine_km
from app.spatial.clustering import cluster_points
from app.spatial.hotspots import getis_ord


def scatter(lat: float, lng: float, n: int, spread: float, seed: int, country: str, band: str | None = None):
    rng = np.random.default_rng(seed)
    return [
        {
            "ref": f"{country}-{i}",
            "lat": lat + float(rng.normal(0, spread)),
            "lng": lng + float(rng.normal(0, spread)),
            "country": country,
            "band": band,
        }
        for i in range(n)
    ]


# ── geometry ─────────────────────────────────────────────────────────────────


def test_haversine_matches_a_known_distance() -> None:
    """Mumbai to Delhi is about 1,150 km."""
    assert haversine_km(19.0760, 72.8777, 28.6139, 77.2090) == pytest.approx(1150, abs=25)


def test_centroid_is_not_a_mean_of_degrees() -> None:
    """Two points either side of the antimeridian average to longitude 0 —
    the wrong side of the planet — if the degrees are simply averaged."""
    result = centroid([(0.0, 179.0), (0.0, -179.0)])
    assert result is not None
    lat, lng = result
    assert abs(lat) < 1e-6
    assert abs(abs(lng) - 180.0) < 1e-6, f"naive mean would give 0, got {lng}"


def test_centroid_of_nothing_is_none() -> None:
    assert centroid([]) is None


# ── clustering ───────────────────────────────────────────────────────────────


def test_two_separate_concentrations_are_two_clusters() -> None:
    points = scatter(19.08, 72.88, 40, 0.15, 1, "India") + scatter(25.20, 55.27, 30, 0.15, 2, "UAE")
    clusters, noise = cluster_points(points)
    assert len(clusters) == 2
    assert noise == 0
    assert [c.size for c in clusters] == [40, 30]


def test_scattered_points_are_noise_not_forced_into_a_cluster() -> None:
    """DBSCAN rather than k-means: sparse points stay unassigned instead of
    being attached to whichever centre happens to be nearest."""
    rng = np.random.default_rng(3)
    far = [
        {"ref": f"F{i}", "lat": float(rng.uniform(-50, 60)), "lng": float(rng.uniform(-160, 160)),
         "country": "Other", "band": None}
        for i in range(25)
    ]
    clusters, noise = cluster_points(scatter(19.08, 72.88, 40, 0.15, 4, "India") + far)
    assert len(clusters) == 1
    assert noise >= 20


def test_a_concentration_across_a_border_is_one_cluster() -> None:
    """The finding `GROUP BY country` cannot make: fifty subjects packed into
    one area become two unremarkable national totals of twenty-five."""
    points = scatter(31.5, 74.0, 25, 0.2, 5, "Pakistan") + scatter(31.7, 74.6, 25, 0.2, 6, "India")
    clusters, _ = cluster_points(points)
    assert len(clusters) == 1
    assert clusters[0].size == 50
    assert clusters[0].crosses_border
    assert set(clusters[0].countries) == {"India", "Pakistan"}


def test_cluster_radius_is_a_real_distance() -> None:
    clusters, _ = cluster_points(scatter(19.08, 72.88, 40, 0.15, 7, "India"))
    c = clusters[0]
    assert 0 < c.radius_km < 200
    assert c.mean_distance_km <= c.radius_km


def test_eps_is_a_distance_not_a_number_of_degrees() -> None:
    """A degree of longitude is 111 km at the equator and 79 km at 45°N.
    Clustering in degrees would use a different radius at every latitude."""
    equator = scatter(0.0, 0.0, 20, 0.35, 8, "A")
    high = scatter(60.0, 0.0, 20, 0.35, 8, "B")
    at_equator, _ = cluster_points(equator, eps_km=60, min_samples=5)
    at_latitude, _ = cluster_points(high, eps_km=60, min_samples=5)
    assert len(at_equator) == len(at_latitude) == 1


def test_too_few_points_produce_no_clusters_and_report_them_as_noise() -> None:
    clusters, noise = cluster_points(scatter(19.0, 72.0, 3, 0.1, 9, "India"))
    assert clusters == []
    assert noise == 3


def test_points_without_coordinates_are_excluded() -> None:
    points = scatter(19.08, 72.88, 40, 0.15, 10, "India")
    points.append({"ref": "NOWHERE", "lat": None, "lng": None, "country": "X", "band": None})
    clusters, _ = cluster_points(points)
    assert all("NOWHERE" not in c.members for c in clusters)


def test_assessment_counts_travel_with_the_cluster() -> None:
    points = scatter(19.08, 72.88, 40, 0.15, 11, "India", band="elevated")
    clusters, _ = cluster_points(points)
    assert clusters[0].elevated == 40
    assert clusters[0].assessed == 40


# ── hotspots ─────────────────────────────────────────────────────────────────


def grid(hot_cells: set[tuple[int, int]], hot: float, base: float, seed: int = 5):
    rng = np.random.default_rng(seed)
    return [
        {
            "key": f"r{r}c{c}",
            "lat": 20 + r * 2.0,
            "lng": 70 + c * 2.0,
            "value": float(max(0, rng.poisson(hot if (r, c) in hot_cells else base))),
        }
        for r in range(8)
        for c in range(8)
    ]


def test_a_block_of_elevated_cells_is_found() -> None:
    hot = {(r, c) for r in (2, 3, 4) for c in (2, 3, 4)}
    report = getis_ord(grid(hot, hot=45, base=10), band_km=350)
    found = {h.key for h in report.hot}
    assert len(found) >= 7
    assert found <= {f"r{r}c{c}" for r, c in hot}, "flagged a cell outside the block"


def test_the_centre_of_a_hotspot_scores_highest() -> None:
    hot = {(r, c) for r in (2, 3, 4) for c in (2, 3, 4)}
    report = getis_ord(grid(hot, hot=45, base=10), band_km=350)
    assert report.hot[0].key == "r3c3"


def test_a_quiet_block_is_reported_as_cold() -> None:
    values = grid(set(), hot=0, base=30, seed=9)
    for item in values:
        r, c = int(item["key"][1]), int(item["key"][3])
        if r in (5, 6) and c in (5, 6):
            item["value"] = 1.0
    report = getis_ord(values, band_km=350)
    assert {h.key for h in report.cold} >= {"r5c5", "r5c6", "r6c5", "r6c6"}
    assert report.hot == []


def test_the_correction_suppresses_hotspots_that_are_only_chance() -> None:
    """Testing 64 cells at alpha 0.05 yields about three by arithmetic. A map
    that highlights three arbitrary places is worse than one that highlights
    none, because an analyst will go and look."""
    raw = corrected = 0
    for seed in range(30):
        rng = np.random.default_rng(2000 + seed)
        cells = [
            {"key": f"r{r}c{c}", "lat": 20 + r * 2.0, "lng": 70 + c * 2.0,
             "value": float(rng.poisson(20))}
            for r in range(8) for c in range(8)
        ]
        payload = getis_ord(cells, band_km=350).as_dict()
        raw += payload["significant_before_correction"]
        corrected += payload["significant_after_correction"]
    assert corrected < raw / 5, f"correction barely helped: {raw} raw, {corrected} corrected"


def test_both_verdicts_are_published() -> None:
    """The correction must be visible, not merely applied."""
    payload = getis_ord(grid({(3, 3)}, hot=60, base=10), band_km=350).as_dict()
    assert "significant_before_correction" in payload
    assert "significant_after_correction" in payload
    assert payload["caveat"]


def test_uniform_values_have_no_hotspot_to_find() -> None:
    cells = [{"key": f"c{i}", "lat": 20 + i, "lng": 70, "value": 10.0} for i in range(12)]
    report = getis_ord(cells)
    assert not report.evaluable
    assert "same value" in (report.reason or "")


def test_too_few_locations_declines_rather_than_guessing() -> None:
    cells = [{"key": f"c{i}", "lat": 20 + i, "lng": 70, "value": float(i)} for i in range(4)]
    report = getis_ord(cells)
    assert not report.evaluable
    assert report.reason
