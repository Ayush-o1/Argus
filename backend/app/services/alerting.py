"""Running the rules, and everything that happens to what they produce.

One pass over ARGUS's own findings:

    gather evidence -> evaluate rules -> group -> price -> match suppressions
                    -> dedup into alerts -> record occurrences

Each step is a module in `app/alerting/`; this file is the order they run in
and the transaction they run inside. The reason it is a service rather than a
route is the same as for assessment and correlation: it is a population-wide
recomputation, and tying one to the lifetime of an HTTP request makes the least
durable thing in the system responsible for the most expensive.

## Suppression happens after the alert exists

Reading the order above, suppression is applied at write time rather than as a
filter over firings. That is deliberate and is the whole design of
`suppression.py`: a suppressed alert is written, counted, grouped and
inspectable, and only excluded from the default queue. Filtering earlier would
be cheaper and would reintroduce exactly the silent blindness the module exists
to prevent.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.alerting.evaluation import AlertEvaluation, evaluate_alerts
from app.alerting.evidence import AlertingEvidence
from app.alerting.identity import alert_key, group_firings
from app.alerting.priority import compute_priority
from app.alerting.rules import RULES, RuleFiring, evaluate_rules, rules_fingerprint
from app.alerting.suppression import Suppression, matching_suppression
from app.database.postgres import transaction
from app.repositories import alert_findings_repo, alert_repo
from app.services import audit, queue

logger = logging.getLogger(__name__)

ALERTING_JOB_KIND = "alerting.run"
ALERTING_ACTOR = "argus.alerting"

# Assessment bands worth alerting on. `clear` and `insufficient_evidence` are
# excluded here rather than inside each rule, so the cost of loading ~2,700
# subjects nothing can fire on is never paid.
ALERTABLE_BANDS: tuple[str, ...] = ("elevated", "notable")

# How many independent methods each rule declares. Read once so priority does
# not have to search the registry per firing.
_METHODS: dict[str, int] = {r.rule_id: r.independent_methods for r in RULES}


@dataclass(frozen=True)
class AlertingOutcome:
    run_id: int
    rules_fingerprint: str
    subjects_considered: int
    firings: int
    alerts_created: int
    alerts_repeated: int
    alerts_suppressed: int
    groups_formed: int


async def _load_suppressions() -> list[Suppression]:
    rows = await alert_repo.list_suppressions(active_only=True)
    return [
        Suppression(
            suppression_id=str(r["suppression_id"]),
            rule_id=r["rule_id"],
            subject_ref=r["subject_ref"],
            reason_code=r["reason_code"],
            note=r["note"],
            created_by=r["created_by"],
            created_at=r["created_at"],
            expires_at=r["expires_at"],
            revoked_at=r["revoked_at"],
        )
        for r in rows
    ]


def _evidence_timestamp(firing: RuleFiring, evidence: AlertingEvidence) -> datetime:
    """When the evidence behind a firing was observed.

    Priority decays with evidence age, so this must be the age of what was
    found rather than of the run that found it — otherwise every alert is
    always maximally recent and the recency term does nothing.
    """
    stamps = [
        evidence.assessments[ref].computed_at
        for ref in firing.scope
        if ref in evidence.assessments
    ]
    if stamps:
        return max(stamps)
    return evidence.gathered_at or datetime.now(UTC)


async def run_alerting(triggered_by: str = ALERTING_ACTOR) -> AlertingOutcome:
    evidence = await alert_findings_repo.fetch_alerting_evidence(ALERTABLE_BANDS)
    evidence.gathered_at = datetime.now(UTC)

    fingerprint = rules_fingerprint()
    run_id = await alert_repo.start_run(
        fingerprint, evidence.assessment_run_id, evidence.correlation_run_id
    )

    try:
        firings = evaluate_rules(evidence)
        groups, assignment = group_firings(firings, evidence)
        suppressions = await _load_suppressions()

        created = repeated = suppressed_count = 0
        now = datetime.now(UTC)

        async with transaction() as conn:
            for group in groups.values():
                await alert_repo.upsert_group(
                    conn, group.key, group.basis, list(group.subjects), group.describe()
                )

            seen: set[str] = set()
            for firing in firings:
                key = alert_key(firing.rule_id, firing.rule_version, firing.scope)
                # Two rules can legitimately produce the same key only if they
                # share id and version, which the registry forbids; the guard
                # is for a rule that yields the same firing twice, which would
                # otherwise double-count an occurrence.
                if key in seen:
                    continue
                seen.add(key)

                breakdown = compute_priority(
                    magnitude=firing.magnitude,
                    confidence=firing.confidence,
                    independent_methods=_METHODS.get(firing.rule_id, 1),
                    evidence_at=_evidence_timestamp(firing, evidence),
                    now=now,
                )
                suppression = matching_suppression(suppressions, firing.rule_id, firing.scope, now)

                was_created, _ = await alert_repo.upsert_alert(
                    conn,
                    alert_key=key,
                    rule_id=firing.rule_id,
                    rule_version=firing.rule_version,
                    scope=list(firing.scope),
                    group_key=assignment[key],
                    title=firing.title,
                    summary=firing.summary,
                    priority=breakdown.priority,
                    priority_band=breakdown.band,
                    priority_factors=json.dumps(breakdown.as_dict()),
                    evidence=json.dumps(firing.evidence, default=str),
                    suppressed=suppression is not None,
                    suppressed_by=suppression.suppression_id if suppression else None,
                    run_id=run_id,
                )
                await alert_repo.record_occurrence(
                    conn, key, run_id, breakdown.priority, firing.magnitude, firing.confidence
                )

                if was_created:
                    created += 1
                    # The opening entry in the alert's history, so every alert
                    # has a first transition and the timeline never begins with
                    # a state that appeared from nowhere.
                    await conn.execute(
                        """
                        INSERT INTO alert_transitions
                            (alert_key, from_state, to_state, actor_username, actor_role, note)
                        VALUES ($1, NULL, 'open', $2, 'system', $3)
                        """,
                        key,
                        ALERTING_ACTOR,
                        f"Raised by {firing.rule_id} v{firing.rule_version}.",
                    )
                else:
                    repeated += 1
                if suppression is not None:
                    suppressed_count += 1

        await alert_repo.finish_run(
            run_id,
            subjects_considered=len(evidence.assessments),
            firings=len(firings),
            alerts_created=created,
            alerts_repeated=repeated,
            alerts_suppressed=suppressed_count,
            groups_formed=len(groups),
        )

        await audit.record(
            audit.AuditEvent(
                action="alerting.run",
                outcome="success",
                actor_username=triggered_by,
                actor_role="system",
                resource_type="AlertRun",
                resource_id=str(run_id),
                detail=(
                    f"{len(firings)} firings -> {created} new, {repeated} repeated, "
                    f"{suppressed_count} suppressed, in {len(groups)} groups"
                ),
            )
        )

        return AlertingOutcome(
            run_id=run_id,
            rules_fingerprint=fingerprint,
            subjects_considered=len(evidence.assessments),
            firings=len(firings),
            alerts_created=created,
            alerts_repeated=repeated,
            alerts_suppressed=suppressed_count,
            groups_formed=len(groups),
        )

    except Exception as exc:
        await alert_repo.fail_run(run_id, str(exc))
        await audit.record(
            audit.AuditEvent(
                action="alerting.run",
                outcome="failure",
                actor_username=triggered_by,
                actor_role="system",
                resource_type="AlertRun",
                resource_id=str(run_id),
                detail=str(exc)[:500],
            )
        )
        raise


@queue.register(ALERTING_JOB_KIND)
async def _run_alerting_job(job: queue.Job) -> None:
    payload = job.payload or {}
    outcome = await run_alerting(triggered_by=str(payload.get("triggered_by", ALERTING_ACTOR)))
    logger.info(
        "alerting run complete",
        extra={
            "run_id": outcome.run_id,
            "created": outcome.alerts_created,
            "repeated": outcome.alerts_repeated,
        },
    )

    if payload.get("evaluate"):
        from app.database.neo4j import get_driver

        report = await run_evaluation(
            get_driver(), triggered_by=str(payload.get("triggered_by", ALERTING_ACTOR))
        )
        logger.info(
            "alerting evaluation published",
            extra={"precision_strict": report.precision_strict, "recall": report.recall},
        )


async def run_evaluation(driver: Any, triggered_by: str = ALERTING_ACTOR) -> AlertEvaluation:
    """Score the current alert set against the planted storylines and publish it.

    The only path in this phase that reads a label. It runs *after* alerting,
    reads ground truth through the correlation phase's graph repository, and
    hands it to a pure function — so nothing a rule can reach ever holds a
    storyline.
    """
    from app.repositories.correlation_graph_repo import fetch_correlation_ground_truth

    runs = await alert_repo.list_runs(limit=1)
    if not runs:
        raise RuntimeError("No alerting run to evaluate. Run the rules first.")
    run_id = runs[0]["run_id"]

    alerts, _ = await alert_repo.list_alerts(include_suppressed=True, page=1, page_size=100_000)
    storylines = await fetch_correlation_ground_truth(driver)
    report = evaluate_alerts(alerts, storylines)

    await alert_repo.store_evaluation(
        run_id=run_id,
        rules_fingerprint=rules_fingerprint(),
        alerts_total=report.alerts_total,
        subjects_alerted=report.subjects_alerted,
        precision_strict=report.precision_strict,
        recall=report.recall,
        per_rule=json.dumps(report.to_dict()["per_rule"]),
        unreachable=json.dumps(report.to_dict()["per_storyline"]),
    )
    await audit.record(
        audit.AuditEvent(
            action="alerting.evaluation",
            outcome="success",
            actor_username=triggered_by,
            actor_role="system",
            resource_type="AlertRun",
            resource_id=str(run_id),
            detail=(
                f"strict precision {report.precision_strict}, recall {report.recall}, "
                f"over {report.alerts_total} alerts"
            ),
        )
    )
    return report


__all__ = [
    "ALERTABLE_BANDS",
    "ALERTING_ACTOR",
    "ALERTING_JOB_KIND",
    "AlertingOutcome",
    "run_alerting",
    "run_evaluation",
]
