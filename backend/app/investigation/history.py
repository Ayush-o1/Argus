"""Reconstructing an investigation as it stood at any past moment.

Phase 9's acceptance criterion is that a case's full history is reconstructable
at any past point. That is not a property of the current row — which by
definition holds only the present — but of `investigation_events`, and this
module is the replay over it.

## The shape of the log

One `opened` event carrying the initial snapshot, then one event per field per
mutation, each carrying the field name and both its old and new value.
Replaying forward from the snapshot to a timestamp gives the row as it stood.

The replay keys on **whether an event carries a field**, not on its type. Event
types are descriptive labels — `closed` and `reopened` say what a change meant
to the person making it, which is worth reading in a timeline — and treating
them as the mechanism is a bug this module already had once: closures were
recorded as `closed` rather than `field_changed`, the replay ignored them, and
every closed investigation reconstructed as still active while the row said
otherwise. The label is for humans; `field` is for the machine.

## Why old values are stored as well as new

They are redundant during a clean replay — the previous event's `new_value`
would do. They are stored because they are what makes tampering *visible*: if
someone writes to `investigations` without going through the event path, the
next recorded change will carry an `old_value` that does not match what the
replay says was there. `verify()` finds exactly that, and it is the same
argument the audit log's hash chain makes in migration 001.

A history that is right only when nobody has interfered is a history that tells
you nothing in the one case you would want to consult it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

__all__ = [
    "TRACKED_FIELDS",
    "HistoryBreak",
    "reconstruct",
    "verify",
]

# Fields of `investigations` whose changes the log covers, and therefore the
# fields a reconstruction can speak about. Named explicitly rather than taken
# from the row, so that adding a column does not silently widen what
# `reconstruct` claims to know — a replayed row missing a field that was never
# logged would read as "it was null then", which is a different statement from
# "this was not tracked".
TRACKED_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "hypothesis",
        "confidence",
        "confidence_basis",
        "state",
        "assigned_to",
        "outcome",
        "outcome_rationale",
        "closed_by",
        "closed_at",
    }
)

# Reviews are deliberately absent. They are their own append-only table, not
# fields of the investigation — so "who reviewed this and did they agree" is
# answered by reading every review, not by replaying the last write to a column
# that only one reviewer could occupy at a time.


@dataclass(frozen=True)
class HistoryBreak:
    """A point where the log stopped explaining the row.

    `event_id` is the first event whose `old_value` disagreed with the state the
    replay had reached. That event is where the divergence became visible, which
    is not necessarily where it was introduced — an out-of-band write leaves no
    event of its own, so the break surfaces at the *next* legitimate change.
    """

    event_id: int
    field: str
    expected: Any
    """What the replay held for this field just before the event."""
    recorded: Any
    """What the event said the previous value was."""
    occurred_at: datetime

    def describe(self) -> str:
        return (
            f"event {self.event_id} at {self.occurred_at.isoformat()} recorded "
            f"{self.field}={self.recorded!r} as the previous value, but the log up to that "
            f"point says it was {self.expected!r}. Something changed this investigation "
            f"without writing an event."
        )


def _ordered(events: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    # By time, then by id. Two events can share a timestamp when one request
    # changes several fields, and only the id orders those deterministically.
    return sorted(events, key=lambda e: (e["occurred_at"], e["event_id"]))


def reconstruct(events: Iterable[Mapping[str, Any]], at: datetime | None = None) -> dict[str, Any]:
    """The tracked fields as they stood at `at` (default: after the last event).

    Events at exactly `at` are included: "as at 14:00" means after everything
    that happened up to and including 14:00, which is how a person reading a
    timestamped record expects it to be read.

    Returns an empty dict if the investigation did not exist yet at that time,
    rather than a row of nulls — those are different facts.
    """
    state: dict[str, Any] = {}
    for event in _ordered(events):
        if at is not None and event["occurred_at"] > at:
            break
        if event["event_type"] == "opened":
            snapshot = event["new_value"] or {}
            state.update({k: v for k, v in snapshot.items() if k in TRACKED_FIELDS})
            continue
        field = event["field"]
        if field in TRACKED_FIELDS:
            state[field] = event["new_value"]
    return state


def verify(events: Iterable[Mapping[str, Any]]) -> HistoryBreak | None:
    """Replay the log checking each event's `old_value` against the running state.

    Returns the first break, or None if the log is self-consistent. Reports one
    rather than all of them: after the first divergence every later comparison
    is made against a state already known to be wrong, so a list would be a list
    of consequences of one problem.
    """
    state: dict[str, Any] = {}
    for event in _ordered(events):
        if event["event_type"] == "opened":
            snapshot = event["new_value"] or {}
            state.update({k: v for k, v in snapshot.items() if k in TRACKED_FIELDS})
            continue

        field = event["field"]
        if field not in TRACKED_FIELDS:
            continue

        # The first change to a field the snapshot never mentioned has nothing
        # to be checked against, and is not evidence of anything.
        if field in state and state[field] != event["old_value"]:
            return HistoryBreak(
                event_id=event["event_id"],
                field=field,
                expected=state[field],
                recorded=event["old_value"],
                occurred_at=event["occurred_at"],
            )
        state[field] = event["new_value"]
    return None
