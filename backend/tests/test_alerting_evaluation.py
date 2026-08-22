"""Scoring the rule set, and refusing to publish one flattering number."""

from __future__ import annotations

from app.alerting.evaluation import UNREACHABLE_BY_DESIGN, evaluate_alerts


def alert(rule_id="assessment.elevated", scope=("PRS-1",)):
    return {"rule_id": rule_id, "scope": list(scope)}


def test_precision_is_labelled_strict_and_explained() -> None:
    report = evaluate_alerts([alert()], [("communication_cluster", ("PRS-1",))]).to_dict()
    assert report["precision_strict"] == 1.0
    assert "floor" in report["precision_note"]
    assert "precision" not in {k for k in report if k == "precision"}


def test_an_unlabelled_alert_is_counted_against_strict_precision() -> None:
    report = evaluate_alerts([alert(scope=("PRS-9",))], [("communication_cluster", ("PRS-1",))])
    assert report.precision_strict == 0.0
    assert report.unlabelled_share == 1.0


def test_recall_excludes_storylines_nothing_could_reach() -> None:
    """Otherwise a property of the admissibility boundary is folded into a
    number that reads as rule quality."""
    storylines = [
        ("communication_cluster", ("PRS-1",)),
        ("identity_overlap", ("PRS-7", "PRS-8")),
    ]
    report = evaluate_alerts([alert(scope=("PRS-1",))], storylines)
    assert report.storyline_subjects_total == 1
    assert report.recall == 1.0


def test_unreachable_storylines_are_named_not_hidden() -> None:
    report = evaluate_alerts([alert()], [("identity_overlap", ("PRS-7",))]).to_dict()
    assert "identity_overlap" in report["unreachable_by_design"]
    entry = next(x for x in report["per_storyline"] if x["storyline_type"] == "identity_overlap")
    assert entry["reachable"] is False
    assert entry["reach_note"] and "SHARES_DEVICE" in entry["reach_note"]


def test_non_assessable_members_are_excluded_from_recall() -> None:
    """A storyline planting only documents can contribute nothing, and counting
    them would measure the ontology rather than the rules."""
    report = evaluate_alerts([], [("document_forgery_ring", ("DOC-1", "DOC-2"))])
    assert report.storyline_subjects_total == 0
    assert report.recall is None


def test_per_rule_precision_is_reported_separately() -> None:
    """The total is dominated by whichever rule fires most; a small rule with
    perfect precision is invisible in the aggregate."""
    alerts = [
        alert("assessment.elevated", ("PRS-9",)),
        alert("assessment.elevated", ("PRS-8",)),
        alert("convergence.assessed_cluster", ("PRS-1",)),
    ]
    report = evaluate_alerts(alerts, [("communication_cluster", ("PRS-1",))]).to_dict()
    by_rule = {r["rule_id"]: r for r in report["per_rule"]}
    assert by_rule["assessment.elevated"]["precision_strict"] == 0.0
    assert by_rule["convergence.assessed_cluster"]["precision_strict"] == 1.0


def test_empty_alert_set_reports_none_not_zero() -> None:
    """No alerts is not the same as perfectly wrong alerts."""
    report = evaluate_alerts([], [("communication_cluster", ("PRS-1",))])
    assert report.precision_strict is None
    assert report.recall == 0.0


def test_multi_subject_alert_counts_every_subject() -> None:
    report = evaluate_alerts(
        [alert("convergence.assessed_cluster", ("PRS-1", "PRS-2", "PRS-9"))],
        [("communication_cluster", ("PRS-1", "PRS-2"))],
    )
    assert report.subjects_alerted == 3
    assert report.subjects_labelled == 2


def test_report_states_it_does_not_measure_usefulness() -> None:
    report = evaluate_alerts([alert()], []).to_dict()
    assert "useful" in report["outcome_note"]


def test_every_unreachable_entry_has_a_reason() -> None:
    for storyline_type, reason in UNREACHABLE_BY_DESIGN.items():
        assert len(reason) > 80, f"{storyline_type} is excluded without an explanation"
