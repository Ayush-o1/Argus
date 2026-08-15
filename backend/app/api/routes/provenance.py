"""Provenance API — where a fact came from, how well it is supported, and what
disagrees with it.

The endpoint that matters most is `GET /subjects/{ref}`, which returns
observations, assertions and conflicts together. Conflicts are returned as
complete sets with no winner and no ordering by rating: resolving a
disagreement is an analyst's job, and a system that quietly picks a side hides
the disagreement from the only person qualified to settle it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.dependencies import require_permission
from app.models.envelope import Envelope
from app.models.provenance import (
    Assertion,
    Conflict,
    Credibility,
    EpistemicKind,
    Observation,
    Rating,
    Reliability,
    Source,
    SourceType,
    SubjectProvenance,
)
from app.repositories import provenance_repo
from app.repositories.entity_labels import resolve_label
from app.security.roles import Permission
from app.security.sessions import AuthenticatedUser
from app.services import audit
from app.services.provenance import ANALYST_SOURCE_ID

router = APIRouter(
    prefix="/api/provenance",
    tags=["provenance"],
    dependencies=[Depends(require_permission(Permission.PROVENANCE_READ))],
)

MAX_PREDICATE = 120
MAX_NOTE = 5_000
MAX_REASON = 1_000

# Kinds a human may claim. `observed` is excluded because a person entering a
# value into a form has not observed anything — the system of record did, and
# the observation layer is where that belongs. `inferred` is excluded because it
# means "an algorithm derived this", and an assertion that names a method it did
# not run is untraceable. Leaving both open would let the strongest-looking
# labels be applied by hand, which is precisely the over-claiming this phase
# exists to stop.
_ANALYST_KINDS = frozenset({EpistemicKind.ASSESSED, EpistemicKind.REPORTED})


class CreateAssertionRequest(BaseModel):
    subject_ref: str = Field(min_length=1, max_length=64)
    predicate: str = Field(min_length=1, max_length=MAX_PREDICATE)
    object_value: Any
    epistemic_kind: EpistemicKind
    reliability: Reliability
    credibility: Credibility
    note: str | None = Field(default=None, max_length=MAX_NOTE)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    supporting_observation_ids: list[str] = Field(default_factory=list, max_length=50)
    contradicting_observation_ids: list[str] = Field(default_factory=list, max_length=50)
    supersedes: str | None = None


class RetractAssertionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=MAX_REASON)


@router.get("/sources")
async def get_sources() -> Envelope[list[Source]]:
    """The source registry, including ARGUS's own.

    Deliberately readable by every role that can read intelligence: knowing that
    a figure came from a synthetic source rated F is part of reading the figure.
    """
    return Envelope(data=await provenance_repo.list_sources())


class RegisterSourceRequest(BaseModel):
    source_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str = Field(min_length=1, max_length=200)
    source_type: SourceType
    description: str = Field(min_length=1, max_length=2_000)
    reliability: Reliability
    # Required, not optional. A rating with no stated basis is an opinion
    # wearing a letter, and every assertion built on this source inherits it.
    reliability_basis: str = Field(min_length=1, max_length=2_000)
    is_synthetic: bool = False
    #: Sources sharing a group count once toward corroboration. Two feeds
    #: reprinting one wire service are one voice.
    independence_group: str | None = Field(default=None, max_length=64)
    #: How long data from this source stays current. Without it ARGUS cannot
    #: tell "quiet because nothing happened" from "quiet because it broke".
    staleness_hours: int | None = Field(default=None, ge=1, le=8_760)


@router.post("/sources")
async def register_source(
    payload: RegisterSourceRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INGEST_MANAGE)),
) -> Envelope[Source]:
    """Register a source.

    Registration is deliberately not an update: an existing source is left
    untouched. A reliability rating is an analytic judgement that every
    assertion resting on it inherits, so silently overwriting one would change
    what a body of past work means without anyone deciding to.
    """
    existing = await provenance_repo.get_source(payload.source_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Source {payload.source_id!r} is already registered. Changing a reliability "
                "rating re-weights every assertion that rests on it, so it is not a side "
                "effect of re-registering."
            ),
        )

    source = Source(
        source_id=payload.source_id,
        name=payload.name,
        source_type=payload.source_type,
        description=payload.description,
        reliability=payload.reliability,
        reliability_basis=payload.reliability_basis,
        is_synthetic=payload.is_synthetic,
        independence_group=payload.independence_group or payload.source_id,
        staleness_hours=payload.staleness_hours,
    )
    await provenance_repo.register_source(source)

    await audit.record(
        audit.AuditEvent(
            action="source.register",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="Source",
            resource_id=payload.source_id,
            after_state=source.model_dump(mode="json"),
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
        )
    )

    created = await provenance_repo.get_source(payload.source_id)
    if created is None:  # pragma: no cover - just written
        raise HTTPException(status_code=500, detail="Source was not persisted")
    return Envelope(data=created)


@router.get("/summary")
async def get_summary() -> Envelope[dict]:
    sources = await provenance_repo.list_sources()
    counts = await provenance_repo.counts()
    synthetic = [s for s in sources if s.is_synthetic]
    return Envelope(
        data={
            "counts": counts,
            "synthetic_source_ids": [s.source_id for s in synthetic],
            "has_synthetic_data": bool(synthetic),
        }
    )


@router.get("/subjects/{subject_ref}")
async def get_subject_provenance(
    subject_ref: str,
    as_of: datetime | None = Query(
        None,
        description=(
            "Reconstruct what ARGUS believed at this instant. Filters on when ARGUS "
            "learned or asserted something, not on when it happened."
        ),
    ),
    include_ended: bool = Query(
        False, description="Include retracted and superseded assertions."
    ),
    observation_limit: int = Query(50, ge=1, le=500),
) -> Envelope[SubjectProvenance]:
    if resolve_label(subject_ref) is None:
        raise HTTPException(status_code=400, detail=f"Unrecognised entity id: {subject_ref}")

    as_of_utc = _as_utc(as_of)

    observations = await provenance_repo.observations_for_subject(
        subject_ref, as_of=as_of_utc, limit=observation_limit
    )
    observation_total = await provenance_repo.count_observations_for_subject(
        subject_ref, as_of=as_of_utc
    )
    assertions = await provenance_repo.assertions_for_subject(
        subject_ref, as_of=as_of_utc, include_ended=include_ended
    )
    # Derived from the assertions already loaded rather than fetched again.
    # Conflicts are a grouping of the same rows, and running the query twice
    # doubled the cost of every entity page for no additional information.
    conflicts = provenance_repo.find_conflicts(
        subject_ref, [a for a in assertions if a.is_current] if include_ended else assertions
    )
    sources = await provenance_repo.sources_for_subject(subject_ref)

    return Envelope(
        data=SubjectProvenance(
            subject_ref=subject_ref,
            as_of=as_of_utc,
            observations=observations,
            observation_total=observation_total,
            assertions=assertions,
            conflicts=conflicts,
            sources=sources,
        )
    )


@router.get("/subjects/{subject_ref}/conflicts")
async def get_subject_conflicts(
    subject_ref: str, as_of: datetime | None = None
) -> Envelope[list[Conflict]]:
    if resolve_label(subject_ref) is None:
        raise HTTPException(status_code=400, detail=f"Unrecognised entity id: {subject_ref}")
    return Envelope(data=await provenance_repo.conflicts_for_subject(subject_ref, as_of=_as_utc(as_of)))


@router.get("/observations/{observation_id}")
async def get_observation(observation_id: str) -> Envelope[Observation]:
    observation = await provenance_repo.get_observation(observation_id)
    if observation is None:
        raise HTTPException(status_code=404, detail="Observation not found")
    return Envelope(data=observation)


@router.get("/assertions/{assertion_id}")
async def get_assertion(assertion_id: str) -> Envelope[Assertion]:
    assertion = await provenance_repo.get_assertion(assertion_id)
    if assertion is None:
        raise HTTPException(status_code=404, detail="Assertion not found")
    return Envelope(data=assertion)


@router.post("/assertions")
async def create_assertion(
    payload: CreateAssertionRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.ASSERTION_WRITE)),
) -> Envelope[Assertion]:
    """Record an analyst's judgement, attributed to them.

    An analyst assessment may contradict the machine's, and that is the point:
    the disagreement is preserved as a first-class record rather than resolved,
    so a reader sees both and knows a person dissented.
    """
    info = resolve_label(payload.subject_ref)
    if info is None:
        raise HTTPException(status_code=400, detail=f"Unrecognised entity id: {payload.subject_ref}")

    if payload.epistemic_kind not in _ANALYST_KINDS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"'{payload.epistemic_kind.value}' cannot be asserted by a person. "
                "Use 'assessed' for your own judgement or 'reported' to record what a "
                "source claims; 'observed' belongs to a system of record and 'inferred' "
                "to an algorithm that names its method."
            ),
        )

    evidence = [(oid, "supports") for oid in payload.supporting_observation_ids]
    evidence += [(oid, "contradicts") for oid in payload.contradicting_observation_ids]
    referenced = [oid for oid, _ in evidence]
    known = await provenance_repo.existing_observation_ids(referenced)
    unknown = [oid for oid in referenced if oid not in known]
    if unknown:
        # Every bad reference at once. Reporting them one per request turns
        # fixing a mistyped evidence list into a guessing game.
        raise HTTPException(
            status_code=400, detail=f"Unknown observation(s): {', '.join(unknown)}"
        )

    if payload.supersedes is not None:
        prior = await provenance_repo.get_assertion(payload.supersedes)
        if prior is None:
            raise HTTPException(status_code=400, detail="Unknown assertion to supersede")
        if prior.subject_ref != payload.subject_ref or prior.predicate != payload.predicate:
            raise HTTPException(
                status_code=400,
                detail="An assertion can only supersede one about the same subject and predicate",
            )

    assertion_id = await provenance_repo.record_assertion(
        subject_ref=payload.subject_ref,
        subject_type=info.label,
        predicate=payload.predicate,
        object_value=payload.object_value,
        epistemic_kind=payload.epistemic_kind,
        rating=Rating(reliability=payload.reliability, credibility=payload.credibility),
        method="analyst-judgement"
        if payload.epistemic_kind is EpistemicKind.ASSESSED
        else "source-report",
        asserted_by=f"user:{user.id}",
        valid_from=_as_utc(payload.valid_from),
        valid_until=_as_utc(payload.valid_until),
        note=payload.note,
        evidence=evidence,
        supersedes=payload.supersedes,
    )

    await audit.record(
        audit.AuditEvent(
            action="assertion.create",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="Assertion",
            resource_id=assertion_id,
            after_state={
                "subject_ref": payload.subject_ref,
                "predicate": payload.predicate,
                "object_value": payload.object_value,
                "epistemic_kind": payload.epistemic_kind.value,
                "reliability": payload.reliability.value,
                "credibility": payload.credibility.value,
                "source": ANALYST_SOURCE_ID,
                "supersedes": payload.supersedes,
            },
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
        )
    )

    created = await provenance_repo.get_assertion(assertion_id)
    if created is None:  # pragma: no cover - the row was just written
        raise HTTPException(status_code=500, detail="Assertion was not persisted")
    return Envelope(data=created)


@router.post("/assertions/{assertion_id}/retract")
async def retract_assertion(
    assertion_id: str,
    payload: RetractAssertionRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.ASSERTION_RETRACT)),
) -> Envelope[Assertion]:
    """Withdraw a belief, with a mandatory reason.

    The assertion is not deleted. It stays visible as retracted, with who
    retracted it and why, because an analyst who relied on it needs to be able
    to find out that they should not have.
    """
    existing = await provenance_repo.get_assertion(assertion_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Assertion not found")
    if existing.retracted_at is not None:
        raise HTTPException(status_code=409, detail="Assertion is already retracted")

    try:
        changed = await provenance_repo.retract_assertion(
            assertion_id, retracted_by=f"user:{user.id}", reason=payload.reason
        )
    except provenance_repo.RetractionRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not changed:
        # Lost a race with another retraction. Reporting success would claim
        # this actor's reason is the recorded one when it is not.
        raise HTTPException(status_code=409, detail="Assertion is already retracted")

    await audit.record(
        audit.AuditEvent(
            action="assertion.retract",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="Assertion",
            resource_id=assertion_id,
            before_state={
                "subject_ref": existing.subject_ref,
                "predicate": existing.predicate,
                "object_value": existing.object_value,
            },
            after_state={"retracted": True, "reason": payload.reason},
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
        )
    )

    retracted = await provenance_repo.get_assertion(assertion_id)
    if retracted is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Assertion disappeared")
    return Envelope(data=retracted)


def _as_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to a naive timestamp rather than letting the database guess.

    A naive datetime compared against a timestamptz column is interpreted in the
    server's session timezone, so the same query would mean different instants
    on differently configured hosts — and "what did we believe at 14:00" would
    silently return a different answer. Interpreting it as UTC is a stated
    convention rather than an inherited accident.
    """
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)
