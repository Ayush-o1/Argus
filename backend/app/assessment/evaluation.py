"""Measuring the assessor against ground truth — the only place labels appear.

The scenario generator knows which entities it planted. That knowledge is used
here, once, to answer "how good is this model?" — and nowhere else. The
separation is structural rather than a convention: the evidence projection in
`assessment_graph_repo.fetch_evidence` never selects a storyline, so there is
no code path from a label to a score. `test_assessment_isolation.py` asserts
that by inspecting the query text.

## What an honest report has to say

Three things this report states that a flattering one would not:

  1. **Detectability, per planted phenomenon.** Some storylines leave no
     admissible trace at all — the identity-overlap plant is expressed purely
     as a `SHARES_DEVICE` edge that exists nowhere else in the world, and the
     document-forgery plant sets a `flagged` boolean without making the
     documents inconsistent with each other. No signal can find those without
     reading the answer key. Recall against them is 0, it is reported as 0, and
     the reason is printed beside it.

  2. **Precision at the operating threshold, separately from ranking.** A model
     can rank every planted subject above every other and still have modest
     precision at a fixed band, because the band has to be set somewhere. Both
     are reported, because they answer different questions: "is the queue worth
     working?" and "is the model discriminating at all?"

  3. **Why the numbers flatter.** This is one synthetic world, whose planted
     behaviour is drawn from a small number of hand-written templates. A model
     measured against templates it was not tuned to is evidence of something;
     it is not evidence of field performance, and the report says so in the
     body rather than in a footnote.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.assessment.model import BAND_ELEVATED, BAND_INSUFFICIENT, BAND_NOTABLE, RiskModel
from app.assessment.scoring import Assessment

# Planted phenomena that no admissible signal can reach, and why. Stated in the
# report rather than quietly excluded from it: a recall figure computed only
# over the detectable subset would be an average over a denominator chosen to
# make the model look good.
UNDETECTABLE_BY_DESIGN: dict[str, str] = {
    "identity_overlap": (
        "The plant is expressed only as a SHARES_DEVICE edge, and no such edge exists anywhere "
        "in the baseline world. Every device has exactly one registered owner, so there is no "
        "co-ownership, no shared-handset traffic and no other trace. A detector keyed on the "
        "edge would score perfectly and discover nothing — it would be the answer key wearing a "
        "different name."
    ),
    "document_forgery_ring": (
        "The plant sets a `flagged` boolean and an `inconsistency_type` label on documents "
        "without making the documents actually inconsistent: issuer, subject and dates are left "
        "as generated. There is no observable discrepancy to detect, so ARGUS reports none."
    ),
}


@dataclass(frozen=True)
class LabelledSubject:
    """A subject the generator deliberately made anomalous.

    Two kinds, and conflating them would misreport the model in opposite
    directions:

      **Storyline membership** — the entity is part of a scripted scenario.

      **Injected anomaly** — the entity was given anomalous *behaviour* without
        being wrapped in a storyline. The shipment generator marks 53 routes
        anomalous; the storyline injector wraps 9 of them. A detector that
        finds the other 44 has found exactly what it was built to find, and
        scoring it against storyline membership alone would count all 44 as
        false positives. Both label sets are reported, and the headline
        precision uses their union, because both are answer keys.
    """

    subject_ref: str
    subject_type: str
    storyline_types: tuple[str, ...]
    injected_anomaly: bool = False


@dataclass
class BandMetrics:
    """Precision, recall and their raw counts at one band threshold."""

    band: str
    selected: int
    true_positives: int
    labelled_total: int

    @property
    def precision(self) -> float | None:
        """None, not 0, when nothing was selected — precision over an empty
        selection is undefined, and reporting 0 would read as "everything it
        picked was wrong" rather than "it picked nothing"."""
        return round(self.true_positives / self.selected, 4) if self.selected else None

    @property
    def recall(self) -> float | None:
        return round(self.true_positives / self.labelled_total, 4) if self.labelled_total else None


@dataclass
class StorylineOutcome:
    storyline_type: str
    planted_subjects: int
    """Only subjects of a type ARGUS assesses. A storyline that plants twelve
    transaction IDs and one account contributes one subject, and the report
    says so rather than counting entities it never had an opinion about."""
    reached_elevated: int
    reached_notable_or_better: int
    insufficient_evidence: int
    detectable: bool
    note: str = ""

    @property
    def recall_at_notable(self) -> float | None:
        if not self.planted_subjects:
            return None
        return round(self.reached_notable_or_better / self.planted_subjects, 4)


