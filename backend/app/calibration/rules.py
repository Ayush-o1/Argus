"""What the feedback says about each detection rule.

## Three measurements, deliberately not combined

A rule's quality is visible from three places, and they answer different
questions over different denominators. Averaging them, or picking whichever is
highest, would produce a single number that means nothing:

  1. **Against planted labels** (Phase 7's `alert_evaluations`). Does the rule
     fire on subjects a storyline touched? Available immediately, for every
     alert, and only meaningful in a synthetic world — there is no ground truth
     like it in a real deployment. It is a floor, and Phase 7 already labels it
     `precision_strict`.

  2. **From triage** (Phase 7's dismissal vocabulary). Of the alerts an analyst
     actually looked at and closed without work, how many did they judge the
     rule simply wrong about? `known_benign` and `not_relevant` are excluded
     here for the reason the vocabulary was built: the rule fired correctly on a
     real pattern this deployment does not care about, which is a scoping
     problem and not a detector problem.

  3. **From outcomes** (Phase 9). Of the investigations someone worked to a
     conclusion, how many confirmed the hypothesis the alert prompted? This is
     the strongest evidence available and always the scarcest — it costs an
     analyst's time to produce a single data point.

Each is published with its own counts and its own interval. A rule can look
good on (1) and bad on (3), and that difference is the most useful thing in this
module: it means the rule finds planted structure that does not survive contact
with an analyst.

## Recall is not estimated here

There is no denominator for it. Recall needs the things ARGUS *should* have
found, and the only observable proxy is an investigation opened with no alert
behind it — which counts the misses somebody happened to notice. That is a lower
bound on false negatives and it is published as one, in `false_negatives()`,
never as a recall figure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.alerting.lifecycle import DISMISSAL_REASONS
from app.calibration.estimates import Proportion, estimate
from app.investigation.outcomes import counts_as_correct

__all__ = ["RuleCalibration", "calibrate_rules", "summarise"]

# Dismissal codes that count against the rule. Read from the vocabulary rather
# than restated, so the two cannot drift — Phase 7 owns that judgement and this
# module consumes it.
_FALSE_POSITIVE_CODES: frozenset[str] = frozenset(r.code for r in DISMISSAL_REASONS if r.counts_as_false_positive)


@dataclass
class RuleCalibration:
    rule_id: str
    rule_version: int

    alerts: int = 0
    firings: int = 0
    still_open: int = 0
    suppressed: int = 0

    dismissed_total: int = 0
    dismissed_as_wrong: int = 0
    """Dismissals whose reason says the rule's premise did not hold."""
    dismissals_by_reason: dict[str, int] = field(default_factory=dict)

    investigations_confirmed: int = 0
    investigations_unfounded: int = 0
    investigations_uninformative: int = 0
    """Closed with an outcome that says nothing about the rule (`inconclusive`,
    `referred`). Counted and published rather than dropped, so the share of work
    that could not settle anything stays visible."""

    @property
    def triage_precision(self) -> Proportion:
        """Of the alerts triaged to a dismissal, how many were not the rule's fault."""
        return estimate(self.dismissed_total - self.dismissed_as_wrong, self.dismissed_total)

    @property
    def outcome_precision(self) -> Proportion:
        """Of the investigations that settled the question, how many confirmed it."""
        decided = self.investigations_confirmed + self.investigations_unfounded
        return estimate(self.investigations_confirmed, decided)

    @property
    def has_feedback(self) -> bool:
        return bool(
            self.dismissed_total
            or self.investigations_confirmed
            or self.investigations_unfounded
            or self.investigations_uninformative
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "alerts": self.alerts,
            "firings": self.firings,
            "still_open": self.still_open,
            "suppressed": self.suppressed,
            "has_feedback": self.has_feedback,
            "triage": {
                "dismissed": self.dismissed_total,
                "dismissed_as_wrong": self.dismissed_as_wrong,
                "by_reason": dict(sorted(self.dismissals_by_reason.items())),
                "precision": self.triage_precision.as_dict(),
                "note": (
                    "Excludes dismissals for known-benign activity and out-of-scope "
                    "findings: the rule fired correctly on a real pattern this deployment "
                    "does not investigate, which is a scoping decision rather than a "
                    "detector fault."
                ),
            },
            "outcomes": {
                "confirmed": self.investigations_confirmed,
                "unfounded": self.investigations_unfounded,
                "did_not_settle": self.investigations_uninformative,
                "precision": self.outcome_precision.as_dict(),
                "note": (
                    "Over investigations closed with an outcome that settles the question. "
                    "`inconclusive` and `referred` are excluded and counted separately — "
                    "they describe the evidence and the jurisdiction, not the rule."
                ),
            },
        }


