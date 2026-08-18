"""Grouping links, and being honest about how fragile each group is.

Connected components are easy to compute and easy to over-read. One incorrect
link between two real groups merges them into a single object that looks twice
as significant as either, and nothing in the component itself reveals that it
hangs on a single edge. These tests pin the parts that make that visible:
bridges, the weakest bridge, over-merge reporting, and stable keys.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.correlation.clustering import _bridges, _components, _louvain, build_clusters
from app.correlation.linking import CorrelationLink
from app.correlation.model import TIER_PROBABLE, default_model

MODEL = default_model()
NOW = datetime(2026, 3, 1, tzinfo=UTC)


def link(a: str, b: str, strength: float = 0.7, families=("financial",)) -> CorrelationLink:
    left, right = (a, b) if a <= b else (b, a)
    return CorrelationLink(
        ref_a=left,
        ref_b=right,
        type_a="Person",
        type_b="Person",
        strength=strength,
        tier=TIER_PROBABLE,
        coverage=0.8,
        evaluable_dimensions=6,
        applicable_dimensions=7,
        families=(),
        corroborating_families=tuple(families),
        outcomes=(),
        model_fingerprint="test",
        model_version="test@v1",
        computed_at=NOW,
    )


def anchors(*refs: str) -> dict[str, tuple[str, str, float | None]]:
    return {ref: ("Person", "notable", 40.0) for ref in refs}


# ─────────────────────────────────────────────────────────────────────────────
# Components
# ─────────────────────────────────────────────────────────────────────────────


def test_a_chain_is_not_a_group() -> None:
    """A–B–C–D is four subjects in a line, not four associates.

    Connected components said otherwise, and that was the defect: measured
    against the live graph they collapsed 454 anchors into a single 351-member
    "cluster", and raising the link threshold did not help — at strength 0.90
    there was still a 111-member blob. Chaining is inherent to components, not a
    thresholding mistake, so the algorithm was replaced rather than tuned.
    """
    links = [link("A", "B"), link("B", "C"), link("C", "D")]
    clusters = build_clusters(links, MODEL, anchors("A", "B", "C", "D"))
    assert all(c.size < 4 for c in clusters)


def test_a_densely_connected_group_is_a_cluster() -> None:
    links = [link("A", "B"), link("B", "C"), link("A", "C")]
    clusters = build_clusters(links, MODEL, anchors("A", "B", "C"))
    assert len(clusters) == 1
    assert clusters[0].size == 3


def test_two_groups_joined_by_one_weak_link_stay_two_groups() -> None:
    """The case connected components could not get right, and the whole reason
    for modularity: six subjects in two triangles joined by one uncertain edge
    are two groups of three, not one group of six that looks twice as
    significant as either."""
    links = [
        link("A", "B", strength=0.9),
        link("B", "C", strength=0.9),
        link("A", "C", strength=0.9),
        link("X", "Y", strength=0.9),
        link("Y", "Z", strength=0.9),
        link("X", "Z", strength=0.9),
        link("C", "X", strength=0.46),
    ]
    clusters = build_clusters(links, MODEL, anchors("A", "B", "C", "X", "Y", "Z"))
    assert len(clusters) == 2
    assert {frozenset(m.ref for m in c.members) for c in clusters} == {
        frozenset({"A", "B", "C"}),
        frozenset({"X", "Y", "Z"}),
    }


def test_separate_groups_stay_separate() -> None:
    links = [
        link("A", "B"), link("B", "C"), link("A", "C"),
        link("X", "Y"), link("Y", "Z"), link("X", "Z"),
    ]
    clusters = build_clusters(links, MODEL, anchors("A", "B", "C", "X", "Y", "Z"))
    assert len(clusters) == 2
    assert {c.size for c in clusters} == {3}


def test_communities_are_deterministic() -> None:
    """Nodes are visited in sorted order and ties broken by community key, so
    the same links always produce the same groups. An analyst comparing two runs
    must not see a difference that is only iteration order."""
    weighted = {
        "A": {"B": 0.9, "C": 0.9},
        "B": {"A": 0.9, "C": 0.9},
        "C": {"A": 0.9, "B": 0.9, "X": 0.4},
        "X": {"C": 0.4, "Y": 0.9, "Z": 0.9},
        "Y": {"X": 0.9, "Z": 0.9},
        "Z": {"X": 0.9, "Y": 0.9},
    }
    first = [sorted(group) for group in _louvain(weighted)]
    for _ in range(5):
        assert [sorted(group) for group in _louvain(weighted)] == first


def test_a_pair_is_not_a_cluster() -> None:
    """Two linked subjects are a link. Calling that a group would make every
    link in the store also a cluster, and the cluster count meaningless."""
    clusters = build_clusters([link("A", "B")], MODEL, anchors("A", "B"))
    assert clusters == []


def test_weak_links_do_not_join_a_cluster() -> None:
    """Links below the cluster threshold are not eligible to group anyone,
    however strong the rest of the group is."""
    links = [
        link("A", "B", strength=0.9),
        link("B", "C", strength=0.9),
        link("A", "C", strength=0.9),
        link("C", "D", strength=0.31),
    ]
    clusters = build_clusters(links, MODEL, anchors("A", "B", "C", "D"))
    assert len(clusters) == 1
    assert {m.ref for m in clusters[0].members} == {"A", "B", "C"}


def test_components_are_found_without_recursion_limits() -> None:
    """A long chain must return a large cluster the over-merge check can report,
    not a RecursionError in the middle of a run."""
    adjacency: dict[str, set[str]] = {}
    for i in range(3000):
        adjacency.setdefault(f"N{i}", set()).add(f"N{i + 1}")
        adjacency.setdefault(f"N{i + 1}", set()).add(f"N{i}")
    found = _components(adjacency)
    assert len(found) == 1
    assert len(found[0]) == 3001


# ─────────────────────────────────────────────────────────────────────────────
# Fragility
# ─────────────────────────────────────────────────────────────────────────────


def test_a_chain_is_all_bridges() -> None:
    adjacency = {"A": {"B"}, "B": {"A", "C"}, "C": {"B"}}
    assert _bridges({"A", "B", "C"}, adjacency) == {("A", "B"), ("B", "C")}


def test_a_triangle_has_no_bridges() -> None:
    """Every member is held by two independent routes, so no single link holds
    the group together — a materially stronger claim than the same three
    subjects in a line."""
    adjacency = {"A": {"B", "C"}, "B": {"A", "C"}, "C": {"A", "B"}}
    assert _bridges({"A", "B", "C"}, adjacency) == set()


def test_the_weakest_bridge_is_the_clusters_real_strength() -> None:
    """A group held together at one point says so. Here three subjects are
    mutually linked and a fourth hangs off one of them: the group is four, but
    it is four only for as long as that single link holds."""
    links = [
        link("A", "B", strength=0.9),
        link("B", "C", strength=0.9),
        link("A", "C", strength=0.9),
        link("C", "D", strength=0.5),
    ]
    clusters = build_clusters(links, MODEL, anchors("A", "B", "C", "D"))
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.size == 4
    assert cluster.bridges == (("C", "D"),)
    assert cluster.weakest_bridge == pytest.approx(0.5)
    assert "splits" in cluster.basis()


def test_a_cluster_with_no_bridge_says_so() -> None:
    links = [link("A", "B"), link("B", "C"), link("A", "C")]
    clusters = build_clusters(links, MODEL, anchors("A", "B", "C"))
    assert clusters[0].weakest_bridge is None
    assert "at least two independent routes" in clusters[0].basis()


def test_degree_distinguishes_the_centre_from_the_edge() -> None:
    links = [link("A", "B"), link("A", "C"), link("A", "D")]
    clusters = build_clusters(links, MODEL, anchors("A", "B", "C", "D"))
    by_ref = {m.ref: m for m in clusters[0].members}
    assert by_ref["A"].degree == 3
    assert by_ref["B"].degree == 1


# ─────────────────────────────────────────────────────────────────────────────
# Over-merge
# ─────────────────────────────────────────────────────────────────────────────


def test_an_oversized_component_is_reported_as_an_over_merge() -> None:
    """A 900-member cluster is a threshold set too low, not an insight. Saying
    so is more useful than rendering it as a finding."""
    links = [link("A", f"N{i}") for i in range(MODEL.max_cluster_size + 5)]
    clusters = build_clusters(links, MODEL, anchors("A", *[f"N{i}" for i in range(200)]))
    assert len(clusters) == 1
    assert clusters[0].over_merged is True
    assert "above the size at which a component stops being a finding" in clusters[0].basis()


def test_over_merged_clusters_sort_last() -> None:
    links = [link("A", f"N{i}") for i in range(MODEL.max_cluster_size + 5)]
    links += [link("X", "Y"), link("Y", "Z"), link("X", "Z")]
    refs = ["A", "X", "Y", "Z", *[f"N{i}" for i in range(200)]]
    clusters = build_clusters(links, MODEL, anchors(*refs))
    assert clusters[-1].over_merged is True
    assert clusters[0].over_merged is False


# ─────────────────────────────────────────────────────────────────────────────
# Keys
# ─────────────────────────────────────────────────────────────────────────────


def test_the_same_membership_produces_the_same_key() -> None:
    """A random id would make every run look like a set of brand-new
    discoveries, and a group could never be followed over time."""
    links = [link("A", "B"), link("B", "C"), link("A", "C")]
    first = build_clusters(links, MODEL, anchors("A", "B", "C"))
    second = build_clusters(list(reversed(links)), MODEL, anchors("A", "B", "C"))
    assert first[0].cluster_key == second[0].cluster_key


def test_a_group_that_gained_a_member_gets_a_different_key() -> None:
    """It is a different group. Reusing the key would silently rewrite the
    history of what ARGUS claimed."""
    triangle = [
        link("A", "B", strength=0.9),
        link("B", "C", strength=0.9),
        link("A", "C", strength=0.9),
    ]
    three = build_clusters(triangle, MODEL, anchors("A", "B", "C"))
    four = build_clusters(
        [*triangle, link("C", "D", strength=0.5)], MODEL, anchors("A", "B", "C", "D")
    )
    assert three[0].size == 3
    assert four[0].size == 4
    assert three[0].cluster_key != four[0].cluster_key


def test_families_are_carried_up_from_the_links() -> None:
    """A cluster resting entirely on one kind of evidence must visibly do so."""
    links = [
        link("A", "B", families=("financial",)),
        link("B", "C", families=("financial",)),
        link("A", "C", families=("financial",)),
    ]
    clusters = build_clusters(links, MODEL, anchors("A", "B", "C"))
    assert clusters[0].families == ("financial",)


def test_no_links_produces_no_clusters() -> None:
    assert build_clusters([], MODEL, {}) == []
