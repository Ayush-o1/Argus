from fastapi import APIRouter, Depends, Query
from neo4j import AsyncDriver

from app.api.dependencies import get_db, require_permission
from app.models.envelope import Envelope, Meta
from app.repositories import graph_repo
from app.security.roles import Permission

router = APIRouter(
    prefix="/api/search",
    tags=["search"],
    dependencies=[Depends(require_permission(Permission.ENTITY_READ))],
)

# Long enough for a full name plus qualifiers; short enough that the Lucene
# parser is never handed an unbounded string.
MAX_QUERY_LENGTH = 200


@router.get("")
async def search(
    q: str = Query("", max_length=MAX_QUERY_LENGTH),
    limit: int = Query(20, ge=1, le=100),
    driver: AsyncDriver = Depends(get_db),
) -> Envelope[list]:
    results = await graph_repo.search_entities(driver, q, limit=limit)
    # `total` is the number of results returned, not the number that exist —
    # the fulltext index is queried with a LIMIT and does not report a total.
    # Named accordingly rather than implying a population it cannot know.
    return Envelope(data=results, meta=Meta(total=len(results), page=1, page_size=limit))
