"""Estimating a proportion honestly when the denominator is small.

## The problem this module exists to prevent

ARGUS currently holds two closed investigations. One confirmed, one unfounded.
A naive calibration would report:

    assessment.elevated        precision 0.00
    convergence.assessed_cluster  precision 1.00

Both figures are arithmetically correct and both are worthless. The second says
a rule is perfect on the evidence of a single case. Printing either one in a
dashboard would be the same failure this project spent nine phases removing from
elsewhere: a number carrying more authority than its evidence supports.

## What is published instead

Never a bare point estimate. Every proportion travels with:

  - the two counts it came from, so the denominator is always visible;
  - an exact (Clopper-Pearson) interval, which is honest at n = 1 where a
    normal approximation is not — at 1 success in 1 trial it reports
    [0.025, 1.000], which is the truth;
  - `informative`, which is false when the interval is so wide that the
    estimate cannot distinguish a good rule from a bad one.

`informative` is a presentation decision, not a statistical one, and it is
declared as such. The threshold is stated in code rather than chosen per chart.

## Why exact rather than Wald or Wilson

Wald intervals are famously wrong at the extremes — at 0 or 1 successes they
have zero width, which is precisely the case calibration starts from and
precisely where a confident-looking interval does the most damage. Clopper-
Pearson is conservative in the other direction: it can be wider than necessary,
which is the correct way to be wrong here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scipy import stats

__all__ = ["INFORMATIVE_WIDTH", "Proportion", "estimate"]

# An interval wider than this cannot separate a rule worth keeping from one
# worth retiring, so the point estimate is withheld from any summary that would
# read as a judgement. 0.35 is a stated convention, not a derived constant: it
# is roughly the width below which two rules an analyst would treat differently
# stop overlapping. It is here, once, rather than as a per-surface cutoff.
INFORMATIVE_WIDTH = 0.35

CONFIDENCE_LEVEL = 0.95


@dataclass(frozen=True)
class Proportion:
    """A proportion, its counts, and how much it is worth believing."""

    successes: int
    trials: int
    point: float | None
    ci_low: float | None
    ci_high: float | None

    @property
    def informative(self) -> bool:
        """Whether the interval is narrow enough for the point to mean anything."""
        if self.ci_low is None or self.ci_high is None:
            return False
        return (self.ci_high - self.ci_low) <= INFORMATIVE_WIDTH

    def describe(self) -> str:
        if self.trials == 0:
            return "No outcomes recorded yet — nothing to estimate from."
        assert self.point is not None and self.ci_low is not None and self.ci_high is not None
        body = f"{self.successes} of {self.trials} ({self.point:.0%}, 95% CI {self.ci_low:.0%}–{self.ci_high:.0%})"
        if not self.informative:
            return (
                body + " — too few outcomes to distinguish a good rule from a bad one. "
                "Reported as counts; the percentage is shown only alongside its interval."
            )
        return body

    def as_dict(self) -> dict[str, Any]:
        return {
            # Counts first, deliberately. Whatever consumes this reads them
            # before it reads the estimate.
            "successes": self.successes,
            "trials": self.trials,
            "point": self.point,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "ci_method": "Clopper-Pearson (exact)",
            "confidence_level": CONFIDENCE_LEVEL,
            "informative": self.informative,
            "describes": self.describe(),
        }


def estimate(successes: int, trials: int) -> Proportion:
    """A proportion with an exact interval.

    `trials == 0` returns nulls rather than 0.0. "No outcomes yet" and "no
    successes out of many" are different facts, and a zero would present the
    first as the second — which would make an untested rule look like a broken
    one.
    """
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError(f"{successes} successes out of {trials} trials is not a proportion")
    if trials == 0:
        return Proportion(successes=0, trials=0, point=None, ci_low=None, ci_high=None)

    test = stats.binomtest(successes, trials)
    ci = test.proportion_ci(confidence_level=CONFIDENCE_LEVEL, method="exact")
    return Proportion(
        successes=successes,
        trials=trials,
        point=successes / trials,
        ci_low=float(ci.low),
        ci_high=float(ci.high),
    )
