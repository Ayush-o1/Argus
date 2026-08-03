from functools import partial

from fastapi import APIRouter, Depends
from neo4j import AsyncDriver
from pydantic import BaseModel
from redis.asyncio import Redis

from app.api.dependencies import get_db, require_api_token
from app.database.redis import get_redis
from app.models.envelope import Envelope
from app.repositories import analytics_repo
from app.services import anomaly, jobs

router = APIRouter(prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(require_api_token)])


class RiskPropagationRequest(BaseModel):
    seed_ids: list[str]
    max_hops: int = 3


@router.post("/pagerank")
async def run_pagerank(driver: AsyncDriver = Depends(get_db), redis: Redis = Depends(get_redis)) -> Envelope[dict]:
    job_id = await jobs.start_job(redis, "pagerank", partial(analytics_repo.run_pagerank, driver))
    return Envelope(data={"job_id": job_id, "status": "running"})


@router.post("/betweenness")
async def run_betweenness(driver: AsyncDriver = Depends(get_db), redis: Redis = Depends(get_redis)) -> Envelope[dict]:
    job_id = await jobs.start_job(redis, "betweenness", partial(analytics_repo.run_betweenness, driver))
    return Envelope(data={"job_id": job_id, "status": "running"})


@router.post("/louvain")
async def run_louvain(driver: AsyncDriver = Depends(get_db), redis: Redis = Depends(get_redis)) -> Envelope[dict]:
    job_id = await jobs.start_job(redis, "louvain", partial(analytics_repo.run_louvain, driver))
    return Envelope(data={"job_id": job_id, "status": "running"})


@router.post("/risk-propagation")
async def run_risk_propagation(
    payload: RiskPropagationRequest,
    driver: AsyncDriver = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> Envelope[dict]:
    job_id = await jobs.start_job(
        redis,
        "risk-propagation",
        partial(analytics_repo.run_risk_propagation, driver, payload.seed_ids, payload.max_hops),
    )
    return Envelope(data={"job_id": job_id, "status": "running"})


@router.post("/cycle-detection")
async def run_cycle_detection(
    driver: AsyncDriver = Depends(get_db), redis: Redis = Depends(get_redis)
) -> Envelope[dict]:
    job_id = await jobs.start_job(redis, "cycle-detection", partial(analytics_repo.run_cycle_detection, driver))
    return Envelope(data={"job_id": job_id, "status": "running"})


@router.post("/similar/{entity_id}")
async def run_similar_entities(
    entity_id: str,
    top_k: int = 10,
    driver: AsyncDriver = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> Envelope[dict]:
    job_id = await jobs.start_job(
        redis,
        "node2vec-similarity",
        partial(analytics_repo.run_node2vec_similarity, driver, entity_id, top_k),
    )
    return Envelope(data={"job_id": job_id, "status": "running"})


@router.post("/anomalies")
async def run_anomaly_detection(
    driver: AsyncDriver = Depends(get_db), redis: Redis = Depends(get_redis)
) -> Envelope[dict]:
    job_id = await jobs.start_job(redis, "anomalies", partial(anomaly.detect_transaction_anomalies, driver))
    return Envelope(data={"job_id": job_id, "status": "running"})


@router.get("/results/{job_id}")
async def get_job_result(job_id: str, redis: Redis = Depends(get_redis)) -> Envelope[dict | None]:
    job = await jobs.get_job(redis, job_id)
    return Envelope(data=job)
