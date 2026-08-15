from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from neo4j import AsyncDriver
from pydantic import BaseModel

from app.api.dependencies import get_db, require_permission
from app.models.envelope import Envelope, Meta
from app.repositories import alert_repo
from app.security.roles import Permission
from app.security.sessions import AuthenticatedUser
from app.services import audit

router = APIRouter(
    prefix="/api/alerts",
    tags=["alerts"],
    dependencies=[Depends(require_permission(Permission.ALERT_READ))],
)


class AlertStatus(StrEnum):
    """The states an alert may be in.

    `status` was previously an unvalidated `str` written straight to the node
    (audit B-13). A typo — or a crafted request — permanently set a status no
    filter matched, silently removing the alert from every queue. There is no
    recovery path in the UI for that, because the UI can only offer the statuses
    it knows about.
    """

    OPEN = "Open"
    UNDER_INVESTIGATION = "UnderInvestigation"
    CLOSED = "Closed"


class AlertSeverity(StrEnum):
    """Severities that qualify as alerts. Restricted to the two the alert view is
    defined by: `priority` was previously unvalidated, so `?priority=Low`
    returned Low-severity incidents through an endpoint whose contract says
    High/Critical (audit B-12)."""

    HIGH = "High"
    CRITICAL = "Critical"


class ReviewAlertRequest(BaseModel):
    status: AlertStatus


@router.get("")
async def list_alerts(
    status: AlertStatus | None = None,
    priority: AlertSeverity | None = None,
    page: int = Query(1, ge=1),
    # Bounded so a caller cannot ask the backend to materialise the entire
    # incident set in memory (audit B-31). A negative value previously produced
    # a negative SKIP and an unhandled 500.
    page_size: int = Query(50, ge=1, le=200),
    driver: AsyncDriver = Depends(get_db),
) -> Envelope[list]:
    alerts, total = await alert_repo.list_alerts(
        driver,
        status.value if status else None,
        priority.value if priority else None,
        page,
        page_size,
    )
    return Envelope(data=alerts, meta=Meta(total=total, page=page, page_size=page_size))


@router.get("/{alert_id}/related")
async def related_alerts(
    alert_id: str,
    limit: int = Query(50, ge=1, le=200),
    driver: AsyncDriver = Depends(get_db),
) -> Envelope[list]:
    """Alerts sharing this one's storyline, searched across the whole graph
    rather than the page the client happens to have loaded (audit B-29)."""
    return Envelope(data=await alert_repo.list_related_alerts(driver, alert_id, limit))


@router.put("/{alert_id}/review")
async def review_alert(
    alert_id: str,
    payload: ReviewAlertRequest,
    request: Request,
    driver: AsyncDriver = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission(Permission.ALERT_TRIAGE)),
) -> Envelope[dict]:
    """Change an alert's triage status.

    Before/after state is captured so review can answer "who downgraded this,
    when, and from what" — the question the audit found to be structurally
    unanswerable, since a bare `SET i.status = $status` left no record and there
    were no identities to attribute it to.
    """
    before = await alert_repo.get_alert(driver, alert_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert = await alert_repo.review_alert(
        driver, alert_id, payload.status.value, reviewed_by=user.username
    )
    if alert is None:  # pragma: no cover - existence was just confirmed
        raise HTTPException(status_code=404, detail="Alert not found")

    await audit.record(
        audit.AuditEvent(
            action="alert.review",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="Incident",
            resource_id=alert_id,
            before_state={"status": before.get("status"), "severity": before.get("severity")},
            after_state={"status": payload.status.value},
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
        )
    )
    return Envelope(data=alert)
