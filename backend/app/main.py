import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    ai,
    alerts,
    analytics,
    cases,
    dashboard,
    entities,
    graph,
    scenario,
    search,
    timeline,
)
from app.api.routes import (
    map as map_routes,
)
from app.config import get_settings
from app.database.neo4j import close_neo4j, connect_neo4j
from app.database.redis import close_redis, connect_redis

# Configure root logger from settings so every module in the app honours LOG_LEVEL.
# Uvicorn controls its own access-log format separately; this covers app-level messages.
_settings = get_settings()
logging.basicConfig(
    level=getattr(logging, _settings.log_level.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await connect_neo4j()
    await connect_redis()
    yield
    await close_neo4j()
    await close_redis()


app = FastAPI(
    title="ARGUS API",
    description="Graph analytics, investigation workflow, and AI-assisted analysis over a synthetic dataset.",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(entities.router)
app.include_router(graph.router)
app.include_router(analytics.router)
app.include_router(cases.router)
app.include_router(alerts.router)
app.include_router(ai.router)
app.include_router(map_routes.router)
app.include_router(timeline.router)
app.include_router(search.router)
app.include_router(scenario.router)


@app.get("/api/health")
async def health() -> dict:
    """Verifies the process is up and both datastore connections are live."""
    from app.database.neo4j import get_driver
    from app.database.redis import get_redis

    neo4j_ok = False
    redis_ok = False
    try:
        await get_driver().verify_connectivity()
        neo4j_ok = True
    except Exception:
        pass
    try:
        await get_redis().ping()
        redis_ok = True
    except Exception:
        pass

    return {
        "status": "ok" if (neo4j_ok and redis_ok) else "degraded",
        "neo4j": neo4j_ok,
        "redis": redis_ok,
    }
