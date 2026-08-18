"""The dimensions: independent reasons two findings might belong together.

Each dimension answers one question, scores it on its own, and explains itself
in a sentence naming the quantity that produced it. They are never summed into
an unexplained total — `linking.py` combines them, and every combination step is
reversible back to the dimension that contributed it.

## Three states, not two

Exactly as in assessment, a dimension can come back three ways:

  * **fired** — magnitude above zero, with evidence attached;
  * **evaluated and clean** — magnitude zero: it looked and found nothing;
  * **not evaluable** — magnitude `None`: it could not look at all, because one
    of the pair has no accounts, no coordinates, or too short a history.

The third is the one that gets erased in most systems, and erasing it is what
turns "we have no idea" into "we checked and it was fine". A pair whose spatial
dimension is unevaluable has not been shown to be far apart.

## Why a dimension may not simply be added

Every dimension declares `reads`, and a test asserts that declaration is a
subset of `ADMISSIBLE_INPUTS`. That is what stops the obvious shortcut: this
graph contains `INVOLVES`, `LINKED_TO`, `CONTROLS` and `SHARES_DEVICE` edges
that join precisely the entities a storyline planted together. A dimension
reading any of them would post a near-perfect precision figure and would have
discovered nothing at all.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from app.correlation.evidence import Anchor, CorrelationEvidence, Place
from app.correlation.measures import (
    ReachedAccount,
    centroid,
    excess_over_chance,
    forward_reach,
    haversine_km,
    overlap_weight,
    ramp,
    rarity_weight,
    window_overlap,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle: the model registers these
    from app.correlation.model import CorrelationModel

FAMILY_FINANCIAL = "financial"
FAMILY_SOCIAL = "social"
FAMILY_LOGISTICAL = "logistical"
FAMILY_SPATIAL = "spatial"
FAMILY_TEMPORAL = "temporal"

PERSON = "Person"
ORGANIZATION = "Organization"
ACCOUNT = "Account"
SHIPMENT = "Shipment"

FINANCIAL_TYPES = frozenset({PERSON, ORGANIZATION, ACCOUNT})


@dataclass(frozen=True)
class DimensionOutcome:
    """One dimension's verdict on one pair."""

    dimension_id: str
    family: str
    evaluable: bool
    magnitude: float | None
    summary: str
    evidence: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # The invariant the Postgres CHECK constraint also enforces, asserted
        # here so it cannot be violated in memory and stored later.
        if self.evaluable and self.magnitude is None:
            raise ValueError(f"{self.dimension_id}: evaluable outcome must carry a magnitude")
        if not self.evaluable and self.magnitude is not None:
            raise ValueError(f"{self.dimension_id}: unevaluable outcome must not carry a magnitude")

    @property
    def fired(self) -> bool:
        return self.evaluable and (self.magnitude or 0.0) > 0.0


@dataclass
class CorrelationContext:
    """Everything the dimensions need, indexed once for the whole run.

    Built up front rather than per pair because every dimension is
    population-relative: a shared counterparty is only evidence in proportion to
    how few other people share it, and that is unknowable from inside a pair.
    """

    evidence: CorrelationEvidence
    model: CorrelationModel

    accounts_of: dict[str, set[str]] = field(default_factory=dict)
    counterparties: dict[str, set[str]] = field(default_factory=dict)
    counterparty_frequency: dict[str, int] = field(default_factory=dict)

    reach: dict[str, dict[str, ReachedAccount]] = field(default_factory=dict)
    reach_truncated: set[str] = field(default_factory=set)

    events_of: dict[str, set[str]] = field(default_factory=dict)
    event_frequency: dict[str, int] = field(default_factory=dict)

    correspondents: dict[str, dict[str, int]] = field(default_factory=dict)
    correspondent_frequency: dict[str, int] = field(default_factory=dict)

    orgs_of: dict[str, set[str]] = field(default_factory=dict)
    org_frequency: dict[str, int] = field(default_factory=dict)

    corridor_of: dict[str, str] = field(default_factory=dict)
    corridor_frequency: dict[str, int] = field(default_factory=dict)

    place_of: dict[str, Place] = field(default_factory=dict)
    place_points: dict[str, int] = field(default_factory=dict)

    activity_of: dict[str, tuple[datetime, ...]] = field(default_factory=dict)

    contains: dict[str, set[str]] = field(default_factory=dict)
    """subject ref -> subjects it structurally contains.

    An Account and the Person who owns it are not two subjects that might be
    connected; they are one subject seen twice. Their counterparties are
    identical by construction, so every financial dimension scores them at full
    strength — and against the live graph all 423 Account anchors had their
    owner as an anchor too, producing 38,142 links whose entire content was
    "this person holds this account".
    """

    observed_span_hours: float = 0.0
    """How long the whole dataset covers, used to estimate chance coincidence.
    Taken from the data rather than assumed, so a short feed does not get the
    coincidence rate of a long one."""

    distinct_counterparties: int = 0
    mean_counterparty_rarity: float = 0.0

    outflow_total: dict[str, float] = field(default_factory=dict)
    """account -> everything it sent, across the whole observed period. The
    denominator for asking whether one payment is a relationship or a
    transaction."""

    def same_entity(self, a: str, b: str) -> bool:
        return b in self.contains.get(a, ()) or a in self.contains.get(b, ())

    @property
    def population(self) -> int:
        """The anchor count, used as the denominator for every rarity weight.

        Anchors rather than the whole graph, because rarity has to be measured
        against the set being compared. A counterparty shared by half the
        anchors is uninformative *for this comparison* however unusual it may be
        in the population at large.
        """
        return max(2, len(self.evidence.anchors))


