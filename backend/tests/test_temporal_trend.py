"""Trend, changepoint and weekly rhythm — including where each declines."""

from __future__ import annotations

import numpy as np
import pytest

from app.temporal.trend import (
    MIN_TREND_POINTS,
    find_changepoint,
    mann_kendall,
    weekly_seasonality,
)


def test_a_rising_series_is_reported_as_rising() -> None:
    rng = np.random.default_rng(1)
    values = [float(i * 0.5 + rng.poisson(3)) for i in range(60)]
    r = mann_kendall(values)
    assert r.significant and r.direction == "rising"
    assert r.slope_per_day == pytest.approx(0.5, abs=0.2)


def test_a_falling_series_is_reported_as_falling() -> None:
    rng = np.random.default_rng(2)
    r = mann_kendall([float(60 - i + rng.poisson(2)) for i in range(60)])
    assert r.significant and r.direction == "falling"
    assert r.slope_per_day < 0


def test_the_false_positive_rate_is_about_alpha() -> None:
    """A trend test that fires on noise is worse than none, because it fires
    on every quiet series an analyst looks at."""
    hits = 0
    for seed in range(400):
        rng = np.random.default_rng(9000 + seed)
        if mann_kendall(list(rng.poisson(5, 60).astype(float))).significant:
            hits += 1
    assert 0.02 <= hits / 400 <= 0.09, f"false positive rate {hits / 400:.3f}"


def test_a_strong_trend_does_not_report_a_p_value_of_exactly_zero() -> None:
    """`1 - cdf` underflows and produces 0, which is a certainty no test can
    deliver. The survival function keeps it representable."""
    r = mann_kendall([float(i) for i in range(200)])
    assert r.p_value is not None and 0 < r.p_value < 1e-9


def test_sens_slope_is_not_moved_by_a_single_spike() -> None:
    """The reason Sen's slope is used instead of least squares: one outlier
    would drag a fitted line, and a trend nobody can see would be reported."""
    rng = np.random.default_rng(21)
    base = [float(10 + rng.integers(-2, 3)) for _ in range(40)]
    spiked = [*base]
    spiked[20] = 5000.0

    plain = mann_kendall(base)
    with_spike = mann_kendall(spiked)
    assert plain.slope_per_day is not None and with_spike.slope_per_day is not None
    assert with_spike.slope_per_day == pytest.approx(plain.slope_per_day, abs=0.05)

    # The contrast that justifies the choice: on this same data a least-squares
    # fit moves by three orders of magnitude when the spike is added, while
    # Sen's slope does not move at all.
    xs = np.arange(40.0)
    ols_plain = abs(float(np.polyfit(xs, np.array(base), 1)[0]))
    ols_spiked = abs(float(np.polyfit(xs, np.array(spiked), 1)[0]))
    assert ols_spiked > 100 * ols_plain
    assert with_spike.slope_per_day == plain.slope_per_day


def test_a_short_series_declines_rather_than_guessing() -> None:
    r = mann_kendall([1.0, 2.0, 3.0])
    assert not r.evaluable
    assert r.reason and str(MIN_TREND_POINTS) in r.reason


def test_a_constant_series_declines_rather_than_reporting_flat() -> None:
    """"No trend" and "nothing to trend" are different statements."""
    r = mann_kendall([7.0] * 40)
    assert not r.evaluable
    assert "identical" in (r.reason or "")


# ── changepoint ──────────────────────────────────────────────────────────────


def test_a_real_level_shift_is_found_near_the_right_place() -> None:
    rng = np.random.default_rng(3)
    series = list(rng.poisson(3, 30).astype(float)) + list(rng.poisson(12, 30).astype(float))
    c = find_changepoint(series)
    assert c.significant
    assert c.index is not None and abs(c.index - 30) <= 3
    assert c.after_mean > c.before_mean


def test_noise_produces_no_significant_changepoint() -> None:
    rng = np.random.default_rng(11)
    assert not find_changepoint(list(rng.poisson(5, 60).astype(float))).significant


def test_the_changepoint_test_is_deterministic() -> None:
    """A randomised test whose answer changes between runs is the defect the
    timeline's `rand()` sampling had: two analysts, two findings, same data."""
    rng = np.random.default_rng(5)
    series = list(rng.poisson(4, 50).astype(float))
    a, b = find_changepoint(series), find_changepoint(series)
    assert (a.index, a.p_value) == (b.index, b.p_value)


def test_a_flat_series_has_no_changepoint_to_find() -> None:
    c = find_changepoint([3.0] * 40)
    assert not c.evaluable and "identical" in (c.reason or "")


def test_the_permutation_p_value_is_never_exactly_zero() -> None:
    """The observed arrangement is one of the orderings; excluding it would
    let the test claim an impossibility."""
    rng = np.random.default_rng(6)
    series = list(rng.poisson(2, 40).astype(float)) + list(rng.poisson(60, 40).astype(float))
    c = find_changepoint(series)
    assert c.p_value is not None and c.p_value > 0


# ── weekly rhythm ────────────────────────────────────────────────────────────


def test_a_weekday_pattern_is_detected() -> None:
    s = weekly_seasonality({0: 50, 1: 52, 2: 48, 3: 51, 4: 49, 5: 8, 6: 7})
    assert s.significant
    assert s.quietest_day == "Sunday"


def test_an_even_week_is_not_a_pattern() -> None:
    s = weekly_seasonality({d: 40 for d in range(7)})
    assert s.evaluable and not s.significant


def test_too_little_data_declines_rather_than_reporting_a_pattern() -> None:
    s = weekly_seasonality({0: 2, 1: 1})
    assert not s.evaluable and s.reason


def test_every_result_names_its_test() -> None:
    """A statistic with no stated method is a number asking to be believed."""
    assert mann_kendall([float(i) for i in range(20)]).as_dict()["test"]
    assert find_changepoint([float(i % 5) for i in range(40)]).as_dict()["test"]
    assert weekly_seasonality({d: 40 for d in range(7)}).as_dict()["test"]
