"""Measuring the correlator, and being honest about what the measurement means.

The load-bearing idea here is that **an unlabelled link is not a wrong link**.
The baseline world contains real structure the generator never scripted — two
directors of the same small company, two people who exchanged eleven calls — and
ARGUS reporting those is correct behaviour with no storyline behind it.

Counting every one of them as a false positive would measure how much of the
world the generator bothered to script, not how well the correlator works. So
three figures are published together, and these tests pin what each one means.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.correlation.clustering import ClusterMember, CorrelatedCluster
from app.correlation.dimensions import DimensionOutcome
from app.correlation.evaluation import (
    UNCORRELATABLE_BY_DESIGN,
    LabelledPair,
    PairMetrics,
    evaluate,
    pairs_from_storylines,
)
from app.correlation.linking import CorrelationLink
from app.correlation.model import TIER_ESTABLISHED, TIER_POSSIBLE, default_model

MODEL = default_model()
NOW = datetime(2026, 3, 1, tzinfo=UTC)


def link(a: str, b: str, tier: str = TIER_ESTABLISHED, outcomes=()) -> CorrelationLink:
    left, right = (a, b) if a <= b else (b, a)
    return CorrelationLink(
        ref_a=left,
        ref_b=right,
        type_a="Person",
        type_b="Person",
        strength=0.8,
        tier=tier,
        coverage=0.8,
        evaluable_dimensions=6,
        applicable_dimensions=7,
        families=(),
        corroborating_families=("financial", "social"),
        outcomes=tuple(outcomes),
        model_fingerprint="test",
        model_version="test@v1",
        computed_at=NOW,
    )


def pair(a: str, b: str, *types: str) -> LabelledPair:
    left, right = (a, b) if a <= b else (b, a)
    return LabelledPair(ref_a=left, ref_b=right, storyline_types=types or ("money_routing_network",))


def report(links, labelled, planted, anchors, clusters=()):
    return evaluate(
        list(links),
        list(clusters),
        list(labelled),
        planted,
        set(anchors),
        MODEL,
        candidate_pairs=100,
        generated_at=NOW,
    )


# ─────────────────────────────────────────────────────────────────────────────
# The three precision figures
# ─────────────────────────────────────────────────────────────────────────────


def test_strict_precision_counts_unlabelled_links_as_wrong() -> None:
    """The pessimistic bound, and by construction an underestimate."""
    result = report(
        links=[link("A", "B"), link("C", "D")],
        labelled=[pair("A", "B")],
        planted={"A": ("money_routing_network",), "B": ("money_routing_network",)},
        anchors={"A", "B", "C", "D"},
    )
    assert result.strict.selected == 2
    assert result.strict.true_positives == 1
    assert result.strict.precision == pytest.approx(0.5)


def test_discriminative_precision_only_judges_pairs_ground_truth_can_judge() -> None:
    """Where both subjects are planted, ground truth is complete: either they
    belong to the same storyline or they do not. That is the figure that
    measures the model."""
    planted = {
        "A": ("money_routing_network",),
        "B": ("money_routing_network",),
        "X": ("communication_cluster",),
        "Y": ("communication_cluster",),
    }
    result = report(
        links=[link("A", "B"), link("A", "X"), link("C", "D")],
        labelled=[pair("A", "B"), pair("X", "Y")],
        planted=planted,
        anchors={"A", "B", "C", "D", "X", "Y"},
    )
    # A-B and A-X have both subjects planted; C-D has neither.
    assert result.both_planted_links == 2
    assert result.discriminative.selected == 2
    assert result.discriminative.true_positives == 1
    assert result.discriminative.precision == pytest.approx(0.5)


def test_the_unlabelled_share_makes_the_gap_between_them_visible() -> None:
    result = report(
        links=[link("A", "B"), link("C", "D"), link("E", "F")],
        labelled=[pair("A", "B")],
        planted={"A": ("money_routing_network",), "B": ("money_routing_network",)},
        anchors={"A", "B", "C", "D", "E", "F"},
    )
    assert result.unlabelled_links == 2
    # Published rounded to four places, as every ratio in the report is.
    assert result.to_dict()["unlabelled_share"] == pytest.approx(2 / 3, abs=1e-4)


def test_precision_over_an_empty_selection_is_none_not_zero() -> None:
    """Zero would read as "everything it picked was wrong". Nothing was picked."""
    metrics = PairMetrics(selected=0, true_positives=0, labelled_total=5)
    assert metrics.precision is None
    assert metrics.recall == 0.0


def test_recall_against_no_ground_truth_is_none() -> None:
    metrics = PairMetrics(selected=3, true_positives=0, labelled_total=0)
    assert metrics.recall is None


# ─────────────────────────────────────────────────────────────────────────────
# What ground truth may hold against the model
# ─────────────────────────────────────────────────────────────────────────────


def test_a_pair_argus_never_considered_is_not_counted_as_a_miss() -> None:
    """One of the subjects was never an anchor, which is a Phase 5 outcome — the
    assessor found nothing in it. Charging it here would count the same
    shortfall twice."""
    result = report(
        links=[],
        labelled=[pair("A", "B"), pair("A", "Z")],
        planted={"A": ("x",), "B": ("x",), "Z": ("x",)},
        anchors={"A", "B"},  # Z never became an anchor
    )
    assert result.strict.labelled_total == 1


def test_recall_counts_recovered_planted_pairs() -> None:
    result = report(
        links=[link("A", "B")],
        labelled=[pair("A", "B"), pair("B", "C")],
        planted={"A": ("x",), "B": ("x",), "C": ("x",)},
        anchors={"A", "B", "C"},
    )
    assert result.strict.recall == pytest.approx(0.5)


def test_the_published_tiers_are_measured_separately() -> None:
    """The operating threshold and the whole output answer different questions.

    `published_tiers` covers exactly the links ARGUS asserts — `established` and
    `probable` — and is named for that. An earlier draft called it
    `established_only` while counting both, which is the kind of label that
    makes a number mean something better than it does.
    """
    result = report(
        links=[link("A", "B", tier=TIER_ESTABLISHED), link("C", "D", tier=TIER_POSSIBLE)],
        labelled=[pair("A", "B")],
        planted={"A": ("x",), "B": ("x",)},
        anchors={"A", "B", "C", "D"},
    )
    assert result.published_tiers.selected == 1
    assert result.published_tiers.precision == pytest.approx(1.0)
    assert result.strict.precision == pytest.approx(0.5)


def test_the_report_names_the_folding_it_followed() -> None:
    """Ground truth naming an account whose holder is also a finding is naming a
    subject correlation folded away. Without following that folding, the
    money-routing storyline reported a recall of zero against a run that had in
    fact linked every one of the holders."""
    pairs = pairs_from_storylines(
        [("money_routing_network", ("ACC-1", "ACC-2"))],
        {"PRS-1", "PRS-2"},
        {"ACC-1": "PRS-1", "ACC-2": "PRS-2"},
    )
    assert [p.key for p in pairs] == [("PRS-1", "PRS-2")]


def test_two_accounts_held_by_one_person_are_not_a_pair() -> None:
    """After folding they are one subject, and a pair of one is not something
    ARGUS can be right or wrong about."""
    pairs = pairs_from_storylines(
        [("money_routing_network", ("ACC-1", "ACC-2"))],
        {"PRS-1"},
        {"ACC-1": "PRS-1", "ACC-2": "PRS-1"},
    )
    assert pairs == []


# ─────────────────────────────────────────────────────────────────────────────
# Pairs from storylines
# ─────────────────────────────────────────────────────────────────────────────


def test_a_storyline_of_three_subjects_yields_three_pairs() -> None:
    pairs = pairs_from_storylines(
        [("shell_company_ring", ("ORG-1", "ORG-2", "ORG-3"))],
        {"ORG-1", "ORG-2", "ORG-3"},
    )
    assert {p.key for p in pairs} == {
        ("ORG-1", "ORG-2"),
        ("ORG-1", "ORG-3"),
        ("ORG-2", "ORG-3"),
    }


def test_entities_argus_does_not_assess_produce_no_pairs() -> None:
    """A storyline naming twelve transaction ids and two accounts yields exactly
    one pair. ARGUS has no opinion about a transaction to be right or wrong
    about."""
    pairs = pairs_from_storylines(
        [("money_routing_network", ("ACC-1", "ACC-2", "TXN-1", "TXN-2", "TXN-3"))],
        {"ACC-1", "ACC-2"},
    )
    assert [p.key for p in pairs] == [("ACC-1", "ACC-2")]


def test_a_storyline_with_one_assessed_subject_yields_nothing() -> None:
    """The anomalous-transaction-burst case: a correlation needs two planted
    subjects to be right about, and this storyline never provides a second."""
    pairs = pairs_from_storylines(
        [("anomalous_transaction_burst", ("ACC-1", "TXN-1", "TXN-2"))], {"ACC-1"}
    )
    assert pairs == []


def test_a_pair_planted_by_two_storylines_records_both() -> None:
    pairs = pairs_from_storylines(
        [("shell_company_ring", ("A", "B")), ("money_routing_network", ("A", "B"))],
        {"A", "B"},
    )
    assert len(pairs) == 1
    assert pairs[0].storyline_types == ("money_routing_network", "shell_company_ring")


# ─────────────────────────────────────────────────────────────────────────────
# Honesty about what cannot be found
# ─────────────────────────────────────────────────────────────────────────────


def test_unreachable_storylines_stay_in_the_report() -> None:
    """Removing them would raise every aggregate above. Recall against them is 0
    by construction and the reason is printed beside it."""
    result = report(
        links=[],
        labelled=[],
        planted={},
        anchors=set(),
    )
    listed = {s.storyline_type for s in result.per_storyline}
    assert set(UNCORRELATABLE_BY_DESIGN).issubset(listed)
    for outcome in result.per_storyline:
        if outcome.storyline_type in UNCORRELATABLE_BY_DESIGN:
            assert outcome.reachable is False
            assert outcome.note


def test_every_unreachable_storyline_states_why() -> None:
    for storyline_type, reason in UNCORRELATABLE_BY_DESIGN.items():
        assert len(reason) > 80, f"{storyline_type} has no real explanation"


def test_the_report_carries_its_caveats() -> None:
    """A precision figure quoted without the note saying an unlabelled link is
    not a wrong link means something considerably worse than what it
    measures."""
    result = report(links=[], labelled=[], planted={}, anchors=set())
    joined = " ".join(result.caveats)
    assert "unlabelled link is not a wrong link" in joined
    assert "one synthetic world" in joined


# ─────────────────────────────────────────────────────────────────────────────
# Per-dimension and clusters
# ─────────────────────────────────────────────────────────────────────────────


def test_per_dimension_precision_separates_the_useful_from_the_decorative() -> None:
    """The check on the family ceilings. If proximity's precision comes out
    level with the financial dimensions, the caps were wrong."""
    fired = DimensionOutcome(
        dimension_id="funds_path",
        family="financial",
        evaluable=True,
        magnitude=0.9,
        summary="",
    )
    blind = DimensionOutcome(
        dimension_id="proximity",
        family="spatial",
        evaluable=False,
        magnitude=None,
        summary="",
    )
    result = report(
        links=[link("A", "B", outcomes=(fired, blind))],
        labelled=[pair("A", "B")],
        planted={"A": ("x",), "B": ("x",)},
        anchors={"A", "B"},
    )
    rows = {row["dimension_id"]: row for row in result.per_dimension}
    assert rows["funds_path"]["fired"] == 1
    assert rows["funds_path"]["precision_within_links"] == pytest.approx(1.0)
    assert rows["proximity"]["not_evaluable"] == 1
    assert rows["proximity"]["precision_within_links"] is None


def test_cluster_purity_ignores_entirely_unlabelled_clusters() -> None:
    """A cluster of unlabelled subjects is not impure — it is outside ground
    truth, and averaging it in as zero would report the generator's coverage as
    a defect in the clustering."""
    labelled_cluster = CorrelatedCluster(
        cluster_key="k1",
        members=(
            ClusterMember("A", "Person", "notable", 40.0, 2),
            ClusterMember("B", "Person", "notable", 40.0, 2),
        ),
        links=(),
        families=("financial",),
        mean_strength=0.8,
        min_strength=0.8,
        bridges=(),
        weakest_bridge=None,
        over_merged=False,
        computed_at=NOW,
    )
    unlabelled_cluster = CorrelatedCluster(
        cluster_key="k2",
        members=(
            ClusterMember("Y", "Person", "notable", 40.0, 2),
            ClusterMember("Z", "Person", "notable", 40.0, 2),
        ),
        links=(),
        families=("social",),
        mean_strength=0.8,
        min_strength=0.8,
        bridges=(),
        weakest_bridge=None,
        over_merged=False,
        computed_at=NOW,
    )
    result = report(
        links=[],
        labelled=[],
        planted={"A": ("x",), "B": ("x",)},
        anchors={"A", "B", "Y", "Z"},
        clusters=[labelled_cluster, unlabelled_cluster],
    )
    assert result.cluster_purity == pytest.approx(1.0)
    assert result.clusters == 2
    assert result.clustered_subjects == 4


def test_a_report_with_nothing_in_it_is_still_a_valid_report() -> None:
    result = report(links=[], labelled=[], planted={}, anchors=set())
    payload = result.to_dict()
    assert payload["links_recorded"] == 0
    assert payload["strict"]["precision"] is None
    assert payload["unlabelled_share"] is None
    assert payload["caveats"]
