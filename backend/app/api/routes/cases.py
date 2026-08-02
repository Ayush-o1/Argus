from fastapi import APIRouter, Depends

from app.api.dependencies import require_api_token
from app.models.envelope import Envelope, Meta

router = APIRouter(prefix="/api/cases", tags=["cases"], dependencies=[Depends(require_api_token)])

# Full implementation lands in Phase 7 (Cases + Alerts workflow).


@router.get("")
async def list_cases() -> Envelope[list]:
    return Envelope(data=[], meta=Meta(total=0))


@router.post("")
async def create_case() -> Envelope[dict | None]:
    return Envelope(data=None)


@router.get("/{case_id}")
async def get_case(case_id: str) -> Envelope[dict | None]:
    return Envelope(data=None)


@router.put("/{case_id}")
async def update_case(case_id: str) -> Envelope[dict | None]:
    return Envelope(data=None)


@router.post("/{case_id}/entities")
async def add_case_entity(case_id: str) -> Envelope[dict | None]:
    return Envelope(data=None)


@router.delete("/{case_id}/entities/{entity_id}")
async def remove_case_entity(case_id: str, entity_id: str) -> Envelope[dict | None]:
    return Envelope(data=None)
