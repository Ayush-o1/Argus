"""Banding, coverage, and the difference between "clean" and "unknown".

The property under test throughout is that a subject ARGUS could not examine
never comes out looking like a subject it examined and cleared. Every other
assertion in this file is a consequence of that one.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.assessment.evidence import (
    AccountFact,
    Contact,
    Directorship,
    EvidenceBundle,
    ShipmentFact,
    Transfer,
)
from app.assessment.model import (
    BAND_ELEVATED,
    BAND_INSUFFICIENT,
    BAND_NOTABLE,
    BAND_ROUTINE,
    RiskModel,
    default_model,
)
from app.assessment.scoring import assess_all, signal_catalogue
from app.assessment.signals import SIGNALS, signals_for
from app.models.provenance import Credibility, Reliability

BASE = datetime(2026, 3, 1, 9, 0, 0)


def bundle(**parts) -> EvidenceBundle:
    return EvidenceBundle(
        subjects=parts.get("subjects", {}),
        accounts=parts.get("accounts", []),
        transfers=parts.get("transfers", []),
        contacts=parts.get("contacts", []),
        shipments=parts.get("shipments", []),
        directorships=parts.get("directorships", []),
        persons_with_devices=parts.get("persons_with_devices", set()),
    )


def assess(evidence: EvidenceBundle, ref: str, model: RiskModel | None = None):
    run = assess_all(evidence, model or default_model(), computed_at=BASE)
    return next(a for a in run.assessments if a.subject_ref == ref)


def ring(prefix: str, hops: int = 6, start: float = 500_000.0) -> list[Transfer]:
    """A value-preserving loop across `hops` distinct accounts."""
    transfers = []
    amount = start
    for i in range(hops):
        amount *= 0.95
        transfers.append(
            Transfer(
                transfer_id=f"{prefix}-T{i}",
                source_account=f"{prefix}-A{i}",
                target_account=f"{prefix}-A{(i + 1) % hops}",
                amount=round(amount, 2),
                occurred_at=BASE + timedelta(hours=i * 3),
            )
        )
    return transfers


# ─────────────────────────────────────────────────────────────────────────────
# The unknown / clean distinction
# ─────────────────────────────────────────────────────────────────────────────


def test_a_person_with_no_evidence_is_unassessable_not_low_risk() -> None:
    person = assess(bundle(subjects={"PRS-1": "Person"}), "PRS-1")
    assert person.band == BAND_INSUFFICIENT
    assert person.score is None, "an unassessable subject must have no score at all"
    assert "does not know" in person.headline() or "cannot assess" in person.headline()


def test_an_unevaluable_signal_has_a_null_magnitude_not_zero() -> None:
    person = assess(bundle(subjects={"PRS-1": "Person"}), "PRS-1")
    funds = next(c for c in person.contributions if c.signal_id == "funds_cycle")
    assert funds.evaluable is False
    assert funds.magnitude is None, "None means 'could not look'; 0 means 'looked and found none'"
    assert "no account" in funds.summary.lower()


def test_an_evaluated_negative_is_distinguishable_from_an_unknown() -> None:
    """The whole phase in one assertion: two signals both contributing zero,
    one because it was checked and clean, one because it could not be checked."""
    evidence = bundle(
        subjects={"PRS-1": "Person", "ACC-1": "Account"},
        accounts=[AccountFact("ACC-1", offshore=False, owner_ref="PRS-1", owner_type="Person")],
    )
    person = assess(evidence, "PRS-1")
    funds = next(c for c in person.contributions if c.signal_id == "funds_cycle")
    contact = next(c for c in person.contributions if c.signal_id == "communication_burst")

    assert funds.evaluable and funds.magnitude == 0.0
    assert not contact.evaluable and contact.magnitude is None
    assert funds.contribution == contact.contribution == 0.0


def test_a_person_with_no_device_is_not_reported_as_having_been_quiet() -> None:
    evidence = bundle(
        subjects={"PRS-1": "Person", "ACC-1": "Account"},
        accounts=[AccountFact("ACC-1", offshore=False, owner_ref="PRS-1", owner_type="Person")],
    )
    contact = next(
        c for c in assess(evidence, "PRS-1").contributions if c.signal_id == "communication_burst"
    )
    assert not contact.evaluable
    assert "absence of collection" in contact.summary


# ─────────────────────────────────────────────────────────────────────────────
# Coverage
# ─────────────────────────────────────────────────────────────────────────────


def test_coverage_is_the_share_of_model_weight_that_could_be_evaluated() -> None:
    evidence = bundle(
        subjects={"PRS-1": "Person", "ACC-1": "Account"},
        accounts=[AccountFact("ACC-1", offshore=False, owner_ref="PRS-1", owner_type="Person")],
    )
    person = assess(evidence, "PRS-1")
    total = sum(s.weight for s in signals_for("Person"))
    # funds_cycle (5) + offshore (1) + directorships (2); transaction_burst and
    # communication_burst have nothing to work with.
    assert person.evaluable_weight == 8.0
    assert person.total_weight == total
    assert person.evidence_coverage == pytest.approx(8.0 / total, abs=1e-4)


def test_a_strong_finding_over_a_sliver_of_the_model_cannot_reach_the_top_band() -> None:
    """A narrow finding is a narrow finding however strong it is. Coverage gates
    the band before the score is consulted."""
    model = default_model()
    strict = RiskModel(min_coverage_for_elevated=0.99)
    evidence = bundle(
        subjects={"PRS-1": "Person", **{f"RING-A{i}": "Account" for i in range(6)}},
        accounts=[
            AccountFact("RING-A0", offshore=False, owner_ref="PRS-1", owner_type="Person"),
            *[
                AccountFact(f"RING-A{i}", offshore=False, owner_ref=None, owner_type=None)
                for i in range(1, 6)
            ],
        ],
        transfers=ring("RING"),
    )
    assert assess(evidence, "PRS-1", model).band == BAND_ELEVATED
    assert assess(evidence, "PRS-1", strict).band == BAND_NOTABLE


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation
# ─────────────────────────────────────────────────────────────────────────────


def test_one_strong_finding_is_not_diluted_by_silent_signals() -> None:
    """Risk evidence is disjunctive. A funds cycle is not made less alarming by
    the subject also having an unremarkable communication pattern.

    Dividing by all evaluable weight said otherwise and produced a middle band
    holding 849 subjects at 6% precision on the live graph — which is how the
    aggregation was found to be wrong.
    """
    evidence = bundle(
        subjects={"PRS-1": "Person", **{f"RING-A{i}": "Account" for i in range(6)}},
        accounts=[
            AccountFact("RING-A0", offshore=False, owner_ref="PRS-1", owner_type="Person"),
            *[
                AccountFact(f"RING-A{i}", offshore=False, owner_ref=None, owner_type=None)
                for i in range(1, 6)
            ],
        ],
        transfers=ring("RING"),
        contacts=[
            Contact("PRS-1", "PRS-2", BASE + timedelta(days=30 * i)) for i in range(6)
        ],
        persons_with_devices={"PRS-1"},
    )
    person = assess(evidence, "PRS-1")
    assert person.score == 100.0
    assert person.band == BAND_ELEVATED


def test_a_lone_weak_signal_does_not_reach_the_notable_band() -> None:
    """Banking abroad is lawful and common. It is worth recording and it is not
    worth a queue position on its own."""
    evidence = bundle(
        subjects={"PRS-1": "Person", "ACC-1": "Account"},
        accounts=[AccountFact("ACC-1", offshore=True, owner_ref="PRS-1", owner_type="Person")],
    )
    person = assess(evidence, "PRS-1")
    offshore = next(c for c in person.contributions if c.signal_id == "offshore_banking")
    assert offshore.magnitude == 1.0, "the signal did fire"
    assert person.band == BAND_ROUTINE, "and it is still not a finding on its own"
    assert person.score == 20.0


def test_the_score_is_capped_rather_than_unbounded() -> None:
    evidence = bundle(
        subjects={"SHP-1": "Shipment"},
        shipments=[
            ShipmentFact("SHP-1", 9.0, "Oceania", "Central Asia", "Textiles", "Machine parts")
        ],
    )
    assert assess(evidence, "SHP-1").score == 100.0


# ─────────────────────────────────────────────────────────────────────────────
# Bands
# ─────────────────────────────────────────────────────────────────────────────


def test_bands_respond_to_thresholds_rather_than_to_hardcoded_numbers() -> None:
    evidence = bundle(
        subjects={"SHP-1": "Shipment"},
        shipments=[ShipmentFact("SHP-1", 1.0, "Europe", "East Asia", "Textiles", "Machine parts")],
    )
    assert assess(evidence, "SHP-1", RiskModel(elevated_score=70.0)).band == BAND_ELEVATED
    assert assess(evidence, "SHP-1", RiskModel(elevated_score=90.0)).band == BAND_NOTABLE
    # Both thresholds have to move: `elevated` is checked first, so raising
    # only the notable bar leaves an 80-point finding in the top band.
    lifted = RiskModel(elevated_score=95.0, notable_score=90.0)
    assert assess(evidence, "SHP-1", lifted).band == BAND_ROUTINE


def test_a_clean_subject_is_routine_and_says_it_was_examined() -> None:
    evidence = bundle(
        subjects={"SHP-1": "Shipment"},
        shipments=[ShipmentFact("SHP-1", 1.0, "Europe", "East Asia", "Textiles", "Textiles")],
    )
    shipment = assess(evidence, "SHP-1")
    assert shipment.band == BAND_ROUTINE
    assert shipment.score == 0.0
    assert "found nothing" in shipment.headline()


# ─────────────────────────────────────────────────────────────────────────────
# Ratings
# ─────────────────────────────────────────────────────────────────────────────


def test_reliability_is_never_better_than_unjudged() -> None:
    """ARGUS has measured this model against one synthetic world. That is not a
    track record, and rating the source higher would launder a measurement into
    one."""
    evidence = bundle(
        subjects={"SHP-1": "Shipment"},
        shipments=[ShipmentFact("SHP-1", 3.0, "Oceania", "Central Asia", "A", "B")],
    )
    assert assess(evidence, "SHP-1").reliability is Reliability.F


def test_credibility_reflects_corroboration_across_independent_families() -> None:
    one_family = bundle(
        subjects={"SHP-1": "Shipment"},
        shipments=[ShipmentFact("SHP-1", 1.0, "Europe", "East Asia", "Textiles", "Machine parts")],
    )
    two_families = bundle(
        subjects={"SHP-2": "Shipment"},
        shipments=[
            ShipmentFact("SHP-2", 3.0, "Europe", "East Asia", "Textiles", "Machine parts")
        ],
    )
    assert assess(one_family, "SHP-1").credibility is Credibility.POSSIBLY_TRUE
    assert assess(two_families, "SHP-2").credibility is Credibility.PROBABLY_TRUE


def test_an_unassessable_subject_states_that_credibility_cannot_be_judged() -> None:
    person = assess(bundle(subjects={"PRS-1": "Person"}), "PRS-1")
    assert person.credibility is Credibility.CANNOT_BE_JUDGED


# ─────────────────────────────────────────────────────────────────────────────
# Determinism and the fingerprint
# ─────────────────────────────────────────────────────────────────────────────


def test_assessment_is_deterministic() -> None:
    evidence = bundle(
        subjects={"PRS-1": "Person", **{f"RING-A{i}": "Account" for i in range(6)}},
        accounts=[
            AccountFact("RING-A0", offshore=True, owner_ref="PRS-1", owner_type="Person"),
            *[
                AccountFact(f"RING-A{i}", offshore=False, owner_ref=None, owner_type=None)
                for i in range(1, 6)
            ],
        ],
        transfers=ring("RING"),
        directorships=[Directorship("PRS-1", f"ORG-{i}") for i in range(4)],
    )
    first = assess_all(evidence, default_model(), computed_at=BASE)
    second = assess_all(evidence, default_model(), computed_at=BASE)
    assert [(a.subject_ref, a.band, a.score) for a in first.assessments] == [
        (a.subject_ref, a.band, a.score) for a in second.assessments
    ]


def test_the_fingerprint_changes_when_any_threshold_moves() -> None:
    baseline = default_model().fingerprint()
    assert RiskModel(elevated_score=61.0).fingerprint() != baseline
    assert RiskModel(cycle_window_days=8).fingerprint() != baseline
    assert RiskModel(burst_floor_expected=0.6).fingerprint() != baseline
    assert RiskModel().fingerprint() == baseline


def test_the_fingerprint_covers_the_signal_registry() -> None:
    """Reweighting a signal changes what a score means as surely as moving a
    threshold does. A fingerprint that missed it would certify two different
    models as the same one."""
    import dataclasses

    from app.assessment import model as model_module

    original = model_module.SIGNALS
    baseline = default_model().fingerprint()
    try:
        model_module.SIGNALS = tuple(
            dataclasses.replace(s, weight=s.weight + 1) for s in original
        )
        assert default_model().fingerprint() != baseline
    finally:
        model_module.SIGNALS = original
    assert default_model().fingerprint() == baseline


# ─────────────────────────────────────────────────────────────────────────────
# The registry itself
# ─────────────────────────────────────────────────────────────────────────────


def test_every_signal_states_a_question_and_a_rationale() -> None:
    """A signal that cannot say why it is evidence of anything has no business
    contributing to a score."""
    for signal in SIGNALS:
        assert signal.question.endswith("?"), signal.signal_id
        assert len(signal.rationale) > 80, signal.signal_id
        assert signal.subject_types, signal.signal_id


def test_the_catalogue_is_published_in_full() -> None:
    catalogue = signal_catalogue()
    assert {row["signal_id"] for row in catalogue} == {s.signal_id for s in SIGNALS}
    for row in catalogue:
        assert row["question"] and row["rationale"] and row["reads"]


def test_no_signal_id_is_duplicated() -> None:
    ids = [s.signal_id for s in SIGNALS]
    assert len(ids) == len(set(ids))
