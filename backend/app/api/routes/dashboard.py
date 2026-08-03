from fastapi import APIRouter, Depends
from neo4j import AsyncDriver

from app.api.dependencies import get_db, require_api_token
from app.models.envelope import Envelope
from app.repositories import dashboard_repo

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(require_api_token)])


@router.get("/summary")
async def get_summary(driver: AsyncDriver = Depends(get_db)) -> Envelope[dict]:
    summary = await dashboard_repo.get_dashboard_summary(driver)
    return Envelope(data=summary)
