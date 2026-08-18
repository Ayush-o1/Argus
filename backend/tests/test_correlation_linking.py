"""Combining dimensions into a link, and the rules about when not to.

The combination rule carries most of this phase's judgement, so these tests
pin the judgement rather than the arithmetic:

  * a strong finding is never diluted by a weak one beside it;
  * two measurements of the same transaction ledger count once, not twice;
  * proximity and coincidence can corroborate a link but can never make one;
  * a link found on two of eight dimensions is reported as thin, not as strong.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.correlation.dimensions import build_context, evaluate_pair
from app.correlation.evidence import (
    Affiliation,
    Anchor,
    Attendance,
    CorrelationEvidence,
    DeviceContact,
    Place,
    Transfer,
)
from app.correlation.linking import dimension_catalogue, link_pair
from app.correlation.model import (
    FAMILY_CEILINGS,
    IDENTIFYING_FAMILIES,
    TIER_ESTABLISHED,
    TIER_PROBABLE,
    default_model,
)
from app.models.provenance import Credibility, Reliability

T0 = datetime(2026, 3, 1, 12, 0)
MODEL = default_model()


def anchor(ref: str, subject_type: str = "Person", activity: tuple = ()) -> Anchor:
    return Anchor(
        ref=ref,
        subject_type=subject_type,
        band="notable",
        score=40.0,
        signal_ids=("funds_cycle",),
        activity=activity,
    )


def world(**overrides) -> CorrelationEvidence:
    evidence = CorrelationEvidence(gathered_at=T0)
    for i in range(60):
        ref = f"PRS-F{i:03d}"
        evidence.anchors[ref] = anchor(ref)
    for ref in ("PRS-A", "PRS-B"):
        evidence.anchors[ref] = anchor(ref)
    for key, value in overrides.items():
        setattr(evidence, key, value)
    return evidence


def link_for(evidence: CorrelationEvidence, model=MODEL):
    ctx = build_context(evidence, model)
    return link_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"])


def _financial() -> dict:
    return {
        "account_owner": {"ACC-A": "PRS-A", "ACC-B": "PRS-B"},
        "transfers": [Transfer("ACC-A", "ACC-B", 100_000.0, T0)],
    }


def _social() -> dict:
    return {
        "contacts": [DeviceContact("PRS-A", "PRS-B", T0 + timedelta(hours=h)) for h in range(3)],
        "subjects_with_devices": {"PRS-A", "PRS-B"},
    }


def _well_observed() -> dict:
    """A pair ARGUS can actually see, on every dimension that applies to it.

    Needed because the top tier is gated on coverage as well as corroboration:
    a pair with three of seven dimensions evaluable has been glanced at, and no
    amount of strength in the survivors promotes it. Building the fixture this
    way makes the gate visible rather than something a test trips over.
    """
    times_a = tuple(T0 + timedelta(days=d) for d in range(20))
    return {
        **_financial(),
        **_social(),
        "affiliations": [
            Affiliation("PRS-A", "ORG-1", "DIRECTS"),
            Affiliation("PRS-B", "ORG-1", "DIRECTS"),
        ],
        "attendances": [
            Attendance("PRS-A", "EVT-1", T0),
            Attendance("PRS-A", "EVT-2", T0),
            Attendance("PRS-B", "EVT-1", T0),
            Attendance("PRS-B", "EVT-3", T0),
        ],
        "event_places": {
            "EVT-1": Place("EVT-1", 19.0760, 72.8777),
            "EVT-2": Place("EVT-2", 19.0800, 72.8800),
            "EVT-3": Place("EVT-3", 19.0700, 72.8700),
        },
        "_activity": times_a,
    }


def observed_world() -> CorrelationEvidence:
    fields = _well_observed()
    times = fields.pop("_activity")
    evidence = world(**fields)
    evidence.anchors["PRS-A"] = anchor("PRS-A", activity=times)
    evidence.anchors["PRS-B"] = anchor(
        "PRS-B", activity=tuple(t + timedelta(hours=2) for t in times)
    )
    return evidence


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation
# ─────────────────────────────────────────────────────────────────────────────


def test_one_strong_family_produces_a_link() -> None:
    link = link_for(world(**_financial()))
    assert link is not None
    assert link.strength >= MODEL.probable_strength
    assert "financial" in link.corroborating_families


def test_two_families_produce_a_stronger_link_than_one() -> None:
    one = link_for(world(**_financial()))
    both = link_for(world(**_financial(), **_social()))
    assert one is not None and both is not None
    assert both.strength >= one.strength
    assert len(both.corroborating_families) > len(one.corroborating_families)


def test_a_weak_dimension_never_lowers_a_strength() -> None:
    """The dilution defect from Phase 5's first scoring scheme, checked directly
    on this phase's combination rule."""
    bare = link_for(world(**_financial()))
    with_weak = link_for(
        world(
            **_financial(),
            attendances=[Attendance("PRS-A", "EVT-1", T0), Attendance("PRS-B", "EVT-1", T0)],
        )
    )
    assert bare is not None and with_weak is not None
    assert with_weak.strength >= bare.strength


