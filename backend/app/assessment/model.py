"""The model: every threshold in one place, fingerprinted.

Nothing in the assessor reads a bare constant. Every number that changes an
outcome lives on `RiskModel`, and the fingerprint is a SHA-256 over all of them
together with the signal registry — so a precision figure published today
cannot be silently re-attributed to a model whose thresholds moved next week.
The same discipline as the matcher's `MatchModel`, for the same reason: a
report about a model is meaningless without a way to say *which* model.

## Bands, and why they are not severities

The bands are `elevated`, `notable`, `routine` and `insufficient_evidence`.
They are deliberately not Critical/High/Medium/Low. A severity names how bad
something is; these name how much ARGUS found and how much of the model it was
able to apply. "Elevated" is a claim about evidence warranting review, not a
verdict about a person — and `insufficient_evidence` is a real band that
outranks any score, because a subject ARGUS knows almost nothing about must
never be rendered as low-risk.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from app.assessment.signals import SIGNALS

BAND_ELEVATED = "elevated"
BAND_NOTABLE = "notable"
BAND_ROUTINE = "routine"
BAND_INSUFFICIENT = "insufficient_evidence"

BANDS: tuple[str, ...] = (BAND_ELEVATED, BAND_NOTABLE, BAND_ROUTINE, BAND_INSUFFICIENT)

BAND_MEANING: dict[str, str] = {
    BAND_ELEVATED: (
        "Several independent signals fired, over enough of the model to be worth an analyst's "
        "time. This is a recommendation to look, not a conclusion about the subject."
    ),
    BAND_NOTABLE: (
        "Something fired, but either weakly or across a narrow slice of the evidence. Worth "
        "noting; not worth acting on alone."
    ),
    BAND_ROUTINE: (
        "Nothing reached the threshold where it would change what an analyst does. A weak "
        "signal may still have fired, and every signal's working is shown in full — this is a "
        "statement about the total, not a claim that nothing was found. It is a real finding "
        "either way: ARGUS looked."
    ),
    BAND_INSUFFICIENT: (
        "Too little of the model could be evaluated for a score to mean anything. ARGUS is not "
        "saying this subject is low risk; it is saying it does not know."
    ),
}


@dataclass(frozen=True)
class RiskModel:
    """Every parameter that can change an assessment.

    Defaults were set by running the detectors against the live graph and
    reading the resulting distributions, then choosing thresholds that sit in
    the gap between populations rather than at a value that maximised agreement
    with the generator's own labels. Tuning to the labels would have produced
    better-looking numbers and a worse model: the labels are the thing the
    assessor is not allowed to see.
    """

    version: str = "argus.assessment@v1"

    # Funds cycles
    cycle_retention_low: float = 0.85
    cycle_retention_high: float = 1.00
    cycle_window_days: int = 7
    cycle_min_hops: int = 3
    cycle_max_hops: int = 8
    cycle_hops_trigger: float = 3.0
    cycle_hops_full: float = 6.0
    cycle_minimum_magnitude: float = 0.5
    """A three-hop ring is already the whole pattern; length adds confidence
    rather than creating it, so the ramp starts halfway up instead of at zero."""

    # Bursts, shared by the transaction and communication signals
    burst_ratio_trigger: float = 5.0
    burst_ratio_full: float = 20.0
    burst_floor_expected: float = 0.5

    transaction_window_hours: int = 6
    transaction_min_events: int = 5
    transaction_min_peak: int = 8

    contact_window_hours: int = 48
    contact_min_events: int = 4
    contact_min_peak: int = 5

    # Structure
    directorship_trigger: float = 3.0
    directorship_full: float = 6.0

    # Shipments
    detour_trigger: float = 1.25
    detour_full: float = 2.50
    corridor_trigger: float = 0.005
    corridor_full: float = 0.001

    # Aggregation
    reference_weight: float = 5.0
    """The weighted evidence that constitutes one full-strength finding — set
    to the weight of the heaviest single signal.

    Risk evidence is disjunctive: a funds cycle is not made less alarming by
    the subject also having an unremarkable communication pattern. Dividing the
    accumulated evidence by *all* evaluable weight said otherwise, and the
    result was a queue in which one strong finding scored 31 while a
    meaningless offshore flag scored 10 — 849 subjects in the middle band at 6%
    precision. Normalising against a fixed reference instead makes the score
    read as "how much evidence, against what one strong finding is worth",
    which is both disjunctive and interpretable. Coverage carries the other
    half of the story and is reported separately, never folded in.
    """

    # Banding
    elevated_score: float = 60.0
    notable_score: float = 30.0
    min_coverage_for_score: float = 0.25
    """Below this share of the model, no score is published at all."""
    min_coverage_for_elevated: float = 0.40
    """A high score over a sliver of the model is a narrow finding, not a
    strong one. Reaching the top band requires both."""

    def fingerprint(self) -> str:
        """SHA-256 over the parameters *and* the signal registry.

        The registry is included because adding, removing or reweighting a
        signal changes what a score means just as surely as moving a threshold
        does, and a fingerprint that missed it would certify two different
        models as the same one.
        """
        payload = {
            "parameters": asdict(self),
            "signals": [
                {
                    "id": s.signal_id,
                    "weight": s.weight,
                    "family": s.family,
                    "subject_types": sorted(s.subject_types),
                    "reads": sorted(s.reads),
                }
                for s in sorted(SIGNALS, key=lambda s: s.signal_id)
            ],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def short_fingerprint(self) -> str:
        return self.fingerprint()[:12]

    @property
    def method(self) -> str:
        """The identifier stamped on every assertion this model produces."""
        return f"{self.version}+{self.short_fingerprint}"


def default_model() -> RiskModel:
    return RiskModel()
