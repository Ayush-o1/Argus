"""The alert queue, its groups, and everything an analyst can do to an alert.

Replaces the severity filter over generator-written `Incident` nodes. Every
route here reads or writes the alerting tables in PostgreSQL; none touches the
graph, and none can reach `Incident` — `test_alerting_isolation.py` fails the
build if that changes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from neo4j import AsyncDriver
from pydantic import BaseModel, Field

from app.alerting.lifecycle import (
    ALERT_STATES,
    DISMISSAL_REASONS,
    STATE_MEANING,
    TERMINAL_STATES,
    TRANSITIONS,
    InvalidTransition,
    check_transition,
)
from app.alerting.rules import RULES, rules_fingerprint
from app.alerting.suppression import MAX_SUPPRESSION, SuppressionScopeError, validate_suppression
from app.api.dependencies import get_db, require_permission
from app.models.envelope import Envelope, Meta
from app.repositories import alert_findings_repo, alert_repo
from app.security.roles import Permission
from app.security.sessions import AuthenticatedUser
from app.services import audit, queue
from app.services.alerting import ALERTING_JOB_KIND

router = APIRouter(
    prefix="/api/alerts",
    tags=["alerts"],
    dependencies=[Depends(require_permission(Permission.ALERT_READ))],
)


class AlertState(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class TransitionRequest(BaseModel):
    to_state: AlertState
    reason_code: str | None = None
    note: str | None = Field(default=None, max_length=2000)


class AssignRequest(BaseModel):
    assignee: str | None = Field(default=None, max_length=64)


class SuppressionRequest(BaseModel):
    rule_id: str | None = Field(default=None, max_length=128)
    subject_ref: str | None = Field(default=None, max_length=128)
    reason_code: str = Field(max_length=64)
    note: str = Field(max_length=2000)
    expires_at: datetime


def _serialise(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("priority",):
        if out.get(key) is not None:
            out[key] = float(out[key])
    out["scope"] = list(out.get("scope") or [])
    return out


@router.get("/model")
async def alert_model() -> Envelope[dict]:
    """The rule set, in the terms it is written in.

    Published for the same reason the risk and correlation models are: a queue
    that cannot say what raised its items, or what would make one wrong, is
    asking to be trusted rather than read.
    """
    return Envelope(
        data={
            "rules_fingerprint": rules_fingerprint(),
            "rules": [
                {
                    "rule_id": r.rule_id,
                    "version": r.version,
                    "title": r.title,
                    "means": r.means,
                    "would_be_wrong_if": r.would_be_wrong_if,
                    "reads": sorted(r.reads),
                    "independent_methods": r.independent_methods,
                }
                for r in RULES
            ],
            "states": [{"state": s, "meaning": STATE_MEANING[s]} for s in ALERT_STATES],
            "transitions": {k: sorted(v) for k, v in TRANSITIONS.items()},
            "dismissal_reasons": [
                {
                    "code": d.code,
                    "label": d.label,
                    "means": d.means,
                    "counts_as_false_positive": d.counts_as_false_positive,
                }
                for d in DISMISSAL_REASONS
            ],
            "max_suppression_days": MAX_SUPPRESSION.days,
            "priority_note": (
                "Priority orders the queue from corroboration, confidence, magnitude "
                "and recency. It deliberately excludes asset criticality: ARGUS has no "
                "asset register, so any value for it would be invented rather than "
                "measured."
            ),
        }
    )


@router.get("/summary")
async def alert_summary() -> Envelope[dict]:
    counts = await alert_repo.queue_counts()
    counts["groups"] = await alert_repo.count_groups()
    runs = await alert_repo.list_runs(limit=1)
    return Envelope(
        data={
            "counts": counts,
            "latest_run": runs[0] if runs else None,
            "suppressed_note": (
                f"{counts.get('suppressed', 0)} alerts are hidden from the default "
                "queue by an active suppression. They were still raised and counted, "
                "and are one filter away."
            ),
        }
    )


@router.get("")
async def list_alerts(
    state: AlertState | None = None,
    suppressed: bool = False,
    include_suppressed: bool = False,
    group_key: str | None = Query(default=None, max_length=64),
    subject_ref: str | None = Query(default=None, max_length=128),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Envelope[list]:
    rows, total = await alert_repo.list_alerts(
        state=state.value if state else None,
        include_suppressed=include_suppressed,
        suppressed_only=suppressed,
        group_key=group_key,
        subject_ref=subject_ref,
        page=page,
        page_size=page_size,
    )
    return Envelope(
        data=[_serialise(r) for r in rows],
        meta=Meta(total=total, page=page, page_size=page_size),
    )


@router.get("/groups")
async def list_groups(limit: int = Query(50, ge=1, le=200)) -> Envelope[list]:
    """The queue rolled up to one row per story.

    This is the answer to alert fatigue that is actually defensible: a group is
    a correlated cluster ARGUS already published, not a similarity heuristic
    invented at display time.
    """
    rows = await alert_repo.group_rollup(limit)
    out = []
    for r in rows:
        item = dict(r)
        if item.get("top_priority") is not None:
            item["top_priority"] = float(item["top_priority"])
        item["subjects"] = list(item.get("subjects") or [])
        item["rule_ids"] = [x for x in (item.get("rule_ids") or []) if x]
        out.append(item)
    return Envelope(data=out)


@router.get("/suppressions")
async def list_suppressions(active_only: bool = True) -> Envelope[list]:
    rows = await alert_repo.list_suppressions(active_only=active_only)
    return Envelope(data=[{**r, "suppression_id": str(r["suppression_id"])} for r in rows])


@router.get("/evaluation")
async def latest_evaluation() -> Envelope[dict | None]:
    row = await alert_repo.latest_evaluation()
    if row is None:
        return Envelope(data=None)
    out = dict(row)
    for key in ("precision_strict", "recall"):
        if out.get(key) is not None:
            out[key] = float(out[key])
    return Envelope(data=out)


@router.get("/runs")
async def list_runs(limit: int = Query(20, ge=1, le=100)) -> Envelope[list]:
    return Envelope(data=await alert_repo.list_runs(limit))


@router.get("/{alert_key}")
async def get_alert(
    alert_key: str,
    driver: AsyncDriver = Depends(get_db),
) -> Envelope[dict]:
    row = await alert_repo.get_alert(alert_key)
    if row is None:
        raise HTTPException(status_code=404, detail="No alert with that key.")
    data = _serialise(row)

    # Display context for the subjects, and the spread across all of them.
    # Computed over the whole scope rather than over a preview: the audit found
    # the previous alert surface deriving its "Spread" figures from a five-entity
    # slice and presenting them as the alert's reach (B-04).
    context = await alert_findings_repo.subject_context(driver, data["scope"])
    data["subjects"] = [context[ref] for ref in data["scope"] if ref in context]
    data["spread"] = alert_findings_repo.spread_of(context)

    data["transitions"] = await alert_repo.list_transitions(alert_key)
    data["occurrences"] = [
        {**o, "priority": float(o["priority"]), "magnitude": float(o["magnitude"]),
         "confidence": float(o["confidence"])}
        for o in await alert_repo.list_occurrences(alert_key)
    ]
    return Envelope(data=data)


@router.post("/{alert_key}/transition")
async def transition_alert(
    alert_key: str,
    payload: TransitionRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.ALERT_TRIAGE)),
) -> Envelope[dict]:
    """Move an alert through its lifecycle.

    The legality check runs before anything is written, and its message names
    what is reachable from here rather than saying "invalid status" — the audit
    found a bare `SET i.status = $status` that would accept any string,
    including one no filter matched, with no route back.
    """
    current = await alert_repo.get_alert(alert_key)
    if current is None:
        raise HTTPException(status_code=404, detail="No alert with that key.")

    try:
        check_transition(current["state"], payload.to_state.value, payload.reason_code)
    except InvalidTransition as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    updated = await alert_repo.apply_transition(
        alert_key=alert_key,
        from_state=current["state"],
        to_state=payload.to_state.value,
        reason_code=payload.reason_code,
        note=payload.note,
        actor_username=user.username,
        actor_role=user.role,
        terminal=payload.to_state.value in TERMINAL_STATES,
    )
    if updated is None:
        # The guarded UPDATE matched nothing, so someone else moved this alert
        # between the read and the write.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This alert changed while you were working on it. Reload and try again.",
        )

    await audit.record(
        audit.AuditEvent(
            action="alert.transition",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="Alert",
            resource_id=alert_key,
            before_state={"state": current["state"]},
            after_state={
                "state": payload.to_state.value,
                "reason_code": payload.reason_code,
            },
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
        )
    )
    return Envelope(data=_serialise(updated))


@router.post("/{alert_key}/assign")
async def assign_alert(
    alert_key: str,
    payload: AssignRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.ALERT_TRIAGE)),
) -> Envelope[dict]:
    before = await alert_repo.get_alert(alert_key)
    if before is None:
        raise HTTPException(status_code=404, detail="No alert with that key.")

    updated = await alert_repo.assign_alert(alert_key, payload.assignee)
    if updated is None:  # pragma: no cover - existence just confirmed
        raise HTTPException(status_code=404, detail="No alert with that key.")

    await audit.record(
        audit.AuditEvent(
            action="alert.assign",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="Alert",
            resource_id=alert_key,
            before_state={"assigned_to": before.get("assigned_to")},
            after_state={"assigned_to": payload.assignee},
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
        )
    )
    return Envelope(data=_serialise(updated))


@router.post("/suppressions")
async def create_suppression(
    payload: SuppressionRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.ALERT_SUPPRESS)),
) -> Envelope[dict]:
    try:
        validate_suppression(
            rule_id=payload.rule_id,
            subject_ref=payload.subject_ref,
            expires_at=payload.expires_at,
            note=payload.note,
        )
    except SuppressionScopeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    row = await alert_repo.create_suppression(
        rule_id=payload.rule_id,
        subject_ref=payload.subject_ref,
        reason_code=payload.reason_code,
        note=payload.note,
        created_by=user.username,
        expires_at=payload.expires_at,
    )
    await audit.record(
        audit.AuditEvent(
            action="alert.suppression.create",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="AlertSuppression",
            resource_id=str(row["suppression_id"]),
            after_state={
                "rule_id": payload.rule_id,
                "subject_ref": payload.subject_ref,
                "expires_at": payload.expires_at.isoformat(),
                "reason_code": payload.reason_code,
            },
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
        )
    )
    return Envelope(data={**row, "suppression_id": str(row["suppression_id"])})


@router.delete("/suppressions/{suppression_id}")
async def revoke_suppression(
    suppression_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.ALERT_SUPPRESS)),
) -> Envelope[dict]:
    row = await alert_repo.revoke_suppression(suppression_id, user.username)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="No active suppression with that id. It may already have been revoked.",
        )
    await audit.record(
        audit.AuditEvent(
            action="alert.suppression.revoke",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="AlertSuppression",
            resource_id=suppression_id,
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
        )
    )
    return Envelope(data={**row, "suppression_id": str(row["suppression_id"])})


@router.post("/run")
async def run_alerting(
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.ALERT_RUN)),
) -> Envelope[dict]:
    job_id = await queue.enqueue(
        ALERTING_JOB_KIND,
        {"triggered_by": user.username},
        idempotency_key=f"{ALERTING_JOB_KIND}:{datetime.now(UTC).strftime('%Y%m%d%H%M')}",
    )
    await audit.record(
        audit.AuditEvent(
            action="alerting.run.requested",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="AlertRun",
            resource_id=str(job_id),
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
        )
    )
    return Envelope(data={"job_id": job_id, "status": "queued"})
