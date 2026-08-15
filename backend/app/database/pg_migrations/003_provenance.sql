-- Migration 003: the provenance layer — sources, observations and assertions.
--
-- This is the schema that lets ARGUS answer "why do you believe this?".
--
-- Why PostgreSQL and not the graph
-- ────────────────────────────────
-- The audit set a bar for new infrastructure: prove the existing stack cannot
-- do it. This adds no new technology, and it needs the one property Postgres
-- has that Neo4j Community does not: enforced immutability. An observation is
-- a record of what a source said. If it can be edited after the fact, it is not
-- evidence of anything — and Neo4j Community has no per-label privilege model,
-- so any process holding write credentials (which ARGUS must) could rewrite it.
--
-- The access pattern also fits: provenance is queried by subject, predicate and
-- time — relational lookups, not traversals. The graph stays authoritative for
-- entities and the relationships between them. Nothing about the intelligence
-- model moves.
--
-- The four kinds of knowing
-- ─────────────────────────
-- ARGUS previously stored an observation ("a transaction occurred"), a source
-- claim ("this feed says X controls Y"), a derivation ("the algorithm linked
-- these") and a judgement ("an analyst considers this significant") as the same
-- kind of graph fact, and rendered them identically. An analyst could not tell
-- which they were looking at. `epistemic_kind` on every assertion makes the
-- distinction structural, and the API refuses to emit an assertion without it.


-- ─────────────────────────────────────────────────────────────────────────────
-- Sources
--
-- Every observation has exactly one source, and a source is a first-class
-- record with a stated reliability. That includes ARGUS's own scenario
-- generator: it is registered as a synthetic source so that generator-authored
-- ground truth can never be silently mistaken for discovered intelligence.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sources (
    source_id       TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    description     TEXT NOT NULL,

    -- Admiralty Code (NATO STANAG 2511) reliability: A completely reliable
    -- through F reliability cannot be judged. Stored as the letter, never a
    -- number, because a number invites arithmetic on an ordinal scale.
    reliability     CHAR(1) NOT NULL,
    -- Why this rating. A rating with no stated basis is an opinion wearing a
    -- letter, so it is required rather than nullable.
    reliability_basis TEXT NOT NULL,

    -- THE flag. True means this source fabricates its content: it is not a
    -- report about the world, and nothing derived from it is evidence of
    -- anything outside ARGUS. Carried through every API response so the UI can
    -- mark it, rather than the UI hardcoding which data is demo data.
    is_synthetic    BOOLEAN NOT NULL,

    -- Corroboration counts independent sources, and two feeds reprinting one
    -- wire service are one source. Sources sharing an independence_group are
    -- treated as one voice. Defaults to the source's own id — independent until
    -- someone states otherwise.
    independence_group TEXT NOT NULL,

    -- How long data from this source stays current, in hours. Displayed as an
    -- age against this threshold rather than silently decayed into a score:
    -- an analyst must be able to see that a basis is six months old.
    staleness_hours INTEGER,

    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT sources_reliability_valid CHECK (reliability IN ('A','B','C','D','E','F')),
    CONSTRAINT sources_type_valid CHECK (
        source_type IN ('synthetic', 'human', 'system', 'osint', 'partner', 'sensor')
    ),
    CONSTRAINT sources_staleness_positive CHECK (staleness_hours IS NULL OR staleness_hours > 0)
);

CREATE INDEX IF NOT EXISTS sources_group_idx ON sources (independence_group);


-- ─────────────────────────────────────────────────────────────────────────────
-- Observations — layer 1, immutable
--
-- What a source said, when it said it, and what it said about. Append-only:
-- observations are never edited or deleted. A correction is a new observation
-- that supersedes the prior one, so the fact that ARGUS once believed something
-- different survives the correction.
--
-- Three timestamps, deliberately (bitemporality):
--   occurred_at  — when the thing happened in the world
--   collected_at — when the source collected it
--   recorded_at  — when ARGUS learned it
-- Only the third is knowable in every case, so only the third is NOT NULL.
-- Defaulting the other two to now() would manufacture a fact, which is the
-- failure mode this entire layer exists to prevent.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS observations (
    seq             BIGSERIAL PRIMARY KEY,
    observation_id  UUID NOT NULL UNIQUE,
    source_id       TEXT NOT NULL REFERENCES sources(source_id),

    content_type    TEXT NOT NULL,
    payload         JSONB NOT NULL,
    -- SHA-256 over the canonical (sorted-key, separator-fixed) payload. With
    -- the uniqueness constraint below this makes ingestion idempotent: the same
    -- payload from the same source twice yields one observation, not two.
    content_hash    TEXT NOT NULL,

    occurred_at     TIMESTAMPTZ,
    collected_at    TIMESTAMPTZ,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- A correction points at what it replaces. The superseded row stays.
    supersedes      UUID REFERENCES observations(observation_id),

    -- Free-text note about how this record came to exist, used to mark records
    -- reconstructed after the fact rather than captured at ingest.
    provenance_note TEXT,

    CONSTRAINT observations_hash_shape CHECK (char_length(content_hash) = 64),
    CONSTRAINT observations_unique_content UNIQUE (source_id, content_hash)
);

CREATE INDEX IF NOT EXISTS observations_source_idx ON observations (source_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS observations_recorded_idx ON observations (recorded_at DESC);
CREATE INDEX IF NOT EXISTS observations_occurred_idx ON observations (occurred_at DESC)
    WHERE occurred_at IS NOT NULL;


-- What each observation is about. An observation can concern several entities
-- (a transaction concerns two accounts), so this is a separate table rather
-- than a column.
CREATE TABLE IF NOT EXISTS observation_subjects (
    observation_id  UUID NOT NULL REFERENCES observations(observation_id),
    subject_ref     TEXT NOT NULL,   -- graph human id, e.g. 'PRS-0002001'
    subject_type    TEXT NOT NULL,   -- graph label, e.g. 'Person'
    subject_role    TEXT NOT NULL DEFAULT 'primary',

    PRIMARY KEY (observation_id, subject_ref)
);

CREATE INDEX IF NOT EXISTS observation_subjects_ref_idx ON observation_subjects (subject_ref);


-- ─────────────────────────────────────────────────────────────────────────────
-- Assertions — layer 2, versioned
--
-- What ARGUS or an analyst *believes*, and on what basis. Distinct from an
-- observation: an observation is what was said, an assertion is what is
-- concluded from it.
--
-- Reliability and credibility are two independent axes and are never combined.
-- "Confidence 0.62" cannot tell an analyst whether that is one excellent source
-- or four poor ones, and those demand different actions. There is deliberately
-- no column, view or function in this schema that averages them.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS assertions (
    seq             BIGSERIAL PRIMARY KEY,
    assertion_id    UUID NOT NULL UNIQUE,

    -- Subject–predicate–object. Two assertions with the same subject and
    -- predicate but different objects are a conflict, and the query that finds
    -- them returns both without choosing.
    subject_ref     TEXT NOT NULL,
    subject_type    TEXT NOT NULL,
    predicate       TEXT NOT NULL,
    object_value    JSONB NOT NULL,

    epistemic_kind  TEXT NOT NULL,

    reliability     CHAR(1) NOT NULL,  -- A–F, of the source or the method
    credibility     CHAR(1) NOT NULL,  -- 1–6, of this specific claim

    -- How the belief was formed: 'source-report', 'analyst-judgement', or a
    -- versioned model identifier such as 'generator.risk_scorer@v1'. Required,
    -- so an assertion can always state how it came to exist.
    method          TEXT NOT NULL,
    -- Who or what asserted it: 'user:<uuid>' or 'source:<source_id>'.
    asserted_by     TEXT NOT NULL,
    asserted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- The period the claim is about, distinct from when it was asserted.
    valid_from      TIMESTAMPTZ,
    valid_until     TIMESTAMPTZ,

    -- Lifecycle terminators. Set once, never cleared — enforced by trigger.
    superseded_by   UUID REFERENCES assertions(assertion_id),
    superseded_at   TIMESTAMPTZ,
    retracted_at    TIMESTAMPTZ,
    retracted_by    TEXT,
    retraction_reason TEXT,

    note            TEXT,

    CONSTRAINT assertions_kind_valid CHECK (
        epistemic_kind IN ('observed', 'reported', 'inferred', 'assessed')
    ),
    CONSTRAINT assertions_reliability_valid CHECK (reliability IN ('A','B','C','D','E','F')),
    CONSTRAINT assertions_credibility_valid CHECK (credibility IN ('1','2','3','4','5','6')),
    -- A retraction without a reason is an unexplained disappearance of a
    -- belief, which is exactly what an investigation cannot afford.
    CONSTRAINT assertions_retraction_complete CHECK (
        (retracted_at IS NULL AND retracted_by IS NULL AND retraction_reason IS NULL)
        OR (retracted_at IS NOT NULL AND retracted_by IS NOT NULL AND retraction_reason IS NOT NULL)
    ),
    CONSTRAINT assertions_supersession_complete CHECK (
        (superseded_by IS NULL AND superseded_at IS NULL)
        OR (superseded_by IS NOT NULL AND superseded_at IS NOT NULL)
    ),
    CONSTRAINT assertions_validity_ordered CHECK (
        valid_from IS NULL OR valid_until IS NULL OR valid_until >= valid_from
    )
);

CREATE INDEX IF NOT EXISTS assertions_subject_idx ON assertions (subject_ref, predicate);
CREATE INDEX IF NOT EXISTS assertions_current_idx ON assertions (subject_ref)
    WHERE retracted_at IS NULL AND superseded_at IS NULL;
CREATE INDEX IF NOT EXISTS assertions_asserted_idx ON assertions (asserted_at DESC);
CREATE INDEX IF NOT EXISTS assertions_kind_idx ON assertions (epistemic_kind, subject_ref);


-- The evidence behind an assertion, and — just as importantly — the evidence
-- against it. An assertion whose contradicting evidence was discarded looks
-- better supported than it is.
CREATE TABLE IF NOT EXISTS assertion_evidence (
    assertion_id    UUID NOT NULL REFERENCES assertions(assertion_id),
    observation_id  UUID NOT NULL REFERENCES observations(observation_id),
    stance          TEXT NOT NULL,

    PRIMARY KEY (assertion_id, observation_id),
    CONSTRAINT assertion_evidence_stance_valid CHECK (stance IN ('supports', 'contradicts'))
);

CREATE INDEX IF NOT EXISTS assertion_evidence_obs_idx ON assertion_evidence (observation_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- Immutability
--
-- Same reasoning as audit_events in migration 001: enforced by the database,
-- not by application code, so it holds even when the caller is the application.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION provenance_append_only() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not permitted', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS observations_no_update ON observations;
CREATE TRIGGER observations_no_update
    BEFORE UPDATE ON observations
    FOR EACH ROW EXECUTE FUNCTION provenance_append_only();

DROP TRIGGER IF EXISTS observations_no_delete ON observations;
CREATE TRIGGER observations_no_delete
    BEFORE DELETE ON observations
    FOR EACH ROW EXECUTE FUNCTION provenance_append_only();

DROP TRIGGER IF EXISTS observations_no_truncate ON observations;
CREATE TRIGGER observations_no_truncate
    BEFORE TRUNCATE ON observations
    FOR EACH STATEMENT EXECUTE FUNCTION provenance_append_only();

DROP TRIGGER IF EXISTS observation_subjects_no_update ON observation_subjects;
CREATE TRIGGER observation_subjects_no_update
    BEFORE UPDATE ON observation_subjects
    FOR EACH ROW EXECUTE FUNCTION provenance_append_only();

DROP TRIGGER IF EXISTS observation_subjects_no_delete ON observation_subjects;
CREATE TRIGGER observation_subjects_no_delete
    BEFORE DELETE ON observation_subjects
    FOR EACH ROW EXECUTE FUNCTION provenance_append_only();

DROP TRIGGER IF EXISTS assertion_evidence_no_update ON assertion_evidence;
CREATE TRIGGER assertion_evidence_no_update
    BEFORE UPDATE ON assertion_evidence
    FOR EACH ROW EXECUTE FUNCTION provenance_append_only();

DROP TRIGGER IF EXISTS assertion_evidence_no_delete ON assertion_evidence;
CREATE TRIGGER assertion_evidence_no_delete
    BEFORE DELETE ON assertion_evidence
    FOR EACH ROW EXECUTE FUNCTION provenance_append_only();


-- Assertions are a narrower case. Their *content* is immutable, but a belief
-- must be able to end: it can be superseded by a newer one or retracted. So
-- UPDATE is permitted for exactly those four columns, only in the direction
-- NULL → set, and never back. Everything else raises.
--
-- Written as an explicit column-by-column comparison rather than a blanket
-- `OLD IS DISTINCT FROM NEW` check, because a new column added later must fail
-- closed: it will not appear in this list, so changing it will be rejected
-- until someone deliberately decides otherwise.
CREATE OR REPLACE FUNCTION assertions_content_immutable() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.assertion_id   IS DISTINCT FROM OLD.assertion_id
       OR NEW.seq         IS DISTINCT FROM OLD.seq
       OR NEW.subject_ref IS DISTINCT FROM OLD.subject_ref
       OR NEW.subject_type IS DISTINCT FROM OLD.subject_type
       OR NEW.predicate   IS DISTINCT FROM OLD.predicate
       OR NEW.object_value IS DISTINCT FROM OLD.object_value
       OR NEW.epistemic_kind IS DISTINCT FROM OLD.epistemic_kind
       OR NEW.reliability IS DISTINCT FROM OLD.reliability
       OR NEW.credibility IS DISTINCT FROM OLD.credibility
       OR NEW.method      IS DISTINCT FROM OLD.method
       OR NEW.asserted_by IS DISTINCT FROM OLD.asserted_by
       OR NEW.asserted_at IS DISTINCT FROM OLD.asserted_at
       OR NEW.valid_from  IS DISTINCT FROM OLD.valid_from
       OR NEW.valid_until IS DISTINCT FROM OLD.valid_until
       OR NEW.note        IS DISTINCT FROM OLD.note
    THEN
        RAISE EXCEPTION 'assertion content is immutable; supersede it instead'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF OLD.retracted_at IS NOT NULL AND NEW.retracted_at IS DISTINCT FROM OLD.retracted_at THEN
        RAISE EXCEPTION 'a retraction cannot be altered or reversed'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF OLD.superseded_at IS NOT NULL AND NEW.superseded_at IS DISTINCT FROM OLD.superseded_at THEN
        RAISE EXCEPTION 'a supersession cannot be altered or reversed'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS assertions_immutable_content ON assertions;
CREATE TRIGGER assertions_immutable_content
    BEFORE UPDATE ON assertions
    FOR EACH ROW EXECUTE FUNCTION assertions_content_immutable();

DROP TRIGGER IF EXISTS assertions_no_delete ON assertions;
CREATE TRIGGER assertions_no_delete
    BEFORE DELETE ON assertions
    FOR EACH ROW EXECUTE FUNCTION provenance_append_only();

DROP TRIGGER IF EXISTS assertions_no_truncate ON assertions;
CREATE TRIGGER assertions_no_truncate
    BEFORE TRUNCATE ON assertions
    FOR EACH STATEMENT EXECUTE FUNCTION provenance_append_only();


-- ─────────────────────────────────────────────────────────────────────────────
-- Grants
--
-- The application inserts and reads. It never updates or deletes provenance,
-- with the single exception of ending an assertion's life, which the trigger
-- above constrains to four columns in one direction.
-- ─────────────────────────────────────────────────────────────────────────────

GRANT SELECT, INSERT ON sources TO argus_app;
GRANT SELECT, INSERT ON observations TO argus_app;
GRANT SELECT, INSERT ON observation_subjects TO argus_app;
GRANT SELECT, INSERT ON assertion_evidence TO argus_app;
GRANT SELECT, INSERT, UPDATE ON assertions TO argus_app;

GRANT USAGE, SELECT ON SEQUENCE observations_seq_seq TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE assertions_seq_seq TO argus_app;
