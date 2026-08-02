from fastapi import APIRouter, Depends

from app.api.dependencies import require_api_token
from app.models.envelope import Envelope

router = APIRouter(prefix="/api/graph", tags=["graph"], dependencies=[Depends(require_api_token)])


@router.get("/subgraph")
async def get_subgraph(entity_ids: str = "", depth: int = 2) -> Envelope[dict]:
    """Full implementation (Cypher traversal) lands in Phase 2/4."""
    return Envelope(data={"nodes": [], "edges": []})


@router.get("/shortest-path")
async def shortest_path(from_id: str, to_id: str) -> Envelope[dict | None]:
    return Envelope(data=None)


@router.get("/neighbors")
async def neighbors(entity_id: str, depth: int = 1) -> Envelope[dict]:
    return Envelope(data={"nodes": [], "edges": []})
