from fastapi import APIRouter, Depends, HTTPException
from neo4j import AsyncDriver
from pydantic import BaseModel

from app.api.dependencies import get_db, require_api_token
from app.models.envelope import Envelope
from app.repositories import case_repo, entity_repo, graph_repo
from app.services import narrative, ollama

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(require_api_token)])

# entity-summary/case-summary are deterministic template NLG (app/services/
# narrative.py) — no network call, no dependency. /ask is the one optional
# path: it probes for a local Ollama instance and returns a clear "assistant
# not available" if absent, rather than failing. See ARGUS_PLAN.md Phase 10.


class AskRequest(BaseModel):
    question: str


@router.post("/entity-summary/{entity_id}")
async def entity_summary(entity_id: str, driver: AsyncDriver = Depends(get_db)) -> Envelope[dict | None]:
    node = await graph_repo.get_node_by_human_id(driver, entity_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    connections = await entity_repo.get_connection_summary(driver, entity_id)
    summary = narrative.compose_entity_narrative(node["label"], node["name"], node["properties"], connections)
    return Envelope(data={"summary": summary})


@router.post("/case-summary/{case_id}")
async def case_summary(case_id: str, driver: AsyncDriver = Depends(get_db)) -> Envelope[dict | None]:
    case = await case_repo.get_case(driver, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    summary = narrative.compose_case_narrative(case, case["linked_entities"])
    return Envelope(data={"summary": summary})


@router.get("/assistant-status")
async def assistant_status() -> Envelope[dict]:
    available = await ollama.is_available()
    return Envelope(data={"available": available})


@router.post("/ask")
async def ask(payload: AskRequest, driver: AsyncDriver = Depends(get_db)) -> Envelope[dict | None]:
    if not await ollama.is_available():
        raise HTTPException(status_code=503, detail="Assistant not available — Ollama not detected")
    answer = await ollama.ask(driver, payload.question)
    return Envelope(data={"answer": answer})
