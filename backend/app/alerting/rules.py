"""The detection rules, versioned and fingerprinted.

A rule is a named, testable condition over ARGUS's own findings, together with
the sentence it puts in front of an analyst. Rules are data rather than
branches in a service function, for the same reason signals and dimensions are:
a precision figure is meaningless without a way to say which rule set produced
it, and a rule that cannot be pointed at cannot be tuned or retired.

## What each rule must carry

Every rule states four things, and the dataclass will not let you omit any:

  - **`means`** — what a firing licenses an analyst to believe. Written to be
    read by the person triaging at 2am, not by the person who wrote the rule.
  - **`would_be_wrong_if`** — the condition under which a firing is *not*
    interesting. This is the field that makes a rule falsifiable, and writing
    it is usually where a bad rule dies.
  - **`reads`** — the admissible inputs it consults, checked against
    `evidence.ADMISSIBLE_INPUTS` by a test.
  - **`independent_methods`** — how many independent ARGUS methods must concur
    for the rule to fire. This is the corroboration term in priority, and it is
    declared rather than inferred so it cannot drift from what the rule does.

## Why there is no `severity` on a rule

Severity is a claim about how bad something would be if true, and ARGUS has no
evidence bearing on that: no asset register, no sanctions list, no statement of
what this deployment cares about. Rules therefore carry **priority inputs** —
corroboration, confidence, magnitude, recency — and `priority.py` combines them
into an ordering. An ordering says "look at this before that", which is
supportable. A severity would say "this is critical", which is not.

The audit's suggested priority formula included asset criticality. It is
deliberately absent; see `priority.py`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from app.alerting.evidence import AlertingEvidence

__all__ = [
    "RULES",
    "Rule",
    "RuleFiring",
    "evaluate_rules",
    "rules_fingerprint",
]

# Bands Phase 5 publishes, ordered. Used by the escalation rule, which needs to
# know that `elevated` is above `notable` — a fact that lives here rather than
# being re-derived from a score, because bands are the published unit and a
# score is optional (a subject with insufficient evidence has no score at all).
BAND_ORDER: tuple[str, ...] = ("insufficient_evidence", "clear", "notable", "elevated")


def _band_rank(band: str) -> int:
    try:
        return BAND_ORDER.index(band)
    except ValueError:
        return -1


@dataclass(frozen=True)
class RuleFiring:
    """One rule firing on one scope.

    `scope` is the set of subjects the alert is about, and it is what dedup
    keys on. A rule about a pair carries both refs; a rule about a cluster
    carries every member. Ordering is normalised by `scope_key` so the same
    finding produces the same key regardless of traversal order.
    """

    rule_id: str
    rule_version: int
    scope: tuple[str, ...]
    title: str
    summary: str
    magnitude: float
    """The rule's own strength measure, 0..1. Feeds priority."""
    confidence: float
    """How much of the underlying model could be evaluated, 0..1. Feeds
    priority. Not a probability that the finding is correct."""
    evidence: dict[str, object] = field(default_factory=dict)
    """The quantities behind the summary, so the UI can show the working."""

    @property
    def scope_key(self) -> str:
        return "|".join(sorted(self.scope))


@dataclass(frozen=True)
class Rule:
    rule_id: str
    version: int
    title: str
    means: str
    would_be_wrong_if: str
    reads: frozenset[str]
    independent_methods: int
    evaluate: Callable[[AlertingEvidence], Iterator[RuleFiring]]

    def identity(self) -> dict[str, object]:
        """The parts that change what a firing means. Used for the fingerprint;
        deliberately excludes `title` and `means`, which are prose and may be
        improved without invalidating a measured precision figure."""
        return {
            "rule_id": self.rule_id,
            "version": self.version,
            "reads": sorted(self.reads),
            "independent_methods": self.independent_methods,
        }


# --------------------------------------------------------------------------
# Rule 1 — a subject ARGUS assessed as elevated
# --------------------------------------------------------------------------

ELEVATED_BAND = "elevated"


def _elevated_assessment(evidence: AlertingEvidence) -> Iterator[RuleFiring]:
    for ref, finding in sorted(evidence.assessments.items()):
        if finding.band != ELEVATED_BAND:
            continue
        families = ", ".join(finding.families_fired) or "none recorded"
        yield RuleFiring(
            rule_id="assessment.elevated",
            rule_version=1,
            scope=(ref,),
            title=f"{ref} assessed elevated",
            summary=(
                f"{ref} was assessed elevated on {len(finding.families_fired)} "
                f"famil{'y' if len(finding.families_fired) == 1 else 'ies'} of evidence "
                f"({families}), with {finding.evidence_coverage:.0%} of the model evaluable."
            ),
            magnitude=min(1.0, (finding.score or 0.0) / 100.0),
            confidence=finding.evidence_coverage,
            evidence={
                "band": finding.band,
                "score": finding.score,
                "families_fired": list(finding.families_fired),
                "evidence_coverage": finding.evidence_coverage,
                "signals": [
                    {"signal_id": s, "family": f, "magnitude": m, "summary": t}
                    for s, f, m, t in finding.signals
                ],
            },
        )


