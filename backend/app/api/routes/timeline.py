from fastapi import APIRouter, Depends
from neo4j import AsyncDriver

from app.api.dependencies import get_db, require_permission
from app.models.envelope import Envelope
from app.repositories import timeline_repo
from app.security.roles import Permission

router = APIRouter(
    prefix="/api/timeline",
    tags=["timeline"],
    dependencies=[Depends(require_permission(Permission.ENTITY_READ))],
)


@router.get("/events")
async def timeline_events(driver: AsyncDriver = Depends(get_db)) -> Envelope[dict]:
    timeline = await timeline_repo.get_global_timeline(driver)
    return Envelope(data=timeline)
