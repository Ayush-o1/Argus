"""Whether the assessor's output shifted between runs — and what that can mean."""

from __future__ import annotations

from datetime import UTC, datetime

from app.calibration.drift import compare_runs

T = datetime(2031, 6, 1, tzinfo=UTC)


def run(run_id, fingerprint, elevated, notable, routine, insufficient):
    return {
        "run_id": run_id,
        "model_version": "v1",
        "model_fingerprint": fingerprint,
        "started_at": T,
        "finished_at": T,
        "subjects_assessed": elevated + notable + routine + insufficient,
        "elevated_count": elevated,
        "notable_count": notable,
        "routine_count": routine,
        "insufficient_count": insufficient,
    }


def test_an_unchanged_distribution_shows_no_shift():
    c = compare_runs(run(1, "fp", 90, 400, 4000, 2700), run(2, "fp", 92, 396, 4010, 2690))
    assert c.evaluable
    assert not c.shifted
    assert "No detectable shift" in c.describe()


def test_a_large_change_is_detected():
    c = compare_runs(run(1, "fp", 90, 400, 4000, 2700), run(2, "fp", 900, 400, 3200, 2700))
    assert c.shifted


def test_a_shift_across_different_models_is_not_called_drift():
    """The most likely misreading, headed off in the text rather than by a flag.

    A new model producing a different distribution is the model working, not
    drifting. The report says so instead of leaving a reader to infer it from
    two fingerprints printed nearby.
    """
    c = compare_runs(run(1, "fp-old", 90, 400, 4000, 2700), run(2, "fp-new", 900, 400, 3200, 2700))
    assert c.shifted
    assert not c.same_model
    assert "not evidence of drift" in c.describe()


def test_a_shift_within_one_model_names_the_two_remaining_causes():
    c = compare_runs(run(1, "fp", 90, 400, 4000, 2700), run(2, "fp", 900, 400, 3200, 2700))
    assert c.same_model
    assert "population or the evidence" in c.describe()


def test_the_report_states_what_the_test_cannot_separate():
    c = compare_runs(run(1, "fp", 90, 400, 4000, 2700), run(2, "fp", 92, 396, 4010, 2690))
    payload = c.as_dict()
    assert "cannot separate" in payload["cannot_distinguish"]
    assert payload["earlier_fingerprint"] and payload["later_fingerprint"]


def test_an_empty_run_is_not_evaluable_rather_than_unchanged():
    c = compare_runs(run(1, "fp", 0, 0, 0, 0), run(2, "fp", 10, 20, 30, 40))
    assert not c.evaluable
    assert not c.shifted
    assert c.reason and "assessed nobody" in c.reason


def test_shares_are_published_alongside_the_counts():
    c = compare_runs(run(1, "fp", 100, 100, 100, 100), run(2, "fp", 200, 200, 200, 200))
    shares = c.shares
    assert shares["earlier"]["elevated"] == 0.25
    assert shares["later"]["elevated"] == 0.25
    # Identical shares over doubled counts: the distribution did not move even
    # though every count did.
    assert not c.shifted
