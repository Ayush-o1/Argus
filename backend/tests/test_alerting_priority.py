"""Priority ordering, and the factor deliberately left out of it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.alerting.priority import (
    CORROBORATION_MULTIPLE,
    CORROBORATION_SINGLE,
    RECENCY_FLOOR,
    compute_priority,
    priority_band,
    recency_weight,
)

NOW = datetime(2026, 8, 18, tzinfo=UTC)


def p(**kw):
    base = dict(magnitude=0.8, confidence=0.8, independent_methods=1, evidence_at=NOW, now=NOW)
    base.update(kw)
    return compute_priority(**base)


def test_two_independent_methods_outrank_one() -> None:
    assert p(independent_methods=2).priority > p(independent_methods=1).priority


def test_corroboration_lift_is_the_declared_one() -> None:
    assert p(independent_methods=1).corroboration == CORROBORATION_SINGLE
    assert p(independent_methods=3).corroboration == CORROBORATION_MULTIPLE


def test_low_coverage_cannot_be_hidden_by_high_magnitude() -> None:
    """Conjunctive, not averaged: a strong finding resting on a tenth of the
    model is uncertain, and averaging would let the magnitude mask that."""
    strong_thin = p(magnitude=1.0, confidence=0.1)
    modest_thick = p(magnitude=0.5, confidence=0.9)
    assert modest_thick.priority > strong_thin.priority


def test_priority_never_exceeds_one() -> None:
    assert p(magnitude=1.0, confidence=1.0, independent_methods=2).priority <= 1.0


def test_older_evidence_ranks_lower() -> None:
    fresh = p(evidence_at=NOW)
    stale = p(evidence_at=NOW - timedelta(days=60))
    assert fresh.priority > stale.priority


def test_recency_has_a_floor_so_old_alerts_sink_but_do_not_vanish() -> None:
    """Decaying to zero would remove an alert from the ordering entirely, which
    is suppression by arithmetic rather than by decision."""
    weight, _ = recency_weight(NOW - timedelta(days=3650), NOW)
    assert weight == RECENCY_FLOOR
    assert p(evidence_at=NOW - timedelta(days=3650)).priority > 0


def test_future_evidence_is_not_penalised() -> None:
    weight, age = recency_weight(NOW + timedelta(days=5), NOW)
    assert weight == 1.0 and age == 0.0


def test_naive_timestamps_are_treated_as_utc() -> None:
    """A naive datetime would otherwise raise on subtraction, turning a clock
    detail into a failed run."""
    weight, _ = recency_weight(datetime(2026, 8, 18), NOW)
    assert 0 < weight <= 1.0


def test_asset_criticality_is_absent_and_says_why() -> None:
    """It multiplies, so an invented constant would silently reorder the whole
    queue while looking like a measurement."""
    payload = p().as_dict()
    assert payload["asset_criticality"] is None
    assert "no asset register" in payload["asset_criticality_note"]
    assert "asset_criticality" not in payload["factors"]


def test_breakdown_publishes_every_factor_used() -> None:
    factors = p().as_dict()["factors"]
    assert set(factors) == {"corroboration", "confidence", "magnitude", "recency"}


@pytest.mark.parametrize(
    "value,expected",
    [(0.9, "high"), (0.55, "high"), (0.4, "medium"), (0.3, "medium"), (0.1, "low"), (0.0, "low")],
)
def test_bands_are_defined_here_not_in_css(value: float, expected: str) -> None:
    assert priority_band(value) == expected


def test_magnitude_and_confidence_are_clamped() -> None:
    out = p(magnitude=5.0, confidence=-1.0)
    assert out.magnitude == 1.0 and out.confidence == 0.0
