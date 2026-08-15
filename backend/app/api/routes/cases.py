from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from neo4j import AsyncDriver
from pydantic import BaseModel, Field

from app.api.dependencies import get_db, require_permission
from app.models.envelope import Envelope, Meta
from app.repositories import case_repo
from app.security.roles import Permission
from app.security.sessions import AuthenticatedUser
from app.services import audit

router = APIRouter(
    prefix="/api/cases",
    tags=["cases"],
    dependencies=[Depends(require_permission(Permission.CASE_READ))],
)


class CaseStatus(StrEnum):
    """Case states. Previously a free-form `str` written straight to the node via
    `SET c += $updates` (audit B-13): a typo set a status no filter matched, and
    the case vanished from every queue with no way back through the UI."""

    DRAFT = "Draft"
    OPEN = "Open"
    UNDER_REVIEW = "UnderReview"
    CLOSED = "Closed"


class CasePriority(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


# Bounded so a caller cannot store an unbounded blob on the node. These are
# generous for real analyst use and still finite.
MAX_TITLE = 200
MAX_NOTES = 20_000
MAX_REASON = 1_000
MAX_ANALYST = 120


class CreateCaseRequest(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    priority: CasePriority = CasePriority.MEDIUM
    notes: str = Field(default="", max_length=MAX_NOTES)


class UpdateCaseRequest(BaseModel):
    status: CaseStatus | None = None
    priority: CasePriority | None = None
    notes: str | None = Field(default=None, max_length=MAX_NOTES)
    assigned_analyst: str | None = Field(default=None, max_length=MAX_ANALYST)


class AddEntityRequest(BaseModel):
    entity_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=MAX_REASON)


async def _audit_case(
    request: Request,
    user: AuthenticatedUser,
    action: str,
    case_id: str,
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
            resource_type="Case",
            resource_id=case_id,
            before_state=before,
            after_state=after,
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
            detail=detail,
        )
    )


@router.get("")
async def list_cases(
    status: CaseStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    driver: AsyncDriver = Depends(get_db),
) -> Envelope[list]:
    cases, total = await case_repo.list_cases(driver, status.value if status else None, page, page_size)
    return Envelope(data=cases, meta=Meta(total=total, page=page, page_size=page_size))


@router.post("")
async def create_case(
    payload: CreateCaseRequest,
    request: Request,
    driver: AsyncDriver = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission(Permission.CASE_CREATE)),
) -> Envelope[dict]:
    case = await case_repo.create_case(
        driver, payload.title, payload.priority.value, payload.notes, opened_by=user.username
    )
    await _audit_case(request, user, "case.create", case["case_id"], after=case)
    return Envelope(data=case)


@router.get("/{case_id}")
async def get_case(case_id: str, driver: AsyncDriver = Depends(get_db)) -> Envelope[dict]:
    case = await case_repo.get_case(driver, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return Envelope(data=case)


@router.put("/{case_id}")
async def update_case(
    case_id: str,
    payload: UpdateCaseRequest,
    request: Request,
    driver: AsyncDriver = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission(Permission.CASE_UPDATE)),
) -> Envelope[dict]:
    # mode="json" so enum members become plain strings rather than reaching the
    # driver as StrEnum instances.
    updates = {k: v for k, v in payload.model_dump(mode="json").items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Read before writing so the audit record can show what actually changed.
    # "The status is now Closed" is far less useful in review than "it went from
    # Open to Closed, and who did it".
    before = await case_repo.get_case(driver, case_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Case not found")

    try:
        case = await case_repo.update_case(driver, case_id, updates)
    except ValueError as exc:
        await _audit_case(request, user, "case.update", case_id, outcome="failure", detail=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    changed_before = {k: before.get(k) for k in updates}
    await _audit_case(request, user, "case.update", case_id, before=changed_before, after=updates)
    return Envelope(data=case)


@router.post("/{case_id}/entities")
async def add_case_entity(
    case_id: str,
    payload: AddEntityRequest,
    request: Request,
    driver: AsyncDriver = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission(Permission.EVIDENCE_LINK)),
) -> Envelope[dict]:
    ok = await case_repo.add_entity_to_case(
        driver, case_id, payload.entity_id, payload.reason, added_by=user.username
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Case or entity not found")
    await _audit_case(
        request,
        user,
        "case.evidence_link",
        case_id,
        after={"entity_id": payload.entity_id, "reason": payload.reason},
    )
    return Envelope(data={"linked": True})


@router.delete("/{case_id}/entities/{entity_id}")
async def remove_case_entity(
    case_id: str,
    entity_id: str,
    request: Request,
    reason: str = Query("", max_length=MAX_REASON),
    driver: AsyncDriver = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission(Permission.EVIDENCE_LINK)),
) -> Envelope[dict]:
    """Unlink evidence from a case.

    Tombstoned rather than deleted (audit G-11): in an investigation, the fact
    that a piece of evidence was once linked — and by whom, and why it was
    removed — is itself evidence. `DELETE r` erased that entirely.
    """
    removed = await case_repo.remove_entity_from_case(
        driver, case_id, entity_id, removed_by=user.username, reason=reason
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Case or evidence link not found")
    await _audit_case(
        request,
        user,
        "case.evidence_unlink",
        case_id,
        before={"entity_id": entity_id},
        detail=reason or None,
    )
    return Envelope(data={"removed": True})