DimensionFunction = Callable[[CorrelationContext, Anchor, Anchor], DimensionOutcome]


@dataclass(frozen=True)
class DimensionDefinition:
    dimension_id: str
    family: str
    label: str
    question: str
    rationale: str
    reads: tuple[str, ...]
    subject_types: frozenset[str]
    evaluate: DimensionFunction

    def applies_to(self, a: Anchor, b: Anchor) -> bool:
        return a.subject_type in self.subject_types and b.subject_type in self.subject_types


# ─────────────────────────────────────────────────────────────────────────────
# Helpers shared by several dimensions
# ─────────────────────────────────────────────────────────────────────────────


def _unevaluable(definition_id: str, family: str, reason: str) -> DimensionOutcome:
    return DimensionOutcome(
        dimension_id=definition_id,
        family=family,
        evaluable=False,
        magnitude=None,
        summary=reason,
        evidence={},
    )


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


# ─────────────────────────────────────────────────────────────────────────────
# Financial
# ─────────────────────────────────────────────────────────────────────────────


def _shared_counterparty(ctx: CorrelationContext, a: Anchor, b: Anchor) -> DimensionOutcome:
    left = ctx.counterparties.get(a.ref)
    right = ctx.counterparties.get(b.ref)
    if not left or not right:
        which = a.ref if not left else b.ref
        return _unevaluable(
            "shared_counterparty",
            FAMILY_FINANCIAL,
            f"{which} has no transaction history, so a shared counterparty cannot be looked for.",
        )

    shared = left & right
    weight = overlap_weight(shared, ctx.counterparty_frequency, population=ctx.population)

    # What chance alone would produce for two subjects dealing with this many
    # counterparties each, drawn from this many distinct accounts. Everything
    # below is measured against this rather than against zero.
    expected = (
        (len(left) * len(right) / ctx.distinct_counterparties) * ctx.mean_counterparty_rarity
        if ctx.distinct_counterparties
        else 0.0
    )
    lift = excess_over_chance(weight, expected)

    if lift is None:
        # Chance predicts nothing here, which is only a problem when there is
        # something to explain. Sharing nothing is a clean finding — ARGUS
        # looked and the sets do not overlap — and calling that unknowable
        # would be the opposite error to the one this dimension was fixed for.
        # Sharing something against a baseline of zero is genuinely unjudgeable:
        # the ratio is undefined, not large, and a world too small to establish
        # a background rate cannot support a claim about an excess over it.
        if weight <= 0:
            return DimensionOutcome(
                dimension_id="shared_counterparty",
                family=FAMILY_FINANCIAL,
                evaluable=True,
                magnitude=0.0,
                summary=(
                    f"No account was paid by both. {a.ref} deals with {len(left)} "
                    f"counterparties, {b.ref} with {len(right)}, and they do not overlap."
                ),
                evidence={"shared_count": 0, "rarity_weight": 0.0},
            )
        return _unevaluable(
            "shared_counterparty",
            FAMILY_FINANCIAL,
            (
                "They share a counterparty, but there is no background rate to judge it "
                "against — no account in this population is used by more than one subject, "
                "so there is nothing to say whether the overlap is more than chance."
            ),
        )

    magnitude = ramp(lift, ctx.model.counterparty_trigger, ctx.model.counterparty_full)

    if not shared:
        summary = (
            f"No account was paid by both. {a.ref} deals with {len(left)} counterparties, "
            f"{b.ref} with {len(right)}, and they do not overlap."
        )
    else:
        detail = sorted(
            shared,
            key=lambda account: rarity_weight(
                ctx.counterparty_frequency.get(account, 0), population=ctx.population
            ),
            reverse=True,
        )
        rarest = detail[0]
        others = ctx.counterparty_frequency.get(rarest, 0)
        summary = (
            f"Both transact with {len(shared)} common {_plural(len(shared), 'account')} — "
            f"{lift:.1f}× what two subjects dealing with {len(left)} and {len(right)} "
            f"counterparties would share by chance. The least common is {rarest}, used by "
            f"{others} of {ctx.population} subjects under assessment."
        )

    return DimensionOutcome(
        dimension_id="shared_counterparty",
        family=FAMILY_FINANCIAL,
        evaluable=True,
        magnitude=magnitude,
        summary=summary,
        evidence={
            "shared_accounts": sorted(shared)[:10],
            "shared_count": len(shared),
            "rarity_weight": round(weight, 3),
            "expected_weight": round(expected, 3),
            "lift": round(lift, 2),
        },
    )


