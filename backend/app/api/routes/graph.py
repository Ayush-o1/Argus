from fastapi import APIRouter, Depends, Query
from neo4j import AsyncDriver

from app.api.dependencies import get_db, require_api_token
from app.models.envelope import Envelope
from app.repositories import graph_repo

router = APIRouter(prefix="/api/graph", tags=["graph"], dependencies=[Depends(require_api_token)])

# Traversal cost grows with depth, and get_neighborhood issues one query per
# frontier node — so an unbounded `depth` let a single request fan out into
# hundreds of sequential queries (audit B-10). Three hops is past the point where
# a neighbourhood is still legible to an analyst anyway.
MAX_DEPTH = 3
DepthParam = Query(1, ge=1, le=MAX_DEPTH, description=f"Traversal hops (1-{MAX_DEPTH})")


@router.get("/subgraph")
async def get_subgraph(
    entity_id: str, depth: int = DepthParam, driver: AsyncDriver = Depends(get_db)
) -> Envelope[dict]:
    subgraph = await graph_repo.get_neighborhood(driver, entity_id, depth=depth)
    return Envelope(data=subgraph)


@router.get("/overview")
async def get_overview(driver: AsyncDriver = Depends(get_db)) -> Envelope[dict]:
    """Default Graph Explorer view: highest-risk entities and their neighbors."""
    subgraph = await graph_repo.get_overview_subgraph(driver)
    return Envelope(data=subgraph)


@router.get("/shortest-path")
async def shortest_path(from_id: str, to_id: str, driver: AsyncDriver = Depends(get_db)) -> Envelope[dict | None]:
    path = await graph_repo.shortest_path(driver, from_id, to_id)
    return Envelope(data=path)


@router.get("/neighbors")
async def neighbors(
    entity_id: str, depth: int = DepthParam, driver: AsyncDriver = Depends(get_db)
) -> Envelope[dict]:
    subgraph = await graph_repo.get_neighborhood(driver, entity_id, depth=depth)
    return Envelope(data=subgraph)
