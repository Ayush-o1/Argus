from fastapi import APIRouter, Depends

from app.api.dependencies import require_api_token
from app.models.envelope import Envelope, Meta

router = APIRouter(prefix="/api/entities", tags=["entities"], dependencies=[Depends(require_api_token)])


@router.get("")
async def list_entities() -> Envelope[list]:
    """Filtered entity listing. Full Cypher-backed implementation lands in Phase 2."""
    return Envelope(data=[], meta=Meta(total=0))


@router.get("/{entity_id}")
async def get_entity(entity_id: str) -> Envelope[dict | None]:
    return Envelope(data=None)


@router.get("/{entity_id}/graph")
async def get_entity_graph(entity_id: str, depth: int = 2) -> Envelope[dict]:
    return Envelope(data={"nodes": [], "edges": []})


@router.get("/{entity_id}/timeline")
async def get_entity_timeline(entity_id: str) -> Envelope[list]:
    return Envelope(data=[])


@router.get("/{entity_id}/ai-summary")
async def get_entity_ai_summary(entity_id: str) -> Envelope[dict | None]:
    """Cached AI narrative. Implemented in Phase 8 (AI Features)."""
    return Envelope(data=None)
