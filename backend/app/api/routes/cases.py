from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import AsyncDriver
from pydantic import BaseModel, Field

from app.api.dependencies import get_db, require_api_token
from app.models.envelope import Envelope, Meta
from app.repositories import case_repo

router = APIRouter(prefix="/api/cases", tags=["cases"], dependencies=[Depends(require_api_token)])


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
async def create_case(payload: CreateCaseRequest, driver: AsyncDriver = Depends(get_db)) -> Envelope[dict]:
    case = await case_repo.create_case(driver, payload.title, payload.priority.value, payload.notes)
    return Envelope(data=case)


@router.get("/{case_id}")
async def get_case(case_id: str, driver: AsyncDriver = Depends(get_db)) -> Envelope[dict]:
    case = await case_repo.get_case(driver, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return Envelope(data=case)


@router.put("/{case_id}")
async def update_case(
    case_id: str, payload: UpdateCaseRequest, driver: AsyncDriver = Depends(get_db)
) -> Envelope[dict]:
    # mode="json" so enum members become plain strings rather than reaching the
    # driver as StrEnum instances.
    updates = {k: v for k, v in payload.model_dump(mode="json").items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        case = await case_repo.update_case(driver, case_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return Envelope(data=case)


@router.post("/{case_id}/entities")
async def add_case_entity(
    case_id: str, payload: AddEntityRequest, driver: AsyncDriver = Depends(get_db)
) -> Envelope[dict]:
    ok = await case_repo.add_entity_to_case(driver, case_id, payload.entity_id, payload.reason)
    if not ok:
        raise HTTPException(status_code=404, detail="Case or entity not found")
    return Envelope(data={"linked": True})


@router.delete("/{case_id}/entities/{entity_id}")
async def remove_case_entity(case_id: str, entity_id: str, driver: AsyncDriver = Depends(get_db)) -> Envelope[dict]:
    await case_repo.remove_entity_from_case(driver, case_id, entity_id)
    return Envelope(data={"removed": True})
