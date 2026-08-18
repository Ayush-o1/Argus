from functools import partial

from fastapi import APIRouter, Depends, HTTPException
from neo4j import AsyncDriver
from pydantic import BaseModel
from redis.asyncio import Redis

from app.api.dependencies import get_db, require_permission
from app.correlation.projection import SPECS
from app.correlation.projection import catalogue as projection_catalogue
from app.database.redis import get_redis
from app.models.envelope import Envelope
from app.repositories import analytics_repo
from app.security.roles import Permission
from app.security.sessions import AuthenticatedUser
from app.services import anomaly, jobs

# The router-level permission gates *reading* results. Every POST below starts a
# GDS job — real CPU, an in-memory graph projection, and a job slot — so each one
# additionally requires ANALYTICS_RUN. Without that, the authorization matrix
# showed a viewer (read-only by definition) able to start unbounded analytics
# work, which is both a privilege and an availability problem.
router = APIRouter(
    prefix="/api/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_permission(Permission.ANALYTICS_READ))],
)


class RiskPropagationRequest(BaseModel):
    seed_ids: list[str]
    max_hops: int = 3


def _validated_projection(name: str | None) -> str | None:
    """Reject an unknown projection at the edge, with the options named.

    Validated here rather than inside the job, because a job that fails on a
    typo reports as a generic analytics failure minutes later. A 422 naming the
    two available graphs is a better answer to a misspelled parameter.
    """
    if name is not None and name not in SPECS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown projection {name!r}. Available: {', '.join(sorted(SPECS))}",
        )
    return name


@router.get("/projections")
async def list_projections() -> Envelope[list[dict]]:
    """The graphs the algorithms can run on, with their weights and caveats.

    Published so a caller can tell which question a ranking answers. Before this
    phase every algorithm ran on one hard-coded account-only graph and none of
    them said so, which made "influence" mean something quite different from
    what the label suggested.
    """
    return Envelope(data=projection_catalogue())


@router.post("/pagerank")
async def run_pagerank(
    projection: str | None = None,
    driver: AsyncDriver = Depends(get_db),
    redis: Redis = Depends(get_redis),
    _: AuthenticatedUser = Depends(require_permission(Permission.ANALYTICS_RUN)),
) -> Envelope[dict]:
    spec = _validated_projection(projection)
    job_id = await jobs.start_job(
        redis, "pagerank", partial(analytics_repo.run_pagerank, driver, projection_name=spec)
    )
    return Envelope(data={"job_id": job_id, "status": "running"})


@router.post("/betweenness")
async def run_betweenness(
    projection: str | None = None,
    driver: AsyncDriver = Depends(get_db),
    redis: Redis = Depends(get_redis),
    _: AuthenticatedUser = Depends(require_permission(Permission.ANALYTICS_RUN)),
) -> Envelope[dict]:
    spec = _validated_projection(projection)
    job_id = await jobs.start_job(
        redis, "betweenness", partial(analytics_repo.run_betweenness, driver, projection_name=spec)
    )
    return Envelope(data={"job_id": job_id, "status": "running"})


@router.post("/louvain")
async def run_louvain(
    projection: str | None = None,
    driver: AsyncDriver = Depends(get_db),
    redis: Redis = Depends(get_redis),
    _: AuthenticatedUser = Depends(require_permission(Permission.ANALYTICS_RUN)),
) -> Envelope[dict]:
    spec = _validated_projection(projection)
    job_id = await jobs.start_job(
        redis, "louvain", partial(analytics_repo.run_louvain, driver, projection_name=spec)
    )
    return Envelope(data={"job_id": job_id, "status": "running"})


@router.post("/risk-propagation")
async def run_risk_propagation(
    payload: RiskPropagationRequest,
    driver: AsyncDriver = Depends(get_db),
    redis: Redis = Depends(get_redis),
    _: AuthenticatedUser = Depends(require_permission(Permission.ANALYTICS_RUN)),
) -> Envelope[dict]:
    job_id = await jobs.start_job(
        redis,
        "risk-propagation",
        partial(analytics_repo.run_risk_propagation, driver, payload.seed_ids, payload.max_hops),
    )
    return Envelope(data={"job_id": job_id, "status": "running"})


@router.post("/cycle-detection")
async def run_cycle_detection(
    driver: AsyncDriver = Depends(get_db),
    redis: Redis = Depends(get_redis),
    _: AuthenticatedUser = Depends(require_permission(Permission.ANALYTICS_RUN)),
) -> Envelope[dict]:
    job_id = await jobs.start_job(redis, "cycle-detection", partial(analytics_repo.run_cycle_detection, driver))
    return Envelope(data={"job_id": job_id, "status": "running"})


@router.post("/similar/{entity_id}")
async def run_similar_entities(
    entity_id: str,
    top_k: int = 10,
    projection: str | None = None,
    driver: AsyncDriver = Depends(get_db),
    redis: Redis = Depends(get_redis),
    _: AuthenticatedUser = Depends(require_permission(Permission.ANALYTICS_RUN)),
) -> Envelope[dict]:
    spec = _validated_projection(projection)
    job_id = await jobs.start_job(
        redis,
        "node2vec-similarity",
        partial(
            analytics_repo.run_node2vec_similarity,
            driver,
            entity_id,
            top_k,
            projection_name=spec,
        ),
    )
    return Envelope(data={"job_id": job_id, "status": "running"})


@router.post("/anomalies")
async def run_anomaly_detection(
    driver: AsyncDriver = Depends(get_db),
    redis: Redis = Depends(get_redis),
    _: AuthenticatedUser = Depends(require_permission(Permission.ANALYTICS_RUN)),
) -> Envelope[dict]:
    job_id = await jobs.start_job(redis, "anomalies", partial(anomaly.detect_transaction_anomalies, driver))
    return Envelope(data={"job_id": job_id, "status": "running"})


@router.get("/results/{job_id}")
async def get_job_result(job_id: str, redis: Redis = Depends(get_redis)) -> Envelope[dict | None]:
    job = await jobs.get_job(redis, job_id)
    return Envelope(data=job)
