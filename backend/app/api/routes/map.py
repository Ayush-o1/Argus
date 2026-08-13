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


@router.get("/regions")
async def map_regions(driver: AsyncDriver = Depends(get_db)) -> Envelope[list]:
    """Regional aggregates + map centers — the world view's data source."""
    return Envelope(data=await map_repo.get_region_rollup(driver))


@router.get("/countries")
async def map_countries(region: str | None = None, driver: AsyncDriver = Depends(get_db)) -> Envelope[list]:
    """Country aggregates, optionally scoped to one region."""
    return Envelope(data=await map_repo.get_country_rollup(driver, region))


@router.get("/corridors")
async def map_corridors(driver: AsyncDriver = Depends(get_db)) -> Envelope[list]:
    """Region-to-region trade corridors with their anomaly share."""
    return Envelope(data=await map_repo.get_corridors(driver))
