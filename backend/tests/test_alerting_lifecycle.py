"""The state machine, and the vocabulary that makes dismissals countable."""

from __future__ import annotations

import pytest

from app.alerting.lifecycle import (
    ALERT_STATES,
    DISMISSAL_REASONS,
    STATE_MEANING,
    TERMINAL_STATES,
    TRANSITIONS,
    InvalidTransition,
    check_transition,
    requires_reason,
)


def test_every_state_has_a_meaning() -> None:
    assert set(STATE_MEANING) == set(ALERT_STATES)
    for state, meaning in STATE_MEANING.items():
        assert len(meaning) > 30, f"{state} has no usable explanation"


def test_every_state_is_reachable_from_open() -> None:
    """A state nothing can reach is dead, and a UI offering it would lie."""
    seen, frontier = {"open"}, ["open"]
    while frontier:
        for nxt in TRANSITIONS.get(frontier.pop(), frozenset()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    assert seen == set(ALERT_STATES), f"unreachable states: {set(ALERT_STATES) - seen}"


def test_no_state_is_a_dead_end() -> None:
    """Terminal is not final. An alert closed in error needs a route back that
    is not a database console."""
    for state in ALERT_STATES:
        assert TRANSITIONS.get(state), f"{state} has no exit"


@pytest.mark.parametrize("terminal", sorted(TERMINAL_STATES))
def test_terminal_states_can_be_reopened(terminal: str) -> None:
    assert "open" in TRANSITIONS[terminal] or "investigating" in TRANSITIONS[terminal]


def test_open_cannot_jump_straight_to_resolved() -> None:
    with pytest.raises(InvalidTransition) as exc:
        check_transition("open", "resolved", None)
    assert "cannot move straight to" in str(exc.value)
    # The message names what *is* reachable, rather than saying "invalid".
    assert "acknowledged" in str(exc.value)


def test_transition_to_the_same_state_is_refused() -> None:
    with pytest.raises(InvalidTransition, match="already"):
        check_transition("open", "open", None)


def test_unknown_state_is_refused_and_lists_the_valid_ones() -> None:
    with pytest.raises(InvalidTransition) as exc:
        check_transition("open", "Closed", None)
    assert "is not an alert state" in str(exc.value)
    assert "dismissed" in str(exc.value)


def test_dismissal_without_a_reason_is_refused() -> None:
    with pytest.raises(InvalidTransition, match="requires a reason"):
        check_transition("open", "dismissed", None)


def test_dismissal_with_an_invented_reason_is_refused() -> None:
    with pytest.raises(InvalidTransition, match="is not a dismissal reason"):
        check_transition("open", "dismissed", "because_i_said_so")


def test_dismissal_with_a_vocabulary_reason_is_allowed() -> None:
    check_transition("open", "dismissed", "known_benign")


def test_only_dismissal_requires_a_reason() -> None:
    assert requires_reason("dismissed")
    for state in set(ALERT_STATES) - {"dismissed"}:
        assert not requires_reason(state)


def test_reasons_separate_rule_error_from_scope() -> None:
    """The distinction the vocabulary exists for. Counting `known_benign`
    against precision would make a correct rule look broken."""
    by_code = {r.code: r for r in DISMISSAL_REASONS}
    assert by_code["false_positive"].counts_as_false_positive is True
    assert by_code["known_benign"].counts_as_false_positive is False
    assert by_code["not_relevant"].counts_as_false_positive is False


def test_reason_codes_are_unique_and_explained() -> None:
    codes = [r.code for r in DISMISSAL_REASONS]
    assert len(set(codes)) == len(codes)
    for reason in DISMISSAL_REASONS:
        assert len(reason.means) > 30, f"{reason.code} is unexplained"
