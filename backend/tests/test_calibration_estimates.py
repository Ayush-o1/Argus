"""The refusal to publish a rate the evidence cannot support.

This is a small module and these are the most important tests in the phase. A
quiet change here — a Wald interval, a dropped `informative` flag, a zero where
a null belongs — would put a confident-looking precision figure back on a
dashboard, which is the failure the whole codebase has been built to avoid.
"""

from __future__ import annotations

import pytest

from app.calibration.estimates import INFORMATIVE_WIDTH, estimate


def test_one_success_out_of_one_is_not_a_perfect_rule():
    # The case that motivates the module. Arithmetic says 100%; the interval
    # says the truth, which is that a single case tells you almost nothing.
    p = estimate(1, 1)
    assert p.point == 1.0
    assert p.ci_low is not None and p.ci_low < 0.05
    assert p.ci_high == 1.0
    assert not p.informative
    assert "too few outcomes" in p.describe()


def test_zero_successes_out_of_one_is_not_a_broken_rule():
    p = estimate(0, 1)
    assert p.point == 0.0
    assert p.ci_high is not None and p.ci_high > 0.9
    assert not p.informative


def test_no_trials_is_null_rather_than_zero():
    # "Nothing has been investigated yet" and "nothing investigated confirmed
    # it" are different facts. A zero would present the first as the second and
    # make an untested rule look like a broken one.
    p = estimate(0, 0)
    assert p.point is None
    assert p.ci_low is None and p.ci_high is None
    assert not p.informative
    assert "Nothing to estimate" in p.describe() or "nothing to estimate" in p.describe()


def test_the_interval_narrows_as_evidence_accumulates():
    widths = [
        estimate(int(0.7 * n), n).ci_high - estimate(int(0.7 * n), n).ci_low  # type: ignore[operator]
        for n in (10, 100, 1000)
    ]
    assert widths[0] > widths[1] > widths[2]


def test_a_rate_becomes_informative_only_once_the_interval_is_narrow():
    assert not estimate(7, 10).informative
    assert estimate(70, 100).informative
    # The threshold is a stated convention rather than a derived constant, and
    # it lives in one place so it cannot be picked per chart.
    p = estimate(70, 100)
    assert (p.ci_high - p.ci_low) <= INFORMATIVE_WIDTH  # type: ignore[operator]


def test_the_counts_come_before_the_estimate_in_the_payload():
    # Whatever renders this reads the denominator first. Ordering a dict is not
    # a guarantee about a UI, but it is a statement about what this module
    # considers primary.
    keys = list(estimate(3, 4).as_dict())
    assert keys.index("successes") < keys.index("point")
    assert keys.index("trials") < keys.index("point")


def test_the_method_is_published_with_the_interval():
    payload = estimate(3, 4).as_dict()
    assert "Clopper-Pearson" in payload["ci_method"]
    assert payload["confidence_level"] == 0.95


def test_an_impossible_proportion_is_refused():
    with pytest.raises(ValueError, match="not a proportion"):
        estimate(5, 3)
    with pytest.raises(ValueError, match="not a proportion"):
        estimate(-1, 3)


def test_the_exact_interval_is_not_degenerate_at_the_extremes():
    """Why Clopper-Pearson and not Wald.

    A Wald interval has zero width at 0 or n successes — it would report
    0.00 ± 0.00 for a rule nothing has confirmed, which is the most confident
    possible statement made from the least possible evidence.
    """
    for successes, trials in ((0, 5), (5, 5), (0, 20), (20, 20)):
        p = estimate(successes, trials)
        assert p.ci_low is not None and p.ci_high is not None
        assert p.ci_high - p.ci_low > 0.1, (
            f"{successes}/{trials} produced a near-zero-width interval"
        )
