-- Migration 005: entity resolution — candidates, decisions, clusters, and the
-- labelled set the matcher is measured against.
--
-- The organising decision of this phase is here in the schema rather than in
-- the code:
--
--   **A merge is a claim about two records, not an edit to either of them.**
--
-- Nothing in this migration can modify or delete an entity. There is no
-- "merged_into" column on a node, no tombstone, no surviving-record pointer.
-- A merge is a row in `resolution_decisions` saying two refs denote the same
-- thing, and un-merging is another row saying they do not. Both source records
-- are untouched throughout, which is what makes every merge reversible without
-- a restore — the acceptance criterion "a merge never destroys either source
-- record" is a property of the data model, not of careful coding.
--
-- The cluster tables are a *derived projection* of those decisions and can be
-- dropped and rebuilt at any time. The decision ledger is the record; the
-- clusters are a cache of what it currently implies.


-- ─────────────────────────────────────────────────────────────────────────────
-- Matcher runs
--
-- A run is scored under an exact model configuration, and that configuration's
-- fingerprint is stamped on every candidate it produced. Without it, an
-- evaluation report published today could be silently re-attributed to a model
-- whose weights changed next week.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS resolution_runs (
    run_id             BIGSERIAL PRIMARY KEY,
    entity_types       TEXT[] NOT NULL,
    model_version      TEXT NOT NULL,
    model_fingerprint  TEXT NOT NULL,

    status             TEXT NOT NULL DEFAULT 'running',
    started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at        TIMESTAMPTZ,

    profiles_examined  INTEGER NOT NULL DEFAULT 0,
    pairs_scored       INTEGER NOT NULL DEFAULT 0,
    auto_count         INTEGER NOT NULL DEFAULT 0,
    review_count       INTEGER NOT NULL DEFAULT 0,
    insufficient_count INTEGER NOT NULL DEFAULT 0,
    reject_count       INTEGER NOT NULL DEFAULT 0,

    -- Blocking's own failure modes: how many records no key could place, and
    -- which keys matched so many records they stopped discriminating. Kept
    -- because a silent loss of recall is the one error in this pipeline that
    -- leaves no trace anywhere else.
    blocking_report    JSONB NOT NULL DEFAULT '{}'::jsonb,

    triggered_by       TEXT NOT NULL,
    error              TEXT,

    CONSTRAINT resolution_runs_status CHECK (status IN ('running', 'complete', 'failed'))
);

