"""The two vocabularies an investigation closes on, and what each one means.

Every other phase built something ARGUS believes. This one records what a
person decided, and the whole value of that record depends on the words being
few, fixed, and meaning the same thing to everyone who uses them.

## Why controlled vocabularies rather than free text

Phase 7 made the argument for dismissals and it applies unchanged here: a
free-text outcome cannot be counted. A rule closed out fifty times for the same
reason looks exactly like a rule closed out fifty times for fifty reasons, and
calibration needs the difference. Free text is still available — every outcome
carries a rationale, and the rationale is required — but the *countable* part is
one of four words.

## The distinction that does the work

`counts_as_correct` is not derivable from the outcome label, which is why it is
declared rather than inferred:

  - `confirmed` and `unfounded` are statements about the **finding**. They are
    the two that calibration can learn from.
  - `inconclusive` and `referred` are statements about the **evidence** and the
    **jurisdiction**. Neither says the rule was right or wrong, and counting
    either as a failure would punish detectors for gaps in collection or for
    correctly escalating something out of scope.

Getting this wrong in the obvious direction — treating `inconclusive` as a soft
`unfounded` — would make every detector look worse the less data ARGUS holds,
which is precisely backwards.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CONFIDENCE_LEVELS",
    "CONFIDENCE_MEANING",
    "OUTCOMES",
    "OUTCOME_CODES",
    "Outcome",
    "counts_as_correct",
    "outcome_by_code",
]


@dataclass(frozen=True)
class Outcome:
    code: str
    label: str
    means: str
    counts_as_correct: bool | None
    """What calibration may conclude about the alert that started this.

    True  — the finding held; this is positive evidence for the rule.
    False — it did not; this is negative evidence.
    None  — this outcome says nothing either way, and calibration must exclude
            it from precision rather than guess. An excluded investigation is
            still counted and reported, so the denominator stays visible.
    """


OUTCOMES: tuple[Outcome, ...] = (
    Outcome(
        code="confirmed",
        label="Confirmed",
        means=("The hypothesis held up against the evidence gathered. What ARGUS pointed at was there."),
        counts_as_correct=True,
    ),
    Outcome(
        code="unfounded",
        label="Unfounded",
        means=("The hypothesis did not hold. The evidence was sufficient to decide, and it decided against."),
        counts_as_correct=False,
    ),
    Outcome(
        code="inconclusive",
        label="Inconclusive",
        means=(
            "The available evidence could not settle it either way. This is a "
            "statement about what ARGUS holds, not about whether the finding was "
            "right — so it is excluded from precision rather than counted against it."
        ),
        counts_as_correct=None,
    ),
    Outcome(
        code="referred",
        label="Referred onward",
        means=(
            "Handed to someone with the authority to take it further. The "
            "analyst judged it warranted action but did not themselves establish "
            "whether the finding was correct, so it supports neither column."
        ),
        counts_as_correct=None,
    ),
)

OUTCOME_CODES: frozenset[str] = frozenset(o.code for o in OUTCOMES)

_BY_CODE: dict[str, Outcome] = {o.code: o for o in OUTCOMES}


def outcome_by_code(code: str) -> Outcome:
    try:
        return _BY_CODE[code]
    except KeyError:
        raise ValueError(
            f"{code!r} is not an investigation outcome. Valid: " + ", ".join(sorted(OUTCOME_CODES))
        ) from None


def counts_as_correct(code: str) -> bool | None:
    return outcome_by_code(code).counts_as_correct


# ─────────────────────────────────────────────────────────────────────────────
# Analytic confidence
#
# Deliberately NOT the Admiralty code the provenance layer uses. Admiralty rates
# a source (A–F) and the credibility of a particular report (1–6); both are
# judgements about someone else's information. An analyst's confidence in their
# own hypothesis is a third thing, and giving it the same letters would put an
# analytic judgement into source-rating units — the exact conflation that
# `epistemic_kind` was introduced in migration 003 to prevent.
#
# Three levels, not five or ten. The scale is ordinal and the gradations have to
# survive being applied by different people on different days; a finer scale
# implies a precision that analytic judgement does not have. There is no numeric
# equivalent anywhere in this codebase, and nothing averages these.
# ─────────────────────────────────────────────────────────────────────────────

CONFIDENCE_LEVELS: tuple[str, ...] = ("low", "moderate", "high")

CONFIDENCE_MEANING: dict[str, str] = {
    "low": (
        "Plausible, but resting on fragmentary, unconfirmed or single-source "
        "evidence. Would not be surprising to find wrong."
    ),
    "moderate": (
        "Supported by evidence that is credible but incomplete, or by sources "
        "that are not fully independent. The most common honest answer."
    ),
    "high": (
        "Supported by well-corroborated evidence from independent sources, with "
        "no significant unexplained contradiction. Reserved, not default."
    ),
}
