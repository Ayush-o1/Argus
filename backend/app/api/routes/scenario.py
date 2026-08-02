from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import require_api_token
from app.models.envelope import Envelope

router = APIRouter(prefix="/api/scenario", tags=["scenario"], dependencies=[Depends(require_api_token)])

# Full implementation lands in Phase 9 (Scenario Generator), run as an
# async background job per ARGUS_PLAN.md Phase 11.


class GenerateScenarioRequest(BaseModel):
    type: str
    complexity: str = "medium"
    seed: int | None = None


@router.post("/generate")
async def generate_scenario(payload: GenerateScenarioRequest) -> Envelope[dict]:
    return Envelope(data={"job_id": None, "status": "not_implemented"})


@router.get("/status/{job_id}")
async def scenario_status(job_id: str) -> Envelope[dict | None]:
    return Envelope(data=None)
