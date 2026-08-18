"""What a correlation dimension is allowed to look at, and the shape it arrives in.

The same discipline as `app/assessment/evidence.py`, applied to a harder case.
Assessment had to avoid reading a *score*; correlation has to avoid reading a
*link*, and this graph is full of links that exist only because a storyline
created them:

  * `INVOLVES` joins an `Incident` to every entity its storyline named. Two
    entities sharing one are, by construction, the two entities a correlation
    engine is supposed to discover independently. Using it would score
    perfectly and prove nothing.
  * `LINKED_TO` does the same from the `Case` side, and the generator's case
    seeder builds cases directly from storylines.
  * `CONTROLS` (24 edges in the live graph) and `SHARES_DEVICE` (2) have no
    baseline population at all. Every instance is a plant.

What is left is the ordinary structure of the world: who paid whom, who
attended what, who works where, whose devices spoke, and where things happened.
That structure is generated independently of the storylines — the injector
*adds* to it rather than being its only source — so a dimension built on it is
measuring something real.

## The cost, stated

Two of the seven planted storyline types have no admissible trace whatsoever:
`identity_overlap` exists purely as `SHARES_DEVICE` edges, and
`document_forgery_ring` exists purely as flags on `Document` nodes. Correlation
cannot find either, and `evaluation.py` reports recall against them as zero
with the reason attached rather than dropping them from the denominator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.integrity import ALL_INADMISSIBLE_TOKENS

__all__ = [
    "ADMISSIBLE_INPUTS",
    "ALL_INADMISSIBLE_TOKENS",
    "Anchor",
    "Attendance",
    "Affiliation",
    "CorrelationEvidence",
    "DeviceContact",
    "Place",
    "Transfer",
]

# Graph data a correlation dimension may consult. Every dimension declares the
# subset it reads, and `test_correlation_isolation.py` asserts each declaration
# is a subset of this set — so adding a dimension that reaches further fails a
# test rather than passing review.
ADMISSIBLE_INPUTS: frozenset[str] = frozenset(
    {
        "Account.account_id",
        "OWNS_ACCOUNT",
        "TRANSACTED_WITH.amount",
        "TRANSACTED_WITH.timestamp",
        "OWNS_DEVICE",
        "COMMUNICATED_WITH.timestamp",
        "ATTENDED",
        "Event.event_id",
        "Event.timestamp",
        "OCCURRED_AT",
        "Location.location_id",
        "Location.lat",
        "Location.lng",
        "DIRECTS",
        "EMPLOYED_BY",
        "Person.lat",
        "Person.lng",
        "Organization.lat",
        "Organization.lng",
        "Shipment.shipment_id",
        "Shipment.origin_id",
        "Shipment.destination_id",
        "Shipment.departure",
    }
)


@dataclass(frozen=True)
class Transfer:
    """One `TRANSACTED_WITH` edge between two accounts."""

    source_account: str
    target_account: str
    amount: float
    occurred_at: datetime


@dataclass(frozen=True)
class DeviceContact:
    """One communication, resolved to the two people who own the devices.

    Device identity is deliberately dropped, exactly as in assessment: no
    admissible dimension asks *which* handset, and carrying it would invite one
    that does — which is how `SHARES_DEVICE` would creep back in through a side
    door.
    """

    person_a: str
    person_b: str
    occurred_at: datetime


@dataclass(frozen=True)
class Attendance:
    """One `ATTENDED` edge. `event_ref` is shared, so co-attendance is a join."""

    person_ref: str
    event_ref: str
    occurred_at: datetime | None


@dataclass(frozen=True)
class Affiliation:
    """A person's declared tie to an organisation — `DIRECTS` or `EMPLOYED_BY`.

    `CONTROLS` is absent by design and its absence is the point: it is the tie
    the shell-company storyline invents, and a dimension keyed on it would be
    reading the plant.
    """

    person_ref: str
    org_ref: str
    kind: str


@dataclass(frozen=True)
class Place:
    """A point on the ground, with the id of whatever fixes it there."""

    ref: str
    lat: float
    lng: float


@dataclass(frozen=True)
class Anchor:
    """A subject ARGUS found something in, and is therefore willing to correlate.

    Correlation runs over findings, not over the whole population. An anchor is
    a subject whose latest assessment fired at least one signal — which is a
    statement ARGUS made, not one the generator planted.

    `signal_ids` and `activity` travel with the anchor because two of the
    dimensions are about the finding rather than the entity: whether the same
    kind of thing was found in both, and whether it was found at the same time.
    """

    ref: str
    subject_type: str
    band: str
    score: float | None
    signal_ids: tuple[str, ...]
    activity: tuple[datetime, ...] = ()
    """When this subject was active, for the temporal dimension. Drawn from the
    subject's own transfers, contacts and attendances — not from the assessment
    run's clock, which would make every anchor coincide with every other."""


@dataclass
class CorrelationEvidence:
    """Everything the correlator may see, for one run.

    Gathered once for the whole population, like the assessment bundle, because
    the dimensions are population-relative: a shared counterparty means nothing
    until you know how many other people share it.
    """

    anchors: dict[str, Anchor] = field(default_factory=dict)

    account_owner: dict[str, str] = field(default_factory=dict)
    """account_id -> owner subject ref. An account is both a subject in its own
    right and the instrument through which a person or organisation transacts,
    so financial dimensions resolve to the owner where one exists."""

    transfers: list[Transfer] = field(default_factory=list)
    contacts: list[DeviceContact] = field(default_factory=list)
    attendances: list[Attendance] = field(default_factory=list)
    affiliations: list[Affiliation] = field(default_factory=list)

    event_places: dict[str, Place] = field(default_factory=dict)
    """event_ref -> where it happened, via `OCCURRED_AT`."""

    subject_places: dict[str, Place] = field(default_factory=dict)
    """subject ref -> its registered coordinates, where it has any."""

    corridors: dict[str, str] = field(default_factory=dict)
    """shipment ref -> "origin>destination". A shipment missing either endpoint
    is absent from this map rather than present with a partial key, so the
    corridor dimension reports it as unevaluable instead of matching it against
    every other half-known route."""

    folded_accounts: set[str] = field(default_factory=set)
    """Account anchors dropped because the entity that holds them is also an
    anchor.

    An account is the instrument through which a person or organisation
    transacts, so its counterparties, its transfers and its timing are already
    attributed to the holder. Keeping both as separate subjects does not
    correlate two things — it reports every financial link twice, once under the
    account and once under whoever holds it. Against the live graph that was
    8,730 duplicated links, and it made `Account-Person` the largest category of
    "discovery" in the system.

    Accounts whose holder is *not* an anchor stay, because there the account is
    the only subject ARGUS has a finding about. Recorded rather than silently
    dropped, so a run can say how many subjects it folded and why."""

    subjects_with_devices: set[str] = field(default_factory=set)
    """Subjects that own at least one device.

    Carried for the same reason assessment carries it: someone with no device
    has no communication record to be quiet or loud against, which is a
    different statement from "they made no calls". The difference decides
    whether the communication dimension is unevaluable or evaluable-and-clean,
    and there is no way to recover it from the contact list alone — a person
    with a phone they never used and a person with no phone both appear there
    as nothing."""

    gathered_at: datetime | None = None

    def anchor_refs(self) -> list[str]:
        return sorted(self.anchors)
