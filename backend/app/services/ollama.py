"""Optional local-LLM adapter (ARGUS_PLAN.md Phase 10, "ARGUS Assistant").

ARGUS Core has zero dependency on this module — every other feature in the
app works with Ollama absent, uninstalled, or unreachable. This is checked
at request time (not required at startup), and any failure here surfaces as
a clear "not available" response rather than a crash.

Simplification vs. the full plan sketch: rather than having the model
generate arbitrary Cypher (a real prompt-injection / correctness risk for a
demo system), the model is given a small bundle of precomputed graph facts
as context and instructed to answer only from those facts. This keeps the
same safety principle — the model never touches the database directly —
with much less surface area than a NL-to-Cypher translator.
"""

import httpx
from neo4j import AsyncDriver

from app.config import get_settings
from app.repositories import dashboard_repo

MODEL = "llama3.2:3b"
TIMEOUT = httpx.Timeout(connect=1.5, read=30.0, write=5.0, pool=5.0)

SYSTEM_PROMPT = (
    "You are ARGUS Assistant, a read-only analyst aide for a financial-crime "
    "intelligence graph. Answer ONLY using the facts given in the CONTEXT "
    "block below. If the answer isn't in the context, say so plainly instead "
    "of guessing. Keep answers to 2-3 sentences, analyst-brief tone, no "
    "markdown."
)


async def is_available() -> bool:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(1.5)) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        return False


async def _build_context(driver: AsyncDriver) -> str:
    summary = await dashboard_repo.get_dashboard_summary(driver)
    lines = [
        f"Total persons: {summary['total_persons']}",
        f"Total organizations: {summary['total_organizations']}",
        f"Total transactions: {summary['total_transactions']}",
        f"Entities ARGUS assessed as elevated: {summary['elevated_entities']}",
        f"Open investigations: {summary['open_investigations']}",
        f"Open alerts: {summary['open_alerts']}",
        # Given as counts across every band, `unassessed` included, so the model
        # cannot describe the population as low-risk when most of it was never
        # examined. There is deliberately no average to quote.
        "Assessment distribution (persons): "
        + ", ".join(f"{b['band']}={b['count']}" for b in summary["assessment_distribution"]),
        "Recent incidents: "
        + "; ".join(f"{i['type']} ({i['severity']}): {i['description']}" for i in summary["recent_incidents"][:5]),
    ]
    return "\n".join(lines)


async def ask(driver: AsyncDriver, question: str) -> str:
    settings = get_settings()
    context = await _build_context(driver)
    prompt = f"{SYSTEM_PROMPT}\n\nCONTEXT:\n{context}\n\nQUESTION: {question}"

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            f"{settings.ollama_base_url}/api/generate",
            json={"model": MODEL, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
