"""Measuring the correlator against ground truth — the only place labels appear.

The generator knows which entities it planted together. That knowledge is used
here, once, to answer "how good is this?" and nowhere else. The separation is
structural rather than conventional: `fetch_correlation_evidence` never selects
a `Storyline`, an `Incident`, a `Case`, or the `INVOLVES`, `LINKED_TO`,
`CONTROLS` and `SHARES_DEVICE` edges that join their members, so no code path
runs from a label to a link.

## Why precision needs two numbers here, not one

Assessment could ask "is this flagged subject really planted?" and get a clean
answer. Correlation cannot, because **an unlabelled link is not a wrong link**.

The baseline world is full of genuine structure the generator did not script.
Two directors of the same small company really do share an affiliation. Two
people who exchanged eleven calls really did speak. When ARGUS reports those, it
is right about the evidence and right about the link — it simply has not found
a storyline, because there is no storyline there to find. Counting every one of
them as a false positive would measure how much of the world the generator
scripted, not how well the correlator works.

So three figures are published side by side:

  * **Discriminative precision** — over pairs where both subjects are planted in
    *some* storyline. Here ground truth is complete: if both are planted and
    ARGUS links them, either they belong to the same storyline or they do not.
    This is the number that actually measures the model.
  * **Strict precision** — every link not co-planted counted as wrong. The
    pessimistic bound, and by construction an underestimate.
  * **Unlabelled share** — how much of the output falls outside ground truth
    altogether, so a reader can see the size of the gap between the two.

Reporting only the first would be flattering. Reporting only the second would be
false modesty that happens to look rigorous. Both, with the gap measured, is the
only honest option.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import combinations
from typing import Any

from app.correlation.clustering import CorrelatedCluster
from app.correlation.linking import CorrelationLink
from app.correlation.model import TIER_ESTABLISHED, TIER_PROBABLE, CorrelationModel

# Planted phenomena that correlation cannot reach, and why. Stated in the report
# rather than dropped from it: a recall figure computed only over the reachable
# subset would be an average across a denominator chosen to flatter.
UNCORRELATABLE_BY_DESIGN: dict[str, str] = {
    "identity_overlap": (
        "Expressed only as a SHARES_DEVICE edge, which exists nowhere in the baseline world. "
        "Every device has exactly one registered owner, so the plant leaves no shared traffic, "
        "no co-ownership and no other trace. A dimension keyed on that edge would score "
        "perfectly and discover nothing."
    ),
    "document_forgery_ring": (
        "Plants flags on Document nodes. Documents are not subjects ARGUS assesses, so no "
        "anchor exists for any of them and no pair can be formed."
    ),
    "anomalous_transaction_burst": (
        "Plants exactly one account, bursting to counterparties chosen at random. A correlation "
        "needs two planted subjects to be right about; this storyline never provides a second, "
        "so it contributes no pairs to ground truth in either direction."
    ),
    "supply_chain_divergence": (
        "Plants between one and four shipments selected independently at random from those "
        "already marked anomalous. Nothing links them to each other — no shared corridor, "
        "carrier or timing is imposed. Any correlation ARGUS found between them would be a "
        "coincidence, and finding none is the correct result rather than a miss."
    ),
}

# Storylines that plant a group but whose *internal* structure is only partly
# admissible. Recorded so a shortfall in recall is attributable to the specific
# tie that was excluded, instead of reading as a general weakness.
PARTIALLY_REACHABLE: dict[str, str] = {
    "shell_company_ring": (
        "The organisations in the ring are joined to each other by circular transactions, which "
        "are admissible and findable. The controllers are joined to the organisations only by "
        "CONTROLS, which is not. Organisation-to-organisation pairs are therefore reachable and "
        "person-to-organisation pairs are not, and recall below 100% here is that exclusion "
        "rather than a failure of the dimensions."
    ),
}


@dataclass(frozen=True)
class LabelledPair:
    """Two subjects the generator planted in the same storyline."""

    ref_a: str
    ref_b: str
    storyline_types: tuple[str, ...]

    @property
    def key(self) -> tuple[str, str]:
        return (self.ref_a, self.ref_b) if self.ref_a <= self.ref_b else (self.ref_b, self.ref_a)


@dataclass
class PairMetrics:
    selected: int
    true_positives: int
    labelled_total: int

    @property
    def precision(self) -> float | None:
        """None rather than 0 over an empty selection.

        Zero would read as "everything it picked was wrong"; nothing was picked.
        """
        return round(self.true_positives / self.selected, 4) if self.selected else None

    @property
    def recall(self) -> float | None:
        return round(self.true_positives / self.labelled_total, 4) if self.labelled_total else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": self.selected,
            "true_positives": self.true_positives,
            "labelled_total": self.labelled_total,
            "precision": self.precision,
            "recall": self.recall,
        }


@dataclass
class StorylineCorrelation:
    storyline_type: str
    planted_subjects: int
    planted_pairs: int
    recovered_pairs: int
    reachable: bool
    note: str = ""

    @property
    def pair_recall(self) -> float | None:
        return round(self.recovered_pairs / self.planted_pairs, 4) if self.planted_pairs else None


@dataclass
class CorrelationEvaluationReport:
    model_version: str
    model_fingerprint: str
    generated_at: datetime

    anchors: int
    candidate_pairs: int
    links_recorded: int
    tier_counts: dict[str, int]

    strict: PairMetrics
    discriminative: PairMetrics
    published_tiers: PairMetrics

    unlabelled_links: int
    both_planted_links: int

    clusters: int
    clustered_subjects: int
    cluster_purity: float | None
    over_merged_clusters: int

    per_storyline: list[StorylineCorrelation] = field(default_factory=list)
    per_dimension: list[dict[str, Any]] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "model_fingerprint": self.model_fingerprint,
            "generated_at": self.generated_at.isoformat(),
            "anchors": self.anchors,
            "candidate_pairs": self.candidate_pairs,
            "links_recorded": self.links_recorded,
            "tier_counts": self.tier_counts,
            "strict": self.strict.to_dict(),
            "discriminative": self.discriminative.to_dict(),
            "published_tiers": self.published_tiers.to_dict(),
            "unlabelled_links": self.unlabelled_links,
            "both_planted_links": self.both_planted_links,
            "unlabelled_share": (
                round(self.unlabelled_links / self.links_recorded, 4)
                if self.links_recorded
                else None
            ),
            "clusters": self.clusters,
            "clustered_subjects": self.clustered_subjects,
            "cluster_purity": self.cluster_purity,
            "over_merged_clusters": self.over_merged_clusters,
            "per_storyline": [
                {
                    "storyline_type": s.storyline_type,
                    "planted_subjects": s.planted_subjects,
                    "planted_pairs": s.planted_pairs,
                    "recovered_pairs": s.recovered_pairs,
                    "pair_recall": s.pair_recall,
                    "reachable": s.reachable,
                    "note": s.note,
                }
                for s in self.per_storyline
            ],
            "per_dimension": self.per_dimension,
            "caveats": self.caveats,
        }


def evaluate(
    links: list[CorrelationLink],
    clusters: list[CorrelatedCluster],
    labelled_pairs: list[LabelledPair],
    planted_subjects: dict[str, tuple[str, ...]],
    anchors: set[str],
    model: CorrelationModel,
    *,
    candidate_pairs: int,
    generated_at: datetime | None = None,
) -> CorrelationEvaluationReport:
    """Measure a run.

    `planted_subjects` maps every planted subject ref to the storyline types it
    belongs to, whether or not it became an anchor — needed to tell a link
    between two planted subjects from a link involving one.
    """
    moment = generated_at or datetime.now(UTC)

    # Ground truth is restricted to pairs where *both* subjects became anchors.
    # A pair ARGUS never had the chance to consider is not a miss by the
    # correlator; it is a subject the assessor found nothing in, which is
    # Phase 5's business and would be double-counted as a failure here.
    truth = {pair.key for pair in labelled_pairs if pair.ref_a in anchors and pair.ref_b in anchors}

    found = {link.key for link in links}
    planted_refs = set(planted_subjects)

    both_planted = {key for key in found if key[0] in planted_refs and key[1] in planted_refs}
    unlabelled = {key for key in found if key[0] not in planted_refs or key[1] not in planted_refs}

    strict = PairMetrics(
        selected=len(found),
        true_positives=len(found & truth),
        labelled_total=len(truth),
    )
    discriminative = PairMetrics(
        selected=len(both_planted),
        true_positives=len(both_planted & truth),
        labelled_total=len(truth),
    )
    # The links ARGUS actually publishes as assertions — `established` and
    # `probable`. Named for what it measures: an earlier draft called this
    # `established_only` while counting both tiers, which is precisely the kind
    # of label that makes a number mean something better than it does.
    published = {
        link.key for link in links if link.tier in (TIER_ESTABLISHED, TIER_PROBABLE)
    }
    published_tiers = PairMetrics(
        selected=len(published),
        true_positives=len(published & truth),
        labelled_total=len(truth),
    )

    tier_counts: dict[str, int] = {}
    for link in links:
        tier_counts[link.tier] = tier_counts.get(link.tier, 0) + 1

    return CorrelationEvaluationReport(
        model_version=model.version,
        model_fingerprint=model.fingerprint(),
        generated_at=moment,
        anchors=len(anchors),
        candidate_pairs=candidate_pairs,
        links_recorded=len(links),
        tier_counts=tier_counts,
        strict=strict,
        discriminative=discriminative,
        published_tiers=published_tiers,
        unlabelled_links=len(unlabelled),
        both_planted_links=len(both_planted),
        clusters=len(clusters),
        clustered_subjects=sum(c.size for c in clusters),
        cluster_purity=_cluster_purity(clusters, planted_subjects),
        over_merged_clusters=sum(1 for c in clusters if c.over_merged),
        per_storyline=_per_storyline(labelled_pairs, found, anchors, planted_subjects),
        per_dimension=_per_dimension(links, truth),
        caveats=_caveats(),
    )


def _cluster_purity(
    clusters: list[CorrelatedCluster], planted_subjects: dict[str, tuple[str, ...]]
) -> float | None:
    """The share of clustered members belonging to their cluster's dominant storyline.

    Computed only over members that are planted at all. A cluster of entirely
    unlabelled subjects has no purity to measure — it is not impure, it is
    outside ground truth — and averaging it in as zero would report the
    generator's coverage as a defect in the clustering.
    """
    scored: list[float] = []
    for cluster in clusters:
        counts: dict[str, int] = {}
        labelled_members = 0
        for member in cluster.members:
            types = planted_subjects.get(member.ref)
            if not types:
                continue
            labelled_members += 1
            for storyline_type in types:
                counts[storyline_type] = counts.get(storyline_type, 0) + 1
        if labelled_members < 2:
            continue
        scored.append(max(counts.values()) / labelled_members)
    return round(sum(scored) / len(scored), 4) if scored else None


def _per_storyline(
    labelled_pairs: list[LabelledPair],
    found: set[tuple[str, str]],
    anchors: set[str],
    planted_subjects: dict[str, tuple[str, ...]],
) -> list[StorylineCorrelation]:
    by_type: dict[str, set[tuple[str, str]]] = {}
    for pair in labelled_pairs:
        if pair.ref_a not in anchors or pair.ref_b not in anchors:
            continue
        for storyline_type in pair.storyline_types:
            by_type.setdefault(storyline_type, set()).add(pair.key)

    subjects_by_type: dict[str, set[str]] = {}
    for ref, types in planted_subjects.items():
        for storyline_type in types:
            subjects_by_type.setdefault(storyline_type, set()).add(ref)

    # Storylines that contribute no pairs still belong in the table. Omitting
    # them would leave a reader believing every planted phenomenon was in scope.
    for storyline_type in list(UNCORRELATABLE_BY_DESIGN) + list(subjects_by_type):
        by_type.setdefault(storyline_type, set())

    outcomes: list[StorylineCorrelation] = []
    for storyline_type in sorted(by_type):
        pairs = by_type[storyline_type]
        reachable = storyline_type not in UNCORRELATABLE_BY_DESIGN
        outcomes.append(
            StorylineCorrelation(
                storyline_type=storyline_type,
                planted_subjects=len(subjects_by_type.get(storyline_type, set()) & anchors),
                planted_pairs=len(pairs),
                recovered_pairs=len(pairs & found),
                reachable=reachable,
                note=UNCORRELATABLE_BY_DESIGN.get(storyline_type)
                or PARTIALLY_REACHABLE.get(storyline_type, ""),
            )
        )
    return outcomes


def _per_dimension(links: list[CorrelationLink], truth: set[tuple[str, str]]) -> list[dict[str, Any]]:
    """How often each dimension fired, and how often it was right when it did.

    This is the check on the family ceilings. Proximity and coincidence are
    capped on the stated belief that they are weak evidence; if their precision
    here comes out level with the financial dimensions, that belief was wrong
    and the caps should move. Published either way.
    """
    stats: dict[str, dict[str, Any]] = {}
    for link in links:
        for outcome in link.outcomes:
            entry = stats.setdefault(
                outcome.dimension_id,
                {
                    "family": outcome.family,
                    "evaluable": 0,
                    "not_evaluable": 0,
                    "fired": 0,
                    "fired_on_labelled": 0,
                },
            )
            if not outcome.evaluable:
                entry["not_evaluable"] += 1
                continue
            entry["evaluable"] += 1
            if outcome.fired:
                entry["fired"] += 1
                if link.key in truth:
                    entry["fired_on_labelled"] += 1

    rows = []
    for dimension_id in sorted(stats):
        entry = stats[dimension_id]
        rows.append(
            {
                "dimension_id": dimension_id,
                **entry,
                # Measured over recorded links only, which is a biased sample:
                # every one of them already cleared the strength threshold. It
                # answers "among links we published, which dimensions were
                # present on the correct ones", not "how good is this dimension
                # at large".
                "precision_within_links": (
                    round(entry["fired_on_labelled"] / entry["fired"], 4)
                    if entry["fired"]
                    else None
                ),
            }
        )
    return rows


def _caveats() -> list[str]:
    return [
        "An unlabelled link is not a wrong link. The baseline world contains real structure the "
        "generator never scripted — shared directorships, genuine call histories — and ARGUS "
        "reporting those is correct behaviour with no storyline behind it. `strict` counts them "
        "as errors and is therefore a lower bound; `discriminative` excludes them and is the "
        "figure that measures the model.",
        "Ground truth counts only pairs where both subjects became anchors. A pair ARGUS never "
        "considered because the assessor found nothing in one of them is a Phase 5 outcome, and "
        "counting it here would charge the same shortfall twice.",
        "Four of the seven planted storyline types cannot produce a correlation at all — two "
        "leave no admissible trace, one plants a single subject, and one plants subjects with "
        "nothing tying them together. Their recall is 0 by construction, they remain in the "
        "table, and removing them would raise every aggregate above.",
        "Per-dimension precision is measured only over links that were recorded, all of which "
        "already cleared the strength threshold. It compares dimensions against each other; it "
        "is not each dimension's standalone accuracy.",
        "Measured against one synthetic world built from seven hand-written templates. It shows "
        "the dimensions find structures they were not tuned against. It says nothing about "
        "performance on real data.",
    ]


def pairs_from_storylines(
    storylines: list[tuple[str, tuple[str, ...]]],
    assessed_refs: set[str],
    aliases: dict[str, str] | None = None,
) -> list[LabelledPair]:
    """Every co-planted pair, from `(storyline_type, entity_refs)` records.

    Restricted to refs ARGUS assesses. A storyline naming twelve transaction ids
    and two accounts yields exactly one pair, because transactions are not
    subjects and ARGUS has no opinion to be right or wrong about.

    `aliases` follows the same folding the correlator applied: an account whose
    holder is also a finding was folded into that holder, so a storyline naming
    the account is naming a subject correlation no longer treats as separate.
    Without this, the money-routing storyline — which plants a chain of accounts
    and nothing else — reported a recall of zero against a run that had in fact
    linked every one of their holders. Aliasing is applied to ground truth only;
    it changes which subject a planted label attaches to, never whether a link
    was found.

    A pair that collapses to a single subject after aliasing is dropped: two
    accounts held by the same person are one subject, and a "pair" of one is not
    something ARGUS can be right or wrong about.
    """
    alias = aliases or {}
    grouped: dict[tuple[str, str], set[str]] = {}
    for storyline_type, refs in storylines:
        members = sorted({alias.get(ref, ref) for ref in refs} & assessed_refs)
        for left, right in combinations(members, 2):
            grouped.setdefault((left, right), set()).add(storyline_type)
    return [
        LabelledPair(ref_a=left, ref_b=right, storyline_types=tuple(sorted(types)))
        for (left, right), types in sorted(grouped.items())
    ]