# --------------------------------------------------------------------------
# Rule 2 — a pair ARGUS correlated on two independent identifying families
# --------------------------------------------------------------------------

ESTABLISHED_TIER = "established"


def _established_link(evidence: AlertingEvidence) -> Iterator[RuleFiring]:
    for link in sorted(evidence.links, key=lambda x: (x.ref_a, x.ref_b)):
        if link.tier != ESTABLISHED_TIER:
            continue
        families = ", ".join(link.corroborating_families)
        yield RuleFiring(
            rule_id="correlation.established_pair",
            rule_version=1,
            scope=(link.ref_a, link.ref_b),
            title=f"{link.ref_a} and {link.ref_b} are independently corroborated",
            summary=(
                f"Two independent kinds of identifying evidence connect "
                f"{link.ref_a} and {link.ref_b} ({families}). Either would point "
                f"here on its own."
            ),
            magnitude=link.strength,
            confidence=link.coverage,
            evidence={
                "tier": link.tier,
                "strength": link.strength,
                "coverage": link.coverage,
                "corroborating_families": list(link.corroborating_families),
            },
        )


# --------------------------------------------------------------------------
# Rule 3 — two independent methods concur on the same group
# --------------------------------------------------------------------------

# How many independently-assessed members a cluster needs before this fires.
# Two is the smallest number that can be called concurrence; one would just be
# rule 1 with extra steps.
CONVERGENCE_MIN_ASSESSED = 2
CONVERGENCE_BANDS = frozenset({"elevated", "notable"})


def _convergent_cluster(evidence: AlertingEvidence) -> Iterator[RuleFiring]:
    """The strongest thing ARGUS can say, and the reason it can say it.

    Assessment looks at each subject alone: transaction structure, contact
    rhythm, shipment routing. Correlation looks only at what joins subjects,
    and is forbidden from reading any assessment output. When both land on the
    same group of people, two methods that could not have influenced each other
    agreed — which is a materially different claim from either alone, and the
    only one here that survives the objection "your detector found what your
    detector was looking for".
    """
    for cluster in sorted(evidence.clusters, key=lambda c: c.cluster_key):
        assessed = [
            evidence.assessments[m]
            for m in cluster.members
            if m in evidence.assessments and evidence.assessments[m].band in CONVERGENCE_BANDS
        ]
        if len(assessed) < CONVERGENCE_MIN_ASSESSED:
            continue

        elevated = [a for a in assessed if a.band == ELEVATED_BAND]
        coverage = sum(a.evidence_coverage for a in assessed) / len(assessed)
        yield RuleFiring(
            rule_id="convergence.assessed_cluster",
            rule_version=1,
            scope=tuple(cluster.members),
            title=f"{len(assessed)} of {cluster.size} in a correlated group were independently assessed",
            summary=(
                f"ARGUS correlated {cluster.size} subjects on "
                f"{', '.join(cluster.families)} evidence, and independently assessed "
                f"{len(assessed)} of them as notable or elevated "
                f"({len(elevated)} elevated). The two methods do not share inputs."
            ),
            # Share of the group that both methods agree on, which is the thing
            # being claimed. A cluster of 12 with 2 assessed is a weaker
            # statement than a cluster of 3 with 2.
            magnitude=len(assessed) / cluster.size,
            confidence=coverage,
            evidence={
                "cluster_key": cluster.cluster_key,
                "cluster_size": cluster.size,
                "cluster_families": list(cluster.families),
                "weakest_bridge": cluster.weakest_bridge,
                "assessed_members": [
                    {"subject_ref": a.subject_ref, "band": a.band, "score": a.score}
                    for a in sorted(assessed, key=lambda x: x.subject_ref)
                ],
            },
        )


# --------------------------------------------------------------------------
# Rule 4 — a subject whose assessment moved up
# --------------------------------------------------------------------------


def _escalated_assessment(evidence: AlertingEvidence) -> Iterator[RuleFiring]:
    """Fires on movement, not on level.

    A subject sitting at `elevated` across ten runs is rule 1's business and
    should not re-alert; a subject that was `clear` last week and is `elevated`
    now is a different event, and the one an analyst is most likely to want to
    see first. `previous_band` is None for a subject never assessed before,
    which is arrival rather than escalation and deliberately does not fire.
    """
    for ref, finding in sorted(evidence.assessments.items()):
        if finding.previous_band is None:
            continue
        now, before = _band_rank(finding.band), _band_rank(finding.previous_band)
        if now <= before or now < 0 or before < 0:
            continue
        # Only movement *into* a band worth an analyst's time. clear ->
        # notable is movement, but alerting on it would bury the queue in
        # subjects that merely stopped being silent.
        if finding.band not in CONVERGENCE_BANDS:
            continue
        yield RuleFiring(
            rule_id="assessment.escalated",
            rule_version=1,
            scope=(ref,),
            title=f"{ref} moved from {finding.previous_band} to {finding.band}",
            summary=(
                f"{ref} was assessed {finding.previous_band} and is now "
                f"{finding.band}. The change is in ARGUS's assessment, which may "
                f"reflect new evidence or evidence that has only now become "
                f"evaluable."
            ),
            magnitude=min(1.0, (now - before) / max(1, len(BAND_ORDER) - 1)),
            confidence=finding.evidence_coverage,
            evidence={
                "band": finding.band,
                "previous_band": finding.previous_band,
                "score": finding.score,
                "evidence_coverage": finding.evidence_coverage,
                "previous_computed_at": (
                    finding.previous_computed_at.isoformat()
                    if finding.previous_computed_at
                    else None
                ),
            },
        )


