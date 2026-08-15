import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi import Response as FastAPIResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from neo4j.exceptions import ServiceUnavailable as Neo4jServiceUnavailable
from neo4j.exceptions import SessionExpired as Neo4jSessionExpired
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.api.routes import (
    admin,
    ai,
    alerts,
    analytics,
    auth,
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
from app.database.migrations import run_migrations
from app.database.neo4j import close_neo4j, connect_neo4j
from app.database.pg_migrations import run_pg_migrations
from app.database.postgres import close_postgres, connect_postgres
from app.database.redis import close_redis, connect_redis
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security import RateLimitMiddleware, SecurityHeadersMiddleware
from app.observability.logging import configure_logging
from app.services.jobs import JobRejected, cancel_active_jobs, reap_stale_jobs

# Structured logging is installed before anything else so startup itself — including
# a migration failure, which is the most important thing to be able to read — is
# captured in the configured format.
_settings = get_settings()
configure_logging(level=_settings.log_level, json_output=_settings.log_json)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    driver = await connect_neo4j()
    redis = await connect_redis()

    # Identity and audit must be migrated before the app can authenticate
    # anyone. A failure here aborts startup: running with a half-built
    # authorization schema risks granting access it should not.
    pg_applied = await run_pg_migrations()
    if pg_applied:
        logger.info("applied %d postgres migration(s): %s", len(pg_applied), pg_applied)
    await connect_postgres()

    # Schema is applied here rather than as a side effect of running the data
    # generator, so a deployed backend can acquire an index without anyone
    # re-running a tool whose default path wipes the graph. A failure raises and
    # aborts startup deliberately — serving requests against a half-migrated
    # schema risks wrong answers, which is worse than being unavailable.
    applied = await run_migrations(driver)
    if applied:
        logger.info("applied %d migration(s): %s", len(applied), applied)

    # Any job still marked "running" belongs to a previous process: in-process
    # asyncio tasks do not survive a restart, so without this the frontend polls
    # a job that will never complete until its TTL expires (audit B-07).
    reaped = await reap_stale_jobs(redis)
    if reaped:
        logger.warning("marked %d orphaned job(s) as failed after restart", reaped)

    yield

    # Cancel in-flight jobs and give them a moment to record terminal state, so
    # a clean shutdown does not manufacture the orphans reap_stale_jobs exists
    # to clean up after an unclean one.
    await cancel_active_jobs()
    await close_neo4j()
    await close_redis()
    await close_postgres()


app = FastAPI(
    title="ARGUS API",
    description="Graph analytics, investigation workflow, and AI-assisted analysis over a synthetic dataset.",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()

# Methods and headers are enumerated rather than wildcarded (audit B-26).
#
# `allow_credentials=True` is required now that the session is a cookie: the
# frontend is a different origin from the API, and without it the browser will
# not attach the session cookie at all. It is only safe because `allow_origins`
# is an explicit list — never "*", which the CORS spec forbids combining with
# credentials precisely because it would let any site make authenticated
# requests. CSRF protection (double-submit token, enforced in
# api/dependencies.current_user) is the other half of this tradeoff.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID", "X-CSRF-Token"],
    expose_headers=["X-Request-ID"],
)
# Order matters: Starlette runs middleware in reverse registration order, so
# the request context (and its correlation id) is established first, then rate
# limiting, then security headers on the way out.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(JobRejected)
async def job_rejected_handler(request: Request, exc: JobRejected) -> JSONResponse:
    """429 rather than 500: the request was well-formed and the system is simply
    saturated, so the client should retry rather than treat it as a defect."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"data": None, "error": str(exc)},
        headers={"Retry-After": "5"},
    )


@app.exception_handler(RedisConnectionError)
@app.exception_handler(RedisTimeoutError)
async def redis_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """A datastore being unreachable is not an application defect.

    Redis backs only job status, so its loss degrades one capability rather than
    the platform: graph reads continue to work. Returning a bare 500 said
    "ARGUS is broken" when the accurate statement is "analytics is temporarily
    unavailable, everything else is fine" — and a 500 gives the client no reason
    to retry, while a 503 does.
    """
    logger.error("redis unavailable", exc_info=exc, extra={"path": request.url.path})
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "data": None,
            "error": "Job service unavailable — analytics and scenario generation are "
            "temporarily offline. Graph, search, alerts and cases are unaffected.",
        },
        headers={"Retry-After": "10"},
    )


@app.exception_handler(Neo4jServiceUnavailable)
@app.exception_handler(Neo4jSessionExpired)
async def neo4j_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """Same reasoning for the graph: a transient database outage should tell the
    client to retry, not present as a server bug."""
    logger.error("neo4j unavailable", exc_info=exc, extra={"path": request.url.path})
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"data": None, "error": "Graph database unavailable — please retry shortly."},
        headers={"Retry-After": "10"},
    )

app.include_router(auth.router)
app.include_router(admin.router)
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


async def _dependency_status() -> tuple[bool, bool, bool]:
    """(neo4j_ok, redis_ok, postgres_ok). Never raises — a health check that
    throws is useless to the orchestrator polling it."""
    from app.database.neo4j import get_driver
    from app.database.postgres import acquire
    from app.database.redis import get_redis

    neo4j_ok = False
    redis_ok = False
    postgres_ok = False
    try:
        await get_driver().verify_connectivity()
        neo4j_ok = True
    except Exception:
        logger.warning("readiness: neo4j unreachable", exc_info=True)
    try:
        await get_redis().ping()
        redis_ok = True
    except Exception:
        logger.warning("readiness: redis unreachable", exc_info=True)
    try:
        async with acquire() as conn:
            await conn.execute("SELECT 1")
        postgres_ok = True
    except Exception:
        logger.warning("readiness: postgres unreachable", exc_info=True)
    return neo4j_ok, redis_ok, postgres_ok


@app.get("/livez")
async def livez() -> dict:
    """Liveness: is the process running. Deliberately checks no dependency —
    conflating the two (as the previous single /api/health did) means a
    transient database blip gets the container killed and restarted, which
    cannot fix a database problem and removes capacity during one."""
    return {"status": "alive"}


@app.get("/readyz")
async def readyz(response: FastAPIResponse) -> dict:
    """Readiness: should this instance receive traffic. Returns 503 when a
    dependency is down so a load balancer drains it rather than sending requests
    that are certain to fail."""
    neo4j_ok, redis_ok, postgres_ok = await _dependency_status()
    # Postgres counts: without it nobody can authenticate, so the instance
    # cannot usefully serve traffic even though the graph is reachable.
    ready = neo4j_ok and redis_ok and postgres_ok
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready else "not_ready",
        "neo4j": neo4j_ok,
        "redis": redis_ok,
        "postgres": postgres_ok,
    }


@app.get("/api/health")
async def health() -> dict:
    """Retained for the existing frontend and docs. Equivalent to /readyz but
    always 200, since callers treat a non-200 as "ARGUS is gone" rather than
    reading the body."""
    neo4j_ok, redis_ok, postgres_ok = await _dependency_status()
    return {
        "status": "ok" if (neo4j_ok and redis_ok and postgres_ok) else "degraded",
        "neo4j": neo4j_ok,
        "redis": redis_ok,
        "postgres": postgres_ok,
    }
