"""Replaying the rules under a candidate configuration, without activating it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.alerting.evidence import AlertingEvidence, AssessmentFinding, ClusterFinding
from app.alerting.identity import alert_key
from app.alerting.rules import DEFAULT_PARAMS, RuleParams, evaluate_rules
from app.calibration.simulation import simulate

NOW = datetime(2031, 6, 1, tzinfo=UTC)


def finding(ref: str, band: str, *, coverage=0.8, previous=None):
    return AssessmentFinding(
        subject_ref=ref,
        subject_type="Person",
        band=band,
        score=80.0,
        evidence_coverage=coverage,
        families_fired=("financial",),
        computed_at=NOW,
        run_id=1,
        model_fingerprint="fp",
        previous_band=previous,
        previous_computed_at=NOW - timedelta(days=7) if previous else None,
        signals=(("s1", "financial", 0.6, "a reason"),),
    )


def world() -> AlertingEvidence:
    """Two elevated subjects, one notable, and a cluster containing all three."""
    return AlertingEvidence(
        assessments={
            "PRS-1": finding("PRS-1", "elevated"),
            "PRS-2": finding("PRS-2", "elevated"),
            "PRS-3": finding("PRS-3", "notable"),
        },
        clusters=[
            ClusterFinding(
                cluster_key="c1",
                members=("PRS-1", "PRS-2", "PRS-3"),
                size=3,
                families=("financial",),
                weakest_bridge=0.6,
            )
        ],
    )


def current_keys(evidence: AlertingEvidence) -> set[str]:
    return {
        alert_key(f.rule_id, f.rule_version, tuple(f.scope))
        for f in evaluate_rules(evidence)
    }


def test_the_default_parameters_change_nothing():
    """The refactor that made thresholds data must not have changed behaviour.

    `evaluate_rules(evidence)` with no parameters has to be the identical
    computation it was before this phase, or every precision figure already
    published against the rules fingerprint would silently refer to a different
    detector.
    """
    ev = world()
    result = simulate(ev, DEFAULT_PARAMS, current_alert_keys=current_keys(ev))
    assert result.changes == []
    assert result.added == []
    assert result.removed_keys == []
    assert result.current_total == result.candidate_total


def test_raising_the_convergence_threshold_removes_the_convergence_alert():
    ev = world()
    strict = RuleParams(convergence_min_assessed=4)
    result = simulate(ev, strict, current_alert_keys=current_keys(ev))
    assert "convergence_min_assessed: 2 → 4" in result.changes
    assert result.removed_keys, "the cluster alert should stop firing"
    assert result.added == []


def test_widening_a_band_adds_alerts():
    ev = world()
    wide = RuleParams(elevated_band="notable")
    result = simulate(ev, wide, current_alert_keys=current_keys(ev))
    assert result.added, "PRS-3 should now trip the elevated rule"
    assert any(a.scope == ("PRS-3",) for a in result.added)


def test_a_removed_alert_is_joined_to_what_analysts_concluded_about_it():
    """The part that makes a simulation worth running.

    A change that removes forty alerts is good or catastrophic depending
    entirely on which forty. Counting them is easy and nearly useless; saying
    that two of them were confirmed by an investigation is the finding.
    """
    ev = world()
    keys = current_keys(ev)
    convergence_key = next(
        k
        for k in keys
        if k == alert_key("convergence.assessed_cluster", 1, ("PRS-1", "PRS-2", "PRS-3"))
    )
    result = simulate(
        ev,
        RuleParams(convergence_min_assessed=4),
        current_alert_keys=keys,
        dismissal_by_key={},
        confirmed_keys={convergence_key},
    )
    assert convergence_key in result.removed_with_confirmed_outcome
    payload = result.as_dict()
    assert payload["removed_with_confirmed_outcome"] == [convergence_key]
    assert "not the finding" in payload["read_the_removals_first"]


def test_dismissal_reasons_on_removed_alerts_are_tallied():
    ev = world()
    keys = current_keys(ev)
    a_key = sorted(keys)[0]
    result = simulate(
        ev,
        RuleParams(convergence_min_assessed=99, elevated_band="nothing"),
        current_alert_keys=keys,
        dismissal_by_key={a_key: "false_positive"},
    )
    assert result.feedback_on_removed.get("false_positive") == 1


def test_the_simulation_refuses_to_estimate_the_new_alerts():
    """Nobody has triaged them, so there is no honest figure to give."""
    ev = world()
    payload = simulate(
        ev, RuleParams(elevated_band="notable"), current_alert_keys=current_keys(ev)
    ).as_dict()
    assert "does not say" in " ".join(payload.keys()).replace("_", " ")
    assert "invented" in payload["what_this_does_not_say"]
    assert "precision" not in {k.lower() for k in payload}


def test_the_diff_is_against_the_live_queue_not_a_re_simulated_baseline():
    """So drift between the code and the rows it already wrote cannot hide.

    An alert key that exists in the database but that no current rule produces
    must show up as a removal, not be quietly cancelled out.
    """
    ev = world()
    stale = "a" * 32
    result = simulate(ev, DEFAULT_PARAMS, current_alert_keys=current_keys(ev) | {stale})
    assert stale in result.removed_keys
