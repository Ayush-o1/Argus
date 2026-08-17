"""The detection algorithms, against inputs whose right answer is obvious.

Every case here is small enough to verify by reading it. That is deliberate:
the detectors were calibrated against a graph of 40,000 transfers, and a
threshold that happens to work on that graph tells you nothing about whether
the algorithm is correct. These tests say what the algorithm must do.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.assessment.detectors import (
    burst_profile,
    corridor_frequencies,
    find_funds_cycles,
    percentile,
    rank_of,
)
from app.assessment.evidence import Transfer

BASE = datetime(2026, 3, 1, 9, 0, 0)


def transfer(tid: str, src: str, dst: str, amount: float, hours: float = 0.0) -> Transfer:
    return Transfer(
        transfer_id=tid,
        source_account=src,
        target_account=dst,
        amount=amount,
        occurred_at=BASE + timedelta(hours=hours),
    )


def cycles(transfers, **overrides):
    params = {
        "retention_low": 0.85,
        "retention_high": 1.0,
        "window": timedelta(days=7),
        "min_hops": 3,
        "max_hops": 8,
    }
    params.update(overrides)
    return find_funds_cycles(transfers, **params)


# ─────────────────────────────────────────────────────────────────────────────
# Funds cycles
# ─────────────────────────────────────────────────────────────────────────────


def test_a_closed_value_preserving_loop_is_found() -> None:
    found, truncated = cycles(
        [
            transfer("T1", "A", "B", 1000, 0),
            transfer("T2", "B", "C", 950, 3),
            transfer("T3", "C", "A", 900, 6),
        ]
    )
    assert not truncated
    assert len(found) == 1
    cycle = found[0]
    assert cycle.accounts == ("A", "B", "C", "A")
    assert cycle.hops == 3
    assert cycle.retained_fraction == pytest.approx(0.9)
    assert cycle.span_hours == pytest.approx(6.0)


def test_hops_need_not_be_in_time_order() -> None:
    """The planted chains in the synthetic world are frequently out of order,
    and so is real feed data with clock skew between systems.

    A detector that required monotonic timestamps found none of the six planted
    rings — the requirement was discovered by the detector returning zero
    cycles against data that visibly contained them, not by reasoning about it.
    """
    found, _ = cycles(
        [
            transfer("T1", "A", "B", 1000, 0),
            transfer("T2", "B", "C", 950, 9),
            transfer("T3", "C", "A", 900, 4),  # arrives "before" the hop it follows
        ]
    )
    assert len(found) == 1
    assert found[0].accounts == ("A", "B", "C", "A")


def test_a_loop_that_grows_in_value_is_not_a_cycle() -> None:
    """Value preservation is the whole signal. Money that comes back larger has
    done something, which may be unusual but is not layering."""
    found, _ = cycles(
        [
            transfer("T1", "A", "B", 1000, 0),
            transfer("T2", "B", "C", 1400, 1),
            transfer("T3", "C", "A", 1900, 2),
        ]
    )
    assert found == []


def test_a_loop_that_loses_most_of_its_value_is_not_a_cycle() -> None:
    found, _ = cycles(
        [
            transfer("T1", "A", "B", 1000, 0),
            transfer("T2", "B", "C", 200, 1),
            transfer("T3", "C", "A", 40, 2),
        ]
    )
    assert found == []


def test_a_loop_spread_beyond_the_window_is_not_a_cycle() -> None:
    found, _ = cycles(
        [
            transfer("T1", "A", "B", 1000, 0),
            transfer("T2", "B", "C", 950, 24 * 30),
            transfer("T3", "C", "A", 900, 24 * 60),
        ]
    )
    assert found == []


def test_an_open_chain_is_not_reported() -> None:
    """A→B→C→D never returns to A. It may be interesting, but it is not the
    pattern this signal claims to detect, and reporting it under that name
    would make the finding's stated rationale false."""
    found, _ = cycles(
        [
            transfer("T1", "A", "B", 1000, 0),
            transfer("T2", "B", "C", 950, 1),
            transfer("T3", "C", "D", 900, 2),
        ]
    )
    assert found == []


def test_a_two_hop_round_trip_is_below_the_minimum() -> None:
    """A pays B, B pays most of it back. Ordinary between two counterparties —
    a refund, a correction, a settlement — so the minimum is three."""
    found, _ = cycles([transfer("T1", "A", "B", 1000, 0), transfer("T2", "B", "A", 950, 1)])
    assert found == []


def test_the_same_cycle_is_reported_once_however_it_is_entered() -> None:
    found, _ = cycles(
        [
            transfer("T1", "A", "B", 1000, 0),
            transfer("T2", "B", "C", 950, 1),
            transfer("T3", "C", "A", 900, 2),
        ]
    )
    assert len(found) == 1


def test_an_account_is_not_revisited_within_one_cycle() -> None:
    """A→B→A→C→A would otherwise be reported as a four-hop ring. The accounts
    in a cycle are distinct by construction, so its length means what it says."""
    found, _ = cycles(
        [
            transfer("T1", "A", "B", 1000, 0),
            transfer("T2", "B", "A", 960, 1),
            transfer("T3", "A", "C", 930, 2),
            transfer("T4", "C", "A", 900, 3),
        ]
    )
    for cycle in found:
        assert len(set(cycle.accounts[:-1])) == len(cycle.accounts) - 1


