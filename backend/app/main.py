import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from asyncpg.exceptions import PostgresConnectionError
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
    assessment,
    auth,
    cases,
    correlation,
    dashboard,
    entities,
    graph,
    ingest,
    provenance,
    resolution,
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
from app.services import queue
from app.services.jobs import JobRejected, cancel_active_jobs, reap_stale_jobs
from app.services.provenance import ensure_builtin_sources
from app.services.scheduler import IngestScheduler

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

    # ARGUS's own sources — including the scenario generator, registered as
    # synthetic — must exist before anything can record an observation against
    # them. Idempotent, and it never overwrites a reliability rating that is
    # already there: a rating is an analytic judgement, and changing one on
    # deploy would alter the meaning of every assertion resting on it.
    await ensure_builtin_sources()

    # The durable job worker. Importing app.services.ingest registers its
    # handler; without the import the worker would start with no known kinds and
    # quietly consume nothing — a stall that looks exactly like an empty queue.
    from app.services import assessment as _assessment  # noqa: F401  (handler registration)
    from app.services import correlation as _correlation  # noqa: F401  (handler registration)
    from app.services import ingest as _ingest  # noqa: F401  (handler registration)
    from app.services import resolution as _resolution  # noqa: F401  (handler registration)

    worker = queue.Worker(
        poll_interval=settings.job_poll_seconds,
        concurrency=settings.job_worker_concurrency,
    )
    scheduler = IngestScheduler(interval=settings.ingest_schedule_seconds)
    if settings.job_worker_enabled:
        worker.start()
        scheduler.start()
    else:
        logger.info("job worker disabled by configuration")

    # Any job still marked "running" belongs to a previous process: in-process
    # asyncio tasks do not survive a restart, so without this the frontend polls
    # a job that will never complete until its TTL expires (audit B-07).
    reaped = await reap_stale_jobs(redis)
    if reaped:
        logger.warning("marked %d orphaned job(s) as failed after restart", reaped)

    yield

    # Stop scheduling first, then drain the worker: reversing this would let a
    # tick queue work the worker is no longer there to run.
    await scheduler.stop()
    await worker.stop()

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

# Middleware order matters, and Starlette applies it in reverse registration
# order — the last registered is the outermost. So this block reads
# inside-out: RequestContext runs first on the way in, then rate limiting, then
# security headers, and CORS is outermost.
#
# CORS *must* be outermost. Registered inside the rate limiter, an early 429
# short-circuits before CORS ever runs, so the response carries no CORS headers
# and the browser reports a bare "blocked by CORS policy" instead of the rate
# limit that actually happened. Found in browser verification; invisible to
# server-side tests, which do not enforce CORS.
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

# `allow_credentials=True` is required now that the session is a cookie: the
# frontend is a different origin from the API, and without it the browser will
# not attach the session cookie at all. It is only safe because `allow_origins`
# is an explicit list — never "*", which the CORS spec forbids combining with
# credentials precisely because it would let any site make authenticated
# requests. CSRF protection (double-submit token, enforced in
# api/dependencies.current_user) is the other half of that tradeoff.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID", "X-CSRF-Token"],
    expose_headers=["X-Request-ID"],
)


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

@app.exception_handler(PostgresConnectionError)
@app.exception_handler(asyncpg.InterfaceError)
@app.exception_handler(ConnectionRefusedError)
async def postgres_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """Postgres, unlike Redis and Neo4j, had no handler — so an outage produced
    a bare `500 Internal Server Error` on every authenticated route.

    Found by failure testing rather than by any test suite: the exception is
    raised inside a dependency, so a caller sees "ARGUS is broken" and no reason
    to retry, while `/readyz` was correctly reporting 503 the whole time.

    Phase 2 made this worth fixing rather than merely noting. Postgres now backs
    provenance as well as identity, so an outage reaches ordinary intelligence
    surfaces instead of only the login path.

    Deliberately not described as partial degradation. Postgres holds identity,
    so while it is down nobody can authenticate at all — claiming the rest of
    the platform is unaffected would be false comfort.
    """
    logger.error("postgres unavailable", exc_info=exc, extra={"path": request.url.path})
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "data": None,
            "error": "Identity and provenance store unavailable — ARGUS cannot authenticate "
            "requests or resolve where a fact came from. Please retry shortly.",
        },
        headers={"Retry-After": "10"},
    )


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(dashboard.router)
app.include_router(entities.router)
app.include_router(provenance.router)
app.include_router(ingest.router)
app.include_router(resolution.router)
app.include_router(assessment.router)
app.include_router(correlation.router)
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
