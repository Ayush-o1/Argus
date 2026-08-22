"""What states an alert can be in, and what may legally follow what.

Before this phase the whole lifecycle was `SET i.status = $status` against a
generator-written node, with no validation (audit B-13), no attribution and no
record. A typo set a status no filter matched, which removed the alert from
every queue with no way back — the UI can only offer the statuses it knows
about.

Three things are enforced here rather than in the route:

  - **transitions are a graph, not a free assignment.** `open -> closed` is not
    reachable without passing through triage; `dismissed -> open` is reachable,
    because reopening a dismissal must always be possible.
  - **dismissal requires a reason from a fixed vocabulary.** A free-text
    dismissal reason cannot be counted, so a rule that is dismissed a thousand
    times for the same reason looks exactly like a rule that is dismissed a
    thousand times for a thousand reasons. Calibration needs the difference.
  - **terminal states are not final.** Nothing here is a one-way door; an alert
    resolved in error can be reopened, and the record shows both.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ALERT_STATES",
    "DISMISSAL_REASONS",
    "STATE_MEANING",
    "TRANSITIONS",
    "TERMINAL_STATES",
    "DismissalReason",
    "InvalidTransition",
    "check_transition",
    "requires_reason",
]

STATE_OPEN = "open"
STATE_ACKNOWLEDGED = "acknowledged"
STATE_INVESTIGATING = "investigating"
STATE_RESOLVED = "resolved"
STATE_DISMISSED = "dismissed"

ALERT_STATES: tuple[str, ...] = (
    STATE_OPEN,
    STATE_ACKNOWLEDGED,
    STATE_INVESTIGATING,
    STATE_RESOLVED,
    STATE_DISMISSED,
)

TERMINAL_STATES: frozenset[str] = frozenset({STATE_RESOLVED, STATE_DISMISSED})

STATE_MEANING: dict[str, str] = {
    STATE_OPEN: "Raised by a rule and not yet looked at by anyone.",
    STATE_ACKNOWLEDGED: "An analyst has seen it and accepted it into their queue.",
    STATE_INVESTIGATING: "Actively being worked. Usually attached to a case.",
    STATE_RESOLVED: (
        "Worked to a conclusion. This says the analyst finished, not that the "
        "finding was correct — whether it was is recorded as the outcome."
    ),
    STATE_DISMISSED: (
        "Judged not to warrant work, with a reason from the vocabulary. The "
        "alert remains queryable and can be reopened; it is not deleted."
    ),
}

# Legal transitions. Deliberately permissive about going backwards and strict
# about skipping forwards.
TRANSITIONS: dict[str, frozenset[str]] = {
    STATE_OPEN: frozenset({STATE_ACKNOWLEDGED, STATE_INVESTIGATING, STATE_DISMISSED}),
    STATE_ACKNOWLEDGED: frozenset({STATE_INVESTIGATING, STATE_DISMISSED, STATE_OPEN}),
    STATE_INVESTIGATING: frozenset({STATE_RESOLVED, STATE_DISMISSED, STATE_ACKNOWLEDGED}),
    # Reopening a finished alert is always available. New evidence arrives, and
    # an analyst who closed something in error needs a route back that does not
    # involve a database console.
    STATE_RESOLVED: frozenset({STATE_INVESTIGATING, STATE_OPEN}),
    STATE_DISMISSED: frozenset({STATE_OPEN, STATE_INVESTIGATING}),
}


@dataclass(frozen=True)
class DismissalReason:
    code: str
    label: str
    means: str
    counts_as_false_positive: bool
    """Whether calibration should treat this dismissal as the rule being wrong.

    The distinction the vocabulary exists for: `known_benign` and `not_relevant`
    mean the rule fired correctly on a real pattern that this deployment does
    not care about — tuning scope, not fixing a detector. `false_positive` means
    the rule's premise did not hold. Counting the first two against precision
    would make a well-behaved rule look broken.
    """


DISMISSAL_REASONS: tuple[DismissalReason, ...] = (
    DismissalReason(
        code="false_positive",
        label="False positive",
        means="The rule's premise does not hold — the pattern it claims to have found is not there.",
        counts_as_false_positive=True,
    ),
    DismissalReason(
        code="known_benign",
        label="Known benign activity",
        means="The pattern is real and has a known, legitimate explanation.",
        counts_as_false_positive=False,
    ),
    DismissalReason(
        code="not_relevant",
        label="Out of scope",
        means="The finding is sound but outside what this deployment investigates.",
        counts_as_false_positive=False,
    ),
    DismissalReason(
        code="insufficient_evidence",
        label="Not enough to act on",
        means="Cannot be judged either way on what ARGUS currently holds.",
        counts_as_false_positive=False,
    ),
    DismissalReason(
        code="duplicate",
        label="Duplicate of another alert",
        means="The same finding is already being worked under a different alert.",
        counts_as_false_positive=False,
    ),
)

DISMISSAL_CODES: frozenset[str] = frozenset(r.code for r in DISMISSAL_REASONS)


class InvalidTransition(ValueError):
    """Raised for an illegal state change. Carries both states so the API can
    say what was attempted rather than 'invalid status'."""

    def __init__(self, current: str, requested: str, detail: str) -> None:
        self.current = current
        self.requested = requested
        super().__init__(detail)


def requires_reason(to_state: str) -> bool:
    return to_state == STATE_DISMISSED


def check_transition(current: str, requested: str, reason_code: str | None) -> None:
    """Raise `InvalidTransition` unless the move is legal and fully specified."""
    if requested not in ALERT_STATES:
        raise InvalidTransition(
            current, requested, f"{requested!r} is not an alert state. Valid: {', '.join(ALERT_STATES)}."
        )
    if current == requested:
        raise InvalidTransition(
            current, requested, f"Alert is already {current!r}; nothing would change."
        )
    allowed = TRANSITIONS.get(current, frozenset())
    if requested not in allowed:
        raise InvalidTransition(
            current,
            requested,
            f"An alert that is {current!r} cannot move straight to {requested!r}. "
            f"From here: {', '.join(sorted(allowed))}.",
        )
    if requires_reason(requested):
        if reason_code is None:
            raise InvalidTransition(
                current,
                requested,
                "Dismissing an alert requires a reason from the vocabulary: "
                + ", ".join(sorted(DISMISSAL_CODES))
                + ".",
            )
        if reason_code not in DISMISSAL_CODES:
            raise InvalidTransition(
                current,
                requested,
                f"{reason_code!r} is not a dismissal reason. Valid: "
                + ", ".join(sorted(DISMISSAL_CODES))
                + ".",
            )