def test_truncation_is_reported_rather_than_hidden() -> None:
    """A search that stopped early has under-reported. The caller is told, so a
    `routine` band produced by an exhausted search cannot be presented as a
    complete answer."""
    ring = [transfer(f"T{i}", f"A{i}", f"A{(i + 1) % 8}", 1000 * (0.99**i), i) for i in range(8)]
    found, truncated = cycles(ring, max_paths=1)
    assert truncated is True
    assert found == []


def test_zero_amount_transfers_cannot_anchor_a_cycle() -> None:
    """A ratio against zero is undefined; treating it as a match would make
    every zero-value transfer a universal connector."""
    found, _ = cycles(
        [
            transfer("T1", "A", "B", 0, 0),
            transfer("T2", "B", "C", 0, 1),
            transfer("T3", "C", "A", 0, 2),
        ]
    )
    assert found == []


def test_min_hops_below_two_is_rejected() -> None:
    with pytest.raises(ValueError):
        cycles([], min_hops=1)


# ─────────────────────────────────────────────────────────────────────────────
# Bursts
# ─────────────────────────────────────────────────────────────────────────────


def test_burst_profile_needs_history_before_it_will_speak() -> None:
    assert burst_profile([], window=timedelta(hours=6)) is None
    assert burst_profile([BASE], window=timedelta(hours=6)) is None
    # Every event at the same instant: no span, so no rate to compare against.
    assert burst_profile([BASE, BASE, BASE], window=timedelta(hours=6)) is None


def test_peak_window_counts_the_densest_span() -> None:
    times = [BASE + timedelta(hours=h) for h in (0, 1, 2, 3, 100, 200, 300)]
    profile = burst_profile(times, window=timedelta(hours=6))
    assert profile is not None
    assert profile.peak_count == 4
    assert profile.peak_start == BASE


def test_a_steady_rate_produces_a_ratio_near_one() -> None:
    # Spaced slightly wider than the window, so exactly one event falls in each.
    # At exactly the window width two would, because the window is inclusive at
    # both ends — which is correct, and would make this test measure the
    # boundary rule rather than the ratio.
    times = [BASE + timedelta(hours=6.5 * i) for i in range(40)]
    profile = burst_profile(times, window=timedelta(hours=6))
    assert profile is not None
    assert profile.peak_count == 1
    assert profile.ratio == pytest.approx(1.0, abs=0.15)


def test_a_spike_against_a_long_baseline_produces_a_large_ratio() -> None:
    steady = [BASE + timedelta(days=7 * i) for i in range(20)]
    spike = [BASE + timedelta(days=70.5, minutes=10 * i) for i in range(30)]
    profile = burst_profile(steady + spike, window=timedelta(hours=6))
    assert profile is not None
    assert profile.peak_count == 30
    assert profile.ratio > 20


def test_the_expected_floor_stops_a_thin_history_dominating() -> None:
    """Two events a year apart would otherwise divide by nearly zero and
    outrank a genuine spike. The floor is a stated model parameter, not a
    silent guard."""
    thin = [BASE, BASE + timedelta(days=365)]
    unfloored = burst_profile(thin, window=timedelta(hours=6), floor_expected=1e-9)
    floored = burst_profile(thin, window=timedelta(hours=6), floor_expected=0.5)
    assert unfloored is not None and floored is not None
    # Two events over a year: the expected count in a 6h window is 0.00137, so
    # a single event reads as 730x the baseline. The floor turns that into 2x.
    assert unfloored.ratio > 500
    assert floored.ratio == pytest.approx(2.0)


# ─────────────────────────────────────────────────────────────────────────────
# Rarity
# ─────────────────────────────────────────────────────────────────────────────


def test_corridor_frequencies_sum_to_one() -> None:
    shares = corridor_frequencies([("A", "B"), ("A", "B"), ("B", "C")])
    assert shares[("A", "B")] == pytest.approx(2 / 3)
    assert shares[("B", "C")] == pytest.approx(1 / 3)
    assert sum(shares.values()) == pytest.approx(1.0)


def test_direction_matters_for_a_corridor() -> None:
    shares = corridor_frequencies([("A", "B"), ("B", "A")])
    assert shares[("A", "B")] == pytest.approx(0.5)
    assert shares[("B", "A")] == pytest.approx(0.5)


def test_percentile_of_nothing_is_undefined_rather_than_zero() -> None:
    """Returning 0 would let a caller compare against it as though it meant
    something — the same defect as scoring a subject with no evidence."""
    assert percentile([], 0.9) is None
    assert rank_of([], 5.0) is None


def test_percentile_uses_nearest_rank() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(values, 0.0) == 1.0
    assert percentile(values, 0.5) == 3.0
    assert percentile(values, 1.0) == 5.0


def test_percentile_rejects_a_fraction_outside_the_unit_interval() -> None:
    with pytest.raises(ValueError):
        percentile([1.0], 1.5)
