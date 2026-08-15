-- Migration 004: ingestion — a durable job queue, connectors, raw landing,
-- a dead-letter queue, and the counters that make a degrading source visible.
--
-- Phase 2 built an observation layer that nothing could write to except a
-- one-off backfill. This is the path by which a real source reaches it.
--
-- What is deliberately NOT here
-- ─────────────────────────────
-- The roadmap called for PostGIS and TimescaleDB in this phase. Both are
-- deferred, by the same test that justified adding Postgres at all — name the
-- property the alternative cannot provide:
--
--   * TimescaleDB was to replace "the sampled timeline" with continuous
--     aggregates. The timeline stopped being sampled in Phase 0; it now
--     aggregates the full population and returns identical results across
--     repeated calls. The problem the extension was for no longer exists.
--   * PostGIS was for spatial clustering, kernel density and corridor analysis
--     — all of which are Phase 8. Nothing in ARGUS queries geometry today, so
--     installing it now would add an extension with no reader.
--
-- Neither is free: TimescaleDB is not in postgres:16-alpine, so adopting it
-- changes the base image that identity, audit and provenance all run on. Taking
-- that risk for a capability nothing yet uses is the trade this project has
-- repeatedly declined. Revisit PostGIS at Phase 8, and TimescaleDB only if
-- sustained ingest makes per-day aggregation over the graph too slow to serve —
-- which is a measurement, not a guess.


-- ─────────────────────────────────────────────────────────────────────────────
-- Durable job queue
--
-- `asyncio.create_task` loses every in-flight job when the process restarts
-- (audit B-07/G-21). Phase 0 stopped orphaned jobs from *looking* alive; it
-- could not make the work survive, because the work only ever existed in
-- memory. Ingestion must not lose a batch to a deploy, so the queue is a table.
--
-- Postgres rather than Celery/RabbitMQ/Kafka: SELECT ... FOR UPDATE SKIP LOCKED
-- is a complete queue primitive, the database is already here, and a queue in
-- the same transaction as the work it records is a property a separate broker
-- cannot offer.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS job_queue (
    job_id          BIGSERIAL PRIMARY KEY,
    kind            TEXT NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Optional dedupe key. Two attempts to enqueue the same logical job — a
    -- scheduler firing twice, a retry racing a manual trigger — collapse into
    -- one row rather than doing the work twice.
    idempotency_key TEXT UNIQUE,

    status          TEXT NOT NULL DEFAULT 'queued',
    priority        INTEGER NOT NULL DEFAULT 100,

    -- Earliest time this may run. Retries push it forward with backoff, so a
    -- persistently failing job does not spin.
    run_after       TIMESTAMPTZ NOT NULL DEFAULT now(),

    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 5,

    -- Lease, not a lock. A worker that dies holds `locked_until` only until it
    -- expires, after which the job is reclaimable — so a crash costs one
    -- visibility timeout rather than the job.
    locked_by       TEXT,
    locked_until    TIMESTAMPTZ,

    last_error      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,

    CONSTRAINT job_status_valid CHECK (
        status IN ('queued', 'running', 'succeeded', 'failed', 'dead', 'cancelled')
    ),
    CONSTRAINT job_attempts_bounded CHECK (max_attempts BETWEEN 1 AND 100)
);

-- The claim query's index. Partial, because only runnable rows are ever
-- scanned and the table is dominated by finished ones.
CREATE INDEX IF NOT EXISTS job_queue_claimable_idx
    ON job_queue (priority, job_id)
    WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS job_queue_reclaim_idx
    ON job_queue (locked_until)
    WHERE status = 'running';
