from fastapi import APIRouter, Depends, HTTPException
from neo4j import AsyncDriver
from pydantic import BaseModel

from app.api.dependencies import get_db, require_api_token
from app.models.envelope import Envelope, Meta
from app.repositories import alert_repo

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(require_api_token)])


class ReviewAlertRequest(BaseModel):
    status: str  # UnderInvestigation | Closed | Open


@router.get("")
async def list_alerts(
    status: str | None = None,
    priority: str | None = None,
    page: int = 1,
    page_size: int = 50,
    driver: AsyncDriver = Depends(get_db),
) -> Envelope[list]:
    alerts, total = await alert_repo.list_alerts(driver, status, priority, page, page_size)
    return Envelope(data=alerts, meta=Meta(total=total, page=page, page_size=page_size))


@router.put("/{alert_id}/review")
async def review_alert(
    alert_id: str, payload: ReviewAlertRequest, driver: AsyncDriver = Depends(get_db)
) -> Envelope[dict]:
    alert = await alert_repo.review_alert(driver, alert_id, payload.status)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return Envelope(data=alert)
