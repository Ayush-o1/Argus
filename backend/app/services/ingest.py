"""The ingestion pipeline: fetch → land → validate → normalise → observe.

## Where a record goes

    connector.fetch()
        └─ raw_records          (append-only, hash-keyed; duplicates stop here)
             └─ apply_mapping   (validate + normalise; rejections go to the DLQ)
                  └─ observation (Phase 2's layer — attributed, immutable)

Every stage that can reject a record writes to `ingest_failures` with the stage
and the reason. **Nothing is ever silently dropped.** A silent drop is the worst
failure mode this system can have: the analyst sees no data and concludes there
was nothing to see, when in fact ARGUS threw it away.

## What this phase deliberately does not do

Ingestion records observations about entities that **already exist**. A record
whose subject does not resolve to a known entity is a DLQ entry, not a new node.

That is a real limit and it is the right one: creating entities from an
unresolved feed is precisely how the same real-world person reported by three
sources becomes three entities, and un-merging them afterwards is far harder
than not doing it. Entity resolution is the next phase; until it exists, those
records wait in the dead-letter queue where they are visible and replayable
rather than being turned into duplicates nobody asked for.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.database.postgres import acquire
from app.ingestion.base import (
    Connector,
    ConnectorConfigError,
    ConnectorError,
    build_connector,
)
from app.ingestion.mapping import (
    InvalidMapping,
    MappingError,
    RecordMapping,
    apply_mapping,
    field_paths,
)
from app.repositories import ingest_repo, provenance_repo
from app.repositories.ingest_repo import ConnectorRow
from app.services import queue

logger = logging.getLogger(__name__)

INGEST_JOB_KIND = "ingest.connector_run"

# A connector whose records fail at this rate, over at least this many records,
# is quarantined rather than left to fill the dead-letter queue. The floor
# matters: without it, one bad record in a batch of one is a 100% failure rate.
QUARANTINE_FAILURE_RATE = 0.5
QUARANTINE_MIN_RECORDS = 20

# How far a batch may deviate from the connector's own recent history before it
# is called out. Three standard deviations, and only once there is enough
# history for that to mean anything.
VOLUME_DRIFT_SIGMA = 3.0
VOLUME_DRIFT_MIN_SAMPLES = 5


@dataclass
class IngestOutcome:
    connector_id: str
    batch_id: int | None = None
    fetched: int = 0
    new: int = 0
    duplicate: int = 0
    failed: int = 0
    unchanged: bool = False
    error: str | None = None
    new_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "connector_id": self.connector_id,
            "batch_id": self.batch_id,
            "fetched": self.fetched,
            "new": self.new,
            "duplicate": self.duplicate,
            "failed": self.failed,
            "unchanged": self.unchanged,
            "error": self.error,
            "new_fields": self.new_fields,
            "warnings": self.warnings,
        }


async def run_connector(connector_id: str) -> IngestOutcome:
    """Run one connector once. Never raises for a source-side problem.

    Isolation is the point: a connector that fails records its own failure and
    returns. It cannot take down the worker, and it cannot affect any other
    feed, because no two connectors share a call stack or a transaction.
    """
    row = await ingest_repo.get_connector(connector_id)
    if row is None:
        raise ConnectorConfigError(f"no connector {connector_id!r}")

    outcome = IngestOutcome(connector_id=connector_id)
    if not row.is_runnable:
        outcome.error = (
            f"connector is {'quarantined' if row.quarantined_at else 'disabled'}"
            f"{f': {row.quarantine_reason}' if row.quarantine_reason else ''}"
        )
        return outcome

    try:
        mapping = RecordMapping.from_config(row.mapping)
        connector = build_connector(row.connector_type, row.connector_id, row.config)
    except (InvalidMapping, ConnectorConfigError) as exc:
        # Configuration is broken, not the data. Quarantine rather than retry:
        # no number of attempts fixes a missing directory or a bad mapping, and
        # a connector retrying a config error forever is noise that hides real
        # failures.
        await ingest_repo.set_quarantine(connector_id, f"configuration error: {exc}")
        async with acquire() as conn:
            await ingest_repo.record_failure(
                conn,
                connector_id=connector_id,
                batch_id=None,
                raw_id=None,
                stage="fetch",
                error_type=type(exc).__name__,
                error_detail=str(exc),
            )
        outcome.error = str(exc)
        return outcome

    batch_id = await ingest_repo.start_batch(connector_id)
    outcome.batch_id = batch_id

    try:
        result = await connector.fetch(row.cursor)
    except ConnectorConfigError as exc:
        # A configuration error that only surfaces at fetch time — a missing
        # directory, an unset credential — is still a configuration error, and
        # retrying it on a schedule forever produces noise that hides real
        # failures. Quarantine here as well as at build time.
        #
        # This branch exists because it did not: `ConnectorConfigError` subclasses
        # `ConnectorError`, so it was silently caught by the handler below and
        # the connector retried indefinitely, while the docstring above claimed
        # it would be quarantined. Found by the test that asserted the claim.
        await ingest_repo.set_quarantine(connector_id, f"configuration error: {exc}")
        await _fail_batch(outcome, connector_id, batch_id, exc, stage="fetch")
        await ingest_repo.mark_run(connector_id, succeeded=False, cursor=None)
        outcome.warnings.append(f"quarantined: {exc}")
        return outcome
    except ConnectorError as exc:
        await _fail_batch(outcome, connector_id, batch_id, exc, stage="fetch")
        await ingest_repo.mark_run(connector_id, succeeded=False, cursor=None)
        return outcome
    except Exception as exc:  # a connector bug, not a source problem
        logger.exception("connector raised an unexpected error", extra={"connector_id": connector_id})
        await _fail_batch(outcome, connector_id, batch_id, exc, stage="fetch")
        await ingest_repo.mark_run(connector_id, succeeded=False, cursor=None)
        return outcome

    outcome.unchanged = result.unchanged
    outcome.fetched = len(result.records)

    for record in result.records:
        await _process_record(
            outcome=outcome,
            row=row,
            connector=connector,
            mapping=mapping,
            batch_id=batch_id,
            payload=record.payload,
        )

    await ingest_repo.finish_batch(
        batch_id,
        status="succeeded",
        fetched=outcome.fetched,
        new=outcome.new,
        duplicate=outcome.duplicate,
        failed=outcome.failed,
    )
    await ingest_repo.mark_run(connector_id, succeeded=True, cursor=result.cursor)

    await _assess_quality(outcome, row)
    return outcome


async def _fail_batch(
    outcome: IngestOutcome, connector_id: str, batch_id: int, exc: Exception, *, stage: str
) -> None:
    outcome.error = f"{type(exc).__name__}: {exc}"
    await ingest_repo.finish_batch(batch_id, status="failed", error=outcome.error)
    async with acquire() as conn:
        await ingest_repo.record_failure(
            conn,
            connector_id=connector_id,
            batch_id=batch_id,
            raw_id=None,
            stage=stage,
            error_type=type(exc).__name__,
            error_detail=str(exc),
        )


async def _process_record(
    *,
    outcome: IngestOutcome,
    row: ConnectorRow,
    connector: Connector,
    mapping: RecordMapping,
    batch_id: int,
    payload: dict[str, Any],
) -> None:
    """One record, in its own transaction.

    Per-record rather than per-batch, so one malformed payload cannot roll back
    the good records around it. A batch is a unit of *fetching*, not a unit of
    atomicity — treating it as the latter means a single bad row discards
    everything that arrived with it.
    """
    content_hash = provenance_repo.canonical_hash(payload)

    async with acquire() as conn, conn.transaction():
        raw_id = await ingest_repo.land_raw(
            conn,
            connector_id=row.connector_id,
            batch_id=batch_id,
            content_hash=content_hash,
            payload=payload,
        )
        if raw_id is None:
            outcome.duplicate += 1
            return

        try:
            new_fields = await ingest_repo.record_field_paths(
                conn, row.connector_id, field_paths(payload)
            )
        except Exception:  # never let stats collection lose a good record
            logger.exception("field-stat recording failed", extra={"connector_id": row.connector_id})
            new_fields = set()

        for path in sorted(new_fields):
            if path not in outcome.new_fields:
                outcome.new_fields.append(path)

        try:
            mapped = apply_mapping(payload, mapping)
        except MappingError as exc:
            await ingest_repo.mark_raw(conn, raw_id, status="failed")
            await ingest_repo.record_failure(
                conn,
                connector_id=row.connector_id,
                batch_id=batch_id,
                raw_id=raw_id,
                stage="validate",
                error_type="MappingError",
                error_detail=str(exc),
            )
            outcome.failed += 1
            return

        note = None
        if mapped.unresolved_timestamps:
            # Recorded on the observation itself, not just logged. The whole
            # point of the provenance layer is that a gap in what ARGUS knows
            # is visible on the record, where an analyst reading it will see it.
            note = (
                "Timestamps the source supplied could not be resolved to an instant: "
                + "; ".join(mapped.unresolved_timestamps)
            )

        try:
            observation_id, created = await provenance_repo.record_observation(
                source_id=row.source_id,
                content_type=mapped.content_type,
                payload=mapped.payload,
                subjects=[(mapped.subject_ref, mapped.subject_type)],
                occurred_at=mapped.occurred_at,
                collected_at=mapped.collected_at,
                provenance_note=note,
                conn=conn,
            )
        except Exception as exc:
            await ingest_repo.mark_raw(conn, raw_id, status="failed")
            await ingest_repo.record_failure(
                conn,
                connector_id=row.connector_id,
                batch_id=batch_id,
                raw_id=raw_id,
                stage="persist",
                error_type=type(exc).__name__,
                error_detail=str(exc),
            )
            outcome.failed += 1
            return

        await ingest_repo.mark_raw(
            conn,
            raw_id,
            status="processed" if created else "duplicate",
            observation_id=observation_id,
        )
        if created:
            outcome.new += 1
        else:
            # Landed as new raw but the observation already existed — two
            # connectors feeding one source, or a payload that normalises onto
            # an earlier one. Counted as a duplicate so corroboration is not
            # inflated by a record that added nothing.
            outcome.duplicate += 1


async def _assess_quality(outcome: IngestOutcome, row: ConnectorRow) -> None:
    """Data-quality checks that run after every batch.

    Three failure modes, only one of which shows up as an error:

      1. **Records failing validation** — visible in the DLQ, and past a
         threshold the connector is quarantined rather than left to fill it.
      2. **A schema change** — the source starts emitting a field it never had.
         Nothing errors; the data just quietly means something different.
      3. **A volume collapse** — the feed still succeeds but has stopped
         carrying data. No error rate catches this, because nothing failed.
    """
    if outcome.new_fields:
        outcome.warnings.append(
            f"schema change: {len(outcome.new_fields)} field(s) not seen before "
            f"({', '.join(outcome.new_fields[:5])}"
            f"{', …' if len(outcome.new_fields) > 5 else ''}). "
            "Anything derived from this feed may no longer mean what it did."
        )

    if outcome.fetched >= QUARANTINE_MIN_RECORDS:
        failure_rate = outcome.failed / outcome.fetched
        if failure_rate >= QUARANTINE_FAILURE_RATE:
            reason = (
                f"{outcome.failed} of {outcome.fetched} records failed validation "
                f"({failure_rate:.0%}). Quarantined automatically; the records are in the "
                "dead-letter queue and can be replayed once the cause is fixed."
            )
            await ingest_repo.set_quarantine(row.connector_id, reason)
            outcome.warnings.append(reason)
            logger.error("connector quarantined", extra={"connector_id": row.connector_id})
            return

    baseline = await ingest_repo.volume_baseline(row.connector_id)
    if (
        baseline
        and baseline["samples"] >= VOLUME_DRIFT_MIN_SAMPLES
        and baseline["stddev"] > 0
        and not outcome.unchanged
    ):
        deviation = (outcome.fetched - baseline["mean"]) / baseline["stddev"]
        if abs(deviation) >= VOLUME_DRIFT_SIGMA:
            outcome.warnings.append(
                f"volume drift: {outcome.fetched} records against a recent mean of "
                f"{baseline['mean']:.0f} (±{baseline['stddev']:.0f}), "
                f"{abs(deviation):.1f}σ {'above' if deviation > 0 else 'below'}."
            )


# ─────────────────────────────────────────────────────────────────────────────
# Staleness
# ─────────────────────────────────────────────────────────────────────────────


async def stale_sources() -> list[dict[str, Any]]:
    """Sources that have not produced within their declared interval.

    A source that stops reporting looks exactly like a world in which nothing is
    happening. That is the most dangerous silent failure an intelligence system
    can have, and the only defence is an explicit expectation to measure against
    — `sources.staleness_hours`, declared when the source is registered.

    A source with no declared expectation is reported as having none rather than
    being given a default, because a made-up threshold produces made-up alerts.
    """
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    rows = await ingest_repo.health_rows()
    stale: list[dict[str, Any]] = []

    for row in rows:
        if not row["enabled"] or row["staleness_hours"] is None:
            continue
        threshold = timedelta(hours=row["staleness_hours"])
        last = row["last_success_at"]

        if last is None:
            # A connector configured five minutes ago has not "stopped
            # producing" — it has not started. Reporting it as stale
            # immediately is a false positive, and false positives are how an
            # alerting surface teaches people to ignore it. Wait until it has
            # had a full window to produce something.
            created = row.get("created_at") or row.get("last_run_at")
            if created is not None and (now - created) < threshold:
                continue
            stale.append(
                {
                    **row,
                    "kind": "never_produced",
                    "reason": (
                        "has never produced a successful batch, and its declared "
                        f"expectation of {row['staleness_hours']}h has passed"
                    ),
                }
            )
            continue

        age = now - last
        if age > threshold:
            stale.append(
                {
                    **row,
                    "kind": "stopped",
                    "reason": (
                        f"last produced {age.total_seconds() / 3600:.1f}h ago, "
                        f"against a declared expectation of {row['staleness_hours']}h"
                    ),
                }
            )
    return stale


# ─────────────────────────────────────────────────────────────────────────────
# Replay
# ─────────────────────────────────────────────────────────────────────────────


async def replay_failure(failure_id: int, *, actor: str) -> dict[str, Any]:
    """Re-run one dead-lettered record through the pipeline.

    This is what makes raw landing worth its storage: when a mapping was wrong,
    the fix is to correct the mapping and replay the original payload. A
    pipeline that discarded its input could only ever be fixed going forward,
    leaving everything already rejected permanently lost.
    """
    failure = await ingest_repo.get_failure(failure_id)
    if failure is None:
        raise ValueError(f"no failure {failure_id}")
    if failure["raw_id"] is None:
        raise ValueError("this failure has no stored payload to replay (it failed at fetch)")

    raw = await ingest_repo.get_raw(failure["raw_id"])
    if raw is None:  # pragma: no cover - foreign key guarantees this
        raise ValueError("the stored payload is missing")

    row = await ingest_repo.get_connector(failure["connector_id"])
    if row is None:
        raise ValueError(f"connector {failure['connector_id']} no longer exists")

    mapping = RecordMapping.from_config(row.mapping)
    try:
        mapped = apply_mapping(raw["payload"], mapping)
    except MappingError as exc:
        return {"replayed": True, "succeeded": False, "error": str(exc)}

    observation_id, created = await provenance_repo.record_observation(
        source_id=row.source_id,
        content_type=mapped.content_type,
        payload=mapped.payload,
        subjects=[(mapped.subject_ref, mapped.subject_type)],
        occurred_at=mapped.occurred_at,
        collected_at=mapped.collected_at,
        provenance_note="Replayed from the dead-letter queue after the cause was corrected.",
    )
    async with acquire() as conn:
        await ingest_repo.mark_raw(
            conn, raw["raw_id"], status="processed", observation_id=observation_id
        )
    await ingest_repo.resolve_failure(
        failure_id,
        resolved_by=actor,
        resolution=f"replayed successfully into observation {observation_id}",
        replayed=True,
    )
    return {
        "replayed": True,
        "succeeded": True,
        "observation_id": observation_id,
        "observation_created": created,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Scheduling
# ─────────────────────────────────────────────────────────────────────────────


@queue.register(INGEST_JOB_KIND)
async def _run_connector_job(job: queue.Job) -> None:
    connector_id = str(job.payload.get("connector_id") or "")
    if not connector_id:
        raise ValueError("ingest job has no connector_id")
    outcome = await run_connector(connector_id)
    logger.info("connector run complete", extra=outcome.as_dict())


async def enqueue_due_connectors() -> int:
    """Queue a run for every connector whose interval has elapsed.

    The idempotency key includes the run window, so a scheduler that fires twice
    — or two API instances scheduling concurrently — produces one job rather
    than two runs of the same feed.
    """
    due = await ingest_repo.due_connectors()
    queued = 0
    for row in due:
        window = int(__import__("time").time()) // max(row.poll_interval_seconds, 10)
        job_id = await queue.enqueue(
            INGEST_JOB_KIND,
            {"connector_id": row.connector_id},
            idempotency_key=f"{INGEST_JOB_KIND}:{row.connector_id}:{window}",
        )
        if job_id is not None:
            queued += 1
    return queued
