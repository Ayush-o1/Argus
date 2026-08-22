"""What would change if a rule fired at a different threshold — before it does.

## Why simulate rather than change and watch

Changing a detection threshold in production and observing the result is a
measurement with a cost paid by analysts: for however long the observation runs,
either they see alerts that should not have been raised, or they do not see ones
that should. Worse, the observation is confounded — the world changes at the
same time as the rule, and nothing separates the two afterwards.

Replaying the candidate rules over the *same* findings the current rules ran on
removes both problems. The evidence is fixed, so every difference is attributable
to the parameter change and nothing else.

## The part that makes this worth having

Counting how many alerts would appear or disappear is easy and nearly useless: a
change that removes forty alerts is good or catastrophic depending entirely on
which forty. So every alert that would stop firing is joined back to the feedback
it already carries — was it dismissed as a false positive, or did an
investigation confirm it? A threshold change that only removes alerts analysts
had already dismissed is a different proposition from one that removes the two
that were confirmed.

## What a simulation cannot tell you

Nothing here estimates what the *new* alerts would turn out to be. They have no
feedback, because nobody has seen them. A simulation that promised a precision
figure for alerts nobody has triaged would be inventing the number that matters
most. The new firings are counted, listed and left unjudged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.alerting.evidence import AlertingEvidence
from app.alerting.identity import alert_key
from app.alerting.rules import DEFAULT_PARAMS, RuleParams, evaluate_rules

__all__ = ["SimulationResult", "simulate"]


@dataclass
class SimulatedAlert:
    alert_key: str
    rule_id: str
    rule_version: int
    scope: tuple[str, ...]
    title: str


@dataclass
class RuleDelta:
    rule_id: str
    unchanged: int = 0
    added: int = 0
    removed: int = 0
    removed_keys: list[str] = field(default_factory=list)
    added_examples: list[str] = field(default_factory=list)


@dataclass
class SimulationResult:
    changes: list[str]
    current_total: int
    candidate_total: int
    unchanged: int
    added: list[SimulatedAlert]
    removed_keys: list[str]
    per_rule: list[RuleDelta]
    feedback_on_removed: dict[str, int] = field(default_factory=dict)
    removed_with_confirmed_outcome: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "changes": self.changes,
            "no_change": not self.changes,
            "current_total": self.current_total,
            "candidate_total": self.candidate_total,
            "unchanged": self.unchanged,
            "added": len(self.added),
            "removed": len(self.removed_keys),
            "per_rule": [
                {
                    "rule_id": d.rule_id,
                    "unchanged": d.unchanged,
                    "added": d.added,
                    "removed": d.removed,
                }
                for d in sorted(self.per_rule, key=lambda x: x.rule_id)
            ],
            "added_examples": [
                {"rule_id": a.rule_id, "scope": list(a.scope), "title": a.title} for a in self.added[:10]
            ],
            "feedback_on_removed": self.feedback_on_removed,
            "removed_with_confirmed_outcome": self.removed_with_confirmed_outcome,
            "what_this_does_not_say": (
                "Nothing here estimates how the newly-raised alerts would turn out. They "
                "carry no feedback because nobody has triaged them, and a figure invented "
                "for them would be the one that matters most."
            ),
            "read_the_removals_first": (
                "The count of removed alerts is not the finding. Which ones — and what "
                "analysts had already concluded about them — is."
            ),
        }


def simulate(
    evidence: AlertingEvidence,
    candidate: RuleParams,
    *,
    current_alert_keys: set[str],
    dismissal_by_key: dict[str, str] | None = None,
    confirmed_keys: set[str] | None = None,
    baseline: RuleParams | None = None,
) -> SimulationResult:
    """Replay the rules under `candidate` and diff against what exists now.

    `current_alert_keys` is what the live queue holds, so the diff is against
    reality rather than against a second simulation — a candidate compared only
    to a re-simulated baseline would silently hide any drift between the code
    and the rows it has already written.
    """
    base = baseline or DEFAULT_PARAMS
    candidate_firings = evaluate_rules(evidence, candidate)

    candidate_by_key: dict[str, SimulatedAlert] = {}
    for firing in candidate_firings:
        key = alert_key(firing.rule_id, firing.rule_version, tuple(firing.scope))
        candidate_by_key[key] = SimulatedAlert(
            alert_key=key,
            rule_id=firing.rule_id,
            rule_version=firing.rule_version,
            scope=tuple(firing.scope),
            title=firing.title,
        )

    candidate_keys = set(candidate_by_key)
    added_keys = sorted(candidate_keys - current_alert_keys)
    removed_keys = sorted(current_alert_keys - candidate_keys)
    unchanged_keys = candidate_keys & current_alert_keys

    per_rule: dict[str, RuleDelta] = {}

    def delta(rule_id: str) -> RuleDelta:
        if rule_id not in per_rule:
            per_rule[rule_id] = RuleDelta(rule_id=rule_id)
        return per_rule[rule_id]

    for key in unchanged_keys:
        delta(candidate_by_key[key].rule_id).unchanged += 1
    for key in added_keys:
        d = delta(candidate_by_key[key].rule_id)
        d.added += 1
        d.added_examples.append(key)

    # Removed alerts are attributed by looking them up in the candidate set,
    # which by definition does not contain them — so the rule is unknown from
    # the simulation alone and is left to the caller's alert rows. Counted
    # under a single bucket rather than guessed at.
    removed_bucket = delta("(removed)")
    removed_bucket.removed = len(removed_keys)
    removed_bucket.removed_keys = removed_keys

    feedback: dict[str, int] = {}
    confirmed_removed: list[str] = []
    if dismissal_by_key:
        for key in removed_keys:
            reason = dismissal_by_key.get(key)
            if reason:
                feedback[reason] = feedback.get(reason, 0) + 1
    if confirmed_keys:
        confirmed_removed = sorted(set(removed_keys) & confirmed_keys)

    return SimulationResult(
        changes=base.describe_differences(candidate),
        current_total=len(current_alert_keys),
        candidate_total=len(candidate_keys),
        unchanged=len(unchanged_keys),
        added=[candidate_by_key[k] for k in added_keys],
        removed_keys=removed_keys,
        per_rule=list(per_rule.values()),
        feedback_on_removed=feedback,
        removed_with_confirmed_outcome=confirmed_removed,
    )
