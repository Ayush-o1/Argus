"""What each rule fires on, and — more importantly — what it does not."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.alerting.evidence import AlertingEvidence, AssessmentFinding, ClusterFinding, LinkFinding
from app.alerting.rules import RULES, evaluate_rules, rules_fingerprint

NOW = datetime(2026, 8, 18, tzinfo=UTC)


def finding(ref: str, band: str, *, score=80.0, coverage=0.8, previous=None, families=("financial",)):
    return AssessmentFinding(
        subject_ref=ref,
        subject_type="Person",
        band=band,
        score=score,
        evidence_coverage=coverage,
        families_fired=tuple(families),
        computed_at=NOW,
        run_id=1,
        model_fingerprint="fp",
        previous_band=previous,
        previous_computed_at=NOW - timedelta(days=7) if previous else None,
        signals=(("s1", "financial", 0.6, "a reason"),),
    )


def fired(evidence: AlertingEvidence, rule_id: str):
    return [f for f in evaluate_rules(evidence) if f.rule_id == rule_id]


# ── assessment.elevated ──────────────────────────────────────────────────────


def test_elevated_fires_on_elevated_only() -> None:
    ev = AlertingEvidence(
        assessments={
            "PRS-1": finding("PRS-1", "elevated"),
            "PRS-2": finding("PRS-2", "notable"),
            "PRS-3": finding("PRS-3", "clear"),
        }
    )
    out = fired(ev, "assessment.elevated")
    assert [f.scope for f in out] == [("PRS-1",)]


def test_elevated_carries_the_signals_behind_it() -> None:
    ev = AlertingEvidence(assessments={"PRS-1": finding("PRS-1", "elevated")})
    firing = fired(ev, "assessment.elevated")[0]
    assert firing.evidence["signals"][0]["summary"] == "a reason"
    assert firing.confidence == 0.8


def test_elevated_summary_pluralises_correctly() -> None:
    """It reads "1 family", not "1 families". A summary an analyst reads a
    hundred times a day should not be ungrammatical a hundred times a day."""
    one = fired(
        AlertingEvidence(assessments={"P": finding("P", "elevated", families=("financial",))}),
        "assessment.elevated",
    )[0]
    many = fired(
        AlertingEvidence(
            assessments={"P": finding("P", "elevated", families=("financial", "social"))}
        ),
        "assessment.elevated",
    )[0]
    assert "1 family of evidence" in one.summary
    assert "2 families of evidence" in many.summary


def test_elevated_magnitude_tracks_score_not_band() -> None:
    low = fired(AlertingEvidence(assessments={"P": finding("P", "elevated", score=55)}), "assessment.elevated")[0]
    high = fired(AlertingEvidence(assessments={"P": finding("P", "elevated", score=95)}), "assessment.elevated")[0]
    assert high.magnitude > low.magnitude


# ── correlation.established_pair ─────────────────────────────────────────────


def test_established_pair_fires_only_on_established_tier() -> None:
    ev = AlertingEvidence(
        links=[
            LinkFinding("A", "B", "established", 0.9, 0.7, ("financial", "social")),
            LinkFinding("C", "D", "probable", 0.8, 0.7, ("financial",)),
            LinkFinding("E", "F", "possible", 0.4, 0.7, ()),
        ]
    )
    out = fired(ev, "correlation.established_pair")
    assert [f.scope for f in out] == [("A", "B")]


# ── convergence.assessed_cluster ─────────────────────────────────────────────


def test_convergence_needs_two_independently_assessed_members() -> None:
    cluster = ClusterFinding("ck", ("A", "B", "C"), 3, ("financial",), 0.8)
    one = AlertingEvidence(assessments={"A": finding("A", "elevated")}, clusters=[cluster])
    two = AlertingEvidence(
        assessments={"A": finding("A", "elevated"), "B": finding("B", "notable")},
        clusters=[cluster],
    )
    assert fired(one, "convergence.assessed_cluster") == []
    assert len(fired(two, "convergence.assessed_cluster")) == 1


def test_convergence_ignores_cleared_members() -> None:
    cluster = ClusterFinding("ck", ("A", "B"), 2, ("financial",), 0.8)
    ev = AlertingEvidence(
        assessments={"A": finding("A", "elevated"), "B": finding("B", "clear")},
        clusters=[cluster],
    )
    assert fired(ev, "convergence.assessed_cluster") == []


def test_convergence_magnitude_is_share_of_group_not_count() -> None:
    """Two of three is a stronger claim than two of twelve, and the magnitude
    has to say so — otherwise a big loose cluster outranks a tight one."""
    tight = AlertingEvidence(
        assessments={"A": finding("A", "elevated"), "B": finding("B", "elevated")},
        clusters=[ClusterFinding("k1", ("A", "B", "C"), 3, ("financial",), 0.8)],
    )
    loose = AlertingEvidence(
        assessments={"A": finding("A", "elevated"), "B": finding("B", "elevated")},
        clusters=[ClusterFinding("k2", tuple("ABCDEFGHIJKL"), 12, ("financial",), 0.8)],
    )
    assert (
        fired(tight, "convergence.assessed_cluster")[0].magnitude
        > fired(loose, "convergence.assessed_cluster")[0].magnitude
    )


def test_convergence_scope_is_the_whole_cluster() -> None:
    ev = AlertingEvidence(
        assessments={"A": finding("A", "elevated"), "B": finding("B", "elevated")},
        clusters=[ClusterFinding("k", ("A", "B", "C"), 3, ("financial",), 0.8)],
    )
    assert fired(ev, "convergence.assessed_cluster")[0].scope == ("A", "B", "C")


# ── assessment.escalated ─────────────────────────────────────────────────────
#
# The live world is static — no subject has ever changed band across runs — so
# this rule fires zero times against real data. That is a fact about the data,
# not evidence the rule works, which is why it is exercised properly here.


def test_escalation_fires_on_upward_movement() -> None:
    ev = AlertingEvidence(assessments={"P": finding("P", "elevated", previous="notable")})
    out = fired(ev, "assessment.escalated")
    assert len(out) == 1
    assert out[0].evidence["previous_band"] == "notable"
    assert out[0].evidence["band"] == "elevated"


def test_escalation_does_not_fire_on_a_first_ever_assessment() -> None:
    """Arrival is not escalation. A subject first seen at `elevated` has not
    moved, and reporting it as movement would invent a history."""
    ev = AlertingEvidence(assessments={"P": finding("P", "elevated", previous=None)})
    assert fired(ev, "assessment.escalated") == []


def test_escalation_does_not_fire_on_a_steady_band() -> None:
    ev = AlertingEvidence(assessments={"P": finding("P", "elevated", previous="elevated")})
    assert fired(ev, "assessment.escalated") == []


def test_escalation_does_not_fire_on_downward_movement() -> None:
    ev = AlertingEvidence(assessments={"P": finding("P", "notable", previous="elevated")})
    assert fired(ev, "assessment.escalated") == []


def test_escalation_ignores_movement_into_an_uninteresting_band() -> None:
    """clear -> notable is movement, but alerting on it buries the queue in
    subjects that merely stopped being silent."""
    ev = AlertingEvidence(assessments={"P": finding("P", "clear", previous="insufficient_evidence")})
    assert fired(ev, "assessment.escalated") == []


def test_escalation_fires_from_insufficient_evidence_to_elevated() -> None:
    ev = AlertingEvidence(
        assessments={"P": finding("P", "elevated", previous="insufficient_evidence")}
    )
    assert len(fired(ev, "assessment.escalated")) == 1


def test_escalation_magnitude_grows_with_distance_moved() -> None:
    small = fired(
        AlertingEvidence(assessments={"P": finding("P", "elevated", previous="notable")}),
        "assessment.escalated",
    )[0]
    large = fired(
        AlertingEvidence(assessments={"P": finding("P", "elevated", previous="insufficient_evidence")}),
        "assessment.escalated",
    )[0]
    assert large.magnitude > small.magnitude


def test_escalation_ignores_an_unknown_band() -> None:
    """A band this rule does not recognise must not be ranked against known
    ones — comparing it would produce an ordering nobody defined."""
    ev = AlertingEvidence(assessments={"P": finding("P", "elevated", previous="something_else")})
    assert fired(ev, "assessment.escalated") == []


# ── registry ─────────────────────────────────────────────────────────────────


def test_fingerprint_is_stable_across_calls() -> None:
    assert rules_fingerprint() == rules_fingerprint()


def test_fingerprint_ignores_prose_but_not_substance() -> None:
    rule = RULES[0]
    identity = rule.identity()
    assert "title" not in identity and "means" not in identity
    assert {"rule_id", "version", "reads", "independent_methods"} <= set(identity)


def test_scope_key_is_order_independent() -> None:
    ev_ab = AlertingEvidence(links=[LinkFinding("A", "B", "established", 0.9, 0.7, ("financial",))])
    ev_ba = AlertingEvidence(links=[LinkFinding("B", "A", "established", 0.9, 0.7, ("financial",))])
    a = fired(ev_ab, "correlation.established_pair")[0].scope_key
    b = fired(ev_ba, "correlation.established_pair")[0].scope_key
    assert a == b


def test_no_rule_fires_on_empty_evidence() -> None:
    assert evaluate_rules(AlertingEvidence()) == []
