from fastapi import APIRouter, Depends

from app.api.dependencies import require_api_token
from app.models.envelope import Envelope

router = APIRouter(prefix="/api/timeline", tags=["timeline"], dependencies=[Depends(require_api_token)])

# Full implementation lands in Phase 5 (Map + Timeline).


@router.get("/events")
async def timeline_events(
    entity_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> Envelope[list]:
    return Envelope(data=[])