def test_two_financial_measurements_count_as_one_voice() -> None:
    """Shared counterparty and funds path read the same ledger. Counting them as
    independent would multiply one fact into confidence."""
    evidence = world(
        account_owner={"ACC-A": "PRS-A", "ACC-B": "PRS-B"},
        transfers=[
            Transfer("ACC-A", "ACC-B", 100_000.0, T0),
            Transfer("ACC-A", "ACC-COMMON", 5_000.0, T0),
            Transfer("ACC-B", "ACC-COMMON", 4_000.0, T0),
        ],
    )
    link = link_for(evidence)
    assert link is not None
    financial = [f for f in link.families if f.family == "financial"]
    assert len(financial) == 1, "a family must contribute exactly one voice"


def test_a_family_contributes_its_strongest_dimension() -> None:
    evidence = world(
        account_owner={"ACC-A": "PRS-A", "ACC-B": "PRS-B"},
        transfers=[
            Transfer("ACC-A", "ACC-B", 100_000.0, T0),
            Transfer("ACC-A", "ACC-COMMON", 5_000.0, T0),
            Transfer("ACC-B", "ACC-COMMON", 4_000.0, T0),
        ],
    )
    link = link_for(evidence)
    assert link is not None
    financial = next(f for f in link.families if f.family == "financial")
    assert financial.dimension_id == "funds_path"
    assert financial.raw == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Ceilings and the identifying-family rule
# ─────────────────────────────────────────────────────────────────────────────


def test_proximity_and_coincidence_alone_never_make_a_link() -> None:
    """Between them they can reach 0.40, which clears `min_strength`. Without
    the identifying-family rule, two people in one city who were both busy in
    March would be reported as correlated."""
    evidence = world()
    # A long observed period, so a tight burst of shared activity is a genuine
    # excess rather than the background rate.
    evidence.anchors["PRS-F000"] = anchor(
        "PRS-F000", activity=(T0, T0 + timedelta(days=365))
    )
    burst = tuple(T0 + timedelta(days=200, hours=h) for h in range(12))
    evidence.anchors["PRS-A"] = anchor("PRS-A", activity=burst)
    evidence.anchors["PRS-B"] = anchor(
        "PRS-B", activity=tuple(t + timedelta(hours=1) for t in burst)
    )
    evidence.event_places = {
        "EVT-1": Place("EVT-1", 19.0760, 72.8777),
        "EVT-2": Place("EVT-2", 19.0761, 72.8778),
    }
    evidence.attendances = [
        Attendance("PRS-A", "EVT-1", T0),
        Attendance("PRS-A", "EVT-2", T0),
        Attendance("PRS-B", "EVT-1", T0),
        Attendance("PRS-B", "EVT-2", T0),
    ]
    ctx = build_context(evidence, MODEL)
    outcomes = evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"])

    # Both non-identifying dimensions are at full strength here, which is what
    # makes the check meaningful: this is the most those two families can ever
    # contribute, and it still must not produce a link.
    spatial = next(o for o in outcomes if o.dimension_id == "proximity")
    temporal = next(o for o in outcomes if o.dimension_id == "coincidence")
    assert (spatial.magnitude or 0) > 0
    assert (temporal.magnitude or 0) > 0

    # Co-attendance is social, and social *is* identifying — so it has to go for
    # the remaining evidence to be spatial and temporal alone.
    evidence.attendances = []
    assert link_for(evidence) is None


def test_the_ceilings_keep_corroborating_families_below_the_reporting_floor() -> None:
    """Stated as arithmetic rather than only as documentation: no combination of
    non-identifying families can reach `min_strength`."""
    corroborating = [
        ceiling
        for family, ceiling in FAMILY_CEILINGS.items()
        if family not in IDENTIFYING_FAMILIES
    ]
    residual = 1.0
    for ceiling in corroborating:
        residual *= 1.0 - ceiling
    assert 1.0 - residual < MODEL.established_strength


