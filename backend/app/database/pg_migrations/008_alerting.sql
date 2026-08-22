-- Migration 008: alerting — alerts ARGUS raised from its own findings, the
-- occurrences behind each one, the groups they fall into, every state change
-- anyone made, and the suppressions that hid some of them.
--
-- The organising decision, and the way this differs from 005–007:
--
--   **An alert is mutable; everything that happened to it is not.**
--
-- Assessments, links and resolution decisions are dated claims — a re-run
-- appends and nothing is ever edited. An alert cannot work that way, because it
-- is a work item: it has a current state, an assignee, and an occurrence count,
-- and an analyst needs to read the current one without folding a history.
--
-- So the mutable row is small and the history is complete beside it. `alerts`
-- holds current state. `alert_occurrences` records every time the rules fired
-- on it, and `alert_transitions` every state change with who made it — both
-- append-only by trigger. Anything you could want to reconstruct is derivable
-- from those two, and the mutable row can be rebuilt from them if it is ever
-- doubted.
--
-- What is deliberately NOT here: any reference to Incident. Alerts were a
-- severity filter over generator-written Incident nodes; that is what this
-- phase replaces. See app/alerting/evidence.py.


-- ─────────────────────────────────────────────────────────────────────────────
-- Runs
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alert_runs (
    run_id              BIGSERIAL PRIMARY KEY,

    rules_fingerprint   TEXT NOT NULL,

    -- The findings this run alerted on. An alert is only interpretable against
    -- the generation of assessments and correlations that produced it.
    assessment_run_id   BIGINT REFERENCES assessment_runs(run_id),
    correlation_run_id  BIGINT REFERENCES correlation_runs(run_id),

    status              TEXT NOT NULL DEFAULT 'running',
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,

    subjects_considered INTEGER NOT NULL DEFAULT 0,
    firings             INTEGER NOT NULL DEFAULT 0,
    alerts_created      INTEGER NOT NULL DEFAULT 0,

    -- Firings that matched an existing alert. The pair (firings,
    -- alerts_created) is the dedup ratio, and reporting only one of them hides
    -- whether the queue is growing with events or with time.
    alerts_repeated     INTEGER NOT NULL DEFAULT 0,
    alerts_suppressed   INTEGER NOT NULL DEFAULT 0,
    groups_formed       INTEGER NOT NULL DEFAULT 0,

    error               TEXT,

    CONSTRAINT alert_runs_status_valid
        CHECK (status IN ('running', 'complete', 'failed'))
);

