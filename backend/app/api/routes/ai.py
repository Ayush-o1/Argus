from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.dependencies import require_api_token
from app.models.envelope import Envelope

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(require_api_token)])

# Full implementation lands in Phase 8 (Local Intelligence Layer).
# entity-summary/case-summary are deterministic template NLG — no network
# call, no dependency. /ask is the one optional path: it probes for a local
# Ollama instance and returns a clear "assistant not available" if absent,
# rather than failing. See ARGUS_PLAN.md Phase 10.


class AskRequest(BaseModel):
    question: str
    context: dict = {}


@router.post("/entity-summary/{entity_id}")
async def entity_summary(entity_id: str) -> Envelope[dict | None]:
    return Envelope(data=None)


@router.post("/case-summary/{case_id}")
async def case_summary(case_id: str) -> Envelope[dict | None]:
    return Envelope(data=None)


@router.post("/ask")
async def ask(payload: AskRequest) -> Envelope[dict | None]:
    return Envelope(data=None)
