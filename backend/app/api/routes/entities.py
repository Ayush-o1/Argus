from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import AsyncDriver

from app.api.dependencies import get_db, require_permission
from app.api.routes.graph import DepthParam
from app.models.envelope import Envelope, Meta
from app.repositories import entity_repo, graph_repo
from app.security.roles import Permission

router = APIRouter(
    prefix="/api/entities",
    tags=["entities"],
    dependencies=[Depends(require_permission(Permission.ENTITY_READ))],
)


@router.get("")
async def list_entities(
    type: str = "Person",
    risk_min: float = Query(0, ge=0, le=100),
    city: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    driver: AsyncDriver = Depends(get_db),
) -> Envelope[list]:
    try:
        nodes, total = await graph_repo.list_entities(driver, type, risk_min, city, page, page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Envelope(data=nodes, meta=Meta(total=total, page=page, page_size=page_size))


@router.get("/{entity_id}")
async def get_entity(entity_id: str, driver: AsyncDriver = Depends(get_db)) -> Envelope[dict | None]:
    node = await graph_repo.get_node_by_human_id(driver, entity_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    node["connections"] = await entity_repo.get_connection_summary(driver, entity_id)
    return Envelope(data=node)


@router.get("/{entity_id}/graph")
async def get_entity_graph(
    entity_id: str, depth: int = DepthParam, driver: AsyncDriver = Depends(get_db)
) -> Envelope[dict]:
    subgraph = await graph_repo.get_neighborhood(driver, entity_id, depth=depth)
    return Envelope(data=subgraph)


@router.get("/{entity_id}/timeline")
async def get_entity_timeline(
    entity_id: str,
    limit: int = Query(200, ge=1, le=1000),
    driver: AsyncDriver = Depends(get_db),
) -> Envelope[list]:
    timeline = await entity_repo.get_entity_timeline(driver, entity_id, limit=limit)
    return Envelope(data=timeline)


@router.get("/{entity_id}/cases")
async def get_entity_cases(entity_id: str, driver: AsyncDriver = Depends(get_db)) -> Envelope[list]:
    cases = await entity_repo.get_related_cases(driver, entity_id)
    return Envelope(data=cases)


@router.get("/{entity_id}/alerts")
async def get_entity_alerts(
    entity_id: str,
    limit: int = Query(20, ge=1, le=200),
    driver: AsyncDriver = Depends(get_db),
) -> Envelope[list]:
    alerts = await entity_repo.get_related_alerts(driver, entity_id, limit=limit)
    return Envelope(data=alerts)