@dataclass
class EvaluationReport:
    model_version: str
    model_fingerprint: str
    generated_at: datetime

    subjects_assessed: int
    labelled_subjects: int
    labelled_by_storyline: int
    labelled_by_injected_anomaly_only: int
    band_counts: dict[str, int]

    elevated: BandMetrics
    notable_or_better: BandMetrics
    elevated_storyline_only: BandMetrics

    top_k: int
    labelled_in_top_k: int

    per_storyline: list[StorylineOutcome] = field(default_factory=list)
    per_signal: list[dict[str, Any]] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "model_fingerprint": self.model_fingerprint,
            "generated_at": self.generated_at.isoformat(),
            "subjects_assessed": self.subjects_assessed,
            "labelled_subjects": self.labelled_subjects,
            "labelled_by_storyline": self.labelled_by_storyline,
            "labelled_by_injected_anomaly_only": self.labelled_by_injected_anomaly_only,
            "band_counts": self.band_counts,
            "elevated": {
                "selected": self.elevated.selected,
                "true_positives": self.elevated.true_positives,
                "labelled_total": self.elevated.labelled_total,
                "precision": self.elevated.precision,
                "recall": self.elevated.recall,
            },
            # The stricter reading, kept beside the headline rather than
            # instead of it: measured only against scripted storylines, which
            # understates precision wherever the generator injected anomalous
            # behaviour without scripting a scenario around it.
            "elevated_storyline_only": {
                "selected": self.elevated_storyline_only.selected,
                "true_positives": self.elevated_storyline_only.true_positives,
                "labelled_total": self.elevated_storyline_only.labelled_total,
                "precision": self.elevated_storyline_only.precision,
                "recall": self.elevated_storyline_only.recall,
            },
            "notable_or_better": {
                "selected": self.notable_or_better.selected,
                "true_positives": self.notable_or_better.true_positives,
                "labelled_total": self.notable_or_better.labelled_total,
                "precision": self.notable_or_better.precision,
                "recall": self.notable_or_better.recall,
            },
            "ranking": {
                "top_k": self.top_k,
                "labelled_in_top_k": self.labelled_in_top_k,
                "share": (
                    round(self.labelled_in_top_k / self.top_k, 4) if self.top_k else None
                ),
            },
            "per_storyline": [
                {
                    "storyline_type": s.storyline_type,
                    "planted_subjects": s.planted_subjects,
                    "reached_elevated": s.reached_elevated,
                    "reached_notable_or_better": s.reached_notable_or_better,
                    "insufficient_evidence": s.insufficient_evidence,
                    "recall_at_notable": s.recall_at_notable,
                    "detectable": s.detectable,
                    "note": s.note,
                }
                for s in self.per_storyline
            ],
            "per_signal": self.per_signal,
            "caveats": self.caveats,
        }


def evaluate(
    assessments: list[Assessment],
    labels: list[LabelledSubject],
    model: RiskModel,
    *,
    top_k: int = 50,
    generated_at: datetime | None = None,
) -> EvaluationReport:
    moment = generated_at or datetime.now(UTC)
    by_ref = {a.subject_ref: a for a in assessments}
    labelled = {label.subject_ref: label for label in labels if label.subject_ref in by_ref}

    band_counts: dict[str, int] = {}
    for assessment in assessments:
        band_counts[assessment.band] = band_counts.get(assessment.band, 0) + 1

    elevated_refs = {a.subject_ref for a in assessments if a.band == BAND_ELEVATED}
    notable_refs = {a.subject_ref for a in assessments if a.band in (BAND_ELEVATED, BAND_NOTABLE)}
    storyline_refs = {ref for ref, label in labelled.items() if label.storyline_types}

    elevated = BandMetrics(
        band=BAND_ELEVATED,
        selected=len(elevated_refs),
        true_positives=len(elevated_refs & labelled.keys()),
        labelled_total=len(labelled),
    )
    notable = BandMetrics(
        band=BAND_NOTABLE,
        selected=len(notable_refs),
        true_positives=len(notable_refs & labelled.keys()),
        labelled_total=len(labelled),
    )
    elevated_storyline_only = BandMetrics(
        band=BAND_ELEVATED,
        selected=len(elevated_refs),
        true_positives=len(elevated_refs & storyline_refs),
        labelled_total=len(storyline_refs),
    )

    # Ranking is measured over subjects that have a score at all. Sorting the
    # unscored in alongside them — at either end — would make the figure a
    # statement about how many subjects lack evidence rather than about how
    # well the model discriminates.
    scored = sorted(
        (a for a in assessments if a.score is not None),
        key=lambda a: (-(a.score or 0), a.subject_ref),
    )
    head = scored[:top_k]
    labelled_in_top_k = sum(1 for a in head if a.subject_ref in labelled)

    per_storyline = _per_storyline(by_ref, labels, model)
    per_signal = _per_signal(assessments, labelled.keys())

    caveats = [
        "Measured against one synthetic world whose planted behaviour comes from seven "
        "hand-written templates. It shows the detectors find the structures they were designed "
        "to find in data they were not tuned against; it says nothing about field performance.",
        "Ground truth counts only planted entities of a type ARGUS assesses "
        "(Person, Organization, Account, Shipment). Planted transaction and communication IDs "
        "are excluded because ARGUS publishes no assessment for them.",
        "A subject banded `insufficient_evidence` is neither a true nor a false positive. It is "
        "counted separately, and it is a failure of collection rather than of the model.",
        "Headline precision counts both scripted storylines and anomalies the generator injected "
        "without scripting a scenario around them. `elevated_storyline_only` reports the "
        "stricter reading; where the two diverge, the difference is entities that really are "
        "anomalous and really were detected, and only the narrower label set calls them wrong.",
        "Scores saturate at the reference weight, so many findings tie at 100 and the top-k "
        "figure is a coarse instrument — it measures the elevated band, not a fine ranking "
        "within it.",
    ]
    if any(not s.detectable for s in per_storyline):
        caveats.append(
            "One or more planted phenomena leave no admissible trace. Their recall is 0 by "
            "construction and the reason is stated per storyline; suppressing them from this "
            "report would inflate every aggregate above."
        )

    return EvaluationReport(
        model_version=model.version,
        model_fingerprint=model.fingerprint(),
        generated_at=moment,
        subjects_assessed=len(assessments),
        labelled_subjects=len(labelled),
        labelled_by_storyline=len(storyline_refs),
        labelled_by_injected_anomaly_only=len(labelled) - len(storyline_refs),
        band_counts=band_counts,
        elevated=elevated,
        notable_or_better=notable,
        elevated_storyline_only=elevated_storyline_only,
        top_k=len(head),
        labelled_in_top_k=labelled_in_top_k,
        per_storyline=per_storyline,
        per_signal=per_signal,
        caveats=caveats,
    )