CREATE INDEX IF NOT EXISTS alert_runs_started_idx ON alert_runs (started_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- Groups
--
-- Written before alerts because alerts reference them. A group is a claim the
-- correlation phase already made (a cluster) or the trivial one (same subjects);
-- `basis` records which, so a grouping is never unexplained.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alert_groups (
    group_key       TEXT PRIMARY KEY,
    basis           TEXT NOT NULL,
    subjects        TEXT[] NOT NULL,
    summary         TEXT NOT NULL,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ─────────────────────────────────────────────────────────────────────────────
-- Alerts
--
-- `alert_key` is the dedup identity: sha256 over (rule_id, rule_version,
-- sorted scope). It is the primary key rather than a surrogate, because the
-- whole point is that the same finding maps to the same row.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alerts (
    alert_key           TEXT PRIMARY KEY,

    rule_id             TEXT NOT NULL,
    rule_version        INTEGER NOT NULL,
    scope               TEXT[] NOT NULL,

    group_key           TEXT REFERENCES alert_groups(group_key),

    title               TEXT NOT NULL,
    summary             TEXT NOT NULL,

    -- Priority and its factors. Stored rather than computed on read because a
    -- queue ordered by a value that changes under it as time passes is not a
    -- queue anyone can work; recomputation happens at run time, visibly.
    priority            NUMERIC(6,4) NOT NULL,
    priority_band       TEXT NOT NULL,
    priority_factors    JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- The quantities behind `summary`, so the UI shows working rather than a
    -- sentence the reader must take on trust.
    evidence            JSONB NOT NULL DEFAULT '{}'::jsonb,

    state               TEXT NOT NULL DEFAULT 'open',
    assigned_to         TEXT,

    -- Set only when the alert reaches a terminal state; cleared on reopen. The
    -- audit found `closed_at` declared on cases and written by no code path,
    -- so this one is asserted by a test rather than by intention.
    closed_at           TIMESTAMPTZ,
    dismissal_reason    TEXT,

    suppressed          BOOLEAN NOT NULL DEFAULT false,
    suppressed_by       TEXT,

    occurrence_count    INTEGER NOT NULL DEFAULT 1,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    first_run_id        BIGINT NOT NULL REFERENCES alert_runs(run_id),
    last_run_id         BIGINT NOT NULL REFERENCES alert_runs(run_id),

    CONSTRAINT alerts_state_valid
        CHECK (state IN ('open', 'acknowledged', 'investigating', 'resolved', 'dismissed')),
    CONSTRAINT alerts_priority_band_valid
        CHECK (priority_band IN ('high', 'medium', 'low')),
    CONSTRAINT alerts_occurrence_positive
        CHECK (occurrence_count >= 1),

    -- A dismissal without a reason is the thing the vocabulary exists to
    -- prevent, enforced here as well as in lifecycle.py so it cannot be
    -- bypassed by a future writer that forgets to call the checker.
    CONSTRAINT alerts_dismissal_has_reason
        CHECK (state <> 'dismissed' OR dismissal_reason IS NOT NULL),

    -- Terminal states carry a closure time; non-terminal ones must not.
    CONSTRAINT alerts_closed_at_iff_terminal
        CHECK ((state IN ('resolved', 'dismissed')) = (closed_at IS NOT NULL)),

    -- A suppressed alert names the suppression that hid it. "Why did I not see
    -- this" must be answerable from the alert.
    CONSTRAINT alerts_suppressed_has_source
        CHECK (NOT suppressed OR suppressed_by IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS alerts_queue_idx
    ON alerts (state, suppressed, priority DESC, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS alerts_group_idx ON alerts (group_key);
CREATE INDEX IF NOT EXISTS alerts_rule_idx ON alerts (rule_id, rule_version);
CREATE INDEX IF NOT EXISTS alerts_scope_idx ON alerts USING GIN (scope);


-- ─────────────────────────────────────────────────────────────────────────────
-- Occurrences — every time the rules fired on an alert.
--
-- This is what makes `occurrence_count` auditable. A count on its own is a
-- number nobody can check; with the rows behind it, "fired 40 times" can be
-- resolved to which runs, when, and at what priority each time.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alert_occurrences (
    occurrence_id   BIGSERIAL PRIMARY KEY,
    alert_key       TEXT NOT NULL REFERENCES alerts(alert_key) ON DELETE CASCADE,
    run_id          BIGINT NOT NULL REFERENCES alert_runs(run_id),
    priority        NUMERIC(6,4) NOT NULL,
    magnitude       NUMERIC(6,4) NOT NULL,
    confidence      NUMERIC(6,4) NOT NULL,
    observed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT alert_occurrences_unique_per_run UNIQUE (alert_key, run_id)
);

CREATE INDEX IF NOT EXISTS alert_occurrences_alert_idx
    ON alert_occurrences (alert_key, observed_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- Transitions — who changed what, when, and from what.
--
-- The question the audit found structurally unanswerable ("who downgraded this,
-- when, and from what") is answerable here by construction. Append-only: the
-- history of a work item is not itself a work item.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alert_transitions (
    transition_id   BIGSERIAL PRIMARY KEY,
    alert_key       TEXT NOT NULL REFERENCES alerts(alert_key) ON DELETE CASCADE,

    from_state      TEXT,
    to_state        TEXT NOT NULL,
    reason_code     TEXT,
    note            TEXT,

    actor_username  TEXT NOT NULL,
    actor_role      TEXT NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT alert_transitions_to_state_valid
        CHECK (to_state IN ('open', 'acknowledged', 'investigating', 'resolved', 'dismissed'))
);

CREATE INDEX IF NOT EXISTS alert_transitions_alert_idx
    ON alert_transitions (alert_key, occurred_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- Suppressions
--
-- Mutable in exactly one direction: a suppression may be revoked, which sets
-- `revoked_at`. It is never edited and never deleted, so the record of what was
-- hidden, by whom, and for how long survives the decision to stop hiding it.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alert_suppressions (
    suppression_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    rule_id         TEXT,
    subject_ref     TEXT,

    reason_code     TEXT NOT NULL,
    note            TEXT NOT NULL,

    created_by      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,

    revoked_at      TIMESTAMPTZ,
    revoked_by      TEXT,

    -- No wildcard. A suppression naming neither a rule nor a subject would
    -- match every firing, which is an off switch for detection wearing the
    -- clothes of triage.
    CONSTRAINT alert_suppressions_has_scope
        CHECK (rule_id IS NOT NULL OR subject_ref IS NOT NULL),
    CONSTRAINT alert_suppressions_expires_after_creation
        CHECK (expires_at > created_at),
    CONSTRAINT alert_suppressions_revocation_complete
        CHECK ((revoked_at IS NULL) = (revoked_by IS NULL))
);

CREATE INDEX IF NOT EXISTS alert_suppressions_active_idx
    ON alert_suppressions (expires_at DESC) WHERE revoked_at IS NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- Evaluations — how well the rule set does against ground truth it never saw.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alert_evaluations (
    evaluation_id       BIGSERIAL PRIMARY KEY,
    run_id              BIGINT NOT NULL REFERENCES alert_runs(run_id),
    rules_fingerprint   TEXT NOT NULL,

    alerts_total        INTEGER NOT NULL,
    subjects_alerted    INTEGER NOT NULL,

    precision_strict    NUMERIC(6,4),
    recall              NUMERIC(6,4),
    per_rule            JSONB NOT NULL DEFAULT '{}'::jsonb,
    unreachable         JSONB NOT NULL DEFAULT '{}'::jsonb,

    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ─────────────────────────────────────────────────────────────────────────────
-- Views: the queue as an analyst sees it, and the group roll-up.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW alert_queue AS
    SELECT a.*,
           g.basis    AS group_basis,
           g.subjects AS group_subjects,
           g.summary  AS group_summary
    FROM alerts a
    LEFT JOIN alert_groups g ON g.group_key = a.group_key
    WHERE a.state NOT IN ('resolved', 'dismissed')
      AND NOT a.suppressed;

CREATE OR REPLACE VIEW alert_group_rollup AS
    SELECT g.group_key,
           g.basis,
           g.subjects,
           g.summary,
           count(a.alert_key)                                        AS alert_count,
           count(a.alert_key) FILTER (WHERE a.state = 'open')        AS open_count,
           count(a.alert_key) FILTER (WHERE a.suppressed)            AS suppressed_count,
           max(a.priority)                                           AS top_priority,
           max(a.last_seen_at)                                       AS last_seen_at,
           array_agg(DISTINCT a.rule_id)                             AS rule_ids
    FROM alert_groups g
    LEFT JOIN alerts a ON a.group_key = g.group_key
    GROUP BY g.group_key, g.basis, g.subjects, g.summary;


-- ─────────────────────────────────────────────────────────────────────────────
-- Append-only enforcement on the history tables.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION alerting_append_only() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not permitted', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS alert_occurrences_no_update ON alert_occurrences;
CREATE TRIGGER alert_occurrences_no_update
    BEFORE UPDATE ON alert_occurrences
    FOR EACH ROW EXECUTE FUNCTION alerting_append_only();

DROP TRIGGER IF EXISTS alert_transitions_no_update ON alert_transitions;
CREATE TRIGGER alert_transitions_no_update
    BEFORE UPDATE ON alert_transitions
    FOR EACH ROW EXECUTE FUNCTION alerting_append_only();

DROP TRIGGER IF EXISTS alert_transitions_no_delete ON alert_transitions;
CREATE TRIGGER alert_transitions_no_delete
    BEFORE DELETE ON alert_transitions
    FOR EACH ROW EXECUTE FUNCTION alerting_append_only();

DROP TRIGGER IF EXISTS alert_evaluations_no_update ON alert_evaluations;
CREATE TRIGGER alert_evaluations_no_update
    BEFORE UPDATE ON alert_evaluations
    FOR EACH ROW EXECUTE FUNCTION alerting_append_only();

DROP TRIGGER IF EXISTS alert_evaluations_no_delete ON alert_evaluations;
CREATE TRIGGER alert_evaluations_no_delete
    BEFORE DELETE ON alert_evaluations
    FOR EACH ROW EXECUTE FUNCTION alerting_append_only();


-- ─────────────────────────────────────────────────────────────────────────────
-- Least privilege
--
-- `alerts` is the one table in this schema the application may UPDATE, because
-- state changes are its purpose. It may not DELETE one: an alert that turned
-- out to be wrong is dismissed with a reason, which is a record, rather than
-- removed, which is not.
-- ─────────────────────────────────────────────────────────────────────────────

GRANT SELECT, INSERT, UPDATE ON alert_runs TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE alert_runs_run_id_seq TO argus_app;

GRANT SELECT, INSERT, UPDATE ON alerts TO argus_app;
GRANT SELECT, INSERT, UPDATE ON alert_groups TO argus_app;

GRANT SELECT, INSERT ON alert_occurrences TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE alert_occurrences_occurrence_id_seq TO argus_app;

GRANT SELECT, INSERT ON alert_transitions TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE alert_transitions_transition_id_seq TO argus_app;

-- UPDATE, not DELETE: revoking a suppression sets revoked_at.
GRANT SELECT, INSERT, UPDATE ON alert_suppressions TO argus_app;

GRANT SELECT, INSERT ON alert_evaluations TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE alert_evaluations_evaluation_id_seq TO argus_app;

GRANT SELECT ON alert_queue TO argus_app;
GRANT SELECT ON alert_group_rollup TO argus_app;
