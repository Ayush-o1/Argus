"""Dedup identity and grouping."""

from __future__ import annotations

from app.alerting.evidence import AlertingEvidence, ClusterFinding
from app.alerting.identity import alert_key, group_firings
from app.alerting.rules import RuleFiring


def firing(rule_id="r.a", version=1, scope=("A",)):
    return RuleFiring(
        rule_id=rule_id, rule_version=version, scope=scope,
        title="t", summary="s", magnitude=0.5, confidence=0.5,
    )


def test_same_finding_yields_the_same_key() -> None:
    assert alert_key("r.a", 1, ("A", "B")) == alert_key("r.a", 1, ("A", "B"))


def test_scope_order_does_not_change_the_key() -> None:
    assert alert_key("r.a", 1, ("A", "B")) == alert_key("r.a", 1, ("B", "A"))


def test_a_new_rule_version_is_a_new_alert() -> None:
    """Folding a re-versioned rule's firings into the old alert's count would
    mix two measurements, which calibration cannot recover from later."""
    assert alert_key("r.a", 1, ("A",)) != alert_key("r.a", 2, ("A",))


def test_different_rules_on_one_subject_are_different_alerts() -> None:
    assert alert_key("r.a", 1, ("A",)) != alert_key("r.b", 1, ("A",))


def test_different_scopes_are_different_alerts() -> None:
    assert alert_key("r.a", 1, ("A",)) != alert_key("r.a", 1, ("A", "B"))


def test_alerts_about_one_cluster_share_a_group() -> None:
    ev = AlertingEvidence(clusters=[ClusterFinding("ck", ("A", "B", "C"), 3, ("financial",), 0.8)])
    groups, assignment = group_firings(
        [firing(scope=("A",)), firing(rule_id="r.b", scope=("B",)), firing(rule_id="r.c", scope=("A", "B", "C"))],
        ev,
    )
    assert len(groups) == 1
    assert len(set(assignment.values())) == 1


def test_uncorrelated_subjects_are_not_forced_together() -> None:
    """Grouping them would invent a relationship. Two subjects ARGUS could not
    connect are two things to look at."""
    groups, _ = group_firings([firing(scope=("A",)), firing(rule_id="r.b", scope=("B",))], AlertingEvidence())
    assert len(groups) == 2


def test_grouping_does_not_chain_through_shared_subjects() -> None:
    """The failure mode transitive closure has, and the reason clusters are
    reused instead: {A,B}, {B,C}, {C,D} would merge into one group whose ends
    have nothing in common."""
    groups, _ = group_firings(
        [firing(scope=("A", "B")), firing(rule_id="r.b", scope=("B", "C")), firing(rule_id="r.c", scope=("C", "D"))],
        AlertingEvidence(),
    )
    assert len(groups) == 3


def test_group_assignment_is_deterministic_across_two_clusters() -> None:
    ev = AlertingEvidence(
        clusters=[
            ClusterFinding("z-cluster", ("A",), 1, ("financial",), 0.5),
            ClusterFinding("a-cluster", ("B",), 1, ("social",), 0.5),
        ]
    )
    first, _ = group_firings([firing(scope=("A", "B"))], ev)
    second, _ = group_firings([firing(scope=("B", "A"))], ev)
    assert list(first) == list(second)


def test_group_records_why_it_exists() -> None:
    ev = AlertingEvidence(clusters=[ClusterFinding("ck", ("A", "B"), 2, ("financial",), 0.8)])
    groups, _ = group_firings([firing(scope=("A",))], ev)
    group = next(iter(groups.values()))
    assert group.basis.startswith("cluster:")
    assert "correlated" in group.describe()


def test_a_lone_alert_is_not_described_as_a_group() -> None:
    """Calling one uncorrelated alert a "group" overstates what was found."""
    groups, _ = group_firings([firing(scope=("A",))], AlertingEvidence())
    text = next(iter(groups.values())).describe()
    assert "One alert" in text
    assert "could not connect" in text


def test_group_description_pluralises() -> None:
    ev = AlertingEvidence(clusters=[ClusterFinding("ck", ("A", "B"), 2, ("financial",), 0.8)])
    groups, _ = group_firings(
        [firing(scope=("A",)), firing(rule_id="r.b", scope=("B",))], ev
    )
    assert "2 alerts" in next(iter(groups.values())).describe()


def test_repeated_identical_firings_collapse_to_one_alert() -> None:
    groups, assignment = group_firings([firing(), firing()], AlertingEvidence())
    assert len(assignment) == 1
    assert sum(g.size for g in groups.values()) == 1