def calibrate_rules(
    disposition_rows: list[dict[str, Any]],
    dismissal_rows: list[dict[str, Any]],
    outcome_rows: list[dict[str, Any]],
) -> list[RuleCalibration]:
    """Fold the three views into one record per rule version.

    Keyed on `(rule_id, rule_version)` rather than on `rule_id`. A rule that was
    edited is a different detector, and pooling its versions would let a fixed
    rule inherit the mistakes of the one it replaced — or hide them.
    """
    by_key: dict[tuple[str, int], RuleCalibration] = {}

    def get(rule_id: str, version: int) -> RuleCalibration:
        key = (rule_id, version)
        if key not in by_key:
            by_key[key] = RuleCalibration(rule_id=rule_id, rule_version=version)
        return by_key[key]

    for row in disposition_rows:
        rec = get(row["rule_id"], row["rule_version"])
        rec.alerts = int(row["alerts"])
        rec.firings = int(row["firings"] or 0)
        rec.still_open = int(row["still_open"])
        rec.suppressed = int(row["suppressed"])
        rec.dismissed_total = int(row["dismissed"])

    for row in dismissal_rows:
        rec = get(row["rule_id"], row["rule_version"])
        code = row["dismissal_reason"]
        n = int(row["alerts"])
        rec.dismissals_by_reason[code] = n
        if code in _FALSE_POSITIVE_CODES:
            rec.dismissed_as_wrong += n

    for row in outcome_rows:
        rec = get(row["rule_id"], row["rule_version"])
        n = int(row["investigations"])
        verdict = counts_as_correct(row["outcome"])
        if verdict is True:
            rec.investigations_confirmed += n
        elif verdict is False:
            rec.investigations_unfounded += n
        else:
            rec.investigations_uninformative += n

    return sorted(by_key.values(), key=lambda r: (r.rule_id, r.rule_version))


def summarise(records: list[RuleCalibration]) -> dict[str, Any]:
    """A whole-system view, with the same refusal to over-claim.

    The totals are pooled across rules, which is legitimate for answering "how
    much feedback does this deployment have at all" and illegitimate for
    answering "how good is detection" — one rule that fires ninety times
    dominates. Both are stated.
    """
    decided = sum(r.investigations_confirmed + r.investigations_unfounded for r in records)
    confirmed = sum(r.investigations_confirmed for r in records)
    dismissed = sum(r.dismissed_total for r in records)
    wrong = sum(r.dismissed_as_wrong for r in records)
    with_feedback = sum(1 for r in records if r.has_feedback)

    return {
        "rules": len(records),
        "rules_with_any_feedback": with_feedback,
        "rules_without_feedback": len(records) - with_feedback,
        "outcome_precision_pooled": estimate(confirmed, decided).as_dict(),
        "triage_precision_pooled": estimate(dismissed - wrong, dismissed).as_dict(),
        "pooling_note": (
            "Pooled across every rule, which answers how much feedback exists and not how "
            "good detection is — whichever rule fires most dominates the total. The "
            "per-rule figures are the ones to tune on."
        ),
        "coverage_note": (
            f"{len(records) - with_feedback} of {len(records)} rule versions have no feedback "
            "at all: nothing they raised has been dismissed or investigated to a conclusion. "
            "Those are unmeasured, which is different from being measured as good."
        ),
    }