def test_every_family_has_a_ceiling_and_a_stated_identity() -> None:
    for definition in dimension_catalogue():
        assert definition["family"] in FAMILY_CEILINGS


# ─────────────────────────────────────────────────────────────────────────────
# Tiers
# ─────────────────────────────────────────────────────────────────────────────


def test_one_family_however_strong_is_not_established() -> None:
    """A single dimension at 1.0 is one observation, however emphatic. Calling
    it established would let one measurement speak with the authority of two."""
    link = link_for(world(**_financial()))
    assert link is not None
    assert link.tier != TIER_ESTABLISHED
    assert link.tier == TIER_PROBABLE


def test_two_corroborating_families_reach_established() -> None:
    link = link_for(observed_world())
    assert link is not None
    assert link.tier == TIER_ESTABLISHED
    assert link.credibility is Credibility.PROBABLY_TRUE


def test_nothing_below_the_minimum_strength_is_recorded() -> None:
    """In a graph this dense every pair has some faint connection, and a store
    containing all of them would contain no information."""
    evidence = world(
        attendances=[Attendance("PRS-A", "EVT-1", T0), Attendance("PRS-B", "EVT-1", T0)]
    )
    assert link_for(evidence) is None


def test_reliability_is_always_f() -> None:
    """The source is ARGUS's own algorithm, measured against one synthetic
    world. Rating it higher would launder a measurement into a track record."""
    link = link_for(world(**_financial(), **_social()))
    assert link is not None
    assert link.reliability is Reliability.F


# ─────────────────────────────────────────────────────────────────────────────
# Coverage
# ─────────────────────────────────────────────────────────────────────────────


def test_coverage_counts_the_dimensions_that_could_be_evaluated() -> None:
    link = link_for(world(**_financial(), **_social()))
    assert link is not None
    assert link.evaluable_dimensions <= link.applicable_dimensions
    assert link.coverage == pytest.approx(
        link.evaluable_dimensions / link.applicable_dimensions, abs=1e-4
    )


def test_a_link_found_on_thin_coverage_cannot_be_established() -> None:
    """A pair where most dimensions could not be evaluated has been glanced at,
    not examined, and the tier says so however strong the survivors were.

    The two pairs here carry *identical* financial and social evidence, so the
    strengths come out the same. The only difference is how much of the model
    could be applied — and that alone decides the tier.
    """
    observed = link_for(observed_world())
    thin = link_for(world(**_financial(), **_social()))
    assert observed is not None and thin is not None

    assert thin.strength == pytest.approx(observed.strength)
    assert len(thin.corroborating_families) >= 2

    assert thin.coverage < 0.5 < observed.coverage
    assert observed.tier == TIER_ESTABLISHED
    assert thin.tier == TIER_PROBABLE


def test_the_basis_names_the_reasons_and_the_blind_spots() -> None:
    link = link_for(world(**_financial(), **_social()))
    assert link is not None
    basis = link.basis()
    assert "independent kinds of evidence" in basis
    if link.unevaluable:
        assert "could not be evaluated" in basis


def test_the_pair_is_stored_in_a_stable_order() -> None:
    """A pair stored in both orders would be two links to any reader joining on
    one side, and would silently double every count."""
    evidence = world(**_financial())
    ctx = build_context(evidence, MODEL)
    forward = link_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"])
    backward = link_pair(ctx, evidence.anchors["PRS-B"], evidence.anchors["PRS-A"])
    assert forward is not None and backward is not None
    assert forward.key == backward.key
    assert forward.ref_a < forward.ref_b


def test_a_subject_is_never_linked_to_itself() -> None:
    evidence = world(**_financial())
    ctx = build_context(evidence, MODEL)
    assert link_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-A"]) is None


def test_the_catalogue_publishes_every_dimension() -> None:
    """A model that describes only the parts of itself that produced results is
    not a description of a model."""
    catalogue = dimension_catalogue()
    assert len(catalogue) == 8
    for entry in catalogue:
        assert entry["question"]
        assert entry["rationale"]
        assert entry["reads"]


# ─────────────────────────────────────────────────────────────────────────────
# One entity is not two
# ─────────────────────────────────────────────────────────────────────────────


