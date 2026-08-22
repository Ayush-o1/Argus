"""Is the increase real, or is it the size of the numbers?

The only statistical test the product had was the timeline's "N days above 2σ
of flagged volume", and it was invalid three ways (audit B-03/B-18): computed
over a random sample redrawn per request, over a mean that omitted empty days,
against a threshold inflated by the very outliers it was meant to find. Phase 0
removed the claim. This module is what replaces it.

## Why a Poisson rate ratio

The quantity is a count of events in a window — transfers, contacts, shipments.
Counts are not normally distributed, and at the volumes an analyst actually asks
about (nine events last week against four the week before) a normal
approximation is wrong in the direction that matters: it declares differences
significant that are ordinary Poisson variation.

So the comparison is done exactly. Conditioning on the total, the count in the
recent window is binomial, and the null "the rate did not change" becomes a
binomial proportion test with a known p. That gives a two-sided exact p-value,
and inverting a Clopper-Pearson interval on the proportion gives a confidence
interval for the rate ratio itself.

## What is deliberately not done

**No result is reported without its window and its baseline.** A rate ratio with
no denominator described is the same class of claim as "N days above 2σ" — it
sounds quantitative and cannot be checked. `RateComparison` carries both, and
the API cannot return one without them.

**Nothing is declared significant on its own.** `significant` is a function of
alpha, and alpha is stated in the payload. A caller comparing hundreds of series
must correct for multiplicity; `fdr_adjust` is provided for exactly that, and
the spatial module uses it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from scipy import stats

__all__ = [
    "DEFAULT_ALPHA",
    "RateComparison",
    "UnusualDay",
    "compare_rates",
    "fdr_adjust",
    "flag_unusual_days",
]

DEFAULT_ALPHA = 0.05


@dataclass(frozen=True)
class RateComparison:
    """A rate change, with everything needed to argue with it."""

    recent_count: int
    recent_days: float
    baseline_count: int
    baseline_days: float

    rate_ratio: float | None
    """Recent rate over baseline rate. None when neither window has an event —
    there is no ratio, which is a different statement from a ratio of 1."""

    ci_low: float | None
    ci_high: float | None
    p_value: float | None
    alpha: float

    recent_from: datetime | None = None
    recent_to: datetime | None = None
    baseline_from: datetime | None = None
    baseline_to: datetime | None = None

    @property
    def recent_rate(self) -> float | None:
        return self.recent_count / self.recent_days if self.recent_days > 0 else None

    @property
    def baseline_rate(self) -> float | None:
        return self.baseline_count / self.baseline_days if self.baseline_days > 0 else None

    @property
    def evaluable(self) -> bool:
        return self.p_value is not None

    @property
    def significant(self) -> bool:
        return self.p_value is not None and self.p_value < self.alpha

    @property
    def direction(self) -> str:
        if not self.evaluable or self.rate_ratio is None:
            return "unknown"
        if not self.significant:
            return "unchanged"
        return "increase" if self.rate_ratio > 1 else "decrease"

    def describe(self) -> str:
        """The finding in words, including the case where there is none."""
        if not self.evaluable:
            return (
                f"No events in either window ({self.recent_days:.0f} days against a "
                f"{self.baseline_days:.0f}-day baseline), so there is no rate to compare."
            )
        assert self.rate_ratio is not None
        window = (
            f"{self.recent_count} in the last {self.recent_days:.0f} days "
            f"against {self.baseline_count} in the {self.baseline_days:.0f} days before"
        )
        if not self.significant:
            return (
                f"{window} — no significant change (rate ratio {self.rate_ratio:.2f}, "
                f"95% CI {self._ci_text()}, p={self.p_value:.3f}). The difference is "
                f"within what this volume varies by anyway."
            )
        word = "higher" if self.rate_ratio > 1 else "lower"
        factor = self.rate_ratio if self.rate_ratio > 1 else (1 / self.rate_ratio)
        return (
            f"{window} — {factor:.1f}x {word} (rate ratio {self.rate_ratio:.2f}, "
            f"95% CI {self._ci_text()}, p={self.p_value:.3g})."
        )

    def _ci_text(self) -> str:
        low = "0" if self.ci_low is None else f"{self.ci_low:.2f}"
        high = "∞" if self.ci_high is None or math.isinf(self.ci_high) else f"{self.ci_high:.2f}"
        return f"{low}–{high}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "recent": {
                "count": self.recent_count,
                "days": self.recent_days,
                "rate_per_day": self.recent_rate,
                "from": self.recent_from.isoformat() if self.recent_from else None,
                "to": self.recent_to.isoformat() if self.recent_to else None,
            },
            "baseline": {
                "count": self.baseline_count,
                "days": self.baseline_days,
                "rate_per_day": self.baseline_rate,
                "from": self.baseline_from.isoformat() if self.baseline_from else None,
                "to": self.baseline_to.isoformat() if self.baseline_to else None,
            },
            "rate_ratio": self.rate_ratio,
            "confidence_interval": {
                "low": self.ci_low,
                "high": None if self.ci_high is not None and math.isinf(self.ci_high) else self.ci_high,
                "level": 0.95,
            },
            "p_value": self.p_value,
            "alpha": self.alpha,
            "evaluable": self.evaluable,
            "significant": self.significant,
            "direction": self.direction,
            "test": "Exact conditional Poisson rate ratio (binomial test on the split)",
            "summary": self.describe(),
        }


def compare_rates(
    recent_count: int,
    recent_days: float,
    baseline_count: int,
    baseline_days: float,
    *,
    alpha: float = DEFAULT_ALPHA,
    recent_from: datetime | None = None,
    recent_to: datetime | None = None,
    baseline_from: datetime | None = None,
    baseline_to: datetime | None = None,
) -> RateComparison:
    """Exact test of whether two Poisson rates differ.

    Conditioning on the total, `recent_count` is binomial over
    `recent_count + baseline_count` with null proportion
    `recent_days / (recent_days + baseline_days)`. Inverting a Clopper-Pearson
    interval on that proportion gives an interval for the rate ratio.
    """
    if recent_days <= 0 or baseline_days <= 0:
        raise ValueError("Both windows must have positive length.")

    total = recent_count + baseline_count
    base = RateComparison(
        recent_count=recent_count,
        recent_days=recent_days,
        baseline_count=baseline_count,
        baseline_days=baseline_days,
        rate_ratio=None,
        ci_low=None,
        ci_high=None,
        p_value=None,
        alpha=alpha,
        recent_from=recent_from,
        recent_to=recent_to,
        baseline_from=baseline_from,
        baseline_to=baseline_to,
    )
    if total == 0:
        # No events anywhere. Reported as not evaluable rather than as "no
        # change": a quiet world and an unchanged world are different findings.
        return base

    null_p = recent_days / (recent_days + baseline_days)
    test = stats.binomtest(recent_count, total, null_p, alternative="two-sided")
    ci = test.proportion_ci(confidence_level=0.95, method="exact")

    exposure = baseline_days / recent_days

    def ratio_from_p(p: float) -> float:
        if p >= 1.0:
            return math.inf
        return (p / (1.0 - p)) * exposure

    recent_rate = recent_count / recent_days
    baseline_rate = baseline_count / baseline_days
    rate_ratio = math.inf if baseline_rate == 0 else recent_rate / baseline_rate

    return RateComparison(
        recent_count=recent_count,
        recent_days=recent_days,
        baseline_count=baseline_count,
        baseline_days=baseline_days,
        rate_ratio=rate_ratio,
        ci_low=ratio_from_p(float(ci.low)),
        ci_high=ratio_from_p(float(ci.high)),
        p_value=float(test.pvalue),
        alpha=alpha,
        recent_from=recent_from,
        recent_to=recent_to,
        baseline_from=baseline_from,
        baseline_to=baseline_to,
    )


def fdr_adjust(p_values: list[float], alpha: float = DEFAULT_ALPHA) -> list[bool]:
    """Benjamini-Hochberg. Returns which hypotheses survive.

    Necessary wherever many series or many locations are tested at once. At
    alpha 0.05, testing 200 places produces about ten "significant" results when
    nothing at all is happening — and a map that highlights ten random cells is
    worse than a map that highlights none, because it looks like a finding.

    BH rather than Bonferroni: controlling the false discovery rate keeps some
    power at this number of tests, where controlling the family-wise error rate
    would leave almost none.
    """
    n = len(p_values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: p_values[i])
    keep = [False] * n
    largest_k = -1
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= alpha * rank / n:
            largest_k = rank
    if largest_k > 0:
        for rank, idx in enumerate(order, start=1):
            if rank <= largest_k:
                keep[idx] = True
    return keep


@dataclass(frozen=True)
class UnusualDay:
    index: int
    count: int
    expected: float
    """The rate implied by every *other* day in the series."""
    p_value: float
    significant: bool
    """After Benjamini-Hochberg across the whole series."""

    @property
    def direction(self) -> str:
        return "high" if self.count > self.expected else "low"


def flag_unusual_days(counts: list[int], alpha: float = DEFAULT_ALPHA) -> list[UnusualDay]:
    """Which days depart from the rest of the series, tested rather than eyeballed.

    Replaces "days above mean + 2σ", which the timeline rendered client-side and
    which was wrong in three ways beyond the sampling the audit already caught:

      1. **The mean and σ included the bursts.** Every unusual day inflated the
         threshold meant to catch it, so a series with several bursts hid all of
         them. The baseline here is leave-one-out: each day is tested against the
         rate implied by every other day.
      2. **It was not a test.** "Two standard deviations" has no null hypothesis
         and no error rate, and on count data it does not correspond to any
         particular false-positive rate — for a Poisson mean of 3, mean+2σ is
         6.5, which happens about 3% of the time; for a mean of 50 it is 64,
         which happens about 2%. The threshold drifted with the volume.
      3. **It was computed over whatever the user had filtered to**, so the
         "mean" changed when someone toggled a lane, and with it the set of days
         called bursts.

    A two-sided Poisson test gives a p-value with an actual null, and
    Benjamini-Hochberg across the series keeps 180 days of testing from
    producing nine bursts by arithmetic.
    """
    n = len(counts)
    if n < 3:
        return []

    total = sum(counts)
    raw: list[float] = []
    expectations: list[float] = []

    for count in counts:
        expected = (total - count) / (n - 1)
        expectations.append(expected)
        if expected <= 0:
            # Every other day was empty. A single non-zero day against an
            # all-zero baseline is not something a Poisson test can speak to.
            raw.append(1.0)
            continue
        lower = float(stats.poisson.cdf(count, expected))
        upper = float(stats.poisson.sf(count - 1, expected))
        raw.append(min(1.0, 2 * min(lower, upper)))

    keep = fdr_adjust(raw, alpha)
    return [
        UnusualDay(
            index=i,
            count=counts[i],
            expected=round(expectations[i], 3),
            p_value=raw[i],
            significant=keep[i],
        )
        for i in range(n)
    ]
