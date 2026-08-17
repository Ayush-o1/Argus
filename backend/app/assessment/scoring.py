"""Turning signal outcomes into an assessment — and, often, into a refusal.

The arithmetic is deliberately dull. What matters is the denominator: a score
is a share of the evidence weight that could actually be evaluated for that
subject, never a share of the whole model. A subject with one evaluable signal
that fired is not the same finding as a subject with every signal evaluable and
one that fired, and a single number cannot tell them apart — so the coverage
travels with the score everywhere, and below a floor there is no score at all.

The same shape as the matcher's evidence weight in Phase 4, for the same
reason: the alternative is to treat "no data" as "no problem".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.assessment.evidence import EvidenceBundle
from app.assessment.model import (
    BAND_ELEVATED,
    BAND_INSUFFICIENT,
    BAND_NOTABLE,
    BAND_ROUTINE,
    RiskModel,
)
from app.assessment.signals import (
    SIGNALS_BY_ID,
    SignalContext,
    SignalOutcome,
    build_context,
    evaluate_subject,
    signals_for,
)
from app.models.provenance import Credibility, Reliability


@dataclass(frozen=True)
class SignalContribution:
    signal_id: str
    title: str
    question: str
    family: str
    weight: float
    evaluable: bool
    magnitude: float | None
    contribution: float
    """weight × magnitude — the points this signal actually put on the score.
    Zero for a signal that was evaluated and came back negative, and zero for
    one that could not be evaluated. The two are told apart by `evaluable`,
    never by this number."""
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Assessment:
    """What ARGUS concluded about one subject, and how far it could see."""

    subject_ref: str
    subject_type: str
    band: str
    score: float | None
    """None when the band is `insufficient_evidence`. Not 0 — a subject ARGUS
    could not assess must be impossible to sort next to one it scored zero."""
    evidence_coverage: float
    evaluable_weight: float
    total_weight: float
    families_fired: tuple[str, ...]
    contributions: tuple[SignalContribution, ...]
    model_fingerprint: str
    model_version: str
    computed_at: datetime

    @property
    def reliability(self) -> Reliability:
        """Always F, and that is not a placeholder.

        Reliability is a property of the source, and the source here is ARGUS's
        own algorithm. Its precision has been measured against one synthetic
        world, which establishes that the code does what it claims on that
        world — not that it is reliable about anything real. Rating it higher
        would launder a measurement into a track record.
        """
        return Reliability.F

    @property
    def credibility(self) -> Credibility:
        """How well this particular claim is corroborated, counted in families.

        Two findings drawn from the same transaction feed are one voice. The
        provenance layer counts independence groups rather than observations
        for exactly this reason, and the same rule applies here.
        """
        if self.band == BAND_INSUFFICIENT:
            return Credibility.CANNOT_BE_JUDGED
        if len(self.families_fired) >= 2:
            return Credibility.PROBABLY_TRUE
        return Credibility.POSSIBLY_TRUE

    @property
    def fired(self) -> tuple[SignalContribution, ...]:
        return tuple(c for c in self.contributions if c.evaluable and (c.magnitude or 0) > 0)

    @property
    def unevaluable(self) -> tuple[SignalContribution, ...]:
        return tuple(c for c in self.contributions if not c.evaluable)

    def headline(self) -> str:
        """One sentence, stating the finding and its limits together.

        Written here rather than in the UI so every surface says the same
        thing: a score rendered without its coverage in one place and with it
        in another is the inconsistency that lets the flattering version travel.
        """
        if self.band == BAND_INSUFFICIENT:
            missing = len(self.unevaluable)
            return (
                f"ARGUS cannot assess this {self.subject_type.lower()}: "
                f"{missing} of {len(self.contributions)} signals had no evidence to work with "
                f"({self.evidence_coverage * 100:.0f}% of the model was evaluable). "
                f"This is not a low-risk finding."
            )
        if not self.fired:
            return (
                f"No signal fired across {self.evidence_coverage * 100:.0f}% of the model that "
                f"could be evaluated. ARGUS looked and found nothing."
            )
        names = ", ".join(c.title.lower() for c in self.fired)
        return (
            f"{len(self.fired)} of {len(self.contributions)} signals fired ({names}), over "
            f"{self.evidence_coverage * 100:.0f}% of the model that could be evaluated."
        )


def _band_for(score: float, coverage: float, model: RiskModel) -> str:
    """Coverage gates the band before the score is even consulted.

    A subject ARGUS could barely look at cannot reach the top band however
    strong the one thing it did see: a high score over a sliver of the model is
    a narrow finding, and presenting it as a strong one is the failure mode
    this ordering exists to prevent.
    """
    if coverage < model.min_coverage_for_score:
        return BAND_INSUFFICIENT
    if score >= model.elevated_score and coverage >= model.min_coverage_for_elevated:
        return BAND_ELEVATED
    if score >= model.notable_score:
        return BAND_NOTABLE
    return BAND_ROUTINE


def assess_subject(
    subject_ref: str, subject_type: str, ctx: SignalContext, computed_at: datetime
) -> Assessment:
    definitions = signals_for(subject_type)
    if not definitions:
        raise ValueError(f"no signals are defined for subject type {subject_type!r}")

    outcomes = evaluate_subject(subject_ref, subject_type, ctx)
    by_id: dict[str, SignalOutcome] = {o.signal_id: o for o in outcomes}

    contributions: list[SignalContribution] = []
    evaluable_weight = 0.0
    earned = 0.0
    families: set[str] = set()

    for definition in definitions:
        outcome = by_id[definition.signal_id]
        magnitude = outcome.magnitude if outcome.evaluable else None
        contribution = definition.weight * (magnitude or 0.0) if outcome.evaluable else 0.0
        if outcome.evaluable:
            evaluable_weight += definition.weight
            earned += contribution
            if (magnitude or 0.0) > 0:
                families.add(definition.family)
        contributions.append(
            SignalContribution(
                signal_id=definition.signal_id,
                title=definition.title,
                question=definition.question,
                family=definition.family,
                weight=definition.weight,
                evaluable=outcome.evaluable,
                magnitude=magnitude,
                contribution=round(contribution, 4),
                summary=outcome.summary,
                detail=outcome.detail,
            )
        )

    total_weight = sum(d.weight for d in definitions)
    coverage = evaluable_weight / total_weight if total_weight else 0.0

    # Evidence accumulated, against what one full-strength finding is worth —
    # not against every signal that happened to be evaluable. See
    # `RiskModel.reference_weight` for why the obvious denominator is wrong.
    # The reference is fixed rather than clamped to what happened to be
    # evaluable: a subject with only light signals available should top out
    # below 100, because the heavy evidence was never on the table for it.
    raw_score = (
        min(100.0, earned / ctx.model.reference_weight * 100) if evaluable_weight else 0.0
    )
    band = _band_for(raw_score, coverage, ctx.model)

    return Assessment(
        subject_ref=subject_ref,
        subject_type=subject_type,
        band=band,
        score=None if band == BAND_INSUFFICIENT else round(raw_score, 1),
        evidence_coverage=round(coverage, 4),
        evaluable_weight=round(evaluable_weight, 2),
        total_weight=round(total_weight, 2),
        families_fired=tuple(sorted(families)),
        contributions=tuple(contributions),
        model_fingerprint=ctx.model.fingerprint(),
        model_version=ctx.model.version,
        computed_at=computed_at,
    )


@dataclass
class AssessmentRun:
    assessments: list[Assessment]
    model: RiskModel
    computed_at: datetime
    cycles_found: int
    cycle_search_truncated: bool
    band_counts: dict[str, int]

    @property
    def fingerprint(self) -> str:
        return self.model.fingerprint()


def assess_all(
    bundle: EvidenceBundle, model: RiskModel, *, computed_at: datetime | None = None
) -> AssessmentRun:
    """Assess every subject in the bundle under one model, in one pass.

    Deterministic: given the same bundle and model, the output is identical
    apart from `computed_at`. The timeline learned this lesson the hard way in
    Phase 0 — a figure that moves when nothing changed cannot be reasoned
    about, and cannot be reviewed.
    """
    moment = computed_at or datetime.now(UTC)
    ctx = build_context(bundle, model)

    assessments = [
        assess_subject(ref, subject_type, ctx, moment)
        for ref, subject_type in sorted(bundle.subjects.items())
        if signals_for(subject_type)
    ]

    counts: dict[str, int] = {}
    for assessment in assessments:
        counts[assessment.band] = counts.get(assessment.band, 0) + 1

    return AssessmentRun(
        assessments=assessments,
        model=model,
        computed_at=moment,
        cycles_found=len(ctx.cycles),
        cycle_search_truncated=ctx.cycle_search_truncated,
        band_counts=counts,
    )


def signal_catalogue() -> list[dict[str, Any]]:
    """The registry, as the API publishes it.

    Exposed so an analyst can read what ARGUS looks for without reading the
    source. A model whose questions are secret cannot be argued with, and a
    finding nobody can argue with is not intelligence.
    """
    return [
        {
            "signal_id": s.signal_id,
            "title": s.title,
            "question": s.question,
            "family": s.family,
            "weight": s.weight,
            "subject_types": sorted(s.subject_types),
            "reads": sorted(s.reads),
            "rationale": s.rationale,
        }
        for s in SIGNALS_BY_ID.values()
    ]