CREATE INDEX IF NOT EXISTS resolution_runs_started_idx ON resolution_runs (started_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- Candidates — a scored pair, with the whole comparison kept
--
-- `comparisons` holds every attribute the model looked at, including the ones
-- it could not compare. Storing only the ones that agreed would produce a
-- review screen that argues for the merge and never against it.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS resolution_candidates (
    candidate_id      BIGSERIAL PRIMARY KEY,
    run_id            BIGINT REFERENCES resolution_runs(run_id),

    entity_type       TEXT NOT NULL,
    left_ref          TEXT NOT NULL,
    right_ref         TEXT NOT NULL,

    -- Nullable on purpose: a pair with no comparable attribute has no score,
    -- and 0.0 would say "definitely different" when the truth is "no idea".
    score             DOUBLE PRECISION,
    -- The denominator for `score` — the share of the model's total weight that
    -- was actually comparable. Never displayed apart from the score.
    evidence_weight   DOUBLE PRECISION NOT NULL,

    band              TEXT NOT NULL,
    band_reason       TEXT NOT NULL,
    comparisons       JSONB NOT NULL,
    blocking_keys     TEXT[] NOT NULL DEFAULT '{}',

    model_version     TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,

    status            TEXT NOT NULL DEFAULT 'open',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Set when a later, complete run no longer produces this pair at all —
    -- usually because a scoring or blocking change means the two records are
    -- no longer considered comparable.
    --
    -- Without this the queue keeps showing pairs scored under a model that no
    -- longer exists, and an analyst reviews a comparison the current matcher
    -- would never make. Withdrawn rather than deleted: "ARGUS used to think
    -- these might be the same and no longer does" is worth keeping.
    withdrawn_at      TIMESTAMPTZ,
    withdrawn_reason  TEXT,

    -- One row per pair. Canonical ordering is enforced rather than assumed:
    -- without it (A,B) and (B,A) become two candidates, two review items, and
    -- eventually two contradicting decisions with nothing to notice.
    CONSTRAINT resolution_candidates_ordered CHECK (left_ref < right_ref),
    CONSTRAINT resolution_candidates_band
        CHECK (band IN ('auto', 'review', 'insufficient', 'reject')),
    CONSTRAINT resolution_candidates_status
        CHECK (status IN ('open', 'decided', 'withdrawn')),
    CONSTRAINT resolution_candidates_withdrawn_complete
        CHECK ((status <> 'withdrawn' AND withdrawn_at IS NULL AND withdrawn_reason IS NULL)
               OR (status = 'withdrawn' AND withdrawn_at IS NOT NULL
                   AND withdrawn_reason IS NOT NULL)),
    CONSTRAINT resolution_candidates_evidence
        CHECK (evidence_weight >= 0 AND evidence_weight <= 1),
    CONSTRAINT resolution_candidates_score
        CHECK (score IS NULL OR (score >= 0 AND score <= 1)),
    CONSTRAINT resolution_candidates_pair UNIQUE (left_ref, right_ref)
);

-- The review queue's own index: open candidates in the review band, worst
-- (most uncertain) first is not what an analyst wants — highest score first
-- clears the easy ones and shortens the queue fastest.
CREATE INDEX IF NOT EXISTS resolution_candidates_queue_idx
    ON resolution_candidates (band, status, score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS resolution_candidates_left_idx ON resolution_candidates (left_ref);
CREATE INDEX IF NOT EXISTS resolution_candidates_right_idx ON resolution_candidates (right_ref);


-- ─────────────────────────────────────────────────────────────────────────────
-- The blocking index
--
-- Which coarse keys each record falls under, written by every matcher run.
--
-- Batch matching does not need this — it blocks in memory over the population
-- it just loaded. It exists for the *single-record* path: when a feed delivers
-- a record whose subject does not resolve to a known entity, ARGUS has to ask
-- "is this anyone we already have?" without scoring it against every person in
-- the graph. One indexed lookup per blocking key answers that.
--
-- Derived state, rebuilt by each run, and therefore freely deletable.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS resolution_blocking_index (
    ref         TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    block_key   TEXT NOT NULL,
    indexed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ref, block_key)
);

CREATE INDEX IF NOT EXISTS resolution_blocking_key_idx
    ON resolution_blocking_index (block_key);


-- ─────────────────────────────────────────────────────────────────────────────
-- Decisions — the ledger, append-only
--
-- There is no `active` column and no `superseded_at`. The current decision for
-- a pair is simply the one with the highest `decision_id`, so reversing a
-- merge is an INSERT and nothing is ever rewritten. A schema in which the
-- current state is derived cannot drift from its own history.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS resolution_decisions (
    decision_id       BIGSERIAL PRIMARY KEY,

    entity_type       TEXT NOT NULL,
    left_ref          TEXT NOT NULL,
    right_ref         TEXT NOT NULL,

    verdict           TEXT NOT NULL,

    -- Who decided, and in what capacity. A matcher decision names the model
    -- fingerprint, so "the machine merged these" is attributable to an exact
    -- configuration rather than to "the system".
    decided_by        TEXT NOT NULL,
    decided_by_kind   TEXT NOT NULL,
    decided_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Required, not optional. A merge with no stated reason is not reviewable,
    -- and every path that writes here has something true to say.
    rationale         TEXT NOT NULL,

    -- What the pair scored at the moment of the decision, so a later model
    -- change does not rewrite the basis on which a person acted.
    score             DOUBLE PRECISION,
    evidence_weight   DOUBLE PRECISION,
    model_version     TEXT,
    model_fingerprint TEXT,
    candidate_id      BIGINT REFERENCES resolution_candidates(candidate_id),

    -- Set when this decision undoes an earlier one. The earlier row stays
    -- exactly as it was: the history of a contested identity is often the most
    -- informative thing about it.
    reverses_decision_id BIGINT REFERENCES resolution_decisions(decision_id),

    CONSTRAINT resolution_decisions_ordered CHECK (left_ref < right_ref),
    CONSTRAINT resolution_decisions_verdict CHECK (verdict IN ('same', 'different')),
    CONSTRAINT resolution_decisions_kind CHECK (decided_by_kind IN ('analyst', 'matcher')),
    CONSTRAINT resolution_decisions_rationale CHECK (length(btrim(rationale)) > 0)
);

CREATE INDEX IF NOT EXISTS resolution_decisions_pair_idx
    ON resolution_decisions (left_ref, right_ref, decision_id DESC);
CREATE INDEX IF NOT EXISTS resolution_decisions_at_idx
    ON resolution_decisions (decided_at DESC);

-- The current decision for every pair, derived rather than stored.
CREATE OR REPLACE VIEW resolution_current_decisions AS
SELECT DISTINCT ON (left_ref, right_ref) *
  FROM resolution_decisions
 ORDER BY left_ref, right_ref, decision_id DESC;


-- ─────────────────────────────────────────────────────────────────────────────
-- Clusters — a derived projection, safe to drop and rebuild
--
-- Connected components over the currently-active `same` decisions. Transitive
-- closure is what makes A~B and B~C imply one entity, and it is also how a
-- single bad merge can pull in records that were never compared — so a
-- component containing a pair explicitly judged `different` is marked
-- **contested** and left for a person, never auto-resolved.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS resolution_clusters (
    cluster_key       TEXT PRIMARY KEY,
    entity_type       TEXT NOT NULL,
    canonical_ref     TEXT NOT NULL,
    canonical_basis   TEXT NOT NULL,
    member_count      INTEGER NOT NULL,
    contested         BOOLEAN NOT NULL DEFAULT FALSE,
    contested_reason  TEXT,
    rebuilt_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT resolution_clusters_contested_complete
        CHECK ((contested = FALSE AND contested_reason IS NULL)
               OR (contested = TRUE AND contested_reason IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS resolution_cluster_members (
    ref          TEXT PRIMARY KEY,
    cluster_key  TEXT NOT NULL REFERENCES resolution_clusters(cluster_key) ON DELETE CASCADE,
    entity_type  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS resolution_cluster_members_key_idx
    ON resolution_cluster_members (cluster_key);

-- An analyst's choice of which record represents a cluster. Pinned by ref
-- rather than by cluster, because cluster identity changes as members join and
-- leave while the analyst's judgement about the record does not.
CREATE TABLE IF NOT EXISTS resolution_canonical_pins (
    ref        TEXT PRIMARY KEY,
    pinned_by  TEXT NOT NULL,
    pinned_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason     TEXT NOT NULL
);


-- ─────────────────────────────────────────────────────────────────────────────
-- The labelled set, and the measurements taken against it
--
-- Labels are append-only for the same reason audit events are: a precision
-- figure computed against a set that can be quietly edited is not a
-- measurement, it is a claim.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS resolution_labels (
    label_id     BIGSERIAL PRIMARY KEY,
    entity_type  TEXT NOT NULL,
    left_ref     TEXT NOT NULL,
    right_ref    TEXT NOT NULL,
    is_same      BOOLEAN NOT NULL,

    -- 'analyst'  — a real decision made in the review queue, which is the only
    --              label that reflects the population ARGUS actually sees.
    -- 'synthetic'— a constructed pair whose truth is known because it was
    --              built, used to measure recall on corruptions the live data
    --              does not yet contain enough of.
    origin       TEXT NOT NULL,
    note         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT resolution_labels_ordered CHECK (left_ref < right_ref),
    CONSTRAINT resolution_labels_origin CHECK (origin IN ('analyst', 'synthetic')),
    CONSTRAINT resolution_labels_pair UNIQUE (left_ref, right_ref, origin)
);

CREATE TABLE IF NOT EXISTS resolution_evaluations (
    evaluation_id     BIGSERIAL PRIMARY KEY,
    model_version     TEXT NOT NULL,
    model_fingerprint TEXT NOT NULL,
    dataset           TEXT NOT NULL,
    ran_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Counts and rates per band, plus the confusion matrix. Kept as JSON
    -- because the useful shape of a calibration report changes faster than a
    -- schema should.
    metrics           JSONB NOT NULL,
    notes             TEXT
);

CREATE INDEX IF NOT EXISTS resolution_evaluations_ran_idx ON resolution_evaluations (ran_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- Ingestion gains a resolve stage
--
-- Phase 3's pipeline validated that a subject id had a *recognised prefix* and
-- called that resolution. It is not: `PRS-9999999` passes a prefix check and
-- names nobody, so observations were landing against entities ARGUS does not
-- hold, silently, with no dead-letter entry and no error.
--
-- Subject existence is now checked against the graph, and a record that cannot
-- be resolved dead-letters at a stage of its own — distinguishable from a
-- mapping failure, because the fix is completely different: a mapping failure
-- means the connector is wrong, an unresolved subject means ARGUS has never
-- heard of who the record is about.
--
-- Widened rather than replaced, so every existing dead-letter entry keeps its
-- stage and stays valid.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE ingest_failures DROP CONSTRAINT IF EXISTS failure_stage_valid;
ALTER TABLE ingest_failures ADD CONSTRAINT failure_stage_valid
    CHECK (stage IN ('fetch', 'validate', 'normalize', 'resolve', 'persist'));


-- ─────────────────────────────────────────────────────────────────────────────
-- Immutability
--
-- Reuses provenance_append_only() from migration 003: the same guarantee, the
-- same error, enforced for every role including superuser.
-- ─────────────────────────────────────────────────────────────────────────────

DROP TRIGGER IF EXISTS resolution_decisions_no_update ON resolution_decisions;
CREATE TRIGGER resolution_decisions_no_update
    BEFORE UPDATE ON resolution_decisions
    FOR EACH ROW EXECUTE FUNCTION provenance_append_only();

DROP TRIGGER IF EXISTS resolution_decisions_no_delete ON resolution_decisions;
CREATE TRIGGER resolution_decisions_no_delete
    BEFORE DELETE ON resolution_decisions
    FOR EACH ROW EXECUTE FUNCTION provenance_append_only();

DROP TRIGGER IF EXISTS resolution_decisions_no_truncate ON resolution_decisions;
CREATE TRIGGER resolution_decisions_no_truncate
    BEFORE TRUNCATE ON resolution_decisions
    FOR EACH STATEMENT EXECUTE FUNCTION provenance_append_only();

DROP TRIGGER IF EXISTS resolution_labels_no_update ON resolution_labels;
CREATE TRIGGER resolution_labels_no_update
    BEFORE UPDATE ON resolution_labels
    FOR EACH ROW EXECUTE FUNCTION provenance_append_only();

DROP TRIGGER IF EXISTS resolution_labels_no_delete ON resolution_labels;
CREATE TRIGGER resolution_labels_no_delete
    BEFORE DELETE ON resolution_labels
    FOR EACH ROW EXECUTE FUNCTION provenance_append_only();

DROP TRIGGER IF EXISTS resolution_labels_no_truncate ON resolution_labels;
CREATE TRIGGER resolution_labels_no_truncate
    BEFORE TRUNCATE ON resolution_labels
    FOR EACH STATEMENT EXECUTE FUNCTION provenance_append_only();

DROP TRIGGER IF EXISTS resolution_evaluations_no_update ON resolution_evaluations;
CREATE TRIGGER resolution_evaluations_no_update
    BEFORE UPDATE ON resolution_evaluations
    FOR EACH ROW EXECUTE FUNCTION provenance_append_only();

DROP TRIGGER IF EXISTS resolution_evaluations_no_delete ON resolution_evaluations;
CREATE TRIGGER resolution_evaluations_no_delete
    BEFORE DELETE ON resolution_evaluations
    FOR EACH ROW EXECUTE FUNCTION provenance_append_only();


-- ─────────────────────────────────────────────────────────────────────────────
-- Grants
-- ─────────────────────────────────────────────────────────────────────────────

-- Runs and candidates are working state: scored, re-scored, and closed as they
-- are decided. Candidates are never deleted — a rejected pair is a record that
-- ARGUS considered and declined, which is worth as much as one it merged.
GRANT SELECT, INSERT, UPDATE ON resolution_runs TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE resolution_runs_run_id_seq TO argus_app;
GRANT SELECT, INSERT, UPDATE ON resolution_candidates TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE resolution_candidates_candidate_id_seq TO argus_app;

-- The ledger: append and read, never rewrite.
GRANT SELECT, INSERT ON resolution_decisions TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE resolution_decisions_decision_id_seq TO argus_app;
GRANT SELECT ON resolution_current_decisions TO argus_app;

GRANT SELECT, INSERT ON resolution_labels TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE resolution_labels_label_id_seq TO argus_app;
GRANT SELECT, INSERT ON resolution_evaluations TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE resolution_evaluations_evaluation_id_seq TO argus_app;

-- Clusters are derived. DELETE is granted precisely because they are a cache
-- rebuilt from the ledger, and nothing is lost by discarding them.
GRANT SELECT, INSERT, UPDATE, DELETE ON resolution_clusters TO argus_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON resolution_cluster_members TO argus_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON resolution_canonical_pins TO argus_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON resolution_blocking_index TO argus_app;
