"""Replaying an investigation's history, and noticing when the log has been bypassed.

Phase 9's acceptance criterion is that a case's full history is reconstructable
at any past point. These tests are that criterion, over the replay itself; the
integration tests then assert the same property against a real database, where
the events were written by the repository rather than by a fixture.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.investigation.history import TRACKED_FIELDS, reconstruct, verify

T0 = datetime(2031, 5, 1, 9, 0, tzinfo=UTC)


def _event(event_id, at, event_type, field=None, old=None, new=None):
    return {
        "event_id": event_id,
        "occurred_at": at,
        "event_type": event_type,
        "field": field,
        "old_value": old,
        "new_value": new,
    }


def _opened(**overrides):
    snapshot = {
        "title": "Layered transfers through three shells",
        "hypothesis": "The three companies are one owner",
        "confidence": "low",
        "confidence_basis": "one source, uncorroborated",
        "state": "open",
        "assigned_to": None,
        "outcome": None,
        "outcome_rationale": None,
        "closed_by": None,
        "closed_at": None,
    }
    snapshot.update(overrides)
    return _event(1, T0, "opened", new=snapshot)


def test_a_history_of_one_event_reconstructs_the_opening_state():
    state = reconstruct([_opened()])
    assert state["state"] == "open"
    assert state["confidence"] == "low"
    assert state["outcome"] is None


def test_replaying_to_now_gives_the_latest_value_of_every_field():
    events = [
        _opened(),
        _event(2, T0 + timedelta(hours=1), "field_changed", "state", "open", "active"),
        _event(3, T0 + timedelta(hours=2), "field_changed", "confidence", "low", "high"),
    ]
    state = reconstruct(events)
    assert state["state"] == "active"
    assert state["confidence"] == "high"


def test_replaying_to_a_past_instant_gives_what_was_true_then():
    events = [
        _opened(),
        _event(2, T0 + timedelta(hours=1), "field_changed", "confidence", "low", "high"),
    ]
    # The point of the whole module: not "what do we believe now", but "what did
    # this investigation say at the moment someone acted on it".
    assert reconstruct(events, T0 + timedelta(minutes=30))["confidence"] == "low"
    assert reconstruct(events, T0 + timedelta(hours=2))["confidence"] == "high"


def test_an_instant_before_the_investigation_existed_reconstructs_nothing():
    # An empty dict, not a row of nulls. "It did not exist" and "every field was
    # null" are different facts and the caller has to be able to tell them apart.
    assert reconstruct([_opened()], T0 - timedelta(days=1)) == {}


def test_the_boundary_instant_is_inclusive():
    # "As at 14:00" means after everything that happened up to and including
    # 14:00, which is how a person reading a timestamped record expects it.
    events = [_opened(), _event(2, T0 + timedelta(hours=1), "field_changed", "state", "open", "active")]
    assert reconstruct(events, T0 + timedelta(hours=1))["state"] == "active"


def test_events_sharing_a_timestamp_are_ordered_by_id():
    # One request changing several fields writes several events with the same
    # clock reading. Without the id tiebreak the replay would be
    # non-deterministic for exactly the case that is most common.
    at = T0 + timedelta(hours=1)
    events = [
        _opened(),
        _event(3, at, "field_changed", "confidence", "moderate", "high"),
        _event(2, at, "field_changed", "confidence", "low", "moderate"),
    ]
    assert reconstruct(events)["confidence"] == "high"
    assert verify(events) is None


def test_untracked_fields_are_ignored_rather_than_replayed():
    events = [
        _opened(),
        _event(2, T0 + timedelta(hours=1), "field_changed", "inv_ref", "INV-1", "INV-2"),
    ]
    assert "inv_ref" not in reconstruct(events)


def test_tracked_fields_covers_the_fields_the_repository_logs():
    # A field logged but not tracked would vanish from every reconstruction; a
    # field tracked but never logged would read as "it was null then".
    assert "outcome" in TRACKED_FIELDS
    assert "state" in TRACKED_FIELDS
    assert "closed_by" in TRACKED_FIELDS
    # Reviews are deliberately not tracked fields: they are their own
    # append-only table, because more than one person may review an
    # investigation and a column can only hold the last one.
    assert not any(f.startswith("review") for f in TRACKED_FIELDS)


class TestVerify:
    def test_a_clean_log_is_consistent(self):
        events = [
            _opened(),
            _event(2, T0 + timedelta(hours=1), "field_changed", "state", "open", "active"),
            _event(3, T0 + timedelta(hours=2), "field_changed", "state", "active", "closed"),
        ]
        assert verify(events) is None

    def test_an_out_of_band_write_is_caught_at_the_next_legitimate_change(self):
        # Nobody edited the log. Someone edited the *row* — so the next real
        # change recorded a previous value the log cannot account for. That gap
        # is the only trace such a write leaves, and it is the one this finds.
        events = [
            _opened(),
            _event(2, T0 + timedelta(hours=1), "field_changed", "state", "open", "active"),
            _event(3, T0 + timedelta(hours=2), "field_changed", "state", "closed", "active"),
        ]
        found = verify(events)
        assert found is not None
        assert found.event_id == 3
        assert found.field == "state"
        assert found.expected == "active"
        assert found.recorded == "closed"
        assert "without writing an event" in found.describe()

    def test_only_the_first_break_is_reported(self):
        events = [
            _opened(),
            _event(2, T0 + timedelta(hours=1), "field_changed", "state", "closed", "active"),
            _event(3, T0 + timedelta(hours=2), "field_changed", "state", "open", "closed"),
        ]
        # Everything after the first divergence is compared against a state
        # already known to be wrong, so a list would be a list of consequences.
        assert verify(events).event_id == 2

    def test_a_first_change_to_a_field_the_snapshot_never_mentioned_is_not_a_break(self):
        events = [_opened(), _event(2, T0, "field_changed", "assigned_to", None, "k.nair")]
        assert verify(events) is None


def test_a_semantically_typed_event_is_still_replayed():
    """`closed` and `reopened` carry field changes and must not be skipped.

    This is a regression test for a defect the integration suite caught: the
    replay keyed on `event_type == "field_changed"`, so a closure — recorded as
    `closed`, because that is what it meant — was invisible to it. Every closed
    investigation reconstructed as still active while the row said closed, and
    the two disagreed with no way to tell which was right.
    """
    events = [
        _opened(),
        _event(2, T0 + timedelta(hours=1), "field_changed", "state", "open", "active"),
        _event(3, T0 + timedelta(hours=2), "closed", "state", "active", "closed"),
        _event(4, T0 + timedelta(hours=2), "closed", "outcome", None, "confirmed"),
    ]
    state = reconstruct(events)
    assert state["state"] == "closed"
    assert state["outcome"] == "confirmed"
    assert verify(events) is None


def test_events_with_no_field_do_not_disturb_the_replay():
    # `alert_attached`, `finding_recorded` and the rest carry a note, not a
    # field. They belong in a timeline and must not touch the reconstruction.
    events = [
        _opened(),
        _event(2, T0 + timedelta(hours=1), "finding_recorded"),
        _event(3, T0 + timedelta(hours=2), "alert_attached"),
    ]
    assert reconstruct(events)["state"] == "open"
    assert verify(events) is None