def _funds_path(ctx: CorrelationContext, a: Anchor, b: Anchor) -> DimensionOutcome:
    accounts_a = ctx.accounts_of.get(a.ref)
    accounts_b = ctx.accounts_of.get(b.ref)
    if not accounts_a or not accounts_b:
        which = a.ref if not accounts_a else b.ref
        return _unevaluable(
            "funds_path",
            FAMILY_FINANCIAL,
            f"{which} holds no account, so no route between them could be traced.",
        )

    best: ReachedAccount | None = None
    direction = ""
    for source, targets, label in ((a.ref, accounts_b, "→"), (b.ref, accounts_a, "←")):
        reached = ctx.reach.get(source, {})
        for account in targets:
            arrival = reached.get(account)
            if arrival is None:
                continue
            if best is None or (arrival.hops, -arrival.retention) < (best.hops, -best.retention):
                best = arrival
                direction = label

    truncated = a.ref in ctx.reach_truncated or b.ref in ctx.reach_truncated

    if best is None:
        if truncated:
            return _unevaluable(
                "funds_path",
                FAMILY_FINANCIAL,
                "The search was cut short at its frontier limit before the two could be "
                "connected or ruled out. No route was found; none was ruled out either.",
            )
        return DimensionOutcome(
            dimension_id="funds_path",
            family=FAMILY_FINANCIAL,
            evaluable=True,
            magnitude=0.0,
            summary=(
                f"No value-preserving route runs between them within "
                f"{ctx.model.path_max_hops} hops."
            ),
            evidence={"max_hops_searched": ctx.model.path_max_hops},
        )

    hop_score = ramp(float(best.hops), ctx.model.path_hops_trigger, ctx.model.path_hops_full)

    # How much of everything that account sent all year left along this route.
    #
    # Distance alone is not enough. Against the live graph, 5,527 pairs of
    # flagged subjects have a direct transfer between them, and the median one
    # is 3.3% of the sending account's annual outflow — an ordinary payment
    # between two busy parties, not a relationship. Scoring on hops alone put
    # 6,960 of those in the `probable` tier, which is a queue no analyst could
    # use and a claim ARGUS could not support.
    outflow = ctx.outflow_total.get(best.origin, 0.0)
    share = best.first_amount / outflow if outflow > 0 else 0.0
    concentration = ramp(
        share, ctx.model.path_concentration_trigger, ctx.model.path_concentration_full
    )
    magnitude = hop_score * concentration

    arrow = f"{a.ref} {direction} {b.ref}"
    summary = (
        f"Money moves {arrow} in {best.hops} {_plural(best.hops, 'hop')}, "
        f"retaining {best.retention:.0%} of its value, over {best.span.days} "
        f"{_plural(best.span.days, 'day')}. That first payment is {share:.0%} of "
        f"everything {best.origin} sent."
    )

    return DimensionOutcome(
        dimension_id="funds_path",
        family=FAMILY_FINANCIAL,
        evaluable=True,
        magnitude=magnitude,
        summary=summary,
        evidence={
            "hops": best.hops,
            "retention": round(best.retention, 3),
            "span_days": best.span.days,
            "direction": "a_to_b" if direction == "→" else "b_to_a",
            "origin_account": best.origin,
            "share_of_outflow": round(share, 4),
            "hop_score": round(hop_score, 3),
            "concentration_score": round(concentration, 3),
            "frontier_truncated": truncated,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Social
# ─────────────────────────────────────────────────────────────────────────────


def _co_attendance(ctx: CorrelationContext, a: Anchor, b: Anchor) -> DimensionOutcome:
    left = ctx.events_of.get(a.ref)
    right = ctx.events_of.get(b.ref)
    if not left or not right:
        which = a.ref if not left else b.ref
        return _unevaluable(
            "co_attendance",
            FAMILY_SOCIAL,
            f"{which} attended nothing on record, so co-attendance cannot be assessed.",
        )

    shared = left & right
    weight = overlap_weight(shared, ctx.event_frequency, population=ctx.population)
    magnitude = ramp(weight, ctx.model.co_attendance_trigger, ctx.model.co_attendance_full)

    if not shared:
        summary = f"They attended no event in common out of {len(left | right)} between them."
    else:
        smallest = min(shared, key=lambda event: ctx.event_frequency.get(event, 0))
        summary = (
            f"Present together at {len(shared)} {_plural(len(shared), 'event')} — "
            f"the smallest with {ctx.event_frequency.get(smallest, 0)} attendees in total."
        )

    return DimensionOutcome(
        dimension_id="co_attendance",
        family=FAMILY_SOCIAL,
        evaluable=True,
        magnitude=magnitude,
        summary=summary,
        evidence={
            "shared_events": sorted(shared)[:10],
            "shared_count": len(shared),
            "rarity_weight": round(weight, 3),
        },
    )


def _communication(ctx: CorrelationContext, a: Anchor, b: Anchor) -> DimensionOutcome:
    left = ctx.correspondents.get(a.ref)
    right = ctx.correspondents.get(b.ref)
    if left is None or right is None:
        which = a.ref if left is None else b.ref
        return _unevaluable(
            "communication",
            FAMILY_SOCIAL,
            f"{which} owns no device, so there is no communication record to compare.",
        )

    direct = left.get(b.ref, 0)
    if direct:
        magnitude = min(1.0, direct / max(1, ctx.model.contact_direct_full))
        return DimensionOutcome(
            dimension_id="communication",
            family=FAMILY_SOCIAL,
            evaluable=True,
            magnitude=magnitude,
            summary=(
                f"Their devices exchanged {direct} "
                f"{_plural(direct, 'communication')} directly."
            ),
            evidence={"direct_contacts": direct, "shared_correspondents": 0},
        )

    shared = set(left) & set(right)
    shared.discard(a.ref)
    shared.discard(b.ref)
    weight = overlap_weight(shared, ctx.correspondent_frequency, population=ctx.population)
    magnitude = ramp(weight, ctx.model.contact_shared_trigger, ctx.model.contact_shared_full)

    if not shared:
        summary = "They never spoke, and share no correspondent."
    else:
        summary = (
            f"They never spoke directly, but both are in contact with "
            f"{len(shared)} of the same {_plural(len(shared), 'person', 'people')}."
        )

    return DimensionOutcome(
        dimension_id="communication",
        family=FAMILY_SOCIAL,
        evaluable=True,
        magnitude=magnitude,
        summary=summary,
        evidence={
            "direct_contacts": 0,
            "shared_correspondents": len(shared),
            "rarity_weight": round(weight, 3),
        },
    )


def _affiliation(ctx: CorrelationContext, a: Anchor, b: Anchor) -> DimensionOutcome:
    left = ctx.orgs_of.get(a.ref)
    right = ctx.orgs_of.get(b.ref)
    if not left or not right:
        which = a.ref if not left else b.ref
        return _unevaluable(
            "affiliation",
            FAMILY_SOCIAL,
            f"{which} has no recorded directorship or employment.",
        )

    shared = left & right
    weight = overlap_weight(shared, ctx.org_frequency, population=ctx.population)
    magnitude = ramp(weight, ctx.model.affiliation_trigger, ctx.model.affiliation_full)

    if not shared:
        summary = "They answer to no organisation in common."
    else:
        smallest = min(shared, key=lambda org: ctx.org_frequency.get(org, 0))
        summary = (
            f"Both are tied to {len(shared)} of the same "
            f"{_plural(len(shared), 'organisation')} — {smallest} has "
            f"{ctx.org_frequency.get(smallest, 0)} such {_plural(ctx.org_frequency.get(smallest, 0), 'tie')} "
            f"among subjects under assessment."
        )

    return DimensionOutcome(
        dimension_id="affiliation",
        family=FAMILY_SOCIAL,
        evaluable=True,
        magnitude=magnitude,
        summary=summary,
        evidence={
            "shared_organisations": sorted(shared)[:10],
            "shared_count": len(shared),
            "rarity_weight": round(weight, 3),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Logistical
# ─────────────────────────────────────────────────────────────────────────────


def _shared_corridor(ctx: CorrelationContext, a: Anchor, b: Anchor) -> DimensionOutcome:
    left = ctx.corridor_of.get(a.ref)
    right = ctx.corridor_of.get(b.ref)
    if left is None or right is None:
        which = a.ref if left is None else b.ref
        return _unevaluable(
            "shared_corridor",
            FAMILY_LOGISTICAL,
            f"{which} has no recorded origin and destination.",
        )

    if left != right:
        return DimensionOutcome(
            dimension_id="shared_corridor",
            family=FAMILY_LOGISTICAL,
            evaluable=True,
            magnitude=0.0,
            summary="They run different routes.",
            evidence={"corridor_a": left, "corridor_b": right},
        )

    users = ctx.corridor_frequency.get(left, 0)
    magnitude = rarity_weight(users, population=ctx.population)
    return DimensionOutcome(
        dimension_id="shared_corridor",
        family=FAMILY_LOGISTICAL,
        evaluable=True,
        magnitude=magnitude,
        summary=(
            f"Both run the same route, {left.replace('>', ' → ')}, which carries "
            f"{users} of the {ctx.population} subjects under assessment."
        ),
        evidence={"corridor": left, "subjects_on_corridor": users},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Spatial and temporal — corroboration only, by design
# ─────────────────────────────────────────────────────────────────────────────


def _proximity(ctx: CorrelationContext, a: Anchor, b: Anchor) -> DimensionOutcome:
    place_a = ctx.place_of.get(a.ref)
    place_b = ctx.place_of.get(b.ref)
    points_a = ctx.place_points.get(a.ref, 0)
    points_b = ctx.place_points.get(b.ref, 0)
    floor = ctx.model.min_activity_points_for_place

    if place_a is None or place_b is None or points_a < floor or points_b < floor:
        which = a.ref if (place_a is None or points_a < floor) else b.ref
        return _unevaluable(
            "proximity",
            FAMILY_SPATIAL,
            (
                f"{which} has fewer than {floor} located activities, so it has no centre of "
                f"activity to compare. This is not a finding that they are far apart."
            ),
        )

    distance = haversine_km(place_a.lat, place_a.lng, place_b.lat, place_b.lng)
    magnitude = ramp(distance, ctx.model.proximity_trigger_km, ctx.model.proximity_full_km)
    return DimensionOutcome(
        dimension_id="proximity",
        family=FAMILY_SPATIAL,
        evaluable=True,
        magnitude=magnitude,
        summary=(
            f"Their activity centres on points {distance:,.0f} km apart "
            f"({points_a} and {points_b} located activities respectively)."
        ),
        evidence={
            "distance_km": round(distance, 2),
            "points_a": points_a,
            "points_b": points_b,
        },
    )


def _coincidence(ctx: CorrelationContext, a: Anchor, b: Anchor) -> DimensionOutcome:
    times_a = ctx.activity_of.get(a.ref, ())
    times_b = ctx.activity_of.get(b.ref, ())
    floor = ctx.model.min_activity_points_for_time

    if len(times_a) < floor or len(times_b) < floor:
        which = a.ref if len(times_a) < floor else b.ref
        return _unevaluable(
            "coincidence",
            FAMILY_TEMPORAL,
            (
                f"{which} has fewer than {floor} dated activities. A coincidence rate computed "
                f"from one or two events would be noise wearing a number."
            ),
        )

    count, earliest = window_overlap(times_a, times_b, window=ctx.model.coincidence_window)

    # Measured against chance, for the same reason the counterparty dimension is.
    # Scoring the raw count made this fire at full magnitude on 797 of 797
    # randomly chosen pairs against the live graph: with a median of 39 dated
    # activities each spread over a year, two unrelated subjects land within a
    # day of each other constantly. Counting coincidences was measuring how busy
    # the world is.
    window_hours = ctx.model.coincidence_window_hours
    expected = min(
        float(len(times_a)),
        len(times_a) * len(times_b) * (2 * window_hours / ctx.observed_span_hours)
        if ctx.observed_span_hours
        else 0.0,
    )
    lift = excess_over_chance(float(count), expected)

    if lift is None:
        # As above: nothing coinciding is a clean finding; coinciding with no
        # baseline to judge it against is not something ARGUS can score.
        if count == 0:
            return DimensionOutcome(
                dimension_id="coincidence",
                family=FAMILY_TEMPORAL,
                evaluable=True,
                magnitude=0.0,
                summary=(
                    f"Nothing either did fell within {window_hours} hours of the other."
                ),
                evidence={"coincidences": 0, "window_hours": window_hours},
            )
        return _unevaluable(
            "coincidence",
            FAMILY_TEMPORAL,
            (
                "The observed period is too short for chance coincidence to be estimated, "
                "so an excess over it cannot be either."
            ),
        )

    magnitude = ramp(lift, ctx.model.coincidence_trigger, ctx.model.coincidence_full)

    if count == 0:
        summary = (
            f"Nothing either did fell within {window_hours} hours of the other, against "
            f"{expected:.1f} such occasions expected by chance."
        )
    else:
        when = earliest.date().isoformat() if earliest else "an unrecorded date"
        summary = (
            f"{count} {_plural(count, 'occasion')} where both were active within "
            f"{window_hours} hours of each other — {lift:.1f}× the {expected:.1f} expected "
            f"from their activity volumes alone. First on {when}."
        )

    return DimensionOutcome(
        dimension_id="coincidence",
        family=FAMILY_TEMPORAL,
        evaluable=True,
        magnitude=magnitude,
        summary=summary,
        evidence={
            "coincidences": count,
            "expected": round(expected, 2),
            "lift": round(lift, 2),
            "window_hours": window_hours,
            "activity_a": len(times_a),
            "activity_b": len(times_b),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# The registry
# ─────────────────────────────────────────────────────────────────────────────

DIMENSIONS: tuple[DimensionDefinition, ...] = (
    DimensionDefinition(
        dimension_id="shared_counterparty",
        family=FAMILY_FINANCIAL,
        label="Shared counterparty",
        question="Does money from both pass through the same third account?",
        rationale=(
            "Two subjects paying the same account is the plainest financial tie there is, "
            "and it is what a control account looks like from the outside. It is only "
            "evidence in proportion to how few others use that account: a clearing account "
            "used by half the population connects everyone to everyone and means nothing."
        ),
        reads=("OWNS_ACCOUNT", "TRANSACTED_WITH.amount", "Account.account_id"),
        subject_types=FINANCIAL_TYPES,
        evaluate=_shared_counterparty,
    ),
    DimensionDefinition(
        dimension_id="funds_path",
        family=FAMILY_FINANCIAL,
        label="Funds path",
        question="Can the same money be followed from one to the other?",
        rationale=(
            "A route where each hop passes on most of what arrived, and the whole route "
            "completes inside a month, is the shape of layering. Requiring value to be "
            "preserved is what separates it from the fact that any two busy accounts are "
            "connected if you walk far enough."
        ),
        reads=("OWNS_ACCOUNT", "TRANSACTED_WITH.amount", "TRANSACTED_WITH.timestamp"),
        subject_types=FINANCIAL_TYPES,
        evaluate=_funds_path,
    ),
    DimensionDefinition(
        dimension_id="co_attendance",
        family=FAMILY_SOCIAL,
        label="Co-attendance",
        question="Were they in the same room?",
        rationale=(
            "Events in this world average under three attendees, so being at one together "
            "is genuinely narrow. One shared event is still weak — people meet — and the "
            "thresholds are set so that one does not reach the corroboration floor and two do."
        ),
        reads=("ATTENDED", "Event.event_id"),
        subject_types=frozenset({PERSON}),
        evaluate=_co_attendance,
    ),
    DimensionDefinition(
        dimension_id="communication",
        family=FAMILY_SOCIAL,
        label="Communication",
        question="Did they speak, or speak to the same people?",
        rationale=(
            "Direct contact between their devices is strong and needs no rarity weighting. "
            "A shared correspondent is much weaker and is weighted by how many others that "
            "correspondent speaks to, because a call centre is not a social tie."
        ),
        reads=("OWNS_DEVICE", "COMMUNICATED_WITH.timestamp"),
        subject_types=frozenset({PERSON}),
        evaluate=_communication,
    ),
    DimensionDefinition(
        dimension_id="affiliation",
        family=FAMILY_SOCIAL,
        label="Shared affiliation",
        question="Do they answer to the same organisation?",
        rationale=(
            "Directorship and employment are declared, durable ties. Weighted by how many "
            "subjects share the organisation, so a common employer counts for little and a "
            "two-director company counts for a great deal."
        ),
        reads=("DIRECTS", "EMPLOYED_BY"),
        subject_types=frozenset({PERSON, ORGANIZATION}),
        evaluate=_affiliation,
    ),
    DimensionDefinition(
        dimension_id="shared_corridor",
        family=FAMILY_LOGISTICAL,
        label="Shared corridor",
        question="Do they run the same route?",
        rationale=(
            "There are 1,119 distinct origin-destination pairs in this world and the busiest "
            "carries three shipments. A corridor is therefore close to an identifier, and two "
            "flagged shipments sharing one is a specific claim rather than a coincidence."
        ),
        reads=("Shipment.origin_id", "Shipment.destination_id"),
        subject_types=frozenset({SHIPMENT}),
        evaluate=_shared_corridor,
    ),
    DimensionDefinition(
        dimension_id="proximity",
        family=FAMILY_SPATIAL,
        label="Spatial proximity",
        question="Is their activity concentrated in the same place?",
        rationale=(
            "Deliberately capped so it can never establish a link by itself. Two people in "
            "one city are not associates by virtue of the city, and a radius wide enough to "
            "feel productive would connect most of the population to most of the rest. It "
            "earns its place as corroboration for a link already made on other grounds."
        ),
        reads=("Person.lat", "Person.lng", "OCCURRED_AT", "Location.lat", "Location.lng"),
        subject_types=frozenset({PERSON, ORGANIZATION, SHIPMENT}),
        evaluate=_proximity,
    ),
    DimensionDefinition(
        dimension_id="coincidence",
        family=FAMILY_TEMPORAL,
        label="Temporal coincidence",
        question="Were they active at the same times?",
        rationale=(
            "The weakest dimension here and capped lowest. In a world of forty thousand "
            "transactions, unrelated subjects coincide constantly. It is retained because a "
            "financial link that also lands in the same week is a better link than one that "
            "does not — and it is published with its own precision figure so that claim can "
            "be checked rather than believed."
        ),
        reads=("TRANSACTED_WITH.timestamp", "COMMUNICATED_WITH.timestamp", "Event.timestamp"),
        subject_types=frozenset({PERSON, ORGANIZATION, ACCOUNT, SHIPMENT}),
        evaluate=_coincidence,
    ),
)

DIMENSIONS_BY_ID: dict[str, DimensionDefinition] = {d.dimension_id: d for d in DIMENSIONS}


def evaluate_pair(ctx: CorrelationContext, a: Anchor, b: Anchor) -> list[DimensionOutcome]:
    """Every dimension's verdict on one pair, in registry order.

    Dimensions that do not apply to this combination of subject types are
    omitted rather than recorded as unevaluable — asking whether a shipment
    attended an event is not a question with a missing answer, it is not a
    question. Dimensions that apply but could not be computed *are* recorded, so
    the difference between "not asked" and "asked, unanswerable" survives.
    """
    outcomes: list[DimensionOutcome] = []
    for definition in DIMENSIONS:
        if not definition.applies_to(a, b):
            continue
        outcomes.append(definition.evaluate(ctx, a, b))
    return outcomes


# ─────────────────────────────────────────────────────────────────────────────
# Index construction
# ─────────────────────────────────────────────────────────────────────────────


def build_context(evidence: CorrelationEvidence, model: CorrelationModel) -> CorrelationContext:
    """Index the evidence once, for the whole run."""
    ctx = CorrelationContext(evidence=evidence, model=model)
    anchors = evidence.anchors

    # ── Accounts and counterparties ──────────────────────────────────────────
    accounts_of: dict[str, set[str]] = defaultdict(set)
    for account, owner in evidence.account_owner.items():
        if owner in anchors:
            accounts_of[owner].add(account)
        if account in anchors:
            accounts_of[account].add(account)
    # An Account anchor whose owner is unknown still holds itself.
    for ref, anchor in anchors.items():
        if anchor.subject_type == ACCOUNT:
            accounts_of[ref].add(ref)
    ctx.accounts_of = dict(accounts_of)

    outgoing: dict[str, list[tuple[str, float, datetime]]] = defaultdict(list)
    account_partners: dict[str, set[str]] = defaultdict(set)
    outflow: dict[str, float] = defaultdict(float)
    for transfer in evidence.transfers:
        outgoing[transfer.source_account].append(
            (transfer.target_account, transfer.amount, transfer.occurred_at)
        )
        outflow[transfer.source_account] += transfer.amount
        account_partners[transfer.source_account].add(transfer.target_account)
        account_partners[transfer.target_account].add(transfer.source_account)
    ctx.outflow_total = dict(outflow)

    counterparties: dict[str, set[str]] = {}
    for ref, owned in ctx.accounts_of.items():
        partners: set[str] = set()
        for account in owned:
            partners |= account_partners.get(account, set())
        counterparties[ref] = partners - owned
    ctx.counterparties = counterparties

    frequency: dict[str, int] = defaultdict(int)
    for partners in counterparties.values():
        for account in partners:
            frequency[account] += 1
    ctx.counterparty_frequency = dict(frequency)

    ctx.distinct_counterparties = len(frequency)
    rarities = [
        rarity_weight(count, population=max(2, len(anchors)))
        for count in frequency.values()
    ]
    ctx.mean_counterparty_rarity = sum(rarities) / len(rarities) if rarities else 0.0

    # Ownership, in both directions, so a subject and the account it holds can
    # be recognised as one entity rather than correlated with itself.
    contains: dict[str, set[str]] = defaultdict(set)
    for account, owner in evidence.account_owner.items():
        contains[owner].add(account)
        contains[account].add(owner)
    ctx.contains = dict(contains)

    # ── Reachability, computed once per anchor rather than once per pair ─────
    for ref, owned in ctx.accounts_of.items():
        if not owned:
            continue
        reached, truncated = forward_reach(
            sorted(owned),
            outgoing,
            max_hops=model.path_max_hops,
            min_hop_retention=model.path_min_hop_retention,
            min_total_retention=model.path_min_total_retention,
            window=model.path_window,
            max_frontier=model.path_max_frontier,
        )
        ctx.reach[ref] = reached
        if truncated:
            ctx.reach_truncated.add(ref)

    # ── Events ───────────────────────────────────────────────────────────────
    events_of: dict[str, set[str]] = defaultdict(set)
    event_attendance: dict[str, int] = defaultdict(int)
    for attendance in evidence.attendances:
        event_attendance[attendance.event_ref] += 1
        if attendance.person_ref in anchors:
            events_of[attendance.person_ref].add(attendance.event_ref)
    ctx.events_of = dict(events_of)
    ctx.event_frequency = dict(event_attendance)

    # ── Communications ───────────────────────────────────────────────────────
    correspondents: dict[str, dict[str, int]] = defaultdict(dict)
    for contact in evidence.contacts:
        for source, target in ((contact.person_a, contact.person_b), (contact.person_b, contact.person_a)):
            correspondents[source][target] = correspondents[source].get(target, 0) + 1
    # Anchors that own a device but never used it get an empty dict rather than
    # no entry at all: "owns a phone and never called anyone" is evaluable, and
    # clean. An anchor with no device gets no entry, and the dimension reports
    # itself unevaluable — which is the honest difference between the two.
    for ref in evidence.subjects_with_devices:
        if ref in anchors:
            correspondents.setdefault(ref, {})
    ctx.correspondents = {ref: dict(partners) for ref, partners in correspondents.items()}
    ctx.correspondent_frequency = {ref: len(partners) for ref, partners in ctx.correspondents.items()}

    # ── Affiliations ─────────────────────────────────────────────────────────
    orgs_of: dict[str, set[str]] = defaultdict(set)
    org_ties: dict[str, int] = defaultdict(int)
    for affiliation in evidence.affiliations:
        org_ties[affiliation.org_ref] += 1
        if affiliation.person_ref in anchors:
            orgs_of[affiliation.person_ref].add(affiliation.org_ref)
        if affiliation.org_ref in anchors:
            orgs_of[affiliation.org_ref].add(affiliation.org_ref)
    ctx.orgs_of = dict(orgs_of)
    ctx.org_frequency = dict(org_ties)

    # ── Places and activity ──────────────────────────────────────────────────
    points: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for attendance in evidence.attendances:
        if attendance.person_ref not in anchors:
            continue
        place = evidence.event_places.get(attendance.event_ref)
        if place is not None:
            points[attendance.person_ref].append((place.lat, place.lng))
    for ref, place in evidence.subject_places.items():
        if ref in anchors:
            points[ref].append((place.lat, place.lng))

    for ref, coordinates in points.items():
        middle = centroid(coordinates)
        if middle is None:
            continue
        ctx.place_of[ref] = Place(ref=ref, lat=middle[0], lng=middle[1])
        ctx.place_points[ref] = len(coordinates)

    ctx.activity_of = {ref: anchor.activity for ref, anchor in anchors.items()}

    # The span the data actually covers, from the data itself.
    moments = [moment for times in ctx.activity_of.values() for moment in times]
    if len(moments) >= 2:
        ctx.observed_span_hours = max(
            1.0, (max(moments) - min(moments)).total_seconds() / 3600.0
        )

    # ── Corridors ────────────────────────────────────────────────────────────
    corridor_users: dict[str, int] = defaultdict(int)
    for ref, corridor in evidence.corridors.items():
        ctx.corridor_of[ref] = corridor
        if ref in anchors:
            corridor_users[corridor] += 1
    ctx.corridor_frequency = dict(corridor_users)

    return ctx
