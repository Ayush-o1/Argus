-- Migration 006: ARGUS's own risk assessment — runs, scored subjects, the
-- signals behind each score, and the measurement of the model that produced it.
--
-- The organising decision of this phase is in the schema, as it was in 005:
--
--   **An assessment is a dated claim by a named model, not a property of the
--   subject.**
--
-- Nothing here writes to an entity. There is no `risk_score` column, and the
-- generator's own number is left untouched on the graph node where provenance
-- can keep showing it for what it is — a synthetic source's inference, rated
-- F6. What ARGUS believes is a row in `assessments` stamped with the
-- fingerprint of the model that produced it, and a re-run appends a new row
-- rather than editing the old one. The history is the record; the `argus_*`
-- properties on the graph nodes are a cache that can be dropped and rebuilt.
--
-- The consequence worth stating: two assessments of the same subject that
-- disagree are not a conflict to be resolved. They are the same model seeing
-- different evidence at different times, or two different models, and both are
-- kept so that "why did this change?" has an answer.


-- ─────────────────────────────────────────────────────────────────────────────
-- Runs
--
-- A run records what was assessed, under which model, and what the population
-- looked like afterwards. `model_fingerprint` covers every threshold and the
-- whole signal registry, so a precision figure published against one run can
-- never be re-attributed to a model whose weights moved.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS assessment_runs (
    run_id             BIGSERIAL PRIMARY KEY,

    model_version      TEXT NOT NULL,
    model_fingerprint  TEXT NOT NULL,

    status             TEXT NOT NULL DEFAULT 'running',
    started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at        TIMESTAMPTZ,

    subjects_assessed  INTEGER NOT NULL DEFAULT 0,
    elevated_count     INTEGER NOT NULL DEFAULT 0,
    notable_count      INTEGER NOT NULL DEFAULT 0,
    routine_count      INTEGER NOT NULL DEFAULT 0,
    insufficient_count INTEGER NOT NULL DEFAULT 0,

    -- What the evidence sweep actually managed to see. A run that found fewer
    -- transfers than the last one produced different scores for a reason that
    -- has nothing to do with the subjects, and without this the difference is
    -- invisible.
    evidence_summary   JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- True when the funds-cycle search hit its path limit. A truncated search
    -- has under-reported, so every `routine` band in that run is weaker than it
    -- looks, and a reader is entitled to know.
    search_truncated   BOOLEAN NOT NULL DEFAULT false,

    triggered_by       TEXT NOT NULL,
    error              TEXT,

    CONSTRAINT assessment_runs_status CHECK (status IN ('running', 'complete', 'failed'))
);

