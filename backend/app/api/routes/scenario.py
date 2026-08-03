from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from redis.asyncio import Redis

from app.api.dependencies import require_api_token
from app.database.redis import get_redis
from app.models.envelope import Envelope
from app.services import jobs, scenario

router = APIRouter(prefix="/api/scenario", tags=["scenario"], dependencies=[Depends(require_api_token)])


class GenerateScenarioRequest(BaseModel):
    type: str
    complexity: str = "Medium"
    seed: int | None = None


@router.get("/types")
async def list_scenario_types() -> Envelope[dict]:
    return Envelope(data={"types": scenario.SCENARIO_TYPES, "complexities": scenario.COMPLEXITIES})


@router.post("/generate")
async def generate_scenario(payload: GenerateScenarioRequest, redis: Redis = Depends(get_redis)) -> Envelope[dict]:
    if payload.type not in scenario.SCENARIO_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown scenario type: {payload.type}")
    if payload.complexity not in scenario.COMPLEXITIES:
        raise HTTPException(status_code=400, detail=f"Unknown complexity: {payload.complexity}")
    job_id = await scenario.start_scenario_job(redis, payload.type, payload.complexity, payload.seed)
    return Envelope(data={"job_id": job_id, "status": "running"})


@router.get("/status/{job_id}")
async def scenario_status(job_id: str, redis: Redis = Depends(get_redis)) -> Envelope[dict | None]:
    job = await jobs.get_job(redis, job_id)
    return Envelope(data=job)