CREATE INDEX IF NOT EXISTS job_queue_kind_idx ON job_queue (kind, created_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- Connectors
--
-- One row per configured source feed. Adding a source is an INSERT, not a code
-- change: `connector_type` selects a registered implementation and `config`
-- parameterises it, while `mapping` says how to read a record — which field is
-- the subject, which is the occurrence time, what the payload is about.
--
-- Credentials are NOT stored here. `config` may name an environment variable to
-- read a secret from; it must never contain the secret. A credential in a table
-- the application can SELECT is a credential in every backup, every replica and
-- every SQL-injection blast radius — and the whole point of the identity work
-- was to stop shipping credentials where they do not belong.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS connectors (
    connector_id    TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES sources(source_id),
    connector_type  TEXT NOT NULL,
    display_name    TEXT NOT NULL,

    config          JSONB NOT NULL DEFAULT '{}'::jsonb,
    mapping         JSONB NOT NULL DEFAULT '{}'::jsonb,

    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    poll_interval_seconds INTEGER NOT NULL DEFAULT 300,

    -- A connector producing malformed data is stopped rather than left to fill
    -- the dead-letter queue. Quarantine is explicit and reversible, and it
    -- records why, because "the feed went quiet" with no reason is how a
    -- collection gap becomes an intelligence gap nobody noticed.
    quarantined_at  TIMESTAMPTZ,
    quarantine_reason TEXT,

    -- Incremental fetch position, connector-defined (a timestamp, an etag, a
    -- file offset). Opaque to the framework.
    cursor          TEXT,

    last_run_at     TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT connector_poll_positive CHECK (poll_interval_seconds >= 10),
    CONSTRAINT connector_quarantine_complete CHECK (
        (quarantined_at IS NULL AND quarantine_reason IS NULL)
        OR (quarantined_at IS NOT NULL AND quarantine_reason IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS connectors_source_idx ON connectors (source_id);
CREATE INDEX IF NOT EXISTS connectors_due_idx ON connectors (last_run_at)
    WHERE enabled AND quarantined_at IS NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- Ingest batches — one row per fetch attempt
--
-- The unit of "did this source produce anything, and did it work". Source
-- health is computed from this table rather than tracked in a counter, so it
-- cannot drift from what actually happened.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ingest_batches (
    batch_id        BIGSERIAL PRIMARY KEY,
    connector_id    TEXT NOT NULL REFERENCES connectors(connector_id),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running',

    records_fetched   INTEGER NOT NULL DEFAULT 0,
    records_new       INTEGER NOT NULL DEFAULT 0,
    records_duplicate INTEGER NOT NULL DEFAULT 0,
    records_failed    INTEGER NOT NULL DEFAULT 0,

    error           TEXT,

    CONSTRAINT batch_status_valid CHECK (status IN ('running', 'succeeded', 'failed'))
);

CREATE INDEX IF NOT EXISTS ingest_batches_connector_idx
    ON ingest_batches (connector_id, started_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- Raw landing — append-only, hash-keyed, replayable
--
-- What arrived, exactly as it arrived, before anything interpreted it. Kept
-- forever and never edited: when a mapping turns out to be wrong, the fix is to
-- correct the mapping and replay, which is only possible if the original
-- payload still exists. A pipeline that discards its input can only ever be
-- fixed going forward.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS raw_records (
    raw_id          BIGSERIAL PRIMARY KEY,
    connector_id    TEXT NOT NULL REFERENCES connectors(connector_id),
    batch_id        BIGINT REFERENCES ingest_batches(batch_id),

    content_hash    TEXT NOT NULL,
    payload         JSONB NOT NULL,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    status          TEXT NOT NULL DEFAULT 'pending',
    processed_at    TIMESTAMPTZ,
    observation_id  UUID REFERENCES observations(observation_id),

    CONSTRAINT raw_hash_shape CHECK (char_length(content_hash) = 64),
    CONSTRAINT raw_status_valid CHECK (
        status IN ('pending', 'processed', 'duplicate', 'failed', 'quarantined')
    ),
    -- Idempotency, at the landing zone rather than only at the observation.
    -- Re-reading the same file or re-polling an unchanged endpoint must not
    -- create a second record, or every downstream count inherits the duplicate.
    CONSTRAINT raw_unique_content UNIQUE (connector_id, content_hash)
);

CREATE INDEX IF NOT EXISTS raw_records_pending_idx ON raw_records (connector_id, raw_id)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS raw_records_received_idx ON raw_records (received_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- Dead-letter queue
--
-- A malformed payload is never silently dropped. It lands here with the stage
-- that rejected it and why, stays inspectable, and can be replayed once the
-- cause is fixed. Silent drops are the failure mode that makes an intelligence
-- gap invisible: the analyst sees no data and concludes there was nothing to
-- see.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ingest_failures (
    failure_id      BIGSERIAL PRIMARY KEY,
    raw_id          BIGINT REFERENCES raw_records(raw_id),
    connector_id    TEXT NOT NULL REFERENCES connectors(connector_id),
    batch_id        BIGINT REFERENCES ingest_batches(batch_id),

    stage           TEXT NOT NULL,
    error_type      TEXT NOT NULL,
    error_detail    TEXT NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    replay_count    INTEGER NOT NULL DEFAULT 0,
    resolved_at     TIMESTAMPTZ,
    resolved_by     TEXT,
    resolution      TEXT,

    CONSTRAINT failure_stage_valid CHECK (
        stage IN ('fetch', 'validate', 'normalize', 'persist')
    ),
    CONSTRAINT failure_resolution_complete CHECK (
        (resolved_at IS NULL AND resolved_by IS NULL)
        OR (resolved_at IS NOT NULL AND resolved_by IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS ingest_failures_open_idx
    ON ingest_failures (connector_id, occurred_at DESC)
    WHERE resolved_at IS NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- Field statistics — schema-drift detection
--
-- A source that quietly renames or drops a field does not error; it just stops
-- populating something, and every derived figure silently degrades. Recording
-- which fields have ever been seen makes both directions detectable: a field
-- that appears for the first time, and one that stops arriving.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS connector_field_stats (
    connector_id    TEXT NOT NULL REFERENCES connectors(connector_id),
    field_path      TEXT NOT NULL,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    occurrences     BIGINT NOT NULL DEFAULT 0,

    PRIMARY KEY (connector_id, field_path)
);


-- ─────────────────────────────────────────────────────────────────────────────
-- Immutability
--
-- Raw payloads and dead-letter entries are evidence of what a source actually
-- sent. Same reasoning, and the same mechanism, as audit_events and
-- observations: enforced by the database so it holds even when the caller is
-- the application.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION raw_records_content_immutable() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.raw_id        IS DISTINCT FROM OLD.raw_id
       OR NEW.connector_id IS DISTINCT FROM OLD.connector_id
       OR NEW.batch_id   IS DISTINCT FROM OLD.batch_id
       OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
       OR NEW.payload    IS DISTINCT FROM OLD.payload
       OR NEW.received_at IS DISTINCT FROM OLD.received_at
    THEN
        RAISE EXCEPTION 'raw record content is immutable; replay it instead'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS raw_records_immutable_content ON raw_records;
CREATE TRIGGER raw_records_immutable_content
    BEFORE UPDATE ON raw_records
    FOR EACH ROW EXECUTE FUNCTION raw_records_content_immutable();

DROP TRIGGER IF EXISTS raw_records_no_delete ON raw_records;
CREATE TRIGGER raw_records_no_delete
    BEFORE DELETE ON raw_records
    FOR EACH ROW EXECUTE FUNCTION provenance_append_only();

DROP TRIGGER IF EXISTS raw_records_no_truncate ON raw_records;
CREATE TRIGGER raw_records_no_truncate
    BEFORE TRUNCATE ON raw_records
    FOR EACH STATEMENT EXECUTE FUNCTION provenance_append_only();

CREATE OR REPLACE FUNCTION ingest_failures_immutable() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.failure_id  IS DISTINCT FROM OLD.failure_id
       OR NEW.raw_id   IS DISTINCT FROM OLD.raw_id
       OR NEW.connector_id IS DISTINCT FROM OLD.connector_id
       OR NEW.stage    IS DISTINCT FROM OLD.stage
       OR NEW.error_type IS DISTINCT FROM OLD.error_type
       OR NEW.error_detail IS DISTINCT FROM OLD.error_detail
       OR NEW.occurred_at IS DISTINCT FROM OLD.occurred_at
    THEN
        RAISE EXCEPTION 'a dead-letter entry records what happened and is immutable'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ingest_failures_immutable_content ON ingest_failures;
CREATE TRIGGER ingest_failures_immutable_content
    BEFORE UPDATE ON ingest_failures
    FOR EACH ROW EXECUTE FUNCTION ingest_failures_immutable();

DROP TRIGGER IF EXISTS ingest_failures_no_delete ON ingest_failures;
CREATE TRIGGER ingest_failures_no_delete
    BEFORE DELETE ON ingest_failures
    FOR EACH ROW EXECUTE FUNCTION provenance_append_only();


-- ─────────────────────────────────────────────────────────────────────────────
-- Grants
-- ─────────────────────────────────────────────────────────────────────────────

-- The queue is working state: the application owns its whole lifecycle.
GRANT SELECT, INSERT, UPDATE, DELETE ON job_queue TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE job_queue_job_id_seq TO argus_app;

-- Connectors and batches are configuration and bookkeeping, also mutable.
GRANT SELECT, INSERT, UPDATE, DELETE ON connectors TO argus_app;
GRANT SELECT, INSERT, UPDATE ON ingest_batches TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE ingest_batches_batch_id_seq TO argus_app;

GRANT SELECT, INSERT, UPDATE ON connector_field_stats TO argus_app;

-- Raw landing and the dead-letter queue are evidence. Insert, read, and move
-- through their lifecycle — never rewrite, never delete.
GRANT SELECT, INSERT, UPDATE ON raw_records TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE raw_records_raw_id_seq TO argus_app;
GRANT SELECT, INSERT, UPDATE ON ingest_failures TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE ingest_failures_failure_id_seq TO argus_app;
