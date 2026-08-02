from fastapi import APIRouter, Depends

from app.api.dependencies import require_api_token
from app.models.envelope import Envelope, Meta

router = APIRouter(prefix="/api/search", tags=["search"], dependencies=[Depends(require_api_token)])

# Full Neo4j fulltext-index-backed implementation lands in Phase 2/3.


@router.get("")
async def search(q: str = "", types: str = "", risk_min: int = 0, city: str | None = None) -> Envelope[list]:
    return Envelope(data=[], meta=Meta(total=0))
