"""The match model: attribute rules, weights, thresholds, and banding.

The model is data, not code paths. Every attribute ARGUS compares is one
`AttributeRule`, and the whole configuration is fingerprinted, so a candidate
recorded last month carries the exact parameters that produced it. Changing a
weight changes the fingerprint, which means an evaluation report can never be
quietly attributed to a model that no longer exists.

Three properties this module is built to guarantee:

  1. **A score is never separated from how much evidence produced it.** Every
     result carries `evidence_weight` — the share of the model's total weight
     that was actually comparable. 0.94 from two attributes out of nine is a
     different claim from 0.94 from eight, and the UI shows both numbers.
  2. **Disagreement on an identifying attribute overrules similarity.** Two
     people with the same name in the same city and different dates of birth
     are two people. No amount of soft agreement outvotes that.
  3. **Automatic action requires more than a high score.** See `BAND_AUTO`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.resolution import similarity
from app.resolution.profile import EntityProfile

Verdict = Literal["agree", "partial", "disagree", "not_comparable"]
Band = Literal["auto", "review", "insufficient", "reject"]

BAND_AUTO: Band = "auto"
BAND_REVIEW: Band = "review"
BAND_INSUFFICIENT: Band = "insufficient"
BAND_REJECT: Band = "reject"

# A comparison at or above this is agreement; at or below the lower bound is
# disagreement. The gap between them is `partial` — real but not decisive, and
# never counted as either in the reasons shown to an analyst.
AGREE_AT = 0.85
DISAGREE_AT = 0.20


def _person_name(left: Any, right: Any) -> float | None:
    return similarity.name_similarity(left, right, kind="person")


def _org_name(left: Any, right: Any) -> float | None:
    return similarity.name_similarity(left, right, kind="organization")


COMPARATORS: dict[str, Callable[[Any, Any], float | None]] = {
    "person_name": _person_name,
    "org_name": _org_name,
    "exact": similarity.exact_similarity,
    "identifier": similarity.identifier_similarity,
    "phone": similarity.phone_similarity,
    "date": similarity.date_similarity,
    "set": similarity.set_similarity,
    "geo": similarity.geo_similarity,
}


@dataclass(frozen=True)
class AttributeRule:
    key: str
    label: str
    comparator: str
    weight: float
    # A rule whose *disagreement* ends the matter. Used only for attributes
    # where two different values genuinely mean two different entities, not
    # merely two differently-recorded ones.
    disqualifying: bool = False
    # A rule whose *exact* agreement is strong enough to be a precondition for
    # acting without a human. Note "exact": a partial score never qualifies,
    # however close.
    strong_identifier: bool = False


@dataclass(frozen=True)
class AttributeComparison:
    key: str
    label: str
    left: Any
    right: Any
    score: float | None
    weight: float
    verdict: Verdict

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "left": self.left,
            "right": self.right,
            "score": self.score,
            "weight": self.weight,
            "verdict": self.verdict,
        }


@dataclass(frozen=True)
class MatchResult:
    left_ref: str
    right_ref: str
    entity_type: str
    # Weighted mean over *comparable* attributes only. None when nothing at all
    # could be compared, which is a different statement from zero.
    score: float | None
    # Comparable weight / total weight. The denominator for `score`.
    evidence_weight: float
    comparisons: list[AttributeComparison]
    band: Band
    band_reason: str
    model_version: str
    model_fingerprint: str
    blocking_keys: list[str] = field(default_factory=list)

    @property
    def agreements(self) -> list[AttributeComparison]:
        return [c for c in self.comparisons if c.verdict == "agree"]

    @property
    def disagreements(self) -> list[AttributeComparison]:
        return [c for c in self.comparisons if c.verdict == "disagree"]

    @property
    def not_comparable(self) -> list[AttributeComparison]:
        return [c for c in self.comparisons if c.verdict == "not_comparable"]


_PERSON_RULES = (
    AttributeRule("name", "Name", "person_name", 3.0),
    AttributeRule("aliases", "Known aliases", "set", 1.0),
    # Two different dates of birth are two different people far more often than
    # they are one person recorded twice. Disqualifying — but the comparator
    # already forgives day/month transposition, which is the error that would
    # otherwise make this rule too blunt.
    AttributeRule("date_of_birth", "Date of birth", "date", 3.0, disqualifying=True),
    # Strong but not disqualifying: numbers are shared within a household or a
    # business and reassigned between people, so agreement is good evidence
    # while disagreement is weak evidence.
    AttributeRule("phone", "Phone", "phone", 3.0, strong_identifier=True),
    AttributeRule("nationality", "Nationality", "exact", 0.75),
    AttributeRule("occupation", "Occupation", "exact", 0.5),
    AttributeRule("city", "City", "exact", 0.5),
    AttributeRule("state", "State or province", "exact", 0.5),
    AttributeRule("country", "Country", "exact", 0.75),
    # Deliberately not disqualifying. Gender is recorded inconsistently across
    # systems, is sometimes absent, and can legitimately differ between two
    # records of the same person. Treating a mismatch as proof of difference
    # would produce a matcher that fails a real population.
    AttributeRule("gender", "Gender", "exact", 0.5),
    AttributeRule("coordinates", "Location", "geo", 0.5),
)

_ORGANIZATION_RULES = (
    AttributeRule("name", "Name", "org_name", 3.0),
    AttributeRule("registration_date", "Registered", "date", 2.0, disqualifying=True),
    AttributeRule("industry", "Industry", "exact", 0.75),
    AttributeRule("org_type", "Legal form", "exact", 0.5),
    AttributeRule("city", "Registered city", "exact", 0.75),
    AttributeRule("state", "State or province", "exact", 0.5),
    # Not disqualifying: subsidiaries and re-domiciled companies legitimately
    # share a name across countries, and deciding between "same group" and
    # "same company" is an analyst's judgement, not a comparator's.
    AttributeRule("country", "Country", "exact", 1.0),
    AttributeRule("coordinates", "Location", "geo", 0.5),
)

_VEHICLE_RULES = (
    AttributeRule("plate", "Registration plate", "identifier", 5.0,
                  disqualifying=True, strong_identifier=True),
    AttributeRule("make", "Make", "exact", 0.5),
    AttributeRule("model", "Model", "exact", 0.5),
    AttributeRule("vehicle_type", "Type", "exact", 0.5),
    AttributeRule("color", "Colour", "exact", 0.25),
)

_DEVICE_RULES = (
    AttributeRule("imei", "IMEI", "identifier", 5.0, disqualifying=True, strong_identifier=True),
    AttributeRule("mac", "MAC address", "identifier", 4.0,
                  disqualifying=True, strong_identifier=True),
    AttributeRule("carrier", "Carrier", "exact", 0.5),
    AttributeRule("device_type", "Type", "exact", 0.5),
)

RULES: dict[str, tuple[AttributeRule, ...]] = {
    "Person": _PERSON_RULES,
    "Organization": _ORGANIZATION_RULES,
    "Vehicle": _VEHICLE_RULES,
    "Device": _DEVICE_RULES,
}


@dataclass(frozen=True)
class MatchModel:
    """Thresholds and their justification.

    `auto_score` alone does not authorise a merge. The full condition is in
    `_band`, and the extra requirements exist because a high score computed
    from two soft attributes is exactly the situation where an automatic merge
    is both most likely and most damaging.
    """

    version: str = "argus.matcher@v1"
    auto_score: float = 0.92
    review_score: float = 0.72
    # Below this share of comparable evidence, ARGUS declines to queue the pair
    # at all. Without it the review queue fills with coincidences — two records
    # agreeing on the one attribute they both happen to have — and a queue an
    # analyst cannot finish is a queue that gets ignored.
    min_evidence_for_review: float = 0.25
    min_evidence_for_auto: float = 0.45

    def fingerprint(self) -> str:
        """Hash over thresholds *and* every rule, so any parameter change is
        visible in the record of every candidate scored under it."""
        payload = {
            "version": self.version,
            "auto_score": self.auto_score,
            "review_score": self.review_score,
            "min_evidence_for_review": self.min_evidence_for_review,
            "min_evidence_for_auto": self.min_evidence_for_auto,
            "rules": {
                entity_type: [
                    [r.key, r.comparator, r.weight, r.disqualifying, r.strong_identifier]
                    for r in rules
                ]
                for entity_type, rules in sorted(RULES.items())
            },
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


DEFAULT_MODEL = MatchModel()


def _verdict(score: float | None) -> Verdict:
    if score is None:
        return "not_comparable"
    if score >= AGREE_AT:
        return "agree"
    if score <= DISAGREE_AT:
        return "disagree"
    return "partial"


def _value_for(profile: EntityProfile, key: str) -> Any:
    if key == "coordinates":
        return profile.coordinates
    return profile.get(key)


def compare(
    left: EntityProfile,
    right: EntityProfile,
    *,
    model: MatchModel = DEFAULT_MODEL,
    blocking_keys: list[str] | None = None,
) -> MatchResult:
    """Score one pair. Pure — no I/O, no clock, no randomness.

    Purity is what makes a merge defensible: the same two records produce the
    same score and the same explanation every time it is asked for, including
    from a test, from the evaluation harness, and from an analyst re-opening
    the decision a year later.
    """
    if left.entity_type != right.entity_type:
        raise ValueError(
            f"cannot compare {left.entity_type} with {right.entity_type} — "
            "entity resolution is within a type, never across one"
        )

    rules = RULES.get(left.entity_type)
    if rules is None:
        raise ValueError(f"no match rules defined for entity type {left.entity_type!r}")

    comparisons: list[AttributeComparison] = []
    weighted_total = 0.0
    comparable_weight = 0.0
    total_weight = 0.0

    for rule in rules:
        total_weight += rule.weight
        comparator = COMPARATORS[rule.comparator]
        score = comparator(_value_for(left, rule.key), _value_for(right, rule.key))
        comparisons.append(
            AttributeComparison(
                key=rule.key,
                label=rule.label,
                left=_value_for(left, rule.key),
                right=_value_for(right, rule.key),
                score=score,
                weight=rule.weight,
                verdict=_verdict(score),
            )
        )
        if score is not None:
            comparable_weight += rule.weight
            weighted_total += rule.weight * score

    overall = weighted_total / comparable_weight if comparable_weight else None
    evidence_weight = comparable_weight / total_weight if total_weight else 0.0

    band, reason = _band(model, rules, comparisons, overall, evidence_weight)

    return MatchResult(
        left_ref=left.ref,
        right_ref=right.ref,
        entity_type=left.entity_type,
        score=overall,
        evidence_weight=evidence_weight,
        comparisons=comparisons,
        band=band,
        band_reason=reason,
        model_version=model.version,
        model_fingerprint=model.fingerprint(),
        blocking_keys=sorted(blocking_keys or []),
    )


def _band(
    model: MatchModel,
    rules: tuple[AttributeRule, ...],
    comparisons: list[AttributeComparison],
    overall: float | None,
    evidence_weight: float,
) -> tuple[Band, str]:
    """Decide the band, and say why in a sentence an analyst can act on.

    The reason is stored with the candidate and shown verbatim. A band with no
    stated reason is an unexplained decision, and this phase exists partly to
    stop ARGUS making those.
    """
    by_key = {c.key: c for c in comparisons}

    # 1. A disqualifying disagreement ends it, whatever the score.
    for rule in rules:
        if not rule.disqualifying:
            continue
        comparison = by_key.get(rule.key)
        if comparison is not None and comparison.verdict == "disagree":
            return BAND_REJECT, (
                f"{rule.label} disagrees ({comparison.left!r} vs {comparison.right!r}). "
                "Two different values here mean two different records, regardless of how "
                "much else agrees."
            )

    if overall is None:
        return BAND_INSUFFICIENT, (
            "No attribute could be compared — the two records have no populated "
            "attribute in common."
        )

    # 2. Too little to say anything about, however well what little there is agrees.
    if evidence_weight < model.min_evidence_for_review:
        return BAND_INSUFFICIENT, (
            f"Only {evidence_weight:.0%} of the model's evidence was comparable — below the "
            f"{model.min_evidence_for_review:.0%} needed to put a pair in front of an analyst. "
            "A high score from one shared attribute is a coincidence, not a lead."
        )

    if overall < model.review_score:
        return BAND_REJECT, (
            f"Scored {overall:.2f}, below the {model.review_score:.2f} review threshold."
        )

    # 3. Automatic action needs more than a high score.
    if overall >= model.auto_score:
        strong = [
            by_key[rule.key]
            for rule in rules
            if rule.strong_identifier
            and by_key.get(rule.key) is not None
            and by_key[rule.key].score == 1.0
        ]
        disagreements = [c for c in comparisons if c.verdict == "disagree"]
        if not strong:
            return BAND_REVIEW, (
                f"Scored {overall:.2f}, but no identifier matched exactly. Soft attributes "
                "agreeing — even all of them — is similarity, not identity, so a person "
                "decides."
            )
        if disagreements:
            labels = ", ".join(c.label.lower() for c in disagreements)
            return BAND_REVIEW, (
                f"Scored {overall:.2f} with an exact {strong[0].label.lower()} match, but "
                f"{labels} disagrees. A contradiction is never resolved automatically."
            )
        if evidence_weight < model.min_evidence_for_auto:
            return BAND_REVIEW, (
                f"Scored {overall:.2f} with an exact {strong[0].label.lower()} match, but only "
                f"{evidence_weight:.0%} of the evidence was comparable — too thin to act on "
                "without a person."
            )
        return BAND_AUTO, (
            f"Exact {strong[0].label.lower()} match, {overall:.2f} overall across "
            f"{evidence_weight:.0%} of the model's evidence, and nothing disagrees."
        )

    return BAND_REVIEW, (
        f"Scored {overall:.2f} across {evidence_weight:.0%} of the model's evidence — "
        "enough to be worth a look, not enough to act on."
    )
