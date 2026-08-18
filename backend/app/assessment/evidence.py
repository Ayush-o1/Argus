"""What the assessor is allowed to look at, and the shape it arrives in.

The types here are deliberately plain: they carry the facts a signal needs and
nothing else. That is the point. If `PersonFact` had a `risk_score` field, some
future signal would eventually read it, and the circularity this phase exists
to remove would be back — quietly, and with a green test suite.

## Admissibility

`ADMISSIBLE_INPUTS` is the whitelist of graph data a signal may consult. It is
narrower than "everything except the risk fields": the reasoning, and the list
of what is disqualified, live in `app/integrity.py`, which Phase 6 promoted to
a shared declaration when correlation became the second package that needs it.

The consequence is that some planted phenomena are *not detectable* by any
admissible signal. That is reported as a finding by `evaluation.py` rather than
worked around, because the alternative — a detector that reads the plant — is
the exact failure this phase was commissioned to remove.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.integrity import INADMISSIBLE_TOKENS

__all__ = [
    "ADMISSIBLE_INPUTS",
    "INADMISSIBLE_TOKENS",
    "ASSESSED_TYPES",
    "AccountFact",
    "Contact",
    "Directorship",
    "EvidenceBundle",
    "ShipmentFact",
    "Transfer",
]

# Graph data a signal may read. Anything not named here is out of bounds, and
# `test_assessment_admissibility.py` asserts every signal's declared `reads` is
# a subset of this set.
ADMISSIBLE_INPUTS: frozenset[str] = frozenset(
    {
        "Account.offshore",
        "Account.account_id",
        "TRANSACTED_WITH.amount",
        "TRANSACTED_WITH.timestamp",
        "COMMUNICATED_WITH.timestamp",
        "OWNS_ACCOUNT",
        "OWNS_DEVICE",
        "DIRECTS",
        "EMPLOYED_BY",
        "Shipment.detour_ratio",
        "Shipment.manifest",
        "Shipment.declared_manifest",
        "Shipment.origin_region",
        "Shipment.destination_region",
    }
)

SUBJECT_PERSON = "Person"
SUBJECT_ORGANIZATION = "Organization"
SUBJECT_ACCOUNT = "Account"
SUBJECT_SHIPMENT = "Shipment"

ASSESSED_TYPES: tuple[str, ...] = (
    SUBJECT_PERSON,
    SUBJECT_ORGANIZATION,
    SUBJECT_ACCOUNT,
    SUBJECT_SHIPMENT,
)


@dataclass(frozen=True)
class Transfer:
    """One `TRANSACTED_WITH` edge, reduced to the three facts a signal uses."""

    transfer_id: str
    source_account: str
    target_account: str
    amount: float
    occurred_at: datetime


@dataclass(frozen=True)
class Contact:
    """One device-to-device communication, resolved to the two people who own
    the devices. Device identity is not carried: no admissible signal asks
    which handset was used, and carrying it would invite one that does."""

    person_a: str
    person_b: str
    occurred_at: datetime


@dataclass(frozen=True)
class AccountFact:
    account_id: str
    offshore: bool
    owner_ref: str | None
    owner_type: str | None


@dataclass(frozen=True)
class ShipmentFact:
    shipment_id: str
    detour_ratio: float | None
    origin_region: str | None
    destination_region: str | None
    manifest: str | None
    declared_manifest: str | None


@dataclass(frozen=True)
class Directorship:
    person_ref: str
    org_ref: str


@dataclass
class EvidenceBundle:
    """Everything the assessor may see, for one run.

    Gathered once for the whole population rather than per subject, because the
    signals that matter are population-relative: a burst is only a burst
    against a baseline, and a funds cycle is a property of a set of accounts
    that no single account can see from where it sits.
    """

    subjects: dict[str, str] = field(default_factory=dict)
    """subject_ref -> subject_type, for every entity in scope."""

    accounts: list[AccountFact] = field(default_factory=list)
    transfers: list[Transfer] = field(default_factory=list)
    contacts: list[Contact] = field(default_factory=list)
    shipments: list[ShipmentFact] = field(default_factory=list)
    directorships: list[Directorship] = field(default_factory=list)
    persons_with_devices: set[str] = field(default_factory=set)
    """People who own at least one device. Someone with no device has no
    communication history to be quiet or loud against, which is a different
    statement from "they made no calls" — the difference decides whether the
    communication signal is evaluable or silent."""

    gathered_at: datetime | None = None

    def refs_of_type(self, subject_type: str) -> list[str]:
        return sorted(ref for ref, kind in self.subjects.items() if kind == subject_type)
