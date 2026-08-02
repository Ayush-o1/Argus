from fastapi import APIRouter, Depends

from app.api.dependencies import require_api_token
from app.models.envelope import Envelope

router = APIRouter(prefix="/api/map", tags=["map"], dependencies=[Depends(require_api_token)])

# Full implementation lands in Phase 5 (Map + Timeline).


@router.get("/entities")
async def map_entities(bbox: str = "", type: str | None = None) -> Envelope[list]:
    return Envelope(data=[])


@router.get("/shipments")
async def map_shipments(bbox: str = "") -> Envelope[list]:
    return Envelope(data=[])
