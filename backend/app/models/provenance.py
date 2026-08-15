"""The vocabulary of belief: how ARGUS knows a thing, and how well.

Three ideas, and the constraints that keep them honest.

**Epistemic kind.** ARGUS previously stored an observation, a source's claim, an
algorithm's derivation and an analyst's judgement as the same kind of fact, and
rendered them identically. Nothing in the UI could distinguish "a transaction
occurred" from "a model inferred a link". `EpistemicKind` is required on every
assertion so the distinction survives all the way to the screen.

**Two independent axes.** Source reliability (A–F) and information credibility
(1–6) come from the Admiralty Code (NATO STANAG 2511), which analysts already
know. They are stored, transported and displayed separately, and there is
deliberately no function anywhere in this module that combines them. Collapsing
them into "confidence: 0.62" destroys exactly the information an analyst needs:
that number cannot tell you whether the basis is one excellent source or four
poor ones, and those call for different actions. `test_provenance_model.py`
pins this by asserting no such function exists.

**Unknown is a value.** F and 6 both mean "cannot be judged". They are real
ratings, not missing data, and they are rendered as such. A system that
substitutes a plausible-looking default for an unknown is manufacturing
confidence, which is the failure this whole layer exists to prevent.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EpistemicKind(StrEnum):
    """How a claim came to be believed. Ordered from directly grounded to most
    derived — but this is a taxonomy, not a scale, and it is never scored."""

    OBSERVED = "observed"
    """Recorded directly by an instrument or system of record. The strongest
    footing available: a transaction that appears in a ledger."""

    REPORTED = "reported"
    """A source claims it. ARGUS holds the claim, not the fact. The reliability
    rating is doing real work here — this is the kind where it matters most."""

    INFERRED = "inferred"
    """Derived by an algorithm from other data. Must name its method and version,
    because an inference is only as reviewable as the process that produced it."""

    ASSESSED = "assessed"
    """A person's judgement, attributed to that person. May disagree with the
    machine, and that disagreement is preserved rather than resolved."""


class Reliability(StrEnum):
    """Admiralty source reliability. A property of the *source*, not the claim.

    Deliberately letters. A numeric encoding invites averaging, and this is an
    ordinal scale on which arithmetic is meaningless — the distance from A to B
    is not the distance from E to F, and no evidence anywhere establishes that
    it is.
    """

    A = "A"  # Completely reliable — history of complete reliability
    B = "B"  # Usually reliable — history of valid information most of the time
    C = "C"  # Fairly reliable — some history of valid information
    D = "D"  # Not usually reliable — some history of invalid information
    E = "E"  # Unreliable — history of invalid information
    F = "F"  # Cannot be judged — no basis for evaluation


class Credibility(StrEnum):
    """Admiralty information credibility. A property of *this claim*, not its
    source. A reliable source can report something uncorroborated, and an
    unreliable one can report something confirmed elsewhere — which is precisely
    why these are two axes and not one."""

    CONFIRMED = "1"  # Confirmed by independent sources
    PROBABLY_TRUE = "2"  # Logical, consistent with other information
    POSSIBLY_TRUE = "3"  # Reasonably logical, agrees with some other information
    DOUBTFUL = "4"  # Not confirmed, and not consistent with other information
    IMPROBABLE = "5"  # Contradicted by other information
    CANNOT_BE_JUDGED = "6"  # No basis for evaluation


RELIABILITY_MEANING: dict[str, str] = {
    "A": "Completely reliable",
    "B": "Usually reliable",
    "C": "Fairly reliable",
    "D": "Not usually reliable",
    "E": "Unreliable",
    "F": "Reliability cannot be judged",
}

CREDIBILITY_MEANING: dict[str, str] = {
    "1": "Confirmed by independent sources",
    "2": "Probably true",
    "3": "Possibly true",
    "4": "Doubtful",
    "5": "Improbable",
    "6": "Credibility cannot be judged",
}


class Rating(BaseModel):
    """An Admiralty rating: two characters, two meanings, no arithmetic.

    Rendered as "B2" — the form analysts read — with both axes always present.
    There is no `.score`, no `.numeric()`, and no ordering. Adding one would be
    the single change that undoes this layer, so its absence is asserted by test.
    """

    reliability: Reliability
    credibility: Credibility

    @property
    def code(self) -> str:
        return f"{self.reliability.value}{self.credibility.value}"

    @property
    def reliability_meaning(self) -> str:
        return RELIABILITY_MEANING[self.reliability.value]

    @property
    def credibility_meaning(self) -> str:
        return CREDIBILITY_MEANING[self.credibility.value]

    def is_unjudged(self) -> bool:
        """True when neither axis has a basis. Worth surfacing plainly: an
        unrated claim looks identical to a rated one at a glance, and it is not."""
        return (
            self.reliability is Reliability.F and self.credibility is Credibility.CANNOT_BE_JUDGED
        )


class SourceType(StrEnum):
    SYNTHETIC = "synthetic"
    HUMAN = "human"
    SYSTEM = "system"
    OSINT = "osint"
    PARTNER = "partner"
    SENSOR = "sensor"


class Source(BaseModel):
    source_id: str
    name: str
    source_type: SourceType
    description: str
    reliability: Reliability
    reliability_basis: str
    is_synthetic: bool
    independence_group: str
    staleness_hours: int | None = None
    is_active: bool = True
    registered_at: datetime | None = None


class Observation(BaseModel):
    """What a source said. Immutable once written."""

    observation_id: str
    source_id: str
    source_name: str
    source_reliability: Reliability
    source_is_synthetic: bool
    content_type: str
    payload: dict[str, Any]
    content_hash: str

    occurred_at: datetime | None = None
    collected_at: datetime | None = None
    recorded_at: datetime

    supersedes: str | None = None
    provenance_note: str | None = None
    subjects: list[str] = Field(default_factory=list)


class EvidenceRef(BaseModel):
    observation_id: str
    stance: str  # 'supports' | 'contradicts'
    source_id: str
    source_name: str
    source_reliability: Reliability
    source_is_synthetic: bool
    recorded_at: datetime
    occurred_at: datetime | None = None
    collected_at: datetime | None = None


class Corroboration(BaseModel):
    """How many *independent* voices support a claim.

    The count that matters is of independence groups, not of observations: two
    feeds reprinting one wire service are one voice, and counting them as two
    is how a single rumour comes to look like a pattern.
    """

    independent_sources: int
    supporting_observations: int
    contradicting_observations: int
    source_groups: list[str] = Field(default_factory=list)
    contradicting_groups: list[str] = Field(default_factory=list)


class Assertion(BaseModel):
    """A belief, with its basis attached."""

    assertion_id: str
    subject_ref: str
    subject_type: str
    predicate: str
    object_value: Any

    epistemic_kind: EpistemicKind
    rating: Rating
    method: str
    asserted_by: str
    """Stable identity: `user:<uuid>` or `source:<source_id>`. Never a name —
    a name can change, and an assertion's attribution must not."""
    asserted_by_display: str
    """The same attribution, readable. Resolved at query time against the user
    and source tables, falling back to the raw identifier when the referent is
    gone. Attribution nobody can read is not attribution, but the readable form
    is derived rather than stored so a rename does not require rewriting
    immutable rows."""
    asserted_at: datetime

    valid_from: datetime | None = None
    valid_until: datetime | None = None

    superseded_by: str | None = None
    superseded_at: datetime | None = None
    retracted_at: datetime | None = None
    retracted_by: str | None = None
    retracted_by_display: str | None = None
    retraction_reason: str | None = None

    note: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    corroboration: Corroboration | None = None

    @property
    def is_current(self) -> bool:
        return self.retracted_at is None and self.superseded_at is None


class Conflict(BaseModel):
    """Two or more current assertions about the same subject and predicate that
    do not agree.

    There is no `winner`, no `preferred`, and no ordering by rating — by design.
    A system that silently picks one is more dangerous than one that shows the
    disagreement, because it hides the conflict from the only party qualified to
    resolve it. The API returns every side; the UI renders them beside each
    other.
    """

    subject_ref: str
    predicate: str
    assertions: list[Assertion]


class SubjectProvenance(BaseModel):
    """Everything ARGUS can say about why it believes what it believes about one
    entity, as at a point in time."""

    subject_ref: str
    as_of: datetime | None = None
    observations: list[Observation] = Field(default_factory=list)
    observation_total: int = 0
    """How many observations exist, against however many are listed. A
    provenance view that silently showed the first fifty of two hundred would be
    the same defect Phase 0 removed from the timeline and the alert spread: a
    partial set rendered with the authority of a complete one."""
    assertions: list[Assertion] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
