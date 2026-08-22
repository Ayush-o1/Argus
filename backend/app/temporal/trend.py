"""Direction, turning points, and whether a rhythm is real.

Three questions an analyst asks of a series that a bucket chart cannot answer:
is it going anywhere, did it change course, and is the weekly pattern I think I
see actually there.

## Why non-parametric tests

Event counts per day are small integers, frequently zero, and skewed. A linear
regression on them reports a slope with a standard error computed under
assumptions the data does not meet, and the p-value that comes out is not the
one it claims to be. Mann-Kendall asks only whether later values tend to exceed
earlier ones, which is the question actually being asked, and holds under any
distribution. Sen's slope gives the magnitude by the median of pairwise slopes,
so a single spike cannot set the trend.

## What a changepoint here is and is not

`find_changepoint` returns the split that maximises the difference in mean
between the two sides, together with a permutation p-value for that difference.
It is a description of where the series divides most sharply, tested against the
null that the ordering carries no information. It is not a claim that something
happened on that date: the series knows nothing about causes, and a changepoint
coinciding with a collection change looks identical to one coinciding with a
real change in the world.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats

from app.temporal.significance import DEFAULT_ALPHA

__all__ = [
    "Changepoint",
    "Seasonality",
    "TrendResult",
    "find_changepoint",
    "mann_kendall",
    "weekly_seasonality",
]

# Below this many buckets no trend statement is made. Mann-Kendall's normal
# approximation is unreliable on very short series, and a trend fitted to five
# days is a description of five days.
MIN_TREND_POINTS = 12


@dataclass(frozen=True)
class TrendResult:
    points: int
    statistic: float | None
    """Mann-Kendall S. Positive means later values tend to be larger."""
    z_score: float | None
    p_value: float | None
    slope_per_day: float | None
    """Sen's slope: the median of all pairwise slopes."""
    alpha: float
    evaluable: bool
    reason: str | None = None

    @property
    def significant(self) -> bool:
        return self.p_value is not None and self.p_value < self.alpha

    @property
    def direction(self) -> str:
        if not self.evaluable or not self.significant or self.slope_per_day is None:
            return "flat"
        return "rising" if self.slope_per_day > 0 else "falling"

    def describe(self) -> str:
        if not self.evaluable:
            return self.reason or "Not enough data to test for a trend."
        if not self.significant:
            return (
                f"No trend over {self.points} days (Mann-Kendall p={self.p_value:.3f}). "
                "The series moves, but not in a consistent direction."
            )
        assert self.slope_per_day is not None
        per_week = self.slope_per_day * 7
        word = "rising" if per_week > 0 else "falling"
        return (
            f"{word.capitalize()} over {self.points} days — about "
            f"{abs(per_week):.2f} events per week (Mann-Kendall p={self.p_value:.3g})."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "points": self.points,
            "statistic": self.statistic,
            "z_score": self.z_score,
            "p_value": self.p_value,
            "slope_per_day": self.slope_per_day,
            "slope_per_week": None if self.slope_per_day is None else self.slope_per_day * 7,
            "alpha": self.alpha,
            "evaluable": self.evaluable,
            "significant": self.significant,
            "direction": self.direction,
            "test": "Mann-Kendall with Sen's slope",
            "summary": self.describe(),
        }


def mann_kendall(values: list[float], alpha: float = DEFAULT_ALPHA) -> TrendResult:
    n = len(values)
    if n < MIN_TREND_POINTS:
        return TrendResult(
            points=n, statistic=None, z_score=None, p_value=None, slope_per_day=None,
            alpha=alpha, evaluable=False,
            reason=f"A trend needs at least {MIN_TREND_POINTS} buckets; this series has {n}.",
        )

    x = np.asarray(values, dtype=float)

    # S = sum of sign(x_j - x_i) over all i < j.
    diff = np.sign(x[None, :] - x[:, None])
    s = float(np.triu(diff, k=1).sum())

    # Variance with the correction for ties. Count data ties constantly — a
    # series of mostly zeroes is nearly all ties — and the uncorrected variance
    # would be far too large, hiding real trends.
    _, counts = np.unique(x, return_counts=True)
    tie_term = float(sum(c * (c - 1) * (2 * c + 5) for c in counts))
    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0

    if var_s <= 0:
        return TrendResult(
            points=n, statistic=s, z_score=None, p_value=None, slope_per_day=None,
            alpha=alpha, evaluable=False,
            reason="Every value in the series is identical; there is nothing to trend.",
        )

    # Continuity correction: S moves in steps of 2, so the normal approximation
    # is applied to S-1 or S+1 rather than to S.
    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0
    # Survival function rather than 1 - cdf: for a strong trend the cdf rounds
    # to 1.0 and the p-value underflows to exactly 0, which is a number no test
    # can produce and which reads as certainty.
    p = float(2 * stats.norm.sf(abs(z)))

    # Sen's slope: median of pairwise slopes. Robust to a single spike in a way
    # least squares is not.
    i, j = np.triu_indices(n, k=1)
    slopes = (x[j] - x[i]) / (j - i)
    slope = float(np.median(slopes))

    return TrendResult(
        points=n, statistic=s, z_score=z, p_value=p, slope_per_day=slope,
        alpha=alpha, evaluable=True,
    )


