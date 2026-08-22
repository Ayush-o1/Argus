"""The rate test, the multiplicity correction, and the per-day burst test.

Expected values are computed by hand or taken from a published worked example
wherever one exists. A statistic verified only against its own output is a
statistic nobody has checked.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.temporal.significance import (
    compare_rates,
    fdr_adjust,
    flag_unusual_days,
)

# ── rate comparison ──────────────────────────────────────────────────────────


def test_identical_rates_report_no_change() -> None:
    r = compare_rates(50, 30, 50, 30)
    assert r.rate_ratio == pytest.approx(1.0)
    assert not r.significant
    assert r.direction == "unchanged"


def test_a_doubling_on_small_numbers_is_not_significant() -> None:
    """The case the old 2σ rule got wrong. Nine events against four is a
    doubling and is entirely ordinary at this volume."""
    r = compare_rates(9, 7, 4, 7)
    assert r.rate_ratio == pytest.approx(2.25)
    assert not r.significant
    assert r.ci_low < 1.0 < r.ci_high


def test_the_same_doubling_on_large_numbers_is_significant() -> None:
    r = compare_rates(200, 30, 100, 30)
    assert r.rate_ratio == pytest.approx(2.0)
    assert r.significant
    assert r.ci_low > 1.0


def test_unequal_windows_are_compared_by_rate_not_by_count() -> None:
    """30 events in 10 days against 30 in 30 days is a tripling, not parity."""
    r = compare_rates(30, 10, 30, 30)
    assert r.rate_ratio == pytest.approx(3.0)
    assert r.significant


def test_confidence_interval_and_p_value_never_disagree() -> None:
    """A CI excluding 1 and a p below alpha are the same statement; if they
    ever differ, one of them is being computed wrongly."""
    for recent in range(0, 60):
        r = compare_rates(recent, 14, 30, 14)
        if not r.evaluable:
            continue
        excludes_one = r.ci_low > 1.0 or r.ci_high < 1.0
        assert excludes_one == r.significant, f"disagreement at recent={recent}"


def test_an_empty_baseline_gives_an_infinite_ratio_with_a_finite_lower_bound() -> None:
    r = compare_rates(12, 7, 0, 7)
    assert r.rate_ratio == float("inf")
    assert r.ci_low > 1.0
    assert r.significant


def test_no_events_anywhere_is_not_evaluable_rather_than_unchanged() -> None:
    """A quiet world and an unchanged world are different findings."""
    r = compare_rates(0, 7, 0, 7)
    assert not r.evaluable
    assert r.rate_ratio is None
    assert r.direction == "unknown"
    assert "no rate to compare" in r.describe()


def test_a_zero_length_window_is_refused() -> None:
    with pytest.raises(ValueError):
        compare_rates(5, 0, 5, 7)


def test_the_result_carries_its_window_and_baseline() -> None:
    """The defect that made "N days above 2σ" uncheckable was that it never
    said what it was measured against."""
    payload = compare_rates(10, 7, 20, 30).as_dict()
    assert payload["recent"]["days"] == 7
    assert payload["baseline"]["days"] == 30
    assert "test" in payload and payload["test"]


# ── multiplicity ─────────────────────────────────────────────────────────────


def test_benjamini_hochberg_matches_the_published_example() -> None:
    """Benjamini & Hochberg (1995), Table 1. The paper rejects four."""
    ps = [.0001, .0004, .0019, .0095, .0201, .0278, .0298, .0344, .0459,
          .3240, .4262, .5719, .6528, .7590, 1.000]
    assert sum(fdr_adjust(ps, 0.05)) == 4


def test_fdr_is_order_independent() -> None:
    ps = [0.04, 0.001, 0.3, 0.02, 0.9]
    forward = {p for p, k in zip(ps, fdr_adjust(ps, 0.05), strict=True) if k}
    reversed_ps = list(reversed(ps))
    backward = {p for p, k in zip(reversed_ps, fdr_adjust(reversed_ps, 0.05), strict=True) if k}
    assert forward == backward


def test_fdr_rejects_nothing_when_nothing_is_significant() -> None:
    assert not any(fdr_adjust([0.5, 0.6, 0.9], 0.05))


def test_fdr_handles_an_empty_list() -> None:
    assert fdr_adjust([], 0.05) == []


# ── per-day bursts ───────────────────────────────────────────────────────────


def test_injected_spikes_are_found() -> None:
    rng = np.random.default_rng(4)
    counts = list(rng.poisson(20, 120).astype(int))
    counts[40], counts[90] = 95, 88
    flagged = {d.index for d in flag_unusual_days(counts) if d.significant}
    assert {40, 90} <= flagged


def test_a_burst_does_not_inflate_its_own_threshold() -> None:
    """The specific defect in "mean + 2σ": each burst raised the bar meant to
    catch it, so a series with several bursts hid all of them. The baseline
    here excludes the day under test."""
    counts = [10] * 60
    for i in (10, 20, 30, 40, 50):
        counts[i] = 60
    flagged = {d.index for d in flag_unusual_days(counts) if d.significant}
    assert {10, 20, 30, 40, 50} <= flagged, "multiple bursts masked each other"


def test_quiet_days_are_flagged_too() -> None:
    counts = [40] * 60
    counts[25] = 2
    flagged = [d for d in flag_unusual_days(counts) if d.significant]
    assert any(d.index == 25 and d.direction == "low" for d in flagged)


def test_ordinary_variation_is_not_called_a_burst() -> None:
    """Measured, not asserted: the old rule flagged about 2.7% of ordinary
    days. This must be far below that."""
    total = 0
    for seed in range(30):
        rng = np.random.default_rng(500 + seed)
        counts = list(rng.poisson(20, 120).astype(int))
        total += sum(1 for d in flag_unusual_days(counts) if d.significant)
    rate = total / (30 * 120)
    assert rate < 0.005, f"false burst rate {rate:.4f} is too high"


def test_a_short_series_reports_nothing_rather_than_guessing() -> None:
    assert flag_unusual_days([1, 2]) == []


def test_an_all_zero_series_flags_nothing() -> None:
    assert not any(d.significant for d in flag_unusual_days([0] * 30))