RULES: tuple[Rule, ...] = (
    Rule(
        rule_id="assessment.elevated",
        version=1,
        title="Subject assessed elevated",
        means=(
            "ARGUS's own assessment placed this subject in its highest band: several "
            "independent signals fired across enough of the model to be worth an "
            "analyst's time. It is a recommendation to look, not a conclusion about "
            "the subject."
        ),
        would_be_wrong_if=(
            "The band was reached on a narrow slice of the model — a low evidence "
            "coverage means most of what ARGUS would want to check could not be "
            "checked, and the band reflects the part that could."
        ),
        reads=frozenset(
            {
                "assessment.subject_ref",
                "assessment.subject_type",
                "assessment.band",
                "assessment.score",
                "assessment.evidence_coverage",
                "assessment.families_fired",
                "assessment_signal.signal_id",
                "assessment_signal.family",
                "assessment_signal.magnitude",
                "assessment_signal.summary",
            }
        ),
        independent_methods=1,
        evaluate=_elevated_assessment,
    ),
    Rule(
        rule_id="correlation.established_pair",
        version=1,
        title="Pair corroborated by two independent families",
        means=(
            "Two or more independent kinds of identifying evidence — financial, "
            "social or logistical — connect these two subjects, and each would point "
            "here on its own. Proximity and timing never contribute to this tier."
        ),
        would_be_wrong_if=(
            "The two subjects are the same real-world party recorded twice. Entity "
            "resolution runs before correlation, but an unresolved duplicate pair "
            "would correlate perfectly and mean nothing."
        ),
        reads=frozenset(
            {
                "correlation_link.ref_a",
                "correlation_link.ref_b",
                "correlation_link.tier",
                "correlation_link.strength",
                "correlation_link.coverage",
                "correlation_link.corroborating_families",
            }
        ),
        independent_methods=1,
        evaluate=_established_link,
    ),
    Rule(
        rule_id="convergence.assessed_cluster",
        version=1,
        title="Assessment and correlation concur on a group",
        means=(
            "Two methods that share no inputs both landed on this group: ARGUS "
            "assessed several of these subjects individually, and separately "
            "correlated them to each other. Agreement between them is a stronger "
            "statement than either makes alone."
        ),
        would_be_wrong_if=(
            "The correlation rests on one load-bearing link. A low weakest-bridge "
            "value means removing a single link splits the group, so the thing both "
            "methods agree on may not be one group at all."
        ),
        reads=frozenset(
            {
                "assessment.subject_ref",
                "assessment.band",
                "assessment.score",
                "assessment.evidence_coverage",
                "correlation_cluster.cluster_key",
                "correlation_cluster.size",
                "correlation_cluster.families",
                "correlation_cluster.weakest_bridge",
                "correlation_cluster.members",
            }
        ),
        independent_methods=2,
        evaluate=_convergent_cluster,
    ),
    Rule(
        rule_id="assessment.escalated",
        version=1,
        title="Assessment moved up a band",
        means=(
            "This subject's assessment is higher than it was at the previous run. "
            "The change is in what ARGUS concluded, which may mean new evidence "
            "arrived or that existing evidence only now became evaluable."
        ),
        would_be_wrong_if=(
            "The model changed between the two runs. A different model fingerprint "
            "on either side makes the comparison one between two different "
            "questions, not a change in the subject."
        ),
        reads=frozenset(
            {
                "assessment.subject_ref",
                "assessment.band",
                "assessment.score",
                "assessment.evidence_coverage",
                "assessment.computed_at",
            }
        ),
        independent_methods=1,
        evaluate=_escalated_assessment,
    ),
)


def rules_fingerprint() -> str:
    """Stable hash over the rule registry.

    Changes when a rule is added, removed, renamed, re-versioned, or when what
    it reads changes. Does not change when prose is edited, so a precision
    figure survives a clearer explanation.
    """
    payload = json.dumps([r.identity() for r in RULES], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evaluate_rules(evidence: AlertingEvidence) -> list[RuleFiring]:
    """Run every rule over the evidence, in registry order."""
    firings: list[RuleFiring] = []
    for rule in RULES:
        firings.extend(rule.evaluate(evidence))
    return firings
