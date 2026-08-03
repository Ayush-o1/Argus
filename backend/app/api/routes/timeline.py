from fastapi import APIRouter, Depends
from neo4j import AsyncDriver

from app.api.dependencies import get_db, require_api_token
from app.models.envelope import Envelope
from app.repositories import timeline_repo

router = APIRouter(prefix="/api/timeline", tags=["timeline"], dependencies=[Depends(require_api_token)])


@router.get("/events")
async def timeline_events(driver: AsyncDriver = Depends(get_db)) -> Envelope[dict]:
    timeline = await timeline_repo.get_global_timeline(driver)
    return Envelope(data=timeline)
