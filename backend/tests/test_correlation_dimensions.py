"""Each dimension, in each of its three states.

The three-state discipline is the point of these tests. A dimension may come
back **fired** (a magnitude above zero, with evidence), **evaluated and clean**
(magnitude zero — it looked and found nothing), or **not evaluable** (magnitude
`None` — it could not look at all). Most systems collapse the last two, which
turns "we have no idea" into "we checked and it was fine", and there is no way
to recover the difference afterwards.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.correlation.dimensions import (
    DIMENSIONS,
    DIMENSIONS_BY_ID,
    DimensionOutcome,
    build_context,
    evaluate_pair,
)
from app.correlation.evidence import (
    Affiliation,
    Anchor,
    Attendance,
    CorrelationEvidence,
    DeviceContact,
    Place,
    Transfer,
)
from app.correlation.model import default_model

T0 = datetime(2026, 3, 1, 12, 0)
MODEL = default_model()


def anchor(ref: str, subject_type: str = "Person", **kwargs) -> Anchor:
    return Anchor(
        ref=ref,
        subject_type=subject_type,
        band=kwargs.pop("band", "notable"),
        score=kwargs.pop("score", 40.0),
        signal_ids=kwargs.pop("signal_ids", ("funds_cycle",)),
        activity=kwargs.pop("activity", ()),
    )


def context(evidence: CorrelationEvidence):
    return build_context(evidence, MODEL)


def outcome_of(outcomes: list[DimensionOutcome], dimension_id: str) -> DimensionOutcome:
    match = [o for o in outcomes if o.dimension_id == dimension_id]
    assert match, f"{dimension_id} was not evaluated for this pair"
    return match[0]


def _populated(**overrides) -> CorrelationEvidence:
    """A world with enough filler that rarity weights are meaningful.

    Rarity is measured against the anchor population, so a two-anchor world
    makes everything maximally rare and every dimension fire. The filler
    anchors exist so the thresholds are exercised at a realistic scale.
    """
    evidence = CorrelationEvidence(gathered_at=T0)
    for i in range(60):
        ref = f"PRS-F{i:03d}"
        evidence.anchors[ref] = anchor(ref)
    for key, value in overrides.items():
        setattr(evidence, key, value)
    return evidence


# ─────────────────────────────────────────────────────────────────────────────
# Shared counterparty
# ─────────────────────────────────────────────────────────────────────────────


def _two_payers_of(
    common: list[str], *, extra_users: int = 0, noise_each: int = 0
) -> CorrelationEvidence:
    """Two subjects sharing some counterparties, in a world with a background rate.

    `noise_each` gives each of them private counterparties, which raises what
    chance alone would predict them to share. That matters because the dimension
    scores *excess over chance*: two subjects who each deal with 40 accounts are
    expected to overlap, and only overlap beyond that expectation is evidence.
    """
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
    evidence.account_owner = {"ACC-A": "PRS-A", "ACC-B": "PRS-B"}
    evidence.transfers = []
    for account in common:
        evidence.transfers.append(Transfer("ACC-A", account, 5_000.0, T0))
        evidence.transfers.append(Transfer("ACC-B", account, 4_000.0, T0 + timedelta(days=1)))
    for i in range(noise_each):
        evidence.transfers.append(Transfer("ACC-A", f"ACC-NA{i}", 500.0, T0))
        evidence.transfers.append(Transfer("ACC-B", f"ACC-NB{i}", 500.0, T0))
    # Background population, so the chance baseline is not degenerate.
    for i in range(40):
        ref, account = f"PRS-X{i}", f"ACC-X{i}"
        evidence.anchors[ref] = anchor(ref)
        evidence.account_owner[account] = ref
        evidence.transfers.append(Transfer(account, f"ACC-BG{i % 20}", 100.0, T0))
    for i in range(extra_users):
        ref, account = f"PRS-C{i}", f"ACC-C{i}"
        evidence.anchors[ref] = anchor(ref)
        evidence.account_owner[account] = ref
        for c in common:
            evidence.transfers.append(Transfer(account, c, 100.0, T0))
    return evidence


def _counterparty(ctx) -> DimensionOutcome:
    return outcome_of(
        evaluate_pair(ctx, ctx.evidence.anchors["PRS-A"], ctx.evidence.anchors["PRS-B"]),
        "shared_counterparty",
    )


def test_overlap_far_beyond_chance_fires() -> None:
    result = _counterparty(context(_two_payers_of(["ACC-C1", "ACC-C2", "ACC-C3"])))
    assert result.evaluable
    assert (result.magnitude or 0) > 0
    assert result.evidence["shared_count"] == 3
    assert result.evidence["lift"] > 1


def test_overlap_no_greater_than_chance_is_clean() -> None:
    """The defect this dimension was rebuilt to fix. Two subjects dealing with
    many counterparties each will share some by arithmetic alone, and scoring
    that raw overlap fired on 545 of 688 random pairs against the live graph."""
    result = _counterparty(context(_two_payers_of(["ACC-C1"], noise_each=30)))
    assert result.evaluable
    assert result.magnitude == 0.0


def test_a_counterparty_everyone_uses_is_worth_almost_nothing() -> None:
    """The clearing-account case. Without rarity weighting this dimension would
    rank the entire population as mutually correlated."""
    rare = context(_two_payers_of(["ACC-C1", "ACC-C2", "ACC-C3"]))
    common = context(_two_payers_of(["ACC-C1", "ACC-C2", "ACC-C3"], extra_users=40))
    assert (_counterparty(common).magnitude or 0) < (_counterparty(rare).magnitude or 0)


def test_no_shared_counterparty_is_clean_not_unevaluable() -> None:
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
    evidence.account_owner = {"ACC-A": "PRS-A", "ACC-B": "PRS-B"}
    evidence.transfers = [
        Transfer("ACC-A", "ACC-P", 5_000.0, T0),
        Transfer("ACC-B", "ACC-Q", 4_000.0, T0),
        Transfer("ACC-R", "ACC-S", 1_000.0, T0),
    ]
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "shared_counterparty",
    )
    assert result.evaluable
    assert result.magnitude == 0.0


def test_a_subject_with_no_transactions_makes_the_dimension_unevaluable() -> None:
    """Not "they share no counterparty" — there was nothing to compare."""
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
    evidence.account_owner = {"ACC-A": "PRS-A"}
    evidence.transfers = [Transfer("ACC-A", "ACC-P", 5_000.0, T0)]
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "shared_counterparty",
    )
    assert not result.evaluable
    assert result.magnitude is None
    assert "PRS-B" in result.summary


# ─────────────────────────────────────────────────────────────────────────────
# Funds path
# ─────────────────────────────────────────────────────────────────────────────


def test_a_direct_transfer_is_the_strongest_funds_path() -> None:
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
    evidence.account_owner = {"ACC-A": "PRS-A", "ACC-B": "PRS-B"}
    evidence.transfers = [Transfer("ACC-A", "ACC-B", 100_000.0, T0)]
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "funds_path",
    )
    assert result.evaluable
    assert result.magnitude == 1.0
    assert result.evidence["hops"] == 1


def test_a_longer_route_scores_lower_than_a_short_one() -> None:
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
    evidence.account_owner = {"ACC-A": "PRS-A", "ACC-B": "PRS-B"}
    evidence.transfers = [
        Transfer("ACC-A", "ACC-M1", 100_000.0, T0),
        Transfer("ACC-M1", "ACC-M2", 92_000.0, T0 + timedelta(days=1)),
        Transfer("ACC-M2", "ACC-B", 86_000.0, T0 + timedelta(days=2)),
    ]
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "funds_path",
    )
    assert result.evidence["hops"] == 3
    assert 0 < (result.magnitude or 0) < 1.0


def test_no_route_is_clean_when_the_search_completed() -> None:
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
    evidence.account_owner = {"ACC-A": "PRS-A", "ACC-B": "PRS-B"}
    evidence.transfers = [Transfer("ACC-A", "ACC-Z", 100_000.0, T0)]
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "funds_path",
    )
    assert result.evaluable
    assert result.magnitude == 0.0


def test_a_subject_holding_no_account_makes_the_path_unevaluable() -> None:
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
    evidence.account_owner = {"ACC-A": "PRS-A"}
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "funds_path",
    )
    assert not result.evaluable


# ─────────────────────────────────────────────────────────────────────────────
# Co-attendance
# ─────────────────────────────────────────────────────────────────────────────


def _co_attendees(shared_events: int, others_per_event: int = 0) -> CorrelationEvidence:
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
    for i in range(shared_events):
        event = f"EVT-{i}"
        evidence.attendances.append(Attendance("PRS-A", event, T0))
        evidence.attendances.append(Attendance("PRS-B", event, T0))
        for j in range(others_per_event):
            evidence.attendances.append(Attendance(f"PRS-F{j:03d}", event, T0))
    return evidence


def test_one_shared_event_does_not_reach_the_corroboration_floor() -> None:
    """People meet. One event together is a fact, not an association, and the
    thresholds are set so it is recorded without counting as corroboration."""
    ctx = context(_co_attendees(1))
    result = outcome_of(
        evaluate_pair(ctx, ctx.evidence.anchors["PRS-A"], ctx.evidence.anchors["PRS-B"]),
        "co_attendance",
    )
    assert result.evaluable
    assert (result.magnitude or 0) < MODEL.dimension_floor


def test_two_shared_events_is_a_real_association() -> None:
    ctx = context(_co_attendees(2))
    result = outcome_of(
        evaluate_pair(ctx, ctx.evidence.anchors["PRS-A"], ctx.evidence.anchors["PRS-B"]),
        "co_attendance",
    )
    assert (result.magnitude or 0) >= MODEL.dimension_floor


def test_a_crowded_event_counts_for_less_than_a_private_one() -> None:
    private = context(_co_attendees(2))
    crowded = context(_co_attendees(2, others_per_event=40))
    private_result = outcome_of(
        evaluate_pair(private, private.evidence.anchors["PRS-A"], private.evidence.anchors["PRS-B"]),
        "co_attendance",
    )
    crowded_result = outcome_of(
        evaluate_pair(crowded, crowded.evidence.anchors["PRS-A"], crowded.evidence.anchors["PRS-B"]),
        "co_attendance",
    )
    assert (crowded_result.magnitude or 0) < (private_result.magnitude or 0)


def test_a_subject_who_attended_nothing_makes_it_unevaluable() -> None:
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
    evidence.attendances = [Attendance("PRS-A", "EVT-1", T0)]
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "co_attendance",
    )
    assert not result.evaluable


# ─────────────────────────────────────────────────────────────────────────────
# Communication
# ─────────────────────────────────────────────────────────────────────────────


def test_direct_contact_is_strong_and_needs_no_rarity_weighting() -> None:
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
        evidence.subjects_with_devices.add(ref)
    evidence.contacts = [
        DeviceContact("PRS-A", "PRS-B", T0 + timedelta(hours=h)) for h in range(3)
    ]
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "communication",
    )
    assert result.magnitude == 1.0
    assert result.evidence["direct_contacts"] == 3


def test_one_call_is_weaker_than_three() -> None:
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
        evidence.subjects_with_devices.add(ref)
    evidence.contacts = [DeviceContact("PRS-A", "PRS-B", T0)]
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "communication",
    )
    assert 0 < (result.magnitude or 0) < 1.0


def test_a_shared_correspondent_is_weaker_than_speaking_directly() -> None:
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B", "PRS-M"):
        evidence.anchors[ref] = anchor(ref)
        evidence.subjects_with_devices.add(ref)
    evidence.contacts = [
        DeviceContact("PRS-A", "PRS-M", T0),
        DeviceContact("PRS-B", "PRS-M", T0 + timedelta(hours=1)),
    ]
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "communication",
    )
    assert result.evidence["direct_contacts"] == 0
    assert result.evidence["shared_correspondents"] == 1
    assert (result.magnitude or 0) < 1.0


def test_a_phone_that_was_never_used_is_evaluable_and_clean() -> None:
    """Owning a device and never calling anyone is a finding. Owning no device
    is not the same finding, and the two must not share an answer."""
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
        evidence.subjects_with_devices.add(ref)
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "communication",
    )
    assert result.evaluable
    assert result.magnitude == 0.0


def test_a_subject_with_no_device_makes_communication_unevaluable() -> None:
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
    evidence.subjects_with_devices.add("PRS-A")
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "communication",
    )
    assert not result.evaluable
    assert "PRS-B" in result.summary


# ─────────────────────────────────────────────────────────────────────────────
# Affiliation
# ─────────────────────────────────────────────────────────────────────────────


def test_a_shared_directorship_in_a_small_company_is_strong() -> None:
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
    evidence.affiliations = [
        Affiliation("PRS-A", "ORG-1", "DIRECTS"),
        Affiliation("PRS-B", "ORG-1", "DIRECTS"),
    ]
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "affiliation",
    )
    assert (result.magnitude or 0) >= MODEL.dimension_floor


def test_a_common_employer_counts_for_little() -> None:
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
    evidence.affiliations = [
        Affiliation("PRS-A", "ORG-BIG", "EMPLOYED_BY"),
        Affiliation("PRS-B", "ORG-BIG", "EMPLOYED_BY"),
    ] + [Affiliation(f"PRS-F{i:03d}", "ORG-BIG", "EMPLOYED_BY") for i in range(55)]
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "affiliation",
    )
    assert (result.magnitude or 0) < MODEL.dimension_floor


# ─────────────────────────────────────────────────────────────────────────────
# Proximity — corroboration only
# ─────────────────────────────────────────────────────────────────────────────


def _located(distance_case: str) -> CorrelationEvidence:
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
    evidence.event_places = {
        "EVT-1": Place("EVT-1", 19.0760, 72.8777),
        "EVT-2": Place("EVT-2", 19.0800, 72.8800),
        "EVT-FAR": Place("EVT-FAR", 28.6139, 77.2090),
    }
    near = "EVT-2" if distance_case == "near" else "EVT-FAR"
    evidence.attendances = [
        Attendance("PRS-A", "EVT-1", T0),
        Attendance("PRS-A", "EVT-2", T0),
        Attendance("PRS-B", near, T0),
        Attendance("PRS-B", "EVT-1" if distance_case == "near" else "EVT-FAR", T0),
    ]
    return evidence


def test_activity_centred_on_the_same_place_fires() -> None:
    ctx = context(_located("near"))
    result = outcome_of(
        evaluate_pair(ctx, ctx.evidence.anchors["PRS-A"], ctx.evidence.anchors["PRS-B"]),
        "proximity",
    )
    assert result.evaluable
    assert (result.magnitude or 0) > 0


def test_activity_a_thousand_kilometres_apart_is_clean() -> None:
    ctx = context(_located("far"))
    result = outcome_of(
        evaluate_pair(ctx, ctx.evidence.anchors["PRS-A"], ctx.evidence.anchors["PRS-B"]),
        "proximity",
    )
    assert result.evaluable
    assert result.magnitude == 0.0


def test_one_located_activity_is_not_a_centre_of_activity() -> None:
    """A centroid computed from a single observation is that observation. The
    dimension says so rather than reporting a distance."""
    evidence = _populated()
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
    evidence.event_places = {"EVT-1": Place("EVT-1", 19.0760, 72.8777)}
    evidence.attendances = [
        Attendance("PRS-A", "EVT-1", T0),
        Attendance("PRS-B", "EVT-1", T0),
    ]
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "proximity",
    )
    assert not result.evaluable
    assert "not a finding that they are far apart" in result.summary


# ─────────────────────────────────────────────────────────────────────────────
# Temporal coincidence — corroboration only
# ─────────────────────────────────────────────────────────────────────────────


def test_coincidence_fires_only_on_an_excess() -> None:
    """Two subjects whose every action shadows the other's, inside a long
    observed period where chance would predict almost no overlap."""
    evidence = _populated()
    # A background subject spread across a year, so the observed span is long
    # and chance coincidence is correspondingly rare.
    evidence.anchors["PRS-F000"] = anchor(
        "PRS-F000", activity=(T0, T0 + timedelta(days=365))
    )
    burst = tuple(T0 + timedelta(days=200, hours=h) for h in range(12))
    evidence.anchors["PRS-A"] = anchor("PRS-A", activity=burst)
    evidence.anchors["PRS-B"] = anchor(
        "PRS-B", activity=tuple(t + timedelta(hours=1) for t in burst)
    )
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "coincidence",
    )
    assert result.evaluable
    assert (result.magnitude or 0) > 0
    assert result.evidence["lift"] > 1


def test_coincidence_no_greater_than_chance_is_clean() -> None:
    """Against the live graph the raw count fired at full magnitude on 797 of
    797 random pairs. Measuring the excess is what stopped it being a permanent
    second voice on every link."""
    evidence = _populated()
    evidence.anchors["PRS-A"] = anchor(
        "PRS-A", activity=tuple(T0 + timedelta(days=d) for d in range(12))
    )
    evidence.anchors["PRS-B"] = anchor(
        "PRS-B", activity=tuple(T0 + timedelta(days=d, hours=2) for d in range(12))
    )
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "coincidence",
    )
    assert result.evaluable
    assert result.magnitude == 0.0


def test_a_thin_history_makes_coincidence_unevaluable() -> None:
    evidence = _populated()
    evidence.anchors["PRS-A"] = anchor("PRS-A", activity=(T0,))
    evidence.anchors["PRS-B"] = anchor(
        "PRS-B", activity=tuple(T0 + timedelta(days=d) for d in range(12))
    )
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"]),
        "coincidence",
    )
    assert not result.evaluable
    assert "noise wearing a number" in result.summary


# ─────────────────────────────────────────────────────────────────────────────
# Shared corridor
# ─────────────────────────────────────────────────────────────────────────────


def test_two_shipments_on_the_same_rare_corridor_fire() -> None:
    evidence = _populated()
    for ref in ("SHP-A", "SHP-B"):
        evidence.anchors[ref] = anchor(ref, subject_type="Shipment")
    evidence.corridors = {"SHP-A": "LOC-1>LOC-2", "SHP-B": "LOC-1>LOC-2"}
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["SHP-A"], evidence.anchors["SHP-B"]),
        "shared_corridor",
    )
    assert result.evaluable
    assert (result.magnitude or 0) > 0


def test_different_routes_are_clean() -> None:
    evidence = _populated()
    for ref in ("SHP-A", "SHP-B"):
        evidence.anchors[ref] = anchor(ref, subject_type="Shipment")
    evidence.corridors = {"SHP-A": "LOC-1>LOC-2", "SHP-B": "LOC-3>LOC-4"}
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["SHP-A"], evidence.anchors["SHP-B"]),
        "shared_corridor",
    )
    assert result.evaluable
    assert result.magnitude == 0.0


def test_a_shipment_missing_an_endpoint_is_unevaluable() -> None:
    evidence = _populated()
    for ref in ("SHP-A", "SHP-B"):
        evidence.anchors[ref] = anchor(ref, subject_type="Shipment")
    evidence.corridors = {"SHP-A": "LOC-1>LOC-2"}
    ctx = context(evidence)
    result = outcome_of(
        evaluate_pair(ctx, evidence.anchors["SHP-A"], evidence.anchors["SHP-B"]),
        "shared_corridor",
    )
    assert not result.evaluable


# ─────────────────────────────────────────────────────────────────────────────
# Applicability
# ─────────────────────────────────────────────────────────────────────────────


def test_dimensions_that_do_not_apply_are_omitted_not_marked_unevaluable() -> None:
    """Asking whether a shipment attended an event is not a question with a
    missing answer. It is not a question."""
    evidence = _populated()
    evidence.anchors["SHP-A"] = anchor("SHP-A", subject_type="Shipment")
    evidence.anchors["SHP-B"] = anchor("SHP-B", subject_type="Shipment")
    ctx = context(evidence)
    outcomes = evaluate_pair(ctx, evidence.anchors["SHP-A"], evidence.anchors["SHP-B"])
    evaluated = {o.dimension_id for o in outcomes}
    assert "co_attendance" not in evaluated
    assert "communication" not in evaluated
    assert "shared_corridor" in evaluated


def test_a_person_and_a_shipment_share_only_the_universal_dimensions() -> None:
    evidence = _populated()
    evidence.anchors["PRS-A"] = anchor("PRS-A")
    evidence.anchors["SHP-B"] = anchor("SHP-B", subject_type="Shipment")
    ctx = context(evidence)
    outcomes = evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["SHP-B"])
    assert {o.dimension_id for o in outcomes} == {"proximity", "coincidence"}


# ─────────────────────────────────────────────────────────────────────────────
# The invariant, structurally
# ─────────────────────────────────────────────────────────────────────────────


def test_an_evaluable_outcome_must_carry_a_magnitude() -> None:
    with pytest.raises(ValueError, match="must carry a magnitude"):
        DimensionOutcome(
            dimension_id="x", family="financial", evaluable=True, magnitude=None, summary=""
        )


def test_an_unevaluable_outcome_must_not_carry_a_magnitude() -> None:
    """Otherwise a zero would be storable against "we could not look", which is
    the collapse this whole discipline exists to prevent."""
    with pytest.raises(ValueError, match="must not carry a magnitude"):
        DimensionOutcome(
            dimension_id="x", family="financial", evaluable=False, magnitude=0.0, summary=""
        )


def test_every_dimension_is_registered_once_and_explains_itself() -> None:
    assert len(DIMENSIONS_BY_ID) == len(DIMENSIONS)
    for definition in DIMENSIONS:
        assert definition.question.endswith("?")
        assert len(definition.rationale) > 80, definition.dimension_id
        assert definition.reads
        assert definition.subject_types
