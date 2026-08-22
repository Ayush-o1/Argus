"""Ordering the queue, from factors ARGUS can actually measure.

Priority answers one question: *what should an analyst open first?* It is an
ordering, not a verdict. Nothing here claims an alert is important — only that,
on the evidence available, it has a better claim on the next ten minutes than
the one below it.

## The factor that is deliberately missing

The audit's suggested formula was:

    severity x confidence x asset criticality x corroboration x recency

**Asset criticality is not implemented, and not stubbed.** ARGUS has no asset
register, no sanctions list, no watchlist, no statement of what this deployment
cares about. Every value such a term could take would be invented here, and
because it multiplies, an invented constant would silently reorder the entire
queue while looking like a measurement. A term whose value is always 1.0 is
worse than no term: it survives review as "already handled" and acquires a real
value later from whoever notices it first.

If a deployment has an asset register, that is a source, and it enters through
ingestion and provenance like every other source — at which point this becomes
a measurable factor rather than a guess.

**Severity is also absent**, for the reason given in `rules.py`: it is a claim
about consequence, and ARGUS observes none.

## What remains, and why each is defensible

| Factor | Range | Measured from |
|---|---|---|
| Corroboration | 1.0 / 1.5 | How many independent ARGUS methods concur — declared by the rule |
| Confidence | 0..1 | Evidence coverage: how much of the model could be evaluated |
| Magnitude | 0..1 | The rule's own strength measure |
| Recency | 0..1 | Age of the underlying evidence against a stated half-life |

They combine multiplicatively because they are conjunctive: a finding that is
strong but rests on a tenth of the model is not "averagely" interesting, it is
uncertain, and averaging would let a high magnitude hide a low coverage. That
is the same reasoning `scoring.py` uses for evidence coverage in Phase 5.

## Bands are for display only

`priority_band` exists so a UI can group the queue without inventing its own
thresholds. The underlying float is what orders it, and the band boundaries are
stated here rather than in CSS.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

__all__ = [
    "CORROBORATION_MULTIPLE",
    "CORROBORATION_SINGLE",
    "PRIORITY_BANDS",
    "PriorityBreakdown",
    "compute_priority",
    "priority_band",
]

# A rule whose firing rests on two methods that share no inputs gets a 50% lift.
# Not a larger one: concurrence is meaningful, but two methods agreeing does not
# make a finding twice as worth reading as one strong method.
CORROBORATION_SINGLE = 1.0
CORROBORATION_MULTIPLE = 1.5

# Evidence loses claim on attention as it ages, but slowly — an investigation
# opened on last month's transfers is still an investigation. Half-life rather
# than a cliff, so nothing changes rank abruptly at a boundary.
RECENCY_HALF_LIFE = timedelta(days=30)

# Below this, recency stops decaying. Old evidence should sink, not vanish:
# an alert that decays to zero drops out of the ordering entirely, which is
# suppression by arithmetic rather than by decision.
RECENCY_FLOOR = 0.25

PRIORITY_BANDS: tuple[tuple[str, float], ...] = (
    ("high", 0.55),
    ("medium", 0.30),
    ("low", 0.0),
)


@dataclass(frozen=True)
class PriorityBreakdown:
    """The factors and the result, so the UI can show why something is at the
    top of the queue rather than asserting that it belongs there."""

    priority: float
    band: str
    corroboration: float
    confidence: float
    magnitude: float
    recency: float
    independent_methods: int
    evidence_age_days: float

    def as_dict(self) -> dict[str, object]:
        return {
            "priority": round(self.priority, 4),
            "band": self.band,
            "factors": {
                "corroboration": round(self.corroboration, 4),
                "confidence": round(self.confidence, 4),
                "magnitude": round(self.magnitude, 4),
                "recency": round(self.recency, 4),
            },
            "independent_methods": self.independent_methods,
            "evidence_age_days": round(self.evidence_age_days, 2),
            "asset_criticality": None,
            "asset_criticality_note": (
                "Not computed. ARGUS has no asset register, so any value here "
                "would be invented rather than measured."
            ),
        }


def recency_weight(evidence_at: datetime, now: datetime) -> tuple[float, float]:
    """Exponential decay on evidence age, floored. Returns (weight, age_days)."""
    if evidence_at.tzinfo is None:
        evidence_at = evidence_at.replace(tzinfo=UTC)
    age = now - evidence_at
    age_days = max(0.0, age.total_seconds() / 86400.0)
    half_lives = age_days / (RECENCY_HALF_LIFE.total_seconds() / 86400.0)
    decayed = math.pow(0.5, half_lives)
    return max(RECENCY_FLOOR, decayed), age_days


def priority_band(priority: float) -> str:
    for name, floor in PRIORITY_BANDS:
        if priority >= floor:
            return name
    return PRIORITY_BANDS[-1][0]


def compute_priority(
    *,
    magnitude: float,
    confidence: float,
    independent_methods: int,
    evidence_at: datetime,
    now: datetime | None = None,
) -> PriorityBreakdown:
    now = now or datetime.now(UTC)
    corroboration = CORROBORATION_MULTIPLE if independent_methods > 1 else CORROBORATION_SINGLE
    recency, age_days = recency_weight(evidence_at, now)

    magnitude = min(1.0, max(0.0, magnitude))
    confidence = min(1.0, max(0.0, confidence))

    # Bounded above by 1: the corroboration lift can push the product past 1 for
    # a strong, well-covered, recent, two-method finding, and a priority that
    # exceeds its own scale is a number nobody can interpret.
    raw = corroboration * confidence * magnitude * recency
    priority = min(1.0, raw)

    return PriorityBreakdown(
        priority=priority,
        band=priority_band(priority),
        corroboration=corroboration,
        confidence=confidence,
        magnitude=magnitude,
        recency=recency,
        independent_methods=independent_methods,
        evidence_age_days=age_days,
    )
