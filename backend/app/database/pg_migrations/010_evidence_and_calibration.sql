-- Migration 010: classification, export with custody, and calibration inputs.
--
-- Two halves of the audit's roadmap merged into one migration, because they
-- operate on the same records: what an investigation concluded, who is allowed
-- to see it, what left the system carrying it, and what all of that says about
-- whether the detection was any good.
--
--
-- What is deliberately NOT built, and the measurement that decided it
-- ──────────────────────────────────────────────────────────────────
-- The roadmap asks for "artifact storage in write-once object storage,
-- referenced by SHA-256". Before writing any of it, the graph was counted:
--
--     MATCH (n) WHERE n.file_path IS NOT NULL OR n.content IS NOT NULL
--                  OR n.blob IS NOT NULL OR n.sha256 IS NOT NULL
--     RETURN count(n)                                          →  0
--     SELECT count(*) FROM raw_records                          →  0
--
-- Nothing in ARGUS holds bytes. The 2,000 `Document` nodes are metadata — a
-- doc_id, a type, an issuer and two dates — with no file behind them. An object
-- store added here would be a store for zero artifacts, and the standard this
-- project holds itself to is that a technology must be shown to be needed
-- before it is added.
--
-- But **export creates artifacts**. The moment an investigation is exported it
-- becomes a byte stream that leaves the system, and that stream is exactly the
-- thing whose integrity has to be verifiable later and whose every access has
-- to be recorded. So the custody chain here is over artifacts that genuinely
-- exist, and it is complete for them: hashed at creation, re-hashable on
-- demand, every read logged, disposal recorded rather than silent.
--
-- The bytes live in PostgreSQL. A case export is kilobytes; an object store
-- would be a second piece of infrastructure to operate, back up and secure for
-- data that fits comfortably in a column. If exports ever carry attachments —
-- images, PDFs, seized files — that trade changes, and the trigger is stated in
-- `app/evidence/artifacts.py` rather than left for someone to guess.


-- ─────────────────────────────────────────────────────────────────────────────
-- Classification
--
-- Four levels with a numeric rank, because "cannot exceed the actor's
-- clearance" is a comparison and a comparison needs an order.
--
-- These are deliberately NOT the markings of any national scheme. Borrowing
-- OFFICIAL / SECRET / TOP SECRET would imply this system had been accredited to
-- handle material under one, which it has not, and a marking that looks
-- official but means nothing is worse than a neutral one that means what it
-- says. `app/evidence/classification.py` carries the handling caveat for each
-- level and states that mapping to a real scheme is a deployment decision.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS clearance TEXT NOT NULL DEFAULT 'internal';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_clearance_valid'
    ) THEN
        ALTER TABLE users ADD CONSTRAINT users_clearance_valid
            CHECK (clearance IN ('unrestricted', 'internal', 'confidential', 'restricted'));
    END IF;
END $$;

ALTER TABLE investigations
    ADD COLUMN IF NOT EXISTS classification TEXT NOT NULL DEFAULT 'internal';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'investigations_classification_valid'
    ) THEN
        ALTER TABLE investigations ADD CONSTRAINT investigations_classification_valid
            CHECK (classification IN ('unrestricted', 'internal', 'confidential', 'restricted'));
    END IF;
END $$;


-- The queue view is redefined here to carry the classification, because the
-- listing query filters on it. `CREATE OR REPLACE VIEW` cannot insert a column
-- in the middle of an existing definition, so the view is dropped and rebuilt —
-- a view holds no data, so nothing is lost.
DROP VIEW IF EXISTS investigation_queue;
CREATE VIEW investigation_queue AS
SELECT i.investigation_id,
       i.inv_ref,
       i.title,
       i.state,
       i.confidence,
       i.classification,
       i.assigned_to,
       i.opened_by,
       i.opened_at,
       i.outcome,
       i.closed_at,
       (SELECT count(*) FROM investigation_reviews r
         WHERE r.investigation_id = i.investigation_id) AS review_count,
       (SELECT count(*) FROM investigation_reviews r
         WHERE r.investigation_id = i.investigation_id AND NOT r.concurs) AS dissenting_reviews,
       (SELECT max(r.reviewed_at) FROM investigation_reviews r
         WHERE r.investigation_id = i.investigation_id) AS last_reviewed_at,
       (SELECT count(*) FROM investigation_alerts a
         WHERE a.investigation_id = i.investigation_id AND a.detached_at IS NULL) AS alert_count,
       (SELECT count(*) FROM investigation_entities e
         WHERE e.investigation_id = i.investigation_id AND e.removed_at IS NULL) AS entity_count,
       (SELECT count(*) FROM investigation_findings f
         WHERE f.investigation_id = i.investigation_id
           AND f.withdrawn_at IS NULL AND f.superseded_at IS NULL) AS finding_count,
       (SELECT count(*) FROM investigation_actions t
         WHERE t.investigation_id = i.investigation_id AND t.completed_at IS NULL) AS open_action_count
