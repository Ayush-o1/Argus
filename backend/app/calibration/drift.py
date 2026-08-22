"""Whether the assessor's output has shifted between runs, and whether that means anything.

## The measurement

Each completed assessment run records how many subjects landed in each band.
Comparing two runs' distributions is a chi-square test of homogeneity on the
2 x k contingency table — the standard test for "did these two samples come from
the same distribution", and the same family of test Phase 8 uses for weekly
seasonality.

## The thing this cannot tell you, stated because it is the obvious mistake

A significant result says the distribution changed. It does **not** say the model
drifted. Three things produce the same signal and this test cannot separate them:

  - the model changed (a new version, or retuned weights);
  - the population changed (subjects were added, merged, or resolved together);
  - the evidence changed (a feed came back after an outage, so subjects that
    were `insufficient_evidence` became assessable).

The third is the common one in this system and the least like drift: it is the
assessor working correctly on better input. So the report carries the model
fingerprints of both runs, and says plainly that a change across *different*
fingerprints is expected rather than alarming — the interesting case is a shift
between two runs of the **same** fingerprint, which is the one that cannot be
explained by the model having been edited.

## Why not a distance metric

Population stability index and similar single numbers are common here and are
worse: they compress the comparison to a figure with a folklore threshold (0.1
"small", 0.25 "large") and no null distribution behind it. A test with a stated
null and a p-value can at least be wrong in a way somebody can check.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scipy import stats

__all__ = ["BANDS", "DriftComparison", "compare_runs"]

BANDS = ("elevated", "notable", "routine", "insufficient_evidence")

DEFAULT_ALPHA = 0.05


@dataclass(frozen=True)
class DriftComparison:
    earlier_run_id: int
    later_run_id: int
    earlier_fingerprint: str
    later_fingerprint: str
    earlier_counts: dict[str, int]
    later_counts: dict[str, int]
    p_value: float | None
    alpha: float
    evaluable: bool
    reason: str | None = None

    @property
    def same_model(self) -> bool:
        return self.earlier_fingerprint == self.later_fingerprint

    @property
    def shifted(self) -> bool:
        return self.evaluable and self.p_value is not None and self.p_value < self.alpha

    @property
    def shares(self) -> dict[str, dict[str, float | None]]:
        def share(counts: dict[str, int]) -> dict[str, float | None]:
            total = sum(counts.values())
            return {b: (counts.get(b, 0) / total if total else None) for b in BANDS}

        return {"earlier": share(self.earlier_counts), "later": share(self.later_counts)}

    def describe(self) -> str:
        if not self.evaluable:
            return self.reason or "Not evaluable."
        assert self.p_value is not None
        if not self.shifted:
            return (
                f"No detectable shift between runs {self.earlier_run_id} and "
                f"{self.later_run_id} (p = {self.p_value:.3f})."
            )
        if not self.same_model:
            return (
                f"The band distribution changed between runs {self.earlier_run_id} and "
                f"{self.later_run_id} (p = {self.p_value:.3g}), but the two runs used "
                f"different models. A different model producing a different distribution "
                f"is expected, and this is not evidence of drift."
            )
        return (
            f"The band distribution changed between runs {self.earlier_run_id} and "
            f"{self.later_run_id} (p = {self.p_value:.3g}) with no change of model. "
            f"Either the population or the evidence available about it moved; the "
            f"assessor itself did not."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "earlier_run_id": self.earlier_run_id,
            "later_run_id": self.later_run_id,
            "earlier_fingerprint": self.earlier_fingerprint,
            "later_fingerprint": self.later_fingerprint,
            "same_model": self.same_model,
            "earlier_counts": self.earlier_counts,
            "later_counts": self.later_counts,
            "shares": self.shares,
            "p_value": self.p_value,
            "alpha": self.alpha,
            "evaluable": self.evaluable,
            "shifted": self.shifted,
            "describes": self.describe(),
            "test": "Chi-square test of homogeneity over the band distribution",
            "cannot_distinguish": (
                "A shift in output has three possible causes this test cannot separate: "
                "the model changed, the population changed, or the evidence available "
                "changed. Only the first is drift, and the fingerprints are published "
                "beside the result so a reader can rule it in or out."
            ),
        }


def compare_runs(earlier: dict[str, Any], later: dict[str, Any], alpha: float = DEFAULT_ALPHA) -> DriftComparison:
    """Compare two rows of `assessment_run_bands`."""
    earlier_counts = {b: int(earlier.get(f"{_col(b)}", 0) or 0) for b in BANDS}
    later_counts = {b: int(later.get(f"{_col(b)}", 0) or 0) for b in BANDS}

    base = DriftComparison(
        earlier_run_id=int(earlier["run_id"]),
        later_run_id=int(later["run_id"]),
        earlier_fingerprint=earlier["model_fingerprint"],
        later_fingerprint=later["model_fingerprint"],
        earlier_counts=earlier_counts,
        later_counts=later_counts,
        p_value=None,
        alpha=alpha,
        evaluable=False,
    )

    table = [
        [earlier_counts[b] for b in BANDS],
        [later_counts[b] for b in BANDS],
    ]
    # Drop bands empty in both runs: a column of zeros contributes nothing and
    # makes the expected frequencies undefined.
    keep = [i for i in range(len(BANDS)) if table[0][i] + table[1][i] > 0]
    if len(keep) < 2 or sum(table[0]) == 0 or sum(table[1]) == 0:
        return DriftComparison(
            **{**base.__dict__, "reason": "One run assessed nobody, or every subject fell in one band."}
        )

    trimmed = [[row[i] for i in keep] for row in table]
    result = stats.chi2_contingency(trimmed)
    return DriftComparison(**{**base.__dict__, "p_value": float(result.pvalue), "evaluable": True})


def _col(band: str) -> str:
    """Band name to the column that counts it in `assessment_run_bands`."""
    return "insufficient_count" if band == "insufficient_evidence" else f"{band}_count"
