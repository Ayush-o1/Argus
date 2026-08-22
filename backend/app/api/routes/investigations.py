"""Investigations: opening one, working it, and closing it with an outcome.

Every route here reads or writes PostgreSQL. None of them touches the graph's
`Case` nodes, and none can: those were written by the scenario generator from
its own storylines, and an investigation surface that mixed them with analyst
work would be presenting the answer key as human judgement — the G-08 family
defect, in the one place it would do the most damage.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.api.dependencies import require_permission
from app.investigation.history import TRACKED_FIELDS, reconstruct, verify
from app.investigation.lifecycle import (
    INVESTIGATION_STATES,
    STATE_MEANING,
    TRANSITIONS,
    InvalidTransition,
    check_transition,
)
from app.investigation.outcomes import (
    CONFIDENCE_LEVELS,
    CONFIDENCE_MEANING,
    OUTCOME_CODES,
    OUTCOMES,
)
from app.models.envelope import Envelope, Meta
from app.repositories import investigation_repo
from app.security.roles import Permission
from app.security.sessions import AuthenticatedUser
from app.services import audit

router = APIRouter(
    prefix="/api/investigations",
    tags=["investigations"],
    dependencies=[Depends(require_permission(Permission.INVESTIGATION_READ))],
)

MAX_TITLE = 200
MAX_TEXT = 20_000
MAX_REASON = 2_000
MAX_NAME = 120


class Confidence(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class InvestigationState(StrEnum):
    OPEN = "open"
    ACTIVE = "active"
    CLOSED = "closed"


class Outcome(StrEnum):
    CONFIRMED = "confirmed"
    UNFOUNDED = "unfounded"
    INCONCLUSIVE = "inconclusive"
    REFERRED = "referred"


class Band(StrEnum):
    ELEVATED = "elevated"
    NOTABLE = "notable"
    ROUTINE = "routine"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class OpenRequest(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    # Required, not optional. An investigation with no stated hypothesis has no
    # proposition to confirm or find unfounded, so its outcome would measure
    # nothing — and measurement is the entire purpose of this object.
    hypothesis: str = Field(min_length=1, max_length=MAX_TEXT)
    confidence: Confidence
    confidence_basis: str = Field(min_length=1, max_length=MAX_TEXT)
    assigned_to: str | None = Field(default=None, max_length=MAX_NAME)
    alert_keys: list[str] = Field(default_factory=list, max_length=200)


class UpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=MAX_TITLE)
    hypothesis: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    confidence: Confidence | None = None
    confidence_basis: str | None = Field(default=None, min_length=1, max_length=MAX_TEXT)
    assigned_to: str | None = Field(default=None, max_length=MAX_NAME)
    unassign: bool = False
    note: str | None = Field(default=None, max_length=MAX_REASON)


class TransitionRequest(BaseModel):
    to_state: InvestigationState
    outcome: Outcome | None = None
    outcome_rationale: str | None = Field(default=None, max_length=MAX_TEXT)
    note: str | None = Field(default=None, max_length=MAX_REASON)


class ReviewRequest(BaseModel):
    concurs: bool
    note: str | None = Field(default=None, max_length=MAX_TEXT)


class FindingRequest(BaseModel):
    statement: str = Field(min_length=1, max_length=MAX_TEXT)
    confidence: Confidence
    cites: list[str] = Field(min_length=1, max_length=200)
    supersedes: str | None = None


class WithdrawRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=MAX_REASON)


class ActionRequest(BaseModel):
    description: str = Field(min_length=1, max_length=MAX_TEXT)
    assigned_to: str | None = Field(default=None, max_length=MAX_NAME)
    due_at: datetime | None = None


class CompleteActionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=MAX_REASON)


class EntityLinkRequest(BaseModel):
    entity_ref: str = Field(min_length=1, max_length=64)
    entity_type: str = Field(min_length=1, max_length=64)
    # Required. An evidence link with no stated reason is a named person
    # asserting two things are related with no recorded basis.
    reason: str = Field(min_length=1, max_length=MAX_REASON)


class AlertLinkRequest(BaseModel):
    alert_key: str = Field(min_length=1, max_length=256)
    reason: str = Field(default="", max_length=MAX_REASON)


class DissentRequest(BaseModel):
    subject_ref: str = Field(min_length=1, max_length=64)
    subject_type: str = Field(min_length=1, max_length=64)
    analyst_band: Band
    rationale: str = Field(min_length=1, max_length=MAX_TEXT)
    confidence: Confidence
    investigation_id: str | None = None


async def _audit_investigation(
    request: Request,
    user: AuthenticatedUser,
    action: str,
    resource_id: str,
    outcome: str = "success",
    before: dict | None = None,
    after: dict | None = None,
    detail: str | None = None,
) -> None:
    await audit.record(
        audit.AuditEvent(
            action=action,
            outcome=outcome,
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="Investigation",
            resource_id=resource_id,
            before_state=before,
            after_state=after,
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
            detail=detail,
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# The vocabulary, served rather than hardcoded in the client
#
# The UI renders the outcome buttons, the confidence levels and their meanings
# from this response. Hardcoding them in the frontend is how a vocabulary drifts
# — the backend gains a fifth outcome and the UI offers four, or worse, offers a
# fifth the database will reject.
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/vocabulary")
async def get_vocabulary() -> Envelope[dict]:
    return Envelope(
        data={
            "states": [
                {"code": s, "meaning": STATE_MEANING[s], "may_move_to": sorted(TRANSITIONS[s])}
                for s in INVESTIGATION_STATES
            ],
            "outcomes": [
                {
                    "code": o.code,
                    "label": o.label,
                    "means": o.means,
                    "counts_as_correct": o.counts_as_correct,
                }
                for o in OUTCOMES
            ],
            "outcome_note": (
                "`counts_as_correct` is what calibration may conclude about the rule that "
                "raised the alert. Null means this outcome says nothing either way and is "
                "excluded from precision rather than counted against it."
            ),
            "confidence_levels": [{"code": c, "means": CONFIDENCE_MEANING[c]} for c in CONFIDENCE_LEVELS],
            "confidence_note": (
                "Analytic confidence in ARGUS's own hypothesis. Deliberately not the "
                "Admiralty code used for source reliability and report credibility — those "
                "rate someone else's information, this rates a judgement. Ordinal: nothing "
                "averages these and there is no numeric equivalent."
            ),
            "due_date_note": (
                "An action's due date is a date a person recorded. Nothing in ARGUS watches "
                "it: there is no reminder, escalation or scheduler behind it."
            ),
        }
    )


@router.get("")
async def list_investigations(
    state: InvestigationState | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_READ)),
) -> Envelope[list]:
    rows = await investigation_repo.list_investigations(
        state=state.value if state else None,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    # Counted over the whole table, never over `rows` — the defect the audit
    # found on four surfaces (B-04, B-05) and Phase 7 found once more in its own
    # new code.
    total = await investigation_repo.count_investigations(state.value if state else None)
    return Envelope(data=rows, meta=Meta(total=total, page=page, page_size=page_size))


@router.get("/outcomes")
async def get_outcomes_by_rule(
    _: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_READ)),
) -> Envelope[dict]:
    """Closed-investigation outcomes, joined to the rules that raised the alerts.

    Counts, never rates. This is the input calibration will consume, and the
    denominators are published with it precisely so nobody computes a precision
    from four closed investigations and reports it as a measurement.
    """
    rows = await investigation_repo.outcomes_by_rule()
    counts = await investigation_repo.queue_counts()
    closed = sum(counts["by_outcome"].values())
    return Envelope(
        data={
            "by_rule": rows,
            "by_outcome": counts["by_outcome"],
            "closed_total": closed,
            "basis_note": (
                f"Derived from {closed} closed investigation(s). No rate is computed: "
                "a precision over a handful of outcomes has the same number of digits as "
                "one over thousands, and only the pair of counts distinguishes them."
            ),
        }
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def open_investigation(
    payload: OpenRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_CREATE)),
) -> Envelope[dict]:
    created = await investigation_repo.create_investigation(
        title=payload.title,
        hypothesis=payload.hypothesis,
        confidence=payload.confidence.value,
        confidence_basis=payload.confidence_basis,
        opened_by=user.username,
        actor_role=user.role,
        assigned_to=payload.assigned_to,
        alert_keys=tuple(payload.alert_keys),
    )
    await _audit_investigation(request, user, "investigation.open", created["inv_ref"], after=_auditable(created))
    return Envelope(data=created)


def _auditable(row: dict[str, Any]) -> dict[str, Any]:
    """The scalar fields of an investigation, for the audit record.

    Nested collections are excluded: an audit entry carrying every finding and
    evidence link would duplicate tables that are already append-only, and would
    grow without bound on a long investigation.
    """
    return {
        k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in row.items() if not isinstance(v, list | dict)
    }


@router.get("/{ref}")
async def get_investigation(
    ref: str,
    _: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_READ)),
) -> Envelope[dict]:
    found = await investigation_repo.get_investigation(ref)
    if found is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return Envelope(data=found)


@router.get("/{ref}/history")
async def get_history(
    ref: str,
    at: datetime | None = Query(None, description="Reconstruct the investigation as it stood at this instant."),
    _: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_READ)),
) -> Envelope[dict]:
    """The event log, and the investigation as it stood at any past moment.

    The `integrity` field is not decoration. Replaying the log checks each
    event's recorded previous value against the state the replay had reached; a
    mismatch means something changed this investigation without writing an
    event, which is the one thing an append-only history is there to make
    visible. The same argument as the audit log's hash chain in migration 001.
    """
    found = await investigation_repo.get_investigation(ref)
    if found is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    events = await investigation_repo.fetch_events(found["investigation_id"])
    break_found = verify(events)

    return Envelope(
        data={
            "inv_ref": found["inv_ref"],
            "events": events,
            "as_at": at,
            "reconstructed": reconstruct(events, at),
            "tracked_fields": sorted(TRACKED_FIELDS),
            "integrity": {
                "consistent": break_found is None,
                "break": (
                    None
                    if break_found is None
                    else {
                        "event_id": break_found.event_id,
                        "field": break_found.field,
                        "expected": break_found.expected,
                        "recorded": break_found.recorded,
                        "occurred_at": break_found.occurred_at,
                        "describes": break_found.describe(),
                    }
                ),
            },
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Working an investigation
# ─────────────────────────────────────────────────────────────────────────────


async def _require(ref: str) -> dict[str, Any]:
    found = await investigation_repo.get_investigation(ref)
    if found is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return found


@router.patch("/{ref}")
async def update_investigation(
    ref: str,
    payload: UpdateRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_UPDATE)),
) -> Envelope[dict]:
    found = await _require(ref)

    # Confidence and its basis move together. A `high` sitting above the
    # reasoning that justified `moderate` reads as though the reasoning
    # supports it, which is worse than either field being stale alone.
    if (payload.confidence is None) != (payload.confidence_basis is None):
        raise HTTPException(
            status_code=400,
            detail=(
                "confidence and confidence_basis must be changed together: a confidence "
                "level shown above the basis for a different one misrepresents both."
            ),
        )

    updated = await investigation_repo.update_fields(
        investigation_id=found["investigation_id"],
        actor_username=user.username,
        actor_role=user.role,
        title=payload.title,
        hypothesis=payload.hypothesis,
        confidence=payload.confidence.value if payload.confidence else None,
        confidence_basis=payload.confidence_basis,
        assigned_to=None if payload.unassign else payload.assigned_to,
        set_assigned=payload.unassign or payload.assigned_to is not None,
        note=payload.note,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    await _audit_investigation(
        request,
        user,
        "investigation.update",
        found["inv_ref"],
        before=_auditable(found),
        after=_auditable(updated),
    )
    return Envelope(data=updated)


@router.post("/{ref}/transition")
async def transition_investigation(
    ref: str,
    payload: TransitionRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_UPDATE)),
) -> Envelope[dict]:
    """Move an investigation between states.

    Closing requires an outcome and its rationale. That is checked here so the
    API can explain itself, and again by a CHECK constraint so it cannot be
    bypassed by anything that writes the table directly. Both exist on purpose:
    this is the field the whole phase is built around.
    """
    found = await _require(ref)
    try:
        check_transition(found["state"], payload.to_state.value)
    except InvalidTransition as exc:
        await _audit_investigation(
            request,
            user,
            "investigation.transition",
            found["inv_ref"],
            outcome="failure",
            detail=str(exc),
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if payload.to_state == InvestigationState.CLOSED:
        if payload.outcome is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Closing an investigation requires an outcome: "
                    + ", ".join(sorted(OUTCOME_CODES))
                    + ". Without one the work cannot be measured, which is the reason "
                    "this object exists."
                ),
            )
        if not (payload.outcome_rationale or "").strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    "An outcome requires the reasoning behind it. A verdict nobody can "
                    "review is not a record of anything."
                ),
            )
    elif payload.outcome is not None:
        raise HTTPException(status_code=400, detail="An outcome may only be recorded when closing.")

    updated = await investigation_repo.transition(
        investigation_id=found["investigation_id"],
        to_state=payload.to_state.value,
        actor_username=user.username,
        actor_role=user.role,
        outcome=payload.outcome.value if payload.outcome else None,
        outcome_rationale=payload.outcome_rationale,
        note=payload.note,
    )
    if updated is None:
        # The guarded UPDATE matched nothing: someone else moved it in between.
        raise HTTPException(
            status_code=409,
            detail=("The investigation changed state while this request was in flight. Reload it and try again."),
        )
    await _audit_investigation(
        request,
        user,
        "investigation.transition",
        found["inv_ref"],
        before={"state": found["state"]},
        after=_auditable(updated),
    )
    return Envelope(data=updated)


@router.post("/{ref}/review")
async def review_investigation(
    ref: str,
    payload: ReviewRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_REVIEW)),
) -> Envelope[dict]:
    """Record an independent judgement about a closed investigation.

    Three rules, and a live walkthrough of this endpoint is what produced two
    of them:

      - **Nobody reviews their own closure.** An investigator holds both
        INVESTIGATION_UPDATE and INVESTIGATION_REVIEW, so permissions were never
        going to prevent it, and the first version of this endpoint accepted a
        self-review without comment. Enforced in the repository's SQL as well as
        here, so no future caller can route around it.
      - **A review never overwrites an earlier review.** The first version
        stored reviews in four columns on the investigation, and a second
        reviewer's "concurs" erased a supervisor's recorded dissent, note and
        all — the same failure `analyst_assessments` exists to prevent, one
        level up. Reviews append.
      - **A review never changes the outcome.** A reviewer who thinks the
        verdict is wrong records that they think so. To put a different verdict
        on the record the investigation is reopened and closed again, and the
        log then holds both closures with the review between them.
    """
    found = await _require(ref)
    if found["state"] != "closed":
        raise HTTPException(
            status_code=409,
            detail="Only a closed investigation can be reviewed; there is no conclusion yet.",
        )
    if user.username == found["closed_by"]:
        raise HTTPException(
            status_code=409,
            detail=(
                "You closed this investigation, so you cannot review it. A review is an "
                "independent judgement about someone else's conclusion; agreeing with "
                "oneself measures nothing."
            ),
        )
    if not payload.concurs and not (payload.note or "").strip():
        raise HTTPException(
            status_code=400,
            detail="A review that does not concur must say why.",
        )

    review = await investigation_repo.record_review(
        investigation_id=found["investigation_id"],
        reviewer=user.username,
        actor_role=user.role,
        concurs=payload.concurs,
        note=payload.note,
    )
    if review is None:
        raise HTTPException(
            status_code=409,
            detail="The investigation is no longer closed, or you closed it yourself.",
        )
    await _audit_investigation(request, user, "investigation.review", found["inv_ref"], after=_auditable(review))
    return Envelope(data=review)


# ─────────────────────────────────────────────────────────────────────────────
# Evidence, findings and actions
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{ref}/alerts")
async def attach_alert(
    ref: str,
    payload: AlertLinkRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_UPDATE)),
) -> Envelope[dict]:
    found = await _require(ref)
    await investigation_repo.attach_alert(
        investigation_id=found["investigation_id"],
        alert_key=payload.alert_key,
        actor_username=user.username,
        actor_role=user.role,
        reason=payload.reason,
    )
    await _audit_investigation(
        request,
        user,
        "investigation.alert_attach",
        found["inv_ref"],
        after={"alert_key": payload.alert_key, "reason": payload.reason},
    )
    return Envelope(data={"attached": True})


@router.delete("/{ref}/alerts/{alert_key}")
async def detach_alert(
    ref: str,
    alert_key: str,
    request: Request,
    reason: str = Query(..., min_length=1, max_length=MAX_REASON),
    user: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_UPDATE)),
) -> Envelope[dict]:
    found = await _require(ref)
    ok = await investigation_repo.detach_alert(
        investigation_id=found["investigation_id"],
        alert_key=alert_key,
        actor_username=user.username,
        actor_role=user.role,
        reason=reason,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="No attached alert with that key")
    await _audit_investigation(
        request,
        user,
        "investigation.alert_detach",
        found["inv_ref"],
        before={"alert_key": alert_key},
        detail=reason,
    )
    return Envelope(data={"detached": True})


@router.post("/{ref}/entities")
async def link_entity(
    ref: str,
    payload: EntityLinkRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_UPDATE)),
) -> Envelope[dict]:
    found = await _require(ref)
    await investigation_repo.link_entity(
        investigation_id=found["investigation_id"],
        entity_ref=payload.entity_ref,
        entity_type=payload.entity_type,
        reason=payload.reason,
        actor_username=user.username,
        actor_role=user.role,
    )
    await _audit_investigation(
        request,
        user,
        "investigation.evidence_link",
        found["inv_ref"],
        after={"entity_ref": payload.entity_ref, "reason": payload.reason},
    )
    return Envelope(data={"linked": True})


@router.delete("/{ref}/entities/{entity_ref}")
async def unlink_entity(
    ref: str,
    entity_ref: str,
    request: Request,
    reason: str = Query(..., min_length=1, max_length=MAX_REASON),
    user: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_UPDATE)),
) -> Envelope[dict]:
    """Unlink evidence. Tombstoned, never deleted (audit G-11).

    A reason is required, where the Neo4j endpoint this replaces defaulted it to
    an empty string — and re-linking later leaves this removal on the record
    rather than clearing it, which the Neo4j version did not.
    """
    found = await _require(ref)
    ok = await investigation_repo.unlink_entity(
        investigation_id=found["investigation_id"],
        entity_ref=entity_ref,
        actor_username=user.username,
        actor_role=user.role,
        reason=reason,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="No live evidence link for that entity")
    await _audit_investigation(
        request,
        user,
        "investigation.evidence_unlink",
        found["inv_ref"],
        before={"entity_ref": entity_ref},
        detail=reason,
    )
    return Envelope(data={"removed": True})


@router.post("/{ref}/findings", status_code=status.HTTP_201_CREATED)
async def record_finding(
    ref: str,
    payload: FindingRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_UPDATE)),
) -> Envelope[dict]:
    found = await _require(ref)
    finding = await investigation_repo.record_finding(
        investigation_id=found["investigation_id"],
        statement=payload.statement,
        confidence=payload.confidence.value,
        cites=payload.cites,
        author_username=user.username,
        author_role=user.role,
        supersedes=payload.supersedes,
    )
    await _audit_investigation(
        request,
        user,
        "investigation.finding",
        found["inv_ref"],
        after={"finding_id": str(finding["finding_id"]), "statement": payload.statement},
    )
    return Envelope(data=finding)


@router.post("/{ref}/findings/{finding_id}/withdraw")
async def withdraw_finding(
    ref: str,
    finding_id: str,
    payload: WithdrawRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_UPDATE)),
) -> Envelope[dict]:
    found = await _require(ref)
    ok = await investigation_repo.withdraw_finding(
        investigation_id=found["investigation_id"],
        finding_id=finding_id,
        actor_username=user.username,
        actor_role=user.role,
        reason=payload.reason,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="No standing finding with that id")
    await _audit_investigation(
        request,
        user,
        "investigation.finding_withdraw",
        found["inv_ref"],
        before={"finding_id": finding_id},
        detail=payload.reason,
    )
    return Envelope(data={"withdrawn": True})


@router.post("/{ref}/actions", status_code=status.HTTP_201_CREATED)
async def record_action(
    ref: str,
    payload: ActionRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_UPDATE)),
) -> Envelope[dict]:
    found = await _require(ref)
    action = await investigation_repo.record_action(
        investigation_id=found["investigation_id"],
        description=payload.description,
        assigned_to=payload.assigned_to,
        due_at=payload.due_at,
        actor_username=user.username,
        actor_role=user.role,
    )
    await _audit_investigation(
        request,
        user,
        "investigation.action",
        found["inv_ref"],
        after={"action_id": str(action["action_id"]), "description": payload.description},
    )
    return Envelope(data=action)


@router.post("/{ref}/actions/{action_id}/complete")
async def complete_action(
    ref: str,
    action_id: str,
    payload: CompleteActionRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_UPDATE)),
) -> Envelope[dict]:
    found = await _require(ref)
    ok = await investigation_repo.complete_action(
        investigation_id=found["investigation_id"],
        action_id=action_id,
        actor_username=user.username,
        actor_role=user.role,
        note=payload.note,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="No open action with that id")
    await _audit_investigation(
        request,
        user,
        "investigation.action_complete",
        found["inv_ref"],
        after={"action_id": action_id},
    )
    return Envelope(data={"completed": True})


# ─────────────────────────────────────────────────────────────────────────────
# Analyst assessments — dissent (audit G-15)
#
# Mounted on its own router because a judgement about a subject is not owned by
# an investigation: an analyst may record one without opening a case, and the
# assessment surface reads them for subjects that were never investigated.
# ─────────────────────────────────────────────────────────────────────────────

assessments_router = APIRouter(
    prefix="/api/analyst-assessments",
    tags=["investigations"],
    dependencies=[Depends(require_permission(Permission.INVESTIGATION_READ))],
)


@assessments_router.post("", status_code=status.HTTP_201_CREATED)
async def record_analyst_assessment(
    payload: DissentRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.ASSESSMENT_DISSENT)),
) -> Envelope[dict]:
    """Record an analyst's own assessment of a subject, beside ARGUS's.

    This never modifies what the model published. The machine's band, its
    fingerprint and the time it was computed are copied into the record so the
    disagreement stays legible after the next assessment run moves the model on
    — otherwise "the analyst disagreed" would quietly become "the analyst
    agreed" the moment the model changed its mind.
    """
    recorded = await investigation_repo.record_analyst_assessment(
        subject_ref=payload.subject_ref,
        subject_type=payload.subject_type,
        analyst_band=payload.analyst_band.value,
        rationale=payload.rationale,
        confidence=payload.confidence.value,
        author_username=user.username,
        author_role=user.role,
        investigation_id=payload.investigation_id,
    )
    await audit.record(
        audit.AuditEvent(
            action="assessment.analyst_judgement",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="Subject",
            resource_id=payload.subject_ref,
            after_state={
                "analyst_band": payload.analyst_band.value,
                "machine_band": recorded["machine_band"],
                "dissents": recorded["dissents"],
            },
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
        )
    )
    return Envelope(data=recorded)


@assessments_router.get("")
async def list_analyst_assessments(
    subject_ref: list[str] = Query(default_factory=list),
    _: AuthenticatedUser = Depends(require_permission(Permission.INVESTIGATION_READ)),
) -> Envelope[dict]:
    """Standing analyst judgements for the given subjects.

    Every standing judgement is returned, not "the current one". Two analysts
    may hold different views of the same subject, and collapsing them to one
    would be ARGUS choosing a winner between two people — which is not a
    decision a database should make.
    """
    grouped = await investigation_repo.standing_analyst_assessments(list(subject_ref))
    return Envelope(data=grouped)
