"""How good the rule set is, measured against labels it never saw.

The same discipline as Phases 4, 5 and 6, and the same refusal to publish a
single flattering number.

## What is being measured

A rule fires on ARGUS's own findings. Those findings came from the graph, and
the graph contains storylines the generator planted. So the question is whether
the alerts land on subjects a storyline actually touched — and, separately,
whether the storylines that exist produced any alert at all.

Neither number is reported alone, because each is misleading by itself:

  - **Precision** counts an alert as correct only if one of its subjects is in
    a storyline. The baseline world contains real structure nobody scripted, so
    an alert on an unlabelled subject is not demonstrably wrong — it is
    unlabelled. Reported as `precision_strict` and never as "precision".
  - **Recall** is computed only over storyline subjects whose type ARGUS
    assesses. A storyline that plants twelve documents and two people can
    contribute at most the two people, and counting the documents against
    recall would measure the ontology rather than the rules.

## Why per-rule matters more than the total

The total is dominated by whichever rule fires most — here
`assessment.elevated`, at roughly 90% of alerts. A convergence rule that fires
eight times with perfect precision is invisible in the aggregate and is the
most valuable thing in the set. Per-rule figures are the ones to tune on, and
the ones `alert_evaluations.per_rule` stores.

## What this cannot tell you

Nothing here measures whether an alert was *useful*. That requires an outcome,
which requires an analyst to close it with a judgement — the lifecycle records
exactly that, and the calibration phase is where those outcomes turn into a
measurement. Until then, precision against planted labels is a proxy, and is
labelled as one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ALERTED_TYPES",
    "UNREACHABLE_BY_DESIGN",
    "AlertEvaluation",
    "RuleOutcome",
    "StorylineReach",
    "evaluate_alerts",
]

# Types ARGUS assesses, and therefore the only ones a rule can fire on. Recall
# is restricted to storyline members of these types.
ALERTED_TYPES: frozenset[str] = frozenset({"Person", "Organization", "Account", "Shipment"})

# Storylines no admissible rule can reach, with the reason. A recall of 0.0 that
# is a property of the boundary is a different fact from a recall of 0.0 that is
# a weak rule, and a bare number cannot tell them apart — so the reason is
# carried into the published report rather than left in a commit message.
#
# The same accounting Phase 6 used for `UNCORRELATABLE_BY_DESIGN`. Neither is a
# workaround: closing these gaps would require reading the plant, which is the
# failure the whole boundary exists to prevent.
UNREACHABLE_BY_DESIGN: dict[str, str] = {
    "document_forgery_ring": (
        "Plants only Document nodes, marked with `flagged` and `inconsistency_type`. "
        "Both are answer keys, and ARGUS does not assess Documents at all — so this "
        "storyline has no assessable member for a rule to fire on. Reported as "
        "recall None rather than 0.0: there was nothing available to find, which is "
        "not the same as having missed it."
    ),
    "identity_overlap": (
        "Its entire trace is the SHARES_DEVICE edge, of which the world contains "
        "exactly two — both written by this storyline. An analytic keyed on it "
        "would score perfectly and have discovered nothing, so the edge is "
        "inadmissible and the storyline is unreachable. The people involved are "
        "otherwise unmodified, which is what makes it undetectable rather than "
        "merely hard."
    ),
}

# Storylines only partly reachable, and why. Distinguished from the above
# because a low number here is a real ceiling on the rules rather than a closed
# door.
PARTIALLY_REACHABLE: dict[str, str] = {
    "shell_company_ring": (
        "Identified in the plant by `Organization.type = 'Shell'`, which is "
        "disqualified — shell companies also occur in the baseline, so the "
        "attribute is partly an answer key. What remains reachable is the "
        "directorship and transfer structure around them."
    ),
    "supply_chain_divergence": (
        "Reachable only through `Shipment.detour_ratio`, which is admissible. The "
        "storyline also sets `route_anomaly`, which is not — and the shipment "
        "generator marks far more routes anomalous than the storylines wrap, so a "
        "detector keyed on the label would be scored against the wrong "
        "denominator."
    ),
}


def _is_alertable(ref: str) -> bool:
    """Whether a reference names a type ARGUS assesses.

    References carry their type as a prefix (PRS-, ORG-, ACC-, SHP-), which is
    how a storyline's entity list can be filtered without a second graph query.
    """
    return ref[:3] in {"PRS", "ORG", "ACC", "SHP"}


@dataclass
class RuleOutcome:
    rule_id: str
    alerts: int = 0
    subjects: set[str] = field(default_factory=set)
    labelled_subjects: set[str] = field(default_factory=set)

    @property
    def precision_strict(self) -> float | None:
        if not self.subjects:
            return None
        return round(len(self.labelled_subjects) / len(self.subjects), 4)


@dataclass
class StorylineReach:
    storyline_type: str
    members: int
    """Members of a type ARGUS assesses."""
    alerted: int
    rules: set[str] = field(default_factory=set)

    @property
    def recall(self) -> float | None:
        if self.members == 0:
            return None
        return round(self.alerted / self.members, 4)


@dataclass
class AlertEvaluation:
    alerts_total: int
    subjects_alerted: int
    subjects_labelled: int
    storyline_subjects_total: int
    storyline_subjects_alerted: int
    per_rule: list[RuleOutcome] = field(default_factory=list)
    per_storyline: list[StorylineReach] = field(default_factory=list)

    @property
    def precision_strict(self) -> float | None:
        if self.subjects_alerted == 0:
            return None
        return round(self.subjects_labelled / self.subjects_alerted, 4)

    @property
    def recall(self) -> float | None:
        if self.storyline_subjects_total == 0:
            return None
        return round(self.storyline_subjects_alerted / self.storyline_subjects_total, 4)

    @property
    def unlabelled_share(self) -> float | None:
        if self.subjects_alerted == 0:
            return None
        return round(1 - (self.subjects_labelled / self.subjects_alerted), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alerts_total": self.alerts_total,
            "subjects_alerted": self.subjects_alerted,
            "subjects_labelled": self.subjects_labelled,
            "precision_strict": self.precision_strict,
            "precision_note": (
                "Strict: every alert on a subject no storyline touched is counted "
                "wrong. The baseline world contains structure nobody scripted, so "
                "an unlabelled subject is not a demonstrated error. Read this as a "
                "floor, not as precision."
            ),
            "unlabelled_share": self.unlabelled_share,
            "recall": self.recall,
            "recall_note": (
                "Over storyline members whose type ARGUS assesses, and only for "
                "storylines an admissible rule can reach. Documents, devices and "
                "events are excluded because nothing assesses them; "
                + ", ".join(sorted(UNREACHABLE_BY_DESIGN))
                + " are excluded because their entire trace is an inadmissible "
                "field or edge. Both exclusions are listed rather than applied "
                "silently."
            ),
            "storyline_subjects_total": self.storyline_subjects_total,
            "storyline_subjects_alerted": self.storyline_subjects_alerted,
            "per_rule": [
                {
                    "rule_id": r.rule_id,
                    "alerts": r.alerts,
                    "subjects": len(r.subjects),
                    "labelled_subjects": len(r.labelled_subjects),
                    "precision_strict": r.precision_strict,
                }
                for r in sorted(self.per_rule, key=lambda x: x.rule_id)
            ],
            "per_storyline": [
                {
                    "storyline_type": s.storyline_type,
                    "assessable_members": s.members,
                    "alerted": s.alerted,
                    "recall": s.recall,
                    "rules": sorted(s.rules),
                    "reachable": s.storyline_type not in UNREACHABLE_BY_DESIGN,
                    "reach_note": (
                        UNREACHABLE_BY_DESIGN.get(s.storyline_type)
                        or PARTIALLY_REACHABLE.get(s.storyline_type)
                    ),
                }
                for s in sorted(self.per_storyline, key=lambda x: x.storyline_type)
            ],
            "unreachable_by_design": sorted(UNREACHABLE_BY_DESIGN),
            "outcome_note": (
                "None of this measures whether an alert was useful. That needs an "
                "analyst's outcome on a closed alert, which the lifecycle records "
                "and the calibration phase turns into a measurement."
            ),
        }


def evaluate_alerts(
    alerts: list[dict[str, Any]],
    storylines: list[tuple[str, tuple[str, ...]]],
) -> AlertEvaluation:
    """Score the current alert set against the planted storylines.

    `alerts` is rows from the `alerts` table; `storylines` is
    `(type, entity_refs)` as the graph repository returns it. Neither the rules
    nor anything they call has seen the second argument.
    """
    labelled: set[str] = set()
    for _, refs in storylines:
        labelled.update(r for r in refs if _is_alertable(r))

    alerted_subjects: set[str] = set()
    per_rule: dict[str, RuleOutcome] = {}

    for alert in alerts:
        rule_id = alert["rule_id"]
        outcome = per_rule.setdefault(rule_id, RuleOutcome(rule_id=rule_id))
        outcome.alerts += 1
        for ref in alert["scope"] or ():
            alerted_subjects.add(ref)
            outcome.subjects.add(ref)
            if ref in labelled:
                outcome.labelled_subjects.add(ref)

    per_storyline: dict[str, StorylineReach] = {}
    for storyline_type, refs in storylines:
        members = {r for r in refs if _is_alertable(r)}
        reach = per_storyline.setdefault(
            storyline_type, StorylineReach(storyline_type=storyline_type, members=0, alerted=0)
        )
        reach.members += len(members)
        reach.alerted += len(members & alerted_subjects)
        for alert in alerts:
            if members & set(alert["scope"] or ()):
                reach.rules.add(alert["rule_id"])

    # Recall is computed over storylines a rule could in principle reach.
    # Including the unreachable ones would fold a property of the admissibility
    # boundary into a number that reads as rule quality, and the two need
    # different responses: one is a ceiling to state, the other a rule to fix.
    reachable_labelled = {
        r
        for storyline_type, refs in storylines
        if storyline_type not in UNREACHABLE_BY_DESIGN
        for r in refs
        if _is_alertable(r)
    }

    return AlertEvaluation(
        alerts_total=len(alerts),
        subjects_alerted=len(alerted_subjects),
        subjects_labelled=len(alerted_subjects & labelled),
        storyline_subjects_total=len(reachable_labelled),
        storyline_subjects_alerted=len(reachable_labelled & alerted_subjects),
        per_rule=list(per_rule.values()),
        per_storyline=list(per_storyline.values()),
    )
