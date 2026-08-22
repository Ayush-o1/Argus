"""What states an investigation can be in, and what may legally follow what.

Three states, and the shortness of that list is deliberate. Phase 7's alert
lifecycle has five because an alert passes through several hands before anyone
commits to it. An investigation has already been committed to by the act of
opening one, so the states that remain are: nobody has started, someone is
working it, and it has a conclusion.

## What was left out, and why

`on_hold` was considered and rejected. An investigation waiting on an external
party is a real situation, but nothing in ARGUS would act on the state — no
reminder, no escalation, no report that reads it. It would be a label an analyst
sets and nothing observes, and a state that exists only to be displayed is worse
than a note saying the same thing, because it looks like a mechanism.

`pending_review` was rejected for a different reason: review happens *after*
closure, on a conclusion that already exists. Modelling it as a state before
`closed` would mean an investigation whose work is finished and whose outcome is
recorded is still described as open, which makes every queue count wrong.

## The one asymmetry

Closing requires an outcome; the database enforces it. Reopening does not
require anything except a reason, because an investigation that was closed in
error must always have a route back that does not involve a database console —
the same principle as Phase 7's terminal states, and for the same reason.
"""

from __future__ import annotations

__all__ = [
    "INVESTIGATION_STATES",
    "STATE_MEANING",
    "TRANSITIONS",
    "InvalidTransition",
    "check_transition",
]

STATE_OPEN = "open"
STATE_ACTIVE = "active"
STATE_CLOSED = "closed"

INVESTIGATION_STATES: tuple[str, ...] = (STATE_OPEN, STATE_ACTIVE, STATE_CLOSED)

STATE_MEANING: dict[str, str] = {
    STATE_OPEN: (
        "Opened with a hypothesis, and not yet worked. An investigation sitting "
        "here is a question nobody has started answering."
    ),
    STATE_ACTIVE: "Being worked. Findings are being recorded against it.",
    STATE_CLOSED: (
        "Worked to a conclusion, with an outcome and the reasoning behind it. "
        "Not final — it can be reopened, and the record shows both."
    ),
}

TRANSITIONS: dict[str, frozenset[str]] = {
    STATE_OPEN: frozenset({STATE_ACTIVE, STATE_CLOSED}),
    STATE_ACTIVE: frozenset({STATE_OPEN, STATE_CLOSED}),
    # Reopening always available. New evidence arrives.
    STATE_CLOSED: frozenset({STATE_ACTIVE}),
}


class InvalidTransition(ValueError):
    """Carries both states so the API can say what was attempted."""

    def __init__(self, current: str, requested: str, detail: str) -> None:
        self.current = current
        self.requested = requested
        super().__init__(detail)


def check_transition(current: str, requested: str) -> None:
    """Raise `InvalidTransition` unless the move is legal.

    Whether the *closure* is fully specified — outcome and rationale present —
    is checked by the database, not here. Both checks exist: this one so the API
    can explain itself, that one so it cannot be bypassed.
    """
    if requested not in INVESTIGATION_STATES:
        raise InvalidTransition(
            current,
            requested,
            f"{requested!r} is not an investigation state. Valid: " + ", ".join(INVESTIGATION_STATES) + ".",
        )
    if current == requested:
        raise InvalidTransition(current, requested, f"Already {current!r}; nothing would change.")
    allowed = TRANSITIONS.get(current, frozenset())
    if requested not in allowed:
        raise InvalidTransition(
            current,
            requested,
            f"An investigation that is {current!r} cannot move to {requested!r}. "
            f"From here: {', '.join(sorted(allowed))}.",
        )