FROM investigations i;

GRANT SELECT ON investigation_queue TO argus_app;


-- ─────────────────────────────────────────────────────────────────────────────
-- Exports — the artifacts, and their custody
--
-- Append-only apart from disposal. An export that was produced is a fact about
-- what left this system and who took it; editing that record would defeat the
-- entire point of hashing the content in the first place.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS exports (
    export_id           UUID PRIMARY KEY,

    -- What was exported. Nullable investigation because a future export may
    -- cover something else; `subject_kind` says what this row is about so the
    -- table does not become a set of mutually exclusive nullable columns.
    subject_kind        TEXT NOT NULL,
    investigation_id    UUID REFERENCES investigations(investigation_id),

    -- json for a machine, html for a person. Both are produced from the same
    -- snapshot in one request, so the two can never describe different states
    -- of the same investigation.
    format              TEXT NOT NULL,

    -- The classification the content carried at the moment it was produced.
    -- Frozen, not a foreign key to the investigation's current value: an export
    -- is a copy that has already left, and reclassifying the source afterwards
    -- cannot reach it. What matters for custody is what was on the paper.
    classification      TEXT NOT NULL,

    content             BYTEA NOT NULL,
    content_sha256      TEXT NOT NULL,
    byte_size           INTEGER NOT NULL,

    requested_by        TEXT NOT NULL,
    requester_role      TEXT NOT NULL,
    requester_clearance TEXT NOT NULL,
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    request_ip          TEXT,

    -- Why it was needed. Required: an export is the one operation that moves
    -- intelligence outside the system's own controls, and an unexplained one is
    -- indistinguishable from exfiltration when it is reviewed later.
    purpose             TEXT NOT NULL,

    -- Automated disposal. `retention_until` is set from the classification's
    -- schedule at creation, so a change of policy cannot retroactively shorten
    -- the life of something already produced.
    retention_until     TIMESTAMPTZ NOT NULL,
    disposed_at         TIMESTAMPTZ,
    disposed_by         TEXT,
    disposal_reason     TEXT,

    CONSTRAINT exports_format_valid CHECK (format IN ('json', 'html')),
    CONSTRAINT exports_subject_kind_valid CHECK (subject_kind IN ('investigation')),
    CONSTRAINT exports_classification_valid
        CHECK (classification IN ('unrestricted', 'internal', 'confidential', 'restricted')),
    CONSTRAINT exports_sha256_shape CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT exports_size_positive CHECK (byte_size > 0),
    CONSTRAINT exports_purpose_present CHECK (length(btrim(purpose)) > 0),
    CONSTRAINT exports_disposal_complete CHECK (
        (disposed_at IS NULL AND disposed_by IS NULL AND disposal_reason IS NULL)
        OR (disposed_at IS NOT NULL AND disposed_by IS NOT NULL AND disposal_reason IS NOT NULL)
    ),
    -- Disposal empties the content and says so. The row survives, because "an
    -- export of this investigation was made on this date by this person and has
    -- since been destroyed" is a fact worth more than the bytes were.
    CONSTRAINT exports_disposed_is_empty
        CHECK (disposed_at IS NULL OR length(content) = 0)
);

CREATE INDEX IF NOT EXISTS exports_investigation_idx ON exports (investigation_id, requested_at DESC);
CREATE INDEX IF NOT EXISTS exports_due_idx ON exports (retention_until) WHERE disposed_at IS NULL;
CREATE INDEX IF NOT EXISTS exports_by_requester_idx ON exports (requested_by, requested_at DESC);