def _per_storyline(
    by_ref: dict[str, Assessment], labels: list[LabelledSubject], model: RiskModel
) -> list[StorylineOutcome]:
    grouped: dict[str, set[str]] = {}
    for label in labels:
        for storyline_type in label.storyline_types:
            grouped.setdefault(storyline_type, set()).add(label.subject_ref)

    # Storylines that plant nothing ARGUS assesses still belong in the report,
    # so a reader can see the whole population of planted phenomena rather than
    # only the ones that happen to appear.
    for storyline_type in UNDETECTABLE_BY_DESIGN:
        grouped.setdefault(storyline_type, set())

    outcomes: list[StorylineOutcome] = []
    for storyline_type in sorted(grouped):
        refs = [ref for ref in sorted(grouped[storyline_type]) if ref in by_ref]
        assessed = [by_ref[ref] for ref in refs]
        outcomes.append(
            StorylineOutcome(
                storyline_type=storyline_type,
                planted_subjects=len(assessed),
                reached_elevated=sum(1 for a in assessed if a.band == BAND_ELEVATED),
                reached_notable_or_better=sum(
                    1 for a in assessed if a.band in (BAND_ELEVATED, BAND_NOTABLE)
                ),
                insufficient_evidence=sum(1 for a in assessed if a.band == BAND_INSUFFICIENT),
                detectable=storyline_type not in UNDETECTABLE_BY_DESIGN,
                note=UNDETECTABLE_BY_DESIGN.get(storyline_type, ""),
            )
        )
    return outcomes


def _per_signal(assessments: list[Assessment], labelled: Any) -> list[dict[str, Any]]:
    """How often each signal fired, and how often it fired on a planted subject.

    A signal that fires on everything carries no information however sensible
    it sounds, and one that never fires is dead weight in the denominator of
    every coverage figure. Both are visible here and nowhere else.
    """
    stats: dict[str, dict[str, int]] = {}
    for assessment in assessments:
        for contribution in assessment.contributions:
            entry = stats.setdefault(
                contribution.signal_id,
                {"evaluable": 0, "not_evaluable": 0, "fired": 0, "fired_on_labelled": 0},
            )
            if not contribution.evaluable:
                entry["not_evaluable"] += 1
                continue
            entry["evaluable"] += 1
            if (contribution.magnitude or 0) > 0:
                entry["fired"] += 1
                if assessment.subject_ref in labelled:
                    entry["fired_on_labelled"] += 1

    rows = []
    for signal_id in sorted(stats):
        entry = stats[signal_id]
        rows.append(
            {
                "signal_id": signal_id,
                **entry,
                "fire_rate": (
                    round(entry["fired"] / entry["evaluable"], 4) if entry["evaluable"] else None
                ),
                "precision": (
                    round(entry["fired_on_labelled"] / entry["fired"], 4)
                    if entry["fired"]
                    else None
                ),
            }
        )
    return rows
