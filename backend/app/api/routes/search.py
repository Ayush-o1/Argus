from fastapi import APIRouter, Depends
from neo4j import AsyncDriver

from app.api.dependencies import get_db, require_api_token
from app.models.envelope import Envelope, Meta
from app.repositories import graph_repo

router = APIRouter(prefix="/api/search", tags=["search"], dependencies=[Depends(require_api_token)])


@router.get("")
async def search(q: str = "", limit: int = 20, driver: AsyncDriver = Depends(get_db)) -> Envelope[list]:
    results = await graph_repo.search_entities(driver, q, limit=limit)
    return Envelope(data=results, meta=Meta(total=len(results), page=1, page_size=limit))