-- Every access to an artifact, not only every modification.
--
-- This is the half of chain of custody that systems usually skip, and it is the
-- half that answers the question actually asked after an incident: not "was
-- this changed" but "who has seen it". Producing the export is one row here
-- too, so the log is complete rather than starting at the second reader.
CREATE TABLE IF NOT EXISTS export_access (
    access_id       BIGSERIAL PRIMARY KEY,
    export_id       UUID NOT NULL REFERENCES exports(export_id),

    action          TEXT NOT NULL,
    actor_username  TEXT NOT NULL,
    actor_role      TEXT NOT NULL,
    actor_clearance TEXT NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip_address      TEXT,

    -- Recorded for refusals as well as successes. A denied read is the more
    -- interesting event of the two.
    outcome         TEXT NOT NULL DEFAULT 'success',
    detail          TEXT,

    CONSTRAINT export_access_action_valid
        CHECK (action IN ('created', 'downloaded', 'verified', 'listed', 'disposed')),
    CONSTRAINT export_access_outcome_valid CHECK (outcome IN ('success', 'denied'))
);

CREATE INDEX IF NOT EXISTS export_access_by_export_idx ON export_access (export_id, occurred_at);
CREATE INDEX IF NOT EXISTS export_access_by_actor_idx ON export_access (actor_username, occurred_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- Immutability
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION evidence_append_only() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not permitted', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

-- Exports get their own trigger rather than reusing migration 009's generic
-- one, because disposal legitimately changes `content` — it empties it — and a
-- generic "only these columns may move" rule cannot express "this column may
-- move, but only to empty, and only in the same statement that records the
-- disposal".
CREATE OR REPLACE FUNCTION exports_disposal_only() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.export_id       IS DISTINCT FROM OLD.export_id
       OR NEW.subject_kind IS DISTINCT FROM OLD.subject_kind
       OR NEW.investigation_id IS DISTINCT FROM OLD.investigation_id
       OR NEW.format       IS DISTINCT FROM OLD.format
       OR NEW.classification IS DISTINCT FROM OLD.classification
       OR NEW.content_sha256 IS DISTINCT FROM OLD.content_sha256
       OR NEW.byte_size    IS DISTINCT FROM OLD.byte_size
       OR NEW.requested_by IS DISTINCT FROM OLD.requested_by
       OR NEW.requester_role IS DISTINCT FROM OLD.requester_role
       OR NEW.requester_clearance IS DISTINCT FROM OLD.requester_clearance
       OR NEW.requested_at IS DISTINCT FROM OLD.requested_at
       OR NEW.request_ip   IS DISTINCT FROM OLD.request_ip
       OR NEW.purpose      IS DISTINCT FROM OLD.purpose
       OR NEW.retention_until IS DISTINCT FROM OLD.retention_until
    THEN
        RAISE EXCEPTION 'an export record is immutable; only disposal may change it'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF OLD.disposed_at IS NOT NULL THEN
        RAISE EXCEPTION 'this export has already been disposed of and cannot be altered'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    -- The content may only ever be destroyed, never replaced. Without this,
    -- "disposal" would be an unrestricted write to the one column whose hash
    -- everything else in this schema exists to protect.
    IF NEW.content IS DISTINCT FROM OLD.content AND length(NEW.content) <> 0 THEN
        RAISE EXCEPTION 'export content may only be emptied, never rewritten'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF length(NEW.content) = 0 AND NEW.disposed_at IS NULL THEN
        RAISE EXCEPTION 'emptying an export requires recording the disposal'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS exports_immutable ON exports;
CREATE TRIGGER exports_immutable
    BEFORE UPDATE ON exports
    FOR EACH ROW EXECUTE FUNCTION exports_disposal_only();

DROP TRIGGER IF EXISTS exports_no_delete ON exports;
CREATE TRIGGER exports_no_delete
    BEFORE DELETE ON exports
    FOR EACH ROW EXECUTE FUNCTION evidence_append_only();

-- The access log is the record of who saw what. If it were mutable, it would
-- answer that question only for people who did not think to edit it.
DROP TRIGGER IF EXISTS export_access_no_update ON export_access;
CREATE TRIGGER export_access_no_update
    BEFORE UPDATE ON export_access
    FOR EACH ROW EXECUTE FUNCTION evidence_append_only();

DROP TRIGGER IF EXISTS export_access_no_delete ON export_access;
CREATE TRIGGER export_access_no_delete
    BEFORE DELETE ON export_access
    FOR EACH ROW EXECUTE FUNCTION evidence_append_only();

DROP TRIGGER IF EXISTS export_access_no_truncate ON export_access;
CREATE TRIGGER export_access_no_truncate
    BEFORE TRUNCATE ON export_access
    FOR EACH STATEMENT EXECUTE FUNCTION evidence_append_only();


-- ─────────────────────────────────────────────────────────────────────────────
-- Calibration inputs
--
-- Views, not tables. Everything calibration reads is already stored
-- append-only somewhere else — alerts and their dismissals in 008,
-- investigations and their outcomes in 009, assessment runs in 006 — so a
-- snapshot table here would be derived data with its own staleness, and the
-- first time it disagreed with its sources nobody would know which to believe.
--
-- Nothing here computes a rate. Every view emits counts, and
-- `app/calibration/` turns them into estimates **with intervals**, refusing to
-- publish a bare figure. That refusal is the point: two closed investigations
-- can produce a precision of 1.00, and a system that prints it has learned
-- nothing and said something false.
-- ─────────────────────────────────────────────────────────────────────────────

-- What happened to the alerts each rule version raised.
CREATE OR REPLACE VIEW rule_alert_disposition AS
SELECT rule_id,
       rule_version,
       count(*)                                              AS alerts,
       count(*) FILTER (WHERE state = 'open')                AS still_open,
       count(*) FILTER (WHERE state = 'acknowledged')        AS acknowledged,
       count(*) FILTER (WHERE state = 'investigating')       AS investigating,
       count(*) FILTER (WHERE state = 'resolved')            AS resolved,
       count(*) FILTER (WHERE state = 'dismissed')           AS dismissed,
       count(*) FILTER (WHERE suppressed)                    AS suppressed,
       sum(occurrence_count)                                 AS firings
FROM alerts
GROUP BY rule_id, rule_version;

-- Dismissals broken out by reason. The reason codes are the training signal;
-- which of them count against a rule is decided in `app/alerting/lifecycle.py`
-- and deliberately not encoded here, so there is one definition of that rather
-- than two that can drift.
CREATE OR REPLACE VIEW rule_dismissal_reasons AS
SELECT rule_id, rule_version, dismissal_reason, count(*) AS alerts
FROM alerts
WHERE dismissal_reason IS NOT NULL
GROUP BY rule_id, rule_version, dismissal_reason;

-- Investigations opened with no alert behind them.
--
-- The false-negative estimate, and the only one available: an analyst opened an
-- investigation into something ARGUS had not raised. It is a lower bound and
-- nothing more — it counts the misses somebody happened to notice, which is not
-- the same as the misses that exist.
CREATE OR REPLACE VIEW investigations_without_alerts AS
SELECT i.investigation_id,
       i.inv_ref,
       i.title,
       i.opened_by,
       i.opened_at,
       i.state,
       i.outcome
FROM investigations i
WHERE NOT EXISTS (
    SELECT 1 FROM investigation_alerts ia
     WHERE ia.investigation_id = i.investigation_id
       AND ia.detached_at IS NULL
);

-- Band distribution per assessment run, for drift.
--
-- Drift is a change in what the model says about a population that did not
-- change. These are the raw counts per run; whether a difference between two of
-- them is a real shift or ordinary variation is a question for a test, and
-- `app/calibration/drift.py` uses one rather than eyeballing the percentages.
CREATE OR REPLACE VIEW assessment_run_bands AS
SELECT run_id,
       model_version,
       model_fingerprint,
       started_at,
       finished_at,
       subjects_assessed,
       elevated_count,
       notable_count,
       routine_count,
       insufficient_count
FROM assessment_runs
WHERE status = 'complete';


-- ─────────────────────────────────────────────────────────────────────────────
-- Least privilege
-- ─────────────────────────────────────────────────────────────────────────────

GRANT SELECT, INSERT, UPDATE ON exports TO argus_app;
GRANT SELECT, INSERT ON export_access TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE export_access_access_id_seq TO argus_app;

GRANT SELECT ON rule_alert_disposition TO argus_app;
GRANT SELECT ON rule_dismissal_reasons TO argus_app;
GRANT SELECT ON investigations_without_alerts TO argus_app;
GRANT SELECT ON assessment_run_bands TO argus_app;
