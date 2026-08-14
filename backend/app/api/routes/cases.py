from fastapi import APIRouter, Depends, HTTPException
from neo4j import AsyncDriver
from pydantic import BaseModel

from app.api.dependencies import get_db, require_api_token
from app.models.envelope import Envelope, Meta
from app.repositories import case_repo

router = APIRouter(prefix="/api/cases", tags=["cases"], dependencies=[Depends(require_api_token)])


class CreateCaseRequest(BaseModel):
    title: str
    priority: str = "Medium"
    notes: str = ""


class UpdateCaseRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    notes: str | None = None
    assigned_analyst: str | None = None


class AddEntityRequest(BaseModel):
    entity_id: str
    reason: str = ""


@router.get("")
async def list_cases(
    status: str | None = None, page: int = 1, page_size: int = 50, driver: AsyncDriver = Depends(get_db)
) -> Envelope[list]:
    cases, total = await case_repo.list_cases(driver, status, page, page_size)
    return Envelope(data=cases, meta=Meta(total=total, page=page, page_size=page_size))


@router.post("")
async def create_case(payload: CreateCaseRequest, driver: AsyncDriver = Depends(get_db)) -> Envelope[dict]:
    case = await case_repo.create_case(driver, payload.title, payload.priority, payload.notes)
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
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    case = await case_repo.update_case(driver, case_id, updates)
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
