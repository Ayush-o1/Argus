from fastapi import APIRouter, Depends
from neo4j import AsyncDriver

from app.api.dependencies import get_db, require_api_token
from app.models.envelope import Envelope
from app.repositories import map_repo

router = APIRouter(prefix="/api/map", tags=["map"], dependencies=[Depends(require_api_token)])


@router.get("/entities")
async def map_entities(type: str | None = None, driver: AsyncDriver = Depends(get_db)) -> Envelope[list]:
    entities = await map_repo.get_map_entities(driver, type)
    return Envelope(data=entities)


@router.get("/shipments")
async def map_shipments(driver: AsyncDriver = Depends(get_db)) -> Envelope[list]:
    shipments = await map_repo.get_map_shipments(driver)
    return Envelope(data=shipments)
