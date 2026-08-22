"""What a rule may fire on, and the shape it arrives in.

## The inversion this phase makes

Phases 5 and 6 read the graph and were forbidden from reading the generator's
answer key. Alerting reads neither. Its inputs are **ARGUS's own published
findings** — an assessment band, a correlation tier, a cluster membership —
which is what makes an alert a statement about what ARGUS concluded rather than
a second, parallel opinion about the world.

That matters for a reason beyond tidiness. Before this phase, `GET /api/alerts`
was:

    MATCH (i:Incident) WHERE i.severity IN ['High','Critical']

`Incident` nodes are written by the scenario generator, one per storyline,
summarising the storyline it just planted. Nothing generated an alert; the
endpoint re-read the answer key and presented it as a queue. Every alert was
correct, and none of them were found. `Incident` has been on the inadmissible
list since Phase 5 — the alert path was simply never held to it.

## Admissibility here

`ADMISSIBLE_INPUTS` names the derived facts a rule may consult. Two properties
are asserted by `test_alerting_isolation.py`:

  - every rule's declared `reads` is a subset of it, and
  - no module in this package references any token in
    `app.integrity.ALL_INADMISSIBLE_TOKENS`.

The second is what stops the old behaviour returning by a side door — a rule
that joined to `Incident` "just to enrich the title" would reintroduce the
circularity with a green test suite, exactly as `run_cycle_detection` did with
`r.flagged` for five phases.

## The consequence, stated plainly

ARGUS can only alert on what it independently found. Storylines its assessment
and correlation phases cannot see produce no alerts, and `evaluation.py`
reports that as a recall figure rather than closing the gap by reading the
plant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.integrity import ALL_INADMISSIBLE_TOKENS

__all__ = [
    "ADMISSIBLE_INPUTS",
    "ALL_INADMISSIBLE_TOKENS",
    "AlertingEvidence",
    "AssessmentFinding",
    "ClusterFinding",
    "LinkFinding",
]

# Derived findings a rule may read. Everything here is something ARGUS
# published, with a run id and a model fingerprint behind it.
ADMISSIBLE_INPUTS: frozenset[str] = frozenset(
    {
        # Phase 5 — assessment
        "assessment.subject_ref",
        "assessment.subject_type",
        "assessment.band",
        "assessment.score",
        "assessment.evidence_coverage",
        "assessment.families_fired",
        "assessment.computed_at",
        "assessment_signal.signal_id",
        "assessment_signal.family",
        "assessment_signal.magnitude",
        "assessment_signal.summary",
        # Phase 6 — correlation
        "correlation_link.ref_a",
        "correlation_link.ref_b",
        "correlation_link.tier",
        "correlation_link.strength",
        "correlation_link.coverage",
        "correlation_link.corroborating_families",
        "correlation_cluster.cluster_key",
        "correlation_cluster.size",
        "correlation_cluster.families",
        "correlation_cluster.weakest_bridge",
        "correlation_cluster.members",
    }
)


@dataclass(frozen=True)
class AssessmentFinding:
    """One subject's current assessment, as Phase 5 published it."""

    subject_ref: str
    subject_type: str
    band: str
    score: float | None
    evidence_coverage: float
    families_fired: tuple[str, ...]
    computed_at: datetime
    run_id: int
    model_fingerprint: str

    # The subject's previous band, where a previous run assessed them. `None`
    # means "not previously assessed", which is not the same as "unchanged" and
    # must not be rendered as one — a subject first seen at `elevated` has not
    # escalated, it has simply arrived.
    previous_band: str | None = None
    previous_computed_at: datetime | None = None

    signals: tuple[tuple[str, str, float | None, str], ...] = ()
    """(signal_id, family, magnitude, summary) for the signals that fired.
    Magnitude is None where the signal was applicable but not evaluable, and
    that distinction survives to the alert."""


@dataclass(frozen=True)
class LinkFinding:
    """One correlation link from the current run."""

    ref_a: str
    ref_b: str
    tier: str
    strength: float
    coverage: float
    corroborating_families: tuple[str, ...]


@dataclass(frozen=True)
class ClusterFinding:
    """One correlated cluster from the current run."""

    cluster_key: str
    members: tuple[str, ...]
    size: int
    families: tuple[str, ...]
    weakest_bridge: float | None


@dataclass
class AlertingEvidence:
    """Everything the rule engine may see, for one run.

    Gathered once for the whole population, like the assessor's bundle and for
    the same reason: the rules that matter are relational. "Two independently
    elevated subjects are correlated" cannot be evaluated from inside either
    subject.
    """

    assessments: dict[str, AssessmentFinding] = field(default_factory=dict)
    """subject_ref -> current assessment."""

    links: list[LinkFinding] = field(default_factory=list)
    clusters: list[ClusterFinding] = field(default_factory=list)

    assessment_run_id: int | None = None
    correlation_run_id: int | None = None
    gathered_at: datetime | None = None

    def cluster_of(self, subject_ref: str) -> ClusterFinding | None:
        for cluster in self.clusters:
            if subject_ref in cluster.members:
                return cluster
        return None
