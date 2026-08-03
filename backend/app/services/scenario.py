"""Scenario Generator trigger (ARGUS_PLAN.md Phase 9, Page 11).

Runs the actual synthetic-data engine (generator/generate_scenario.py) as a
subprocess against the live graph — "make the invisible visible": this
demo feature invokes the same tested generation code that built the whole
dataset, additively, rather than faking a progress bar over canned data.
"""

import asyncio
import json
from pathlib import Path

from redis.asyncio import Redis

from app.config import get_settings
from app.services import jobs

GENERATOR_DIR = Path(__file__).resolve().parents[3] / "generator"
GENERATOR_PYTHON = GENERATOR_DIR / ".venv" / "bin" / "python3"

SCENARIO_TYPES = [
    "shell_company_ring",
    "money_routing_network",
    "communication_cluster",
    "supply_chain_divergence",
    "document_forgery_ring",
    "identity_overlap",
]

COMPLEXITIES = ["Low", "Medium", "High"]


async def start_scenario_job(
    redis: Redis, scenario_type: str, complexity: str, seed: int | None
) -> str:
    return await jobs.start_job_with_progress(
        redis, "scenario", lambda job_id: _run(redis, job_id, scenario_type, complexity, seed)
    )


async def _run(redis: Redis, job_id: str, scenario_type: str, complexity: str, seed: int | None) -> dict:
    settings = get_settings()
    cmd = [
        str(GENERATOR_PYTHON),
        "generate_scenario.py",
        "--type",
        scenario_type,
        "--complexity",
        complexity,
        "--neo4j-uri",
        settings.neo4j_uri,
        "--neo4j-user",
        settings.neo4j_user,
        "--neo4j-password",
        settings.neo4j_password,
    ]
    if seed is not None:
        cmd += ["--seed", str(seed)]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(GENERATOR_DIR),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stages: list[str] = []
    result: dict | None = None
    assert proc.stdout is not None
    async for raw_line in proc.stdout:
        line = raw_line.decode().strip()
        if line.startswith("STAGE:"):
            stages.append(line.removeprefix("STAGE:").strip())
            await jobs.update_job_progress(redis, job_id, stages)
        elif line.startswith("RESULT_JSON:"):
            result = json.loads(line.removeprefix("RESULT_JSON:").strip())

    stderr = (await proc.stderr.read()).decode() if proc.stderr else ""
    await proc.wait()

    if result is not None and "error" in result:
        raise RuntimeError(result["error"])
    if proc.returncode != 0 or result is None:
        raise RuntimeError(stderr[-800:] or "Scenario generation failed with no output")

    return {**result, "stages": stages}
