"""Case records, read-only since Phase 9.

Every `Case` node in this graph — all twenty of them — was written by the
scenario generator from a storyline it had just planted: titled after the
storyline, noted "Auto-seeded from storyline STL-…", linked to exactly the
entity list the storyline named, and assigned to one of five invented analyst
names. Not one was opened by a person.

That makes this store a record of what a source reported, which is a perfectly
good thing to keep and read — the same treatment Phase 7 gave `Incident`. What
it cannot be is the place analyst work is written, because work written here
would be indistinguishable from the generator's plant a week later.

So the read routes remain and the write routes return 410. Analyst work goes to
`/api/investigations`, which is a different object in a different store, with an
outcome, an append-only history, and no generator-authored rows in it at all.
"""

from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from neo4j import AsyncDriver
from pydantic import BaseModel, Field

from app.api.dependencies import get_db, require_permission
from app.models.envelope import Envelope, Meta
from app.repositories import case_repo
from app.security.roles import Permission
from app.security.sessions import AuthenticatedUser

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


_GONE = (
    "Case records are read-only. Every case in this store was written by the "
    "scenario generator from a storyline, so analyst work recorded here would be "
    "indistinguishable from planted data. Open an investigation instead: "
    "POST /api/investigations, which records a hypothesis, evidence, findings and "
    "an outcome, with an append-only history."
)


def _gone() -> HTTPException:
    return HTTPException(status_code=status.HTTP_410_GONE, detail=_GONE)


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
    raise _gone()


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
    raise _gone()


@router.post("/{case_id}/entities")
async def add_case_entity(
    case_id: str,
    payload: AddEntityRequest,
    request: Request,
    driver: AsyncDriver = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission(Permission.EVIDENCE_LINK)),
) -> Envelope[dict]:
    raise _gone()


@router.delete("/{case_id}/entities/{entity_id}")
async def remove_case_entity(
    case_id: str,
    entity_id: str,
    request: Request,
    reason: str = Query("", max_length=MAX_REASON),
    driver: AsyncDriver = Depends(get_db),
    user: AuthenticatedUser = Depends(require_permission(Permission.EVIDENCE_LINK)),
) -> Envelope[dict]:
    raise _gone()
