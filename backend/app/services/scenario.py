"""Scenario Generator trigger (ARGUS_PLAN.md Phase 9, Page 11).

Runs the actual synthetic-data engine (generator/generate_scenario.py) as a
subprocess against the live graph — "make the invisible visible": this
demo feature invokes the same tested generation code that built the whole
dataset, additively, rather than faking a progress bar over canned data.
"""

import asyncio
import json
import logging
import os
from pathlib import Path

from redis.asyncio import Redis

from app.config import get_settings
from app.services import jobs

logger = logging.getLogger(__name__)

# Default: resolve relative to this file's location (works when running from repo root).
# Override: set GENERATOR_DIR env var (used in Docker where generator lives at /generator).
_DEFAULT_GENERATOR_DIR = Path(__file__).resolve().parents[3] / "generator"


def _get_generator_dir() -> Path:
    """Return the generator directory, preferring the GENERATOR_DIR env-var override."""
    settings = get_settings()
    return Path(settings.generator_dir) if settings.generator_dir else _DEFAULT_GENERATOR_DIR


def _get_generator_python() -> Path:
    return _get_generator_dir() / ".venv" / "bin" / "python3"

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
    generator_dir = _get_generator_dir()
    generator_python = _get_generator_python()

    cmd = [
        str(generator_python),
        "generate_scenario.py",
        "--type",
        scenario_type,
        "--complexity",
        complexity,
    ]
    if seed is not None:
        cmd += ["--seed", str(seed)]

    # Credentials go through the environment, never argv (audit B-08). Command
    # lines are world-readable via /proc/<pid>/cmdline and `ps`, so the database
    # password was visible to every local user for the life of the subprocess —
    # and to any process-monitoring agent collecting command lines.
    env = {
        **os.environ,
        "NEO4J_URI": settings.neo4j_uri,
        "NEO4J_USER": settings.neo4j_user,
        "NEO4J_PASSWORD": settings.neo4j_password,
    }

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(generator_dir),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        return await asyncio.wait_for(
            _consume(proc, redis, job_id), timeout=settings.scenario_timeout_seconds
        )
    except TimeoutError:
        # Without this the job holds a concurrency slot forever: the previous
        # code awaited `proc.wait()` with no timeout, so a wedged generator
        # blocked the reader loop indefinitely.
        logger.error(
            "scenario generation timed out; killing subprocess",
            extra={"job_id": job_id, "timeout_s": settings.scenario_timeout_seconds},
        )
        proc.kill()
        await proc.wait()
        raise RuntimeError(
            f"Scenario generation exceeded {settings.scenario_timeout_seconds:.0f}s and was terminated."
        ) from None


async def _consume(proc: asyncio.subprocess.Process, redis: Redis, job_id: str) -> dict:
    """Reads staged progress from the generator's stdout until it exits."""
    stages: list[str] = []
    result: dict | None = None

    assert proc.stdout is not None
    async for raw_line in proc.stdout:
        line = raw_line.decode(errors="replace").strip()
        if line.startswith("STAGE:"):
            stages.append(line.removeprefix("STAGE:").strip())
            await jobs.update_job_progress(redis, job_id, stages)
        elif line.startswith("RESULT_JSON:"):
            try:
                result = json.loads(line.removeprefix("RESULT_JSON:").strip())
            except json.JSONDecodeError:
                logger.warning("generator emitted unparseable RESULT_JSON", extra={"job_id": job_id})

    stderr = (await proc.stderr.read()).decode(errors="replace") if proc.stderr else ""
    await proc.wait()

    if result is not None and "error" in result:
        raise RuntimeError(result["error"])
    if proc.returncode != 0 or result is None:
        raise RuntimeError(stderr[-800:] or "Scenario generation failed with no output")

    return {**result, "stages": stages}
