from fastapi import APIRouter, Depends, HTTPException
from neo4j import AsyncDriver

from app.api.dependencies import get_db, require_api_token
from app.models.envelope import Envelope, Meta
from app.repositories import entity_repo, graph_repo

router = APIRouter(prefix="/api/entities", tags=["entities"], dependencies=[Depends(require_api_token)])


@router.get("")
async def list_entities(
    type: str = "Person",
    risk_min: float = 0,
    city: str | None = None,
    page: int = 1,
    page_size: int = 50,
    driver: AsyncDriver = Depends(get_db),
) -> Envelope[list]:
    nodes, total = await graph_repo.list_entities(driver, type, risk_min, city, page, page_size)
    return Envelope(data=nodes, meta=Meta(total=total, page=page, page_size=page_size))


@router.get("/{entity_id}")
async def get_entity(entity_id: str, driver: AsyncDriver = Depends(get_db)) -> Envelope[dict | None]:
    node = await graph_repo.get_node_by_human_id(driver, entity_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    node["connections"] = await entity_repo.get_connection_summary(driver, entity_id)
    return Envelope(data=node)


@router.get("/{entity_id}/graph")
async def get_entity_graph(entity_id: str, depth: int = 1, driver: AsyncDriver = Depends(get_db)) -> Envelope[dict]:
    subgraph = await graph_repo.get_neighborhood(driver, entity_id, depth=depth)
    return Envelope(data=subgraph)


@router.get("/{entity_id}/timeline")
async def get_entity_timeline(entity_id: str, driver: AsyncDriver = Depends(get_db)) -> Envelope[list]:
    timeline = await entity_repo.get_entity_timeline(driver, entity_id)
    return Envelope(data=timeline)


@router.get("/{entity_id}/cases")
async def get_entity_cases(entity_id: str, driver: AsyncDriver = Depends(get_db)) -> Envelope[list]:
    cases = await entity_repo.get_related_cases(driver, entity_id)
    return Envelope(data=cases)


@router.get("/{entity_id}/alerts")
async def get_entity_alerts(entity_id: str, driver: AsyncDriver = Depends(get_db)) -> Envelope[list]:
    alerts = await entity_repo.get_related_alerts(driver, entity_id)
    return Envelope(data=alerts)