CREATE INDEX IF NOT EXISTS assessment_runs_started_idx ON assessment_runs (started_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- Assessments
--
-- Append-only history. `score` is nullable *and that is load-bearing*: a
-- subject ARGUS could not assess has no score, and storing 0 would let it sort
-- alongside subjects that were examined and found unremarkable. The band says
-- `insufficient_evidence` and the score is NULL, so every query has to decide
-- what to do about it rather than being silently handed a number.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS assessments (
    assessment_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id             BIGINT NOT NULL REFERENCES assessment_runs(run_id),

    subject_ref        TEXT NOT NULL,
    subject_type       TEXT NOT NULL,

    band               TEXT NOT NULL,
    score              NUMERIC(5,2),

    -- The denominator. `evidence_coverage` is the share of the model's weight
    -- that could be evaluated for this subject, and it travels with the score
    -- everywhere it is displayed.
    evidence_coverage  NUMERIC(6,4) NOT NULL,
    evaluable_weight   NUMERIC(8,2) NOT NULL,
    total_weight       NUMERIC(8,2) NOT NULL,

    families_fired     TEXT[] NOT NULL DEFAULT '{}',

    model_version      TEXT NOT NULL,
    model_fingerprint  TEXT NOT NULL,
    computed_at        TIMESTAMPTZ NOT NULL,

    CONSTRAINT assessments_band CHECK (
        band IN ('elevated', 'notable', 'routine', 'insufficient_evidence')
    ),
    -- The two halves of the same rule, stated where it cannot be forgotten:
    -- an unassessable subject has no score, and an assessable one has one.
    CONSTRAINT assessments_score_matches_band CHECK (
        (band = 'insufficient_evidence' AND score IS NULL)
        OR (band <> 'insufficient_evidence' AND score IS NOT NULL)
    ),
    CONSTRAINT assessments_coverage_range CHECK (evidence_coverage BETWEEN 0 AND 1)
);

CREATE INDEX IF NOT EXISTS assessments_subject_idx
    ON assessments (subject_ref, computed_at DESC);
CREATE INDEX IF NOT EXISTS assessments_run_idx ON assessments (run_id);
CREATE INDEX IF NOT EXISTS assessments_band_idx ON assessments (band, score DESC);


-- One row per signal per assessment: the model's working, kept.
--
-- `evaluable` is separate from `magnitude` on purpose. A signal that was
-- evaluated and found nothing has magnitude 0; a signal that could not be
-- evaluated has magnitude NULL. Collapsing the two would erase the distinction
-- between "we looked and it was clean" and "we could not look", which is the
-- distinction this whole phase exists to preserve.
CREATE TABLE IF NOT EXISTS assessment_signals (
    assessment_id  UUID NOT NULL REFERENCES assessments(assessment_id) ON DELETE CASCADE,
    signal_id      TEXT NOT NULL,
    family         TEXT NOT NULL,
    weight         NUMERIC(6,2) NOT NULL,
    evaluable      BOOLEAN NOT NULL,
    magnitude      NUMERIC(6,4),
    contribution   NUMERIC(8,4) NOT NULL DEFAULT 0,
    summary        TEXT NOT NULL,
    detail         JSONB NOT NULL DEFAULT '{}'::jsonb,

    PRIMARY KEY (assessment_id, signal_id),
    CONSTRAINT assessment_signals_magnitude CHECK (
        (evaluable AND magnitude IS NOT NULL) OR (NOT evaluable AND magnitude IS NULL)
    )
);


-- The current assessment per subject: the newest row, and nothing else.
--
-- A view rather than a maintained table, so it cannot drift from the history it
-- summarises. DISTINCT ON is Postgres's cheapest form of "latest per group" and
-- uses the (subject_ref, computed_at DESC) index directly.
CREATE OR REPLACE VIEW assessment_current AS
SELECT DISTINCT ON (subject_ref) *
  FROM assessments
 ORDER BY subject_ref, computed_at DESC, assessment_id;


-- ─────────────────────────────────────────────────────────────────────────────
-- Evaluation
--
-- Precision and recall against the generator's planted storylines, stored
-- against the fingerprint of the model measured. Kept in its own table rather
-- than on the run, because a model can be re-measured against a different
-- dataset without being re-run.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS assessment_evaluations (
    evaluation_id      BIGSERIAL PRIMARY KEY,
    run_id             BIGINT REFERENCES assessment_runs(run_id),
    model_version      TEXT NOT NULL,
    model_fingerprint  TEXT NOT NULL,
    generated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- The whole report, including the per-storyline breakdown and the caveats.
    -- Stored whole so a figure can never be quoted without the text that
    -- qualifies it.
    report             JSONB NOT NULL,

    triggered_by       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS assessment_evaluations_model_idx
    ON assessment_evaluations (model_fingerprint, generated_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- Immutability
--
-- Same reasoning as 001, 003 and 005: enforced by the database, so it holds
-- even when the caller is the application. An assessment is a dated claim, and
-- a claim that can be edited after the fact is not a record of what was
-- believed — it is a record of what someone would prefer to have believed.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION assessment_append_only() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not permitted', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS assessments_no_update ON assessments;
CREATE TRIGGER assessments_no_update
    BEFORE UPDATE ON assessments
    FOR EACH ROW EXECUTE FUNCTION assessment_append_only();

DROP TRIGGER IF EXISTS assessments_no_delete ON assessments;
CREATE TRIGGER assessments_no_delete
    BEFORE DELETE ON assessments
    FOR EACH ROW EXECUTE FUNCTION assessment_append_only();

DROP TRIGGER IF EXISTS assessments_no_truncate ON assessments;
CREATE TRIGGER assessments_no_truncate
    BEFORE TRUNCATE ON assessments
    FOR EACH STATEMENT EXECUTE FUNCTION assessment_append_only();

DROP TRIGGER IF EXISTS assessment_signals_no_update ON assessment_signals;
CREATE TRIGGER assessment_signals_no_update
    BEFORE UPDATE ON assessment_signals
    FOR EACH ROW EXECUTE FUNCTION assessment_append_only();

DROP TRIGGER IF EXISTS assessment_evaluations_no_update ON assessment_evaluations;
CREATE TRIGGER assessment_evaluations_no_update
    BEFORE UPDATE ON assessment_evaluations
    FOR EACH ROW EXECUTE FUNCTION assessment_append_only();

DROP TRIGGER IF EXISTS assessment_evaluations_no_delete ON assessment_evaluations;
CREATE TRIGGER assessment_evaluations_no_delete
    BEFORE DELETE ON assessment_evaluations
    FOR EACH ROW EXECUTE FUNCTION assessment_append_only();


-- ─────────────────────────────────────────────────────────────────────────────
-- Least privilege
--
-- The application inserts assessments and reads them. It cannot update or
-- delete one — the triggers above refuse anyway, but the grant means the
-- attempt never reaches them. `assessment_signals` is deliberately granted
-- DELETE: the ON DELETE CASCADE from `assessments` needs it, and since
-- `assessments` rows can never be deleted, the cascade can never fire.
-- ─────────────────────────────────────────────────────────────────────────────

GRANT SELECT, INSERT, UPDATE ON assessment_runs TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE assessment_runs_run_id_seq TO argus_app;

GRANT SELECT, INSERT ON assessments TO argus_app;
GRANT SELECT, INSERT, DELETE ON assessment_signals TO argus_app;
GRANT SELECT ON assessment_current TO argus_app;

GRANT SELECT, INSERT ON assessment_evaluations TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE assessment_evaluations_evaluation_id_seq TO argus_app;
