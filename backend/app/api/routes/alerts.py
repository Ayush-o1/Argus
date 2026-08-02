from fastapi import APIRouter, Depends

from app.api.dependencies import require_api_token
from app.models.envelope import Envelope, Meta

router = APIRouter(prefix="/api/alerts", tags=["alerts"], dependencies=[Depends(require_api_token)])

# Full implementation lands in Phase 7 (Cases + Alerts workflow).


@router.get("")
async def list_alerts(status: str | None = None, priority: str | None = None) -> Envelope[list]:
    return Envelope(data=[], meta=Meta(total=0))


@router.put("/{alert_id}/review")
async def review_alert(alert_id: str) -> Envelope[dict | None]:
    return Envelope(data=None)
