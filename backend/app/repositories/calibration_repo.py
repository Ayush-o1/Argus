"""Reads for calibration. Every statement selects from a view defined in migration 010.

Nothing here computes an estimate. The views emit counts, this module hands them
over, and `app/calibration/` turns them into figures with intervals — which
keeps the one judgement that matters (when is a denominator too small to speak
about) in a single place with a test around it, rather than spread across SQL.
"""

from __future__ import annotations

from typing import Any

from app.database.postgres import acquire

__all__ = [
    "fetch_alert_keys",
    "fetch_assessment_runs",
    "fetch_confirmed_alert_keys",
    "fetch_dismissal_by_key",
    "fetch_dismissals",
    "fetch_disposition",
    "fetch_outcomes",
    "fetch_unalerted_investigations",
]

_DISPOSITION = """
    SELECT rule_id, rule_version, alerts, still_open, acknowledged, investigating,
           resolved, dismissed, suppressed, firings
    FROM rule_alert_disposition
    ORDER BY rule_id, rule_version
"""

_DISMISSALS = """
    SELECT rule_id, rule_version, dismissal_reason, alerts
    FROM rule_dismissal_reasons
    ORDER BY rule_id, rule_version, dismissal_reason
"""

_OUTCOMES = """
    SELECT rule_id, rule_version, outcome, investigations, alerts
    FROM investigation_outcomes_by_rule
    ORDER BY rule_id, rule_version, outcome
"""

_UNALERTED = """
    SELECT investigation_id, inv_ref, title, opened_by, opened_at, state, outcome
    FROM investigations_without_alerts
    ORDER BY opened_at DESC
"""

_RUNS = """
    SELECT run_id, model_version, model_fingerprint, started_at, finished_at,
           subjects_assessed, elevated_count, notable_count, routine_count,
           insufficient_count
    FROM assessment_run_bands
    ORDER BY run_id
"""

_ALERT_KEYS = "SELECT alert_key FROM alerts"

_DISMISSAL_BY_KEY = """
    SELECT alert_key, dismissal_reason FROM alerts WHERE dismissal_reason IS NOT NULL
"""

# Alert keys attached to an investigation that confirmed its hypothesis. Used by
# the simulator to say whether a proposed threshold change would remove an alert
# somebody had already established was real — the single most important thing to
# know before activating one.
_CONFIRMED_KEYS = """
    SELECT DISTINCT ia.alert_key
    FROM investigation_alerts ia
    JOIN investigations i ON i.investigation_id = ia.investigation_id
    WHERE ia.detached_at IS NULL AND i.outcome = 'confirmed'
"""


async def _rows(query: str) -> list[dict[str, Any]]:
    async with acquire() as conn:
        return [dict(r) for r in await conn.fetch(query)]


async def fetch_disposition() -> list[dict[str, Any]]:
    return await _rows(_DISPOSITION)


async def fetch_dismissals() -> list[dict[str, Any]]:
    return await _rows(_DISMISSALS)


async def fetch_outcomes() -> list[dict[str, Any]]:
    return await _rows(_OUTCOMES)


async def fetch_unalerted_investigations() -> list[dict[str, Any]]:
    return await _rows(_UNALERTED)


async def fetch_assessment_runs() -> list[dict[str, Any]]:
    return await _rows(_RUNS)


async def fetch_alert_keys() -> set[str]:
    async with acquire() as conn:
        rows = await conn.fetch(_ALERT_KEYS)
    return {r["alert_key"] for r in rows}


async def fetch_dismissal_by_key() -> dict[str, str]:
    async with acquire() as conn:
        rows = await conn.fetch(_DISMISSAL_BY_KEY)
    return {r["alert_key"]: r["dismissal_reason"] for r in rows}


async def fetch_confirmed_alert_keys() -> set[str]:
    async with acquire() as conn:
        rows = await conn.fetch(_CONFIRMED_KEYS)
    return {r["alert_key"] for r in rows}
