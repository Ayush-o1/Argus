"""The arithmetic under the dimensions, checked against worked examples.

Every expected value here was computed by hand before the test was written. A
similarity measure whose only check is that it returns a float between 0 and 1
is not tested — it is merely observed not to crash, which is how a formula
nobody has verified ends up producing numbers nobody can question.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from app.correlation.measures import (
    centroid,
    forward_reach,
    haversine_km,
    noisy_or,
    overlap_weight,
    ramp,
    rarity_weight,
    window_overlap,
)

T0 = datetime(2026, 3, 1, 12, 0)


# ─────────────────────────────────────────────────────────────────────────────
# Distance
# ─────────────────────────────────────────────────────────────────────────────


def test_haversine_matches_a_known_distance() -> None:
    """Mumbai to Delhi is about 1,150 km by great circle."""
    distance = haversine_km(19.0760, 72.8777, 28.6139, 77.2090)
    assert 1140 < distance < 1170


def test_haversine_is_zero_for_the_same_point() -> None:
    assert haversine_km(19.0760, 72.8777, 19.0760, 72.8777) == pytest.approx(0.0, abs=1e-9)


def test_haversine_is_symmetric() -> None:
    there = haversine_km(19.0760, 72.8777, 28.6139, 77.2090)
    back = haversine_km(28.6139, 77.2090, 19.0760, 72.8777)
    assert there == pytest.approx(back)


# ─────────────────────────────────────────────────────────────────────────────
# Rarity
# ─────────────────────────────────────────────────────────────────────────────


def test_rarity_of_a_thing_only_two_subjects_share_is_near_one() -> None:
    # log(1000/2) / log(1000) = 6.2146 / 6.9078
    assert rarity_weight(2, population=1000) == pytest.approx(0.8996, abs=1e-4)


def test_rarity_of_a_thing_everyone_shares_is_zero() -> None:
    """The clearing account case: it connects everybody to everybody, which is
    a fact about the account rather than about any pair."""
    assert rarity_weight(1000, population=1000) == 0.0
    assert rarity_weight(1200, population=1000) == 0.0


def test_rarity_of_a_thing_half_the_population_shares_is_small_but_not_zero() -> None:
    # log(2) / log(1000) = 0.6931 / 6.9078
    assert rarity_weight(500, population=1000) == pytest.approx(0.1003, abs=1e-4)


def test_a_thing_only_one_subject_touches_is_worth_nothing() -> None:
    """Not shared at all. Treating it as maximally rare would be an off-by-one
    that rewarded non-evidence with the highest possible weight."""
    assert rarity_weight(1, population=1000) == 0.0
    assert rarity_weight(0, population=1000) == 0.0


def test_rarity_falls_as_more_subjects_share_it() -> None:
    weights = [rarity_weight(n, population=500) for n in (2, 5, 25, 100, 400)]
    assert weights == sorted(weights, reverse=True)


def test_overlap_sums_rather_than_averages() -> None:
    """Two rare shared counterparties are stronger evidence than one. An average
    would call them equally strong."""
    frequency = {"A-1": 2, "A-2": 2}
    one = overlap_weight(["A-1"], frequency, population=1000)
    two = overlap_weight(["A-1", "A-2"], frequency, population=1000)
    assert two == pytest.approx(2 * one)


def test_overlap_of_nothing_is_zero() -> None:
    assert overlap_weight([], {}, population=1000) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Ramp
# ─────────────────────────────────────────────────────────────────────────────


def test_ramp_is_zero_below_the_trigger_and_one_at_full() -> None:
    assert ramp(0.4, 0.55, 2.20) == 0.0
    assert ramp(0.55, 0.55, 2.20) == 0.0
    assert ramp(2.20, 0.55, 2.20) == 1.0
    assert ramp(9.0, 0.55, 2.20) == 1.0


def test_ramp_interpolates_linearly() -> None:
    # (0.90 - 0.55) / (2.20 - 0.55) = 0.35 / 1.65
    assert ramp(0.90, 0.55, 2.20) == pytest.approx(0.2121, abs=1e-4)


def test_an_inverted_ramp_scores_smaller_values_higher() -> None:
    """Distance: closer is stronger. (25 - 10) / (25 - 2) = 15 / 23."""
    assert ramp(10.0, 25.0, 2.0) == pytest.approx(0.6522, abs=1e-4)
    assert ramp(30.0, 25.0, 2.0) == 0.0
    assert ramp(1.0, 25.0, 2.0) == 1.0


def test_a_degenerate_ramp_becomes_a_step() -> None:
    assert ramp(5.0, 5.0, 5.0) == 1.0
    assert ramp(4.9, 5.0, 5.0) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Combination
# ─────────────────────────────────────────────────────────────────────────────


def test_noisy_or_of_two_halves_is_three_quarters() -> None:
    assert noisy_or([0.5, 0.5]) == pytest.approx(0.75)


def test_noisy_or_never_lowers_a_strength() -> None:
    """The dilution defect that made Phase 5's first scoring scheme unusable
    cannot recur here: adding weak evidence beside strong evidence must not
    reduce the result."""
    strong = noisy_or([0.9])
    with_weak = noisy_or([0.9, 0.05])
    assert with_weak >= strong


def test_noisy_or_does_not_reach_certainty_by_accumulation() -> None:
    assert noisy_or([0.9, 0.9, 0.9]) == pytest.approx(0.999, abs=1e-6)
    assert noisy_or([0.6] * 20) < 1.0


def test_noisy_or_reaches_one_only_on_a_categorical_input() -> None:
    """A dimension at exactly 1 found a fact, not an inference — three direct
    communications between the pair, say. The 1 that results is a statement
    about an observation rather than confidence assembled by adding up."""
    assert noisy_or([1.0, 0.1]) == 1.0


def test_noisy_or_of_nothing_is_zero() -> None:
    assert noisy_or([]) == 0.0


def test_noisy_or_clamps_out_of_range_inputs() -> None:
    assert noisy_or([1.5]) == 1.0
    assert noisy_or([-0.5, 0.5]) == pytest.approx(0.5)


# ─────────────────────────────────────────────────────────────────────────────
# Reachability
# ─────────────────────────────────────────────────────────────────────────────


def _chain() -> dict[str, list[tuple[str, float, datetime]]]:
    """A -> B -> C -> D, each hop passing on most of what arrived."""
    return {
        "A": [("B", 100_000.0, T0)],
        "B": [("C", 90_000.0, T0 + timedelta(days=1))],
        "C": [("D", 85_000.0, T0 + timedelta(days=2))],
    }


def test_forward_reach_follows_a_value_preserving_chain() -> None:
    reached, truncated = forward_reach(
        ["A"],
        _chain(),
        max_hops=4,
        min_hop_retention=0.80,
        min_total_retention=0.55,
        window=timedelta(days=30),
        max_frontier=100,
    )
    assert not truncated
    assert set(reached) == {"B", "C", "D"}
    assert reached["B"].hops == 1
    assert reached["C"].hops == 2
    assert reached["D"].hops == 3
    # 90,000/100,000 = 0.9, then 85,000/90,000 = 0.9444 -> 0.85
    assert reached["C"].retention == pytest.approx(0.9)
    assert reached["D"].retention == pytest.approx(0.85, abs=1e-4)


def test_a_hop_that_loses_most_of_the_value_is_not_followed() -> None:
    """Two busy accounts are connected if you walk far enough. Requiring the
    money to survive the hop is what separates a chain from that fact."""
    adjacency = {"A": [("B", 100_000.0, T0)], "B": [("C", 500.0, T0 + timedelta(days=1))]}
    reached, _ = forward_reach(
        ["A"],
        adjacency,
        max_hops=4,
        min_hop_retention=0.80,
        min_total_retention=0.55,
        window=timedelta(days=30),
        max_frontier=100,
    )
    assert set(reached) == {"B"}


def test_a_hop_larger_than_what_arrived_is_not_a_pass_through() -> None:
    """Money leaving an account that exceeds what came in is that account's own
    money, not the money being traced."""
    adjacency = {"A": [("B", 1_000.0, T0)], "B": [("C", 900_000.0, T0 + timedelta(days=1))]}
    reached, _ = forward_reach(
        ["A"],
        adjacency,
        max_hops=4,
        min_hop_retention=0.80,
        min_total_retention=0.55,
        window=timedelta(days=30),
        max_frontier=100,
    )
    assert set(reached) == {"B"}


def test_hops_need_not_be_in_time_order() -> None:
    """The planted chains advance each hop by `hop * uniform(1, 6)` hours, which
    is not monotonic. Phase 5 lost every planted ring to a detector that
    required increasing timestamps; this must not repeat that."""
    adjacency = {
        "A": [("B", 100_000.0, T0 + timedelta(days=5))],
        "B": [("C", 92_000.0, T0)],
    }
    reached, _ = forward_reach(
        ["A"],
        adjacency,
        max_hops=3,
        min_hop_retention=0.80,
        min_total_retention=0.55,
        window=timedelta(days=30),
        max_frontier=100,
    )
    assert "C" in reached


def test_a_route_spanning_longer_than_the_window_is_not_one_movement() -> None:
    adjacency = {
        "A": [("B", 100_000.0, T0)],
        "B": [("C", 92_000.0, T0 + timedelta(days=200))],
    }
    reached, _ = forward_reach(
        ["A"],
        adjacency,
        max_hops=3,
        min_hop_retention=0.80,
        min_total_retention=0.55,
        window=timedelta(days=30),
        max_frontier=100,
    )
    assert set(reached) == {"B"}


def test_reach_stops_at_the_hop_limit() -> None:
    reached, _ = forward_reach(
        ["A"],
        _chain(),
        max_hops=2,
        min_hop_retention=0.80,
        min_total_retention=0.55,
        window=timedelta(days=30),
        max_frontier=100,
    )
    assert set(reached) == {"B", "C"}


def test_truncation_is_reported_rather_than_swallowed() -> None:
    """A pair that was never compared must not be reported as a pair with
    nothing between them."""
    adjacency: dict[str, list[tuple[str, float, datetime]]] = {
        "A": [(f"H{i}", 100_000.0, T0) for i in range(10)]
    }
    for i in range(10):
        adjacency[f"H{i}"] = [(f"T{i}", 95_000.0, T0 + timedelta(hours=1))]

    _, truncated = forward_reach(
        ["A"],
        adjacency,
        max_hops=3,
        min_hop_retention=0.80,
        min_total_retention=0.55,
        window=timedelta(days=30),
        max_frontier=3,
    )
    assert truncated is True


def test_reach_never_returns_to_its_starting_account() -> None:
    adjacency = {
        "A": [("B", 100_000.0, T0)],
        "B": [("A", 95_000.0, T0 + timedelta(days=1))],
    }
    reached, _ = forward_reach(
        ["A"],
        adjacency,
        max_hops=4,
        min_hop_retention=0.80,
        min_total_retention=0.55,
        window=timedelta(days=30),
        max_frontier=100,
    )
    assert "A" not in reached


def test_reach_from_nowhere_is_empty() -> None:
    reached, truncated = forward_reach(
        [],
        _chain(),
        max_hops=4,
        min_hop_retention=0.80,
        min_total_retention=0.55,
        window=timedelta(days=30),
        max_frontier=100,
    )
    assert reached == {}
    assert truncated is False


# ─────────────────────────────────────────────────────────────────────────────
# Temporal overlap
# ─────────────────────────────────────────────────────────────────────────────


def test_window_overlap_counts_coincidences() -> None:
    a = [T0, T0 + timedelta(days=10)]
    b = [T0 + timedelta(hours=2), T0 + timedelta(days=10, hours=3)]
    count, earliest = window_overlap(a, b, window=timedelta(hours=24))
    assert count == 2
    assert earliest == T0


def test_window_overlap_counts_once_per_event_not_once_per_pair() -> None:
    """One transfer by A inside a flurry of fifty by B is one coincidence. Pair
    counting would let a single busy subject manufacture arbitrarily strong
    temporal evidence against everybody."""
    a = [T0]
    b = [T0 + timedelta(minutes=m) for m in range(50)]
    count, _ = window_overlap(a, b, window=timedelta(hours=24))
    assert count == 1


def test_window_overlap_is_zero_when_nothing_lines_up() -> None:
    a = [T0]
    b = [T0 + timedelta(days=40)]
    count, earliest = window_overlap(a, b, window=timedelta(hours=24))
    assert count == 0
    assert earliest is None


def test_window_overlap_includes_the_window_boundary() -> None:
    a = [T0]
    b = [T0 + timedelta(hours=24)]
    count, _ = window_overlap(a, b, window=timedelta(hours=24))
    assert count == 1


def test_window_overlap_of_an_empty_history_is_zero() -> None:
    assert window_overlap([], [T0], window=timedelta(hours=24)) == (0, None)
    assert window_overlap([T0], [], window=timedelta(hours=24)) == (0, None)


def test_window_overlap_does_not_depend_on_input_order() -> None:
    a = [T0 + timedelta(days=10), T0]
    b = [T0 + timedelta(days=10, hours=3), T0 + timedelta(hours=2)]
    assert window_overlap(a, b, window=timedelta(hours=24))[0] == 2


# ─────────────────────────────────────────────────────────────────────────────
# Centroid
# ─────────────────────────────────────────────────────────────────────────────


def test_centroid_of_one_point_is_that_point() -> None:
    result = centroid([(19.0760, 72.8777)])
    assert result is not None
    assert result[0] == pytest.approx(19.0760, abs=1e-6)
    assert result[1] == pytest.approx(72.8777, abs=1e-6)


def test_centroid_of_two_points_lies_between_them() -> None:
    result = centroid([(19.0, 72.0), (21.0, 74.0)])
    assert result is not None
    assert 19.0 < result[0] < 21.0
    assert 72.0 < result[1] < 74.0


def test_centroid_of_nothing_is_none() -> None:
    assert centroid([]) is None


def test_centroid_of_antipodes_is_undefined_rather_than_wrong() -> None:
    """Two exactly opposite points have no meaningful centre. Returning one
    would be inventing a location."""
    assert centroid([(0.0, 0.0), (0.0, 180.0)]) is None


def test_centroid_does_not_average_degrees_across_the_antimeridian() -> None:
    """Averaging 179 and -179 in degrees gives 0 — the wrong side of the planet.
    The three-dimensional computation gives 180."""
    result = centroid([(0.0, 179.0), (0.0, -179.0)])
    assert result is not None
    assert abs(result[1]) == pytest.approx(180.0, abs=1e-6)
    assert not math.isclose(result[1], 0.0, abs_tol=1.0)
