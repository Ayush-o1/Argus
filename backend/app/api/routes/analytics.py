from fastapi import APIRouter, Depends

from app.api.dependencies import require_api_token
from app.models.envelope import Envelope

router = APIRouter(prefix="/api/analytics", tags=["analytics"], dependencies=[Depends(require_api_token)])

# Full GDS-backed implementations (PageRank, Louvain, Betweenness, Risk
# Propagation, Cycle Detection) land in Phase 6, run as async background
# jobs per ARGUS_PLAN.md Phase 11 (asyncio task + Redis job status).


@router.post("/pagerank")
async def run_pagerank() -> Envelope[dict]:
    return Envelope(data={"job_id": None, "status": "not_implemented"})


@router.post("/betweenness")
async def run_betweenness() -> Envelope[dict]:
    return Envelope(data={"job_id": None, "status": "not_implemented"})


@router.post("/louvain")
async def run_louvain() -> Envelope[dict]:
    return Envelope(data={"job_id": None, "status": "not_implemented"})


@router.post("/risk-propagation")
async def run_risk_propagation(seed_ids: str = "") -> Envelope[dict]:
    return Envelope(data={"job_id": None, "status": "not_implemented"})


@router.post("/cycle-detection")
async def run_cycle_detection() -> Envelope[dict]:
    return Envelope(data={"job_id": None, "status": "not_implemented"})


@router.get("/results/{job_id}")
async def get_job_result(job_id: str) -> Envelope[dict | None]:
    return Envelope(data=None)
