"""Suppression scope, expiry, and the refusal to silence everything."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.alerting.suppression import (
    MAX_SUPPRESSION,
    Suppression,
    SuppressionScopeError,
    matching_suppression,
    validate_suppression,
)

NOW = datetime(2026, 8, 18, tzinfo=UTC)
NOTE = "Known remediation window agreed with the data owner."


def s(sid="1", rule_id=None, subject_ref=None, expires=None, revoked=None):
    return Suppression(
        suppression_id=sid, rule_id=rule_id, subject_ref=subject_ref,
        reason_code="known_benign", note=NOTE, created_by="iris",
        created_at=NOW - timedelta(days=1),
        expires_at=expires or NOW + timedelta(days=7), revoked_at=revoked,
    )


def test_a_wildcard_suppression_is_refused() -> None:
    with pytest.raises(SuppressionScopeError, match="no wildcard"):
        validate_suppression(rule_id=None, subject_ref=None, expires_at=NOW + timedelta(days=1), note=NOTE, now=NOW)


def test_an_indefinite_suppression_is_refused() -> None:
    with pytest.raises(SuppressionScopeError, match="at most"):
        validate_suppression(
            rule_id="r.a", subject_ref=None,
            expires_at=NOW + MAX_SUPPRESSION + timedelta(days=1), note=NOTE, now=NOW,
        )


def test_an_already_expired_suppression_is_refused() -> None:
    with pytest.raises(SuppressionScopeError, match="expire in the future"):
        validate_suppression(rule_id="r.a", subject_ref=None, expires_at=NOW - timedelta(days=1), note=NOTE, now=NOW)


def test_an_unexplained_suppression_is_refused() -> None:
    with pytest.raises(SuppressionScopeError, match="needs a note"):
        validate_suppression(rule_id="r.a", subject_ref=None, expires_at=NOW + timedelta(days=1), note="ok", now=NOW)


def test_a_scoped_explained_bounded_suppression_is_accepted() -> None:
    validate_suppression(rule_id="r.a", subject_ref="PRS-1", expires_at=NOW + timedelta(days=30), note=NOTE, now=NOW)


def test_rule_scope_matches_any_subject() -> None:
    assert s(rule_id="r.a").matches("r.a", ("PRS-9",))
    assert not s(rule_id="r.a").matches("r.b", ("PRS-9",))


def test_subject_scope_matches_any_rule() -> None:
    assert s(subject_ref="PRS-1").matches("r.a", ("PRS-1", "PRS-2"))
    assert not s(subject_ref="PRS-1").matches("r.a", ("PRS-2",))


def test_both_together_require_both() -> None:
    both = s(rule_id="r.a", subject_ref="PRS-1")
    assert both.matches("r.a", ("PRS-1",))
    assert not both.matches("r.b", ("PRS-1",))
    assert not both.matches("r.a", ("PRS-2",))


def test_expired_suppression_does_not_match() -> None:
    assert matching_suppression([s(rule_id="r.a", expires=NOW - timedelta(days=1))], "r.a", ("P",), NOW) is None


def test_revoked_suppression_does_not_match() -> None:
    assert matching_suppression([s(rule_id="r.a", revoked=NOW - timedelta(hours=1))], "r.a", ("P",), NOW) is None


def test_the_narrowest_suppression_is_the_one_recorded() -> None:
    """So the alert names the targeted suppression that hid it, not whichever
    broad one happened to sort first."""
    broad = s(sid="broad", rule_id="r.a")
    narrow = s(sid="narrow", rule_id="r.a", subject_ref="PRS-1")
    chosen = matching_suppression([broad, narrow], "r.a", ("PRS-1",), NOW)
    assert chosen is not None and chosen.suppression_id == "narrow"


def test_no_match_returns_none_rather_than_a_default() -> None:
    assert matching_suppression([], "r.a", ("P",), NOW) is None


def test_describe_names_who_and_until_when() -> None:
    text = s(rule_id="r.a", subject_ref="PRS-1").describe()
    assert "iris" in text and "r.a" in text and "PRS-1" in text
