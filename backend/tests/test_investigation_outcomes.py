"""The two vocabularies an investigation closes on.

These are small tests over a small module, and they are here because the module
is the input to every measurement the next phase will make. A quiet change to
`counts_as_correct` would silently rewrite ARGUS's opinion of its own detectors.
"""

from __future__ import annotations

import pytest

from app.investigation.lifecycle import (
    INVESTIGATION_STATES,
    STATE_MEANING,
    TRANSITIONS,
    InvalidTransition,
    check_transition,
)
from app.investigation.outcomes import (
    CONFIDENCE_LEVELS,
    CONFIDENCE_MEANING,
    OUTCOME_CODES,
    OUTCOMES,
    counts_as_correct,
    outcome_by_code,
)


def test_the_four_outcomes_are_the_ones_the_database_accepts():
    # The CHECK constraint in migration 009 lists these by hand. If the two ever
    # disagree, the API offers an outcome the database rejects — a 500 at the
    # moment an analyst tries to finish their work.
    assert OUTCOME_CODES == {"confirmed", "unfounded", "inconclusive", "referred"}


def test_only_confirmed_and_unfounded_say_anything_about_the_rule():
    # The distinction the whole vocabulary exists for. `inconclusive` is a
    # statement about the evidence and `referred` about jurisdiction; neither is
    # evidence that the detector was right or wrong.
    assert counts_as_correct("confirmed") is True
    assert counts_as_correct("unfounded") is False
    assert counts_as_correct("inconclusive") is None
    assert counts_as_correct("referred") is None


def test_inconclusive_is_not_a_soft_unfounded():
    # Getting this wrong in the obvious direction would make every detector look
    # worse the less data ARGUS holds, which is exactly backwards.
    assert counts_as_correct("inconclusive") is not False


def test_every_outcome_explains_itself():
    for outcome in OUTCOMES:
        assert outcome.means.strip()
        assert outcome.label.strip()


def test_an_unknown_outcome_is_refused_by_name():
    with pytest.raises(ValueError, match="not an investigation outcome"):
        outcome_by_code("probably")


def test_confidence_is_ordinal_and_has_no_numeric_equivalent():
    assert CONFIDENCE_LEVELS == ("low", "moderate", "high")
    assert set(CONFIDENCE_MEANING) == set(CONFIDENCE_LEVELS)
    # Nothing in the module offers a number for a confidence level. An analytic
    # judgement expressed as 0.7 invites arithmetic that the scale cannot bear.
    import app.investigation.outcomes as module

    assert not any(
        isinstance(getattr(module, name), dict)
        and any(isinstance(v, int | float) for v in getattr(module, name).values())
        for name in dir(module)
        if not name.startswith("_")
    )


class TestLifecycle:
    def test_the_states_are_the_ones_the_database_accepts(self):
        assert set(INVESTIGATION_STATES) == {"open", "active", "closed"}
        assert set(STATE_MEANING) == set(INVESTIGATION_STATES)

    def test_a_closed_investigation_can_always_be_reopened(self):
        # No one-way doors, for the same reason Phase 7 gave for alerts: new
        # evidence arrives, and a conclusion reached in error needs a route back
        # that is not a database console.
        check_transition("closed", "active")

    def test_an_invented_state_is_refused_with_the_valid_ones(self):
        with pytest.raises(InvalidTransition) as exc:
            check_transition("open", "on_hold")
        assert "open, active, closed" in str(exc.value)

    def test_a_no_op_transition_is_refused(self):
        with pytest.raises(InvalidTransition, match="nothing would change"):
            check_transition("active", "active")

    def test_reopening_does_not_jump_straight_back_to_open(self):
        # `closed -> open` would claim nobody had ever worked it.
        with pytest.raises(InvalidTransition):
            check_transition("closed", "open")

    def test_every_state_is_reachable_and_can_be_left(self):
        reachable = {t for targets in TRANSITIONS.values() for t in targets}
        for state in INVESTIGATION_STATES:
            assert TRANSITIONS[state], f"{state} is a dead end"
            if state != "open":
                assert state in reachable, f"{state} cannot be reached"