@dataclass(frozen=True)
class Changepoint:
    index: int | None
    p_value: float | None
    before_mean: float | None
    after_mean: float | None
    evaluable: bool
    alpha: float
    reason: str | None = None

    @property
    def significant(self) -> bool:
        return self.p_value is not None and self.p_value < self.alpha

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "p_value": self.p_value,
            "before_mean": self.before_mean,
            "after_mean": self.after_mean,
            "evaluable": self.evaluable,
            "significant": self.significant,
            "alpha": self.alpha,
            "test": "Maximum mean-shift split, permutation-tested",
            "note": (
                "Where the series divides most sharply. It says nothing about what "
                "caused the division: a change in collection looks identical to a "
                "change in the world."
            ),
            "reason": self.reason,
        }


def find_changepoint(
    values: list[float], alpha: float = DEFAULT_ALPHA, permutations: int = 2000, seed: int = 42
) -> Changepoint:
    """The sharpest split in the series, with a permutation p-value.

    Deterministic: the permutation seed is fixed, so two analysts running the
    same query get the same answer. A randomised test that changes between runs
    is the defect the timeline's `rand()` sampling had.
    """
    n = len(values)
    if n < MIN_TREND_POINTS:
        return Changepoint(
            index=None, p_value=None, before_mean=None, after_mean=None,
            evaluable=False, alpha=alpha,
            reason=f"A changepoint needs at least {MIN_TREND_POINTS} buckets; this series has {n}.",
        )

    x = np.asarray(values, dtype=float)
    if float(x.std()) == 0.0:
        return Changepoint(
            index=None, p_value=None, before_mean=None, after_mean=None,
            evaluable=False, alpha=alpha,
            reason="Every value in the series is identical; there is no split to find.",
        )

    # Leave at least three points either side, so a "changepoint" cannot be one
    # outlier at an end.
    margin = 3

    def best_split(arr: np.ndarray) -> tuple[int, float]:
        cum = np.cumsum(arr)
        total = cum[-1]
        best_k, best_stat = margin, -1.0
        for k in range(margin, n - margin):
            left_mean = cum[k - 1] / k
            right_mean = (total - cum[k - 1]) / (n - k)
            stat = abs(left_mean - right_mean) * math.sqrt(k * (n - k) / n)
            if stat > best_stat:
                best_stat, best_k = stat, k
        return best_k, best_stat

    k, observed = best_split(x)

    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(permutations):
        _, stat = best_split(rng.permutation(x))
        if stat >= observed:
            exceed += 1
    # +1 in both parts: the observed arrangement is itself one of the possible
    # orderings, and omitting it can produce a p-value of exactly zero.
    p = (exceed + 1) / (permutations + 1)

    return Changepoint(
        index=k,
        p_value=float(p),
        before_mean=float(x[:k].mean()),
        after_mean=float(x[k:].mean()),
        evaluable=True,
        alpha=alpha,
    )


@dataclass(frozen=True)
class Seasonality:
    p_value: float | None
    statistic: float | None
    busiest_day: str | None
    quietest_day: str | None
    per_day: dict[str, int]
    evaluable: bool
    alpha: float
    reason: str | None = None

    @property
    def significant(self) -> bool:
        return self.p_value is not None and self.p_value < self.alpha

    def describe(self) -> str:
        if not self.evaluable:
            return self.reason or "Not enough data to test for a weekly rhythm."
        if not self.significant:
            return (
                f"No weekly pattern (chi-square p={self.p_value:.3f}). Activity is "
                "spread across the week about as evenly as chance would put it."
            )
        return (
            f"Activity is not spread evenly across the week (chi-square "
            f"p={self.p_value:.3g}): heaviest on {self.busiest_day}, lightest on "
            f"{self.quietest_day}."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "p_value": self.p_value,
            "statistic": self.statistic,
            "busiest_day": self.busiest_day,
            "quietest_day": self.quietest_day,
            "per_day": self.per_day,
            "evaluable": self.evaluable,
            "significant": self.significant,
            "alpha": self.alpha,
            "test": "Chi-square goodness-of-fit against an even week",
            "summary": self.describe(),
        }


DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# Chi-square needs a reasonable expected count per cell. Below five per weekday
# the approximation is poor and the p-value is not the one it claims to be.
MIN_PER_WEEKDAY = 5


def weekly_seasonality(counts_by_weekday: dict[int, int], alpha: float = DEFAULT_ALPHA) -> Seasonality:
    """Whether activity concentrates on particular days of the week."""
    observed = [counts_by_weekday.get(d, 0) for d in range(7)]
    per_day = {DAY_NAMES[d]: observed[d] for d in range(7)}
    total = sum(observed)

    if total < MIN_PER_WEEKDAY * 7:
        return Seasonality(
            p_value=None, statistic=None, busiest_day=None, quietest_day=None,
            per_day=per_day, evaluable=False, alpha=alpha,
            reason=(
                f"A weekly test needs about {MIN_PER_WEEKDAY * 7} events to be "
                f"meaningful; this series has {total}."
            ),
        )

    result = stats.chisquare(observed)
    busiest = DAY_NAMES[int(np.argmax(observed))]
    quietest = DAY_NAMES[int(np.argmin(observed))]
    return Seasonality(
        p_value=float(result.pvalue),
        statistic=float(result.statistic),
        busiest_day=busiest,
        quietest_day=quietest,
        per_day=per_day,
        evaluable=True,
        alpha=alpha,
    )
