"""Folding the three feedback sources into a per-rule picture."""

from __future__ import annotations

from app.calibration.rules import calibrate_rules, summarise


def _disposition(rule_id="r.one", version=1, **kw):
    row = {
        "rule_id": rule_id, "rule_version": version, "alerts": 10, "still_open": 4,
        "acknowledged": 0, "investigating": 0, "resolved": 0, "dismissed": 6,
        "suppressed": 0, "firings": 25,
    }
    row.update(kw)
    return row


def test_only_false_positive_dismissals_count_against_a_rule():
    """The distinction Phase 7's vocabulary exists for.

    `known_benign` and `not_relevant` mean the rule fired correctly on a real
    pattern this deployment does not investigate. Counting them as errors would
    make a well-behaved detector look broken because of a scoping decision
    nobody made about the detector.
    """
    records = calibrate_rules(
        [_disposition(dismissed=6)],
        [
            {"rule_id": "r.one", "rule_version": 1, "dismissal_reason": "false_positive", "alerts": 2},
            {"rule_id": "r.one", "rule_version": 1, "dismissal_reason": "known_benign", "alerts": 3},
            {"rule_id": "r.one", "rule_version": 1, "dismissal_reason": "not_relevant", "alerts": 1},
        ],
        [],
    )
    rec = records[0]
    assert rec.dismissed_total == 6
    assert rec.dismissed_as_wrong == 2
    assert rec.triage_precision.successes == 4
    assert rec.triage_precision.trials == 6


def test_inconclusive_and_referred_are_excluded_from_precision_but_still_counted():
    records = calibrate_rules(
        [_disposition()],
        [],
        [
            {"rule_id": "r.one", "rule_version": 1, "outcome": "confirmed", "investigations": 3, "alerts": 3},
            {"rule_id": "r.one", "rule_version": 1, "outcome": "unfounded", "investigations": 1, "alerts": 1},
            {"rule_id": "r.one", "rule_version": 1, "outcome": "inconclusive", "investigations": 5, "alerts": 5},
            {"rule_id": "r.one", "rule_version": 1, "outcome": "referred", "investigations": 2, "alerts": 2},
        ],
    )
    rec = records[0]
    assert rec.outcome_precision.successes == 3
    assert rec.outcome_precision.trials == 4, "only the outcomes that settle the question"
    # The excluded work is published rather than discarded — the share of
    # investigations that could not decide anything is itself a finding.
    assert rec.investigations_uninformative == 7


def test_rule_versions_are_not_pooled():
    """A rule that was edited is a different detector.

    Pooling versions would let a fixed rule inherit the reputation of the one it
    replaced, in whichever direction is least useful.
    """
    records = calibrate_rules(
        [_disposition(version=1, dismissed=2), _disposition(version=2, dismissed=0)],
        [{"rule_id": "r.one", "rule_version": 1, "dismissal_reason": "false_positive", "alerts": 2}],
        [],
    )
    assert len(records) == 2
    v1 = next(r for r in records if r.rule_version == 1)
    v2 = next(r for r in records if r.rule_version == 2)
    assert v1.dismissed_as_wrong == 2
    assert v2.dismissed_as_wrong == 0


def test_a_rule_with_no_feedback_is_reported_as_unmeasured():
    records = calibrate_rules([_disposition(dismissed=0)], [], [])
    rec = records[0]
    assert not rec.has_feedback
    # Not zero precision. Nothing has come back about it, which is different
    # from everything that came back being bad.
    assert rec.outcome_precision.point is None
    assert rec.triage_precision.point is None


def test_the_summary_says_how_much_is_unmeasured():
    records = calibrate_rules(
        [_disposition(rule_id="r.one", dismissed=0), _disposition(rule_id="r.two", dismissed=3)],
        [{"rule_id": "r.two", "rule_version": 1, "dismissal_reason": "false_positive", "alerts": 3}],
        [],
    )
    summary = summarise(records)
    assert summary["rules"] == 2
    assert summary["rules_with_any_feedback"] == 1
    assert summary["rules_without_feedback"] == 1
    assert "unmeasured" in summary["coverage_note"]


def test_the_pooled_figure_warns_that_it_is_dominated_by_volume():
    summary = summarise(calibrate_rules([_disposition()], [], []))
    assert "dominates" in summary["pooling_note"]


def test_the_two_precisions_are_kept_apart():
    """They have different denominators and answer different questions."""
    records = calibrate_rules(
        [_disposition(dismissed=4)],
        [{"rule_id": "r.one", "rule_version": 1, "dismissal_reason": "false_positive", "alerts": 4}],
        [{"rule_id": "r.one", "rule_version": 1, "outcome": "confirmed", "investigations": 2, "alerts": 2}],
    )
    payload = records[0].as_dict()
    assert payload["triage"]["precision"]["trials"] == 4
    assert payload["outcomes"]["precision"]["trials"] == 2
    assert payload["triage"]["precision"] is not payload["outcomes"]["precision"]