def test_a_subject_is_never_linked_to_an_account_it_holds() -> None:
    """Found in live verification, and it was the largest category of "finding"
    in the system: 38,142 links whose entire content was that a person holds a
    bank account. Their counterparties are identical by construction, so every
    financial dimension scored them at full strength."""
    evidence = world(**_financial())
    evidence.anchors["ACC-A"] = anchor("ACC-A", subject_type="Account")
    ctx = build_context(evidence, MODEL)
    assert link_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["ACC-A"]) is None
    assert link_pair(ctx, evidence.anchors["ACC-A"], evidence.anchors["PRS-A"]) is None


def test_an_account_held_by_someone_else_is_still_correlatable() -> None:
    """The exclusion is about identity, not about accounts. An account whose
    holder is not this subject is a different subject and may well be linked."""
    evidence = world(**_financial())
    evidence.anchors["ACC-B"] = anchor("ACC-B", subject_type="Account")
    ctx = build_context(evidence, MODEL)
    assert not ctx.same_entity("PRS-A", "ACC-B")


# ─────────────────────────────────────────────────────────────────────────────
# Corroboration versus support
# ─────────────────────────────────────────────────────────────────────────────


def test_only_identifying_families_count_as_corroboration() -> None:
    """Measured on the live graph, temporal coincidence at full magnitude acted
    as a permanent second voice and pushed 59,056 of 91,212 links into the top
    tier. Being busy in the same week is not a second opinion about a pair."""
    fields = _well_observed()
    fields.pop("_activity")  # this test supplies its own activity, below
    evidence = world(**fields)
    evidence.anchors["PRS-F000"] = anchor(
        "PRS-F000", activity=(T0, T0 + timedelta(days=365))
    )
    burst = tuple(T0 + timedelta(days=200, hours=h) for h in range(12))
    evidence.anchors["PRS-A"] = anchor("PRS-A", activity=burst)
    evidence.anchors["PRS-B"] = anchor(
        "PRS-B", activity=tuple(t + timedelta(hours=1) for t in burst)
    )
    link = link_for(evidence)
    assert link is not None
    assert "temporal" not in link.corroborating_families
    assert "spatial" not in link.corroborating_families
    for family in link.corroborating_families:
        assert family in IDENTIFYING_FAMILIES


def test_supporting_families_are_recorded_rather_than_discarded() -> None:
    """They contributed to the strength, so a reader is entitled to see them."""
    fields = _well_observed()
    times = fields.pop("_activity")
    evidence = world(**fields)
    evidence.anchors["PRS-A"] = anchor("PRS-A", activity=times)
    evidence.anchors["PRS-B"] = anchor(
        "PRS-B", activity=tuple(t + timedelta(hours=2) for t in times)
    )
    link = link_for(evidence)
    assert link is not None
    assert set(link.supporting_families).isdisjoint(link.corroborating_families)


# ─────────────────────────────────────────────────────────────────────────────
# Concentration
# ─────────────────────────────────────────────────────────────────────────────


def test_an_ordinary_payment_is_not_a_relationship() -> None:
    """Against the live graph, 5,527 pairs of flagged subjects have a direct
    transfer between them and the median one is 3.3% of the sender's annual
    outflow. Scoring on hop distance alone put 6,960 of those in `probable`."""
    evidence = world(
        account_owner={"ACC-A": "PRS-A", "ACC-B": "PRS-B"},
        transfers=[
            Transfer("ACC-A", "ACC-B", 3_000.0, T0),
            *[
                Transfer("ACC-A", f"ACC-OTHER{i}", 10_000.0, T0 + timedelta(days=i))
                for i in range(10)
            ],
        ],
    )
    ctx = build_context(evidence, MODEL)
    outcome = next(
        o
        for o in evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"])
        if o.dimension_id == "funds_path"
    )
    assert outcome.evaluable
    assert outcome.evidence["hops"] == 1
    assert outcome.evidence["share_of_outflow"] < MODEL.path_concentration_trigger
    assert outcome.magnitude == 0.0


def test_a_payment_that_is_most_of_what_an_account_sends_is_a_relationship() -> None:
    evidence = world(
        account_owner={"ACC-A": "PRS-A", "ACC-B": "PRS-B"},
        transfers=[
            Transfer("ACC-A", "ACC-B", 90_000.0, T0),
            Transfer("ACC-A", "ACC-OTHER", 10_000.0, T0 + timedelta(days=1)),
        ],
    )
    ctx = build_context(evidence, MODEL)
    outcome = next(
        o
        for o in evaluate_pair(ctx, evidence.anchors["PRS-A"], evidence.anchors["PRS-B"])
        if o.dimension_id == "funds_path"
    )
    assert outcome.evidence["share_of_outflow"] == pytest.approx(0.9)
    assert outcome.magnitude == 1.0
