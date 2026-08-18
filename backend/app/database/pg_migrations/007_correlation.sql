-- Migration 007: correlation — discovered links between ARGUS's own findings,
-- the dimensions behind each link, the clusters they form, and the measurement
-- of the model that produced them.
--
-- The organising decision, as in 005 and 006, is in the schema:
--
--   **A link is a dated claim about a pair, not an edge in the world.**
--
-- Nothing here writes a relationship into the graph. A correlation is a row
-- stamped with the fingerprint of the model that produced it, and a re-run
-- appends new rows rather than editing old ones. The consequence worth stating:
-- two runs that disagree about a pair are not a conflict to be resolved. They
-- are the same model seeing more evidence, or two different models, and both are
-- kept so "why did this link appear?" has an answer.
--
-- The `argus_cluster` properties written onto graph nodes are a cache of the
-- cluster tables here, and `rebuild_projection` proves it by clearing them and
-- rebuilding.


-- ─────────────────────────────────────────────────────────────────────────────
-- Runs
--
-- `candidate_pairs` and `pairs_scored` are separate on purpose. The first is how
-- many pairs blocking proposed, the second how many survived to be scored. A run
-- where those diverge sharply has been shaped more by its blocking than by its
-- dimensions, and without both numbers that is invisible.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS correlation_runs (
    run_id             BIGSERIAL PRIMARY KEY,

    model_version      TEXT NOT NULL,
    model_fingerprint  TEXT NOT NULL,

    -- The assessment run these findings were correlated from. Correlation
    -- operates on assessments, so a link is only interpretable against the
    -- generation of assessments that produced its anchors.
    assessment_run_id  BIGINT REFERENCES assessment_runs(run_id),

    status             TEXT NOT NULL DEFAULT 'running',
    started_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at        TIMESTAMPTZ,

    anchors            INTEGER NOT NULL DEFAULT 0,
    candidate_pairs    INTEGER NOT NULL DEFAULT 0,
    pairs_scored       INTEGER NOT NULL DEFAULT 0,
    links_recorded     INTEGER NOT NULL DEFAULT 0,
    clusters_found     INTEGER NOT NULL DEFAULT 0,

    -- Keys whose fan-out exceeded the cap and therefore generated no pairs.
    -- Recorded because "we did not look there" is a fact about the result, and
    -- a link count with no note attached reads as exhaustive.
    keys_skipped       INTEGER NOT NULL DEFAULT 0,

    -- True when any reachability search hit its frontier limit. A truncated
    -- search has under-reported, so an absent funds path in that run is weaker
    -- evidence of absence than it looks.
    search_truncated   BOOLEAN NOT NULL DEFAULT false,

    evidence_summary   JSONB NOT NULL DEFAULT '{}'::jsonb,

    triggered_by       TEXT NOT NULL,
    error              TEXT,

    CONSTRAINT correlation_runs_status CHECK (status IN ('running', 'complete', 'failed'))
);

CREATE INDEX IF NOT EXISTS correlation_runs_started_idx ON correlation_runs (started_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- Links
--
-- `ref_a < ref_b` is enforced rather than assumed. A pair stored in both orders
-- would be two links to every reader that joins on one side, and the duplicate
-- would quietly double every count on this page.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS correlation_links (
    link_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id             BIGINT NOT NULL REFERENCES correlation_runs(run_id),

    ref_a              TEXT NOT NULL,
    ref_b              TEXT NOT NULL,
    type_a             TEXT NOT NULL,
    type_b             TEXT NOT NULL,

    strength           NUMERIC(6,4) NOT NULL,
    tier               TEXT NOT NULL,

    -- Share of the dimensions applicable to this pair that could be evaluated.
    -- Travels with the strength everywhere it is shown, for the same reason
    -- evidence coverage travels with an assessment score: a link found on two
    -- of eight dimensions has not been examined, it has been glanced at.
    coverage           NUMERIC(6,4) NOT NULL,
    evaluable_dimensions  INTEGER NOT NULL,
    applicable_dimensions INTEGER NOT NULL,

    -- Families scoring at or above the corroboration floor. The *count* of
    -- these, not the strength, is what separates `established` from `probable`.
    corroborating_families TEXT[] NOT NULL DEFAULT '{}',

    model_version      TEXT NOT NULL,
    model_fingerprint  TEXT NOT NULL,
    computed_at        TIMESTAMPTZ NOT NULL,

    CONSTRAINT correlation_links_tier CHECK (tier IN ('established', 'probable', 'possible')),
    CONSTRAINT correlation_links_strength_range CHECK (strength BETWEEN 0 AND 1),
    CONSTRAINT correlation_links_coverage_range CHECK (coverage BETWEEN 0 AND 1),
    CONSTRAINT correlation_links_ordered CHECK (ref_a < ref_b)
);

CREATE INDEX IF NOT EXISTS correlation_links_run_idx ON correlation_links (run_id, strength DESC);
CREATE INDEX IF NOT EXISTS correlation_links_a_idx ON correlation_links (ref_a, computed_at DESC);
CREATE INDEX IF NOT EXISTS correlation_links_b_idx ON correlation_links (ref_b, computed_at DESC);


-- One row per dimension per link: the model's working, kept.
--
-- `evaluable` is separate from `magnitude` for the reason it is separate in
-- `assessment_signals`. A dimension evaluated and found empty has magnitude 0;
-- one that could not be evaluated has magnitude NULL. Collapsing them erases the
-- difference between "they were not near each other" and "we could not tell",
-- and the second must never be displayed as the first.
CREATE TABLE IF NOT EXISTS correlation_link_dimensions (
    link_id        UUID NOT NULL REFERENCES correlation_links(link_id) ON DELETE CASCADE,
    dimension_id   TEXT NOT NULL,
    family         TEXT NOT NULL,
    evaluable      BOOLEAN NOT NULL,
    magnitude      NUMERIC(6,4),
    contribution   NUMERIC(6,4) NOT NULL DEFAULT 0,
    summary        TEXT NOT NULL,
    evidence       JSONB NOT NULL DEFAULT '{}'::jsonb,

    PRIMARY KEY (link_id, dimension_id),
    CONSTRAINT correlation_dimensions_magnitude CHECK (
        (evaluable AND magnitude IS NOT NULL) OR (NOT evaluable AND magnitude IS NULL)
    )
);


-- ─────────────────────────────────────────────────────────────────────────────
-- Clusters
--
-- Deliberately not `ThreatActor` or `Campaign` (audit gap G-31). Both of those
-- assert something ARGUS has no evidence for: a campaign asserts a plan, a
-- threat actor asserts a someone. What was measured is a group of findings
-- joined by structure that can be named, and that is what the table stores. An
-- analyst who concludes a cluster is a campaign records that judgement in
-- Phase 9, attributed to them, which is where a claim about intent belongs.
--
-- `cluster_key` is derived from the sorted membership rather than minted, so the
-- same group keeps the same key across runs and can be followed over time — and
-- a group that gains a member gets a different key, because it is a different
-- group and pretending otherwise would rewrite the history of what was claimed.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS correlation_clusters (
    cluster_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id             BIGINT NOT NULL REFERENCES correlation_runs(run_id),

    cluster_key        TEXT NOT NULL,
    size               INTEGER NOT NULL,
    families           TEXT[] NOT NULL DEFAULT '{}',

    mean_strength      NUMERIC(6,4) NOT NULL,
    min_strength       NUMERIC(6,4) NOT NULL,

    -- The strength of the weakest link whose removal would split the group.
    -- NULL when no such link exists, which means every member is held by at
    -- least two independent routes — a materially stronger claim than a group
    -- of the same size hanging off one `possible` link.
    weakest_bridge     NUMERIC(6,4),
    bridge_count       INTEGER NOT NULL DEFAULT 0,

    -- A component larger than the model's ceiling is published as an over-merge
    -- rather than as a discovery. Connected components collapse without warning
    -- in a dense graph, and a 900-member cluster is a threshold set too low.
    over_merged        BOOLEAN NOT NULL DEFAULT false,

    basis              TEXT NOT NULL,

    model_version      TEXT NOT NULL,
    model_fingerprint  TEXT NOT NULL,
    computed_at        TIMESTAMPTZ NOT NULL,

    CONSTRAINT correlation_clusters_size CHECK (size >= 2)
);

CREATE INDEX IF NOT EXISTS correlation_clusters_run_idx
    ON correlation_clusters (run_id, size DESC);
CREATE INDEX IF NOT EXISTS correlation_clusters_key_idx
    ON correlation_clusters (cluster_key, computed_at DESC);


CREATE TABLE IF NOT EXISTS correlation_cluster_members (
    cluster_id     UUID NOT NULL REFERENCES correlation_clusters(cluster_id) ON DELETE CASCADE,
    subject_ref    TEXT NOT NULL,
    subject_type   TEXT NOT NULL,
    band           TEXT NOT NULL,
    score          NUMERIC(5,2),

    -- Links inside the cluster touching this member. A member joined by one
    -- weak link sits at the edge of the group rather than at its centre, and
    -- that difference matters to whoever reads it.
    degree         INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (cluster_id, subject_ref)
);

CREATE INDEX IF NOT EXISTS correlation_cluster_members_subject_idx
    ON correlation_cluster_members (subject_ref);


-- The newest run that completed, and the links and clusters belonging to it.
-- Views rather than maintained tables, so they cannot drift from the history
-- they summarise.
CREATE OR REPLACE VIEW correlation_latest_run AS
SELECT * FROM correlation_runs
 WHERE status = 'complete'
 ORDER BY finished_at DESC NULLS LAST, run_id DESC
 LIMIT 1;

CREATE OR REPLACE VIEW correlation_current_links AS
SELECT l.* FROM correlation_links l
  JOIN correlation_latest_run r ON r.run_id = l.run_id;

CREATE OR REPLACE VIEW correlation_current_clusters AS
SELECT c.* FROM correlation_clusters c
  JOIN correlation_latest_run r ON r.run_id = c.run_id;


-- ─────────────────────────────────────────────────────────────────────────────
-- Evaluation
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS correlation_evaluations (
    evaluation_id      BIGSERIAL PRIMARY KEY,
    run_id             BIGINT REFERENCES correlation_runs(run_id),
    model_version      TEXT NOT NULL,
    model_fingerprint  TEXT NOT NULL,
    generated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- The whole report, including the per-storyline breakdown and the caveats.
    -- Stored whole so a precision figure can never be quoted without the text
    -- that qualifies it — which here includes the fact that an unlabelled link
    -- is not a wrong link.
    report             JSONB NOT NULL,

    triggered_by       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS correlation_evaluations_model_idx
    ON correlation_evaluations (model_fingerprint, generated_at DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- Immutability
--
-- Same reasoning as 001, 003, 005 and 006: enforced by the database, so it holds
-- even when the caller is the application.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION correlation_append_only() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not permitted', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS correlation_links_no_update ON correlation_links;
CREATE TRIGGER correlation_links_no_update
    BEFORE UPDATE ON correlation_links
    FOR EACH ROW EXECUTE FUNCTION correlation_append_only();

DROP TRIGGER IF EXISTS correlation_links_no_delete ON correlation_links;
CREATE TRIGGER correlation_links_no_delete
    BEFORE DELETE ON correlation_links
    FOR EACH ROW EXECUTE FUNCTION correlation_append_only();

DROP TRIGGER IF EXISTS correlation_link_dimensions_no_update ON correlation_link_dimensions;
CREATE TRIGGER correlation_link_dimensions_no_update
    BEFORE UPDATE ON correlation_link_dimensions
    FOR EACH ROW EXECUTE FUNCTION correlation_append_only();

DROP TRIGGER IF EXISTS correlation_clusters_no_update ON correlation_clusters;
CREATE TRIGGER correlation_clusters_no_update
    BEFORE UPDATE ON correlation_clusters
    FOR EACH ROW EXECUTE FUNCTION correlation_append_only();

DROP TRIGGER IF EXISTS correlation_clusters_no_delete ON correlation_clusters;
CREATE TRIGGER correlation_clusters_no_delete
    BEFORE DELETE ON correlation_clusters
    FOR EACH ROW EXECUTE FUNCTION correlation_append_only();

DROP TRIGGER IF EXISTS correlation_evaluations_no_update ON correlation_evaluations;
CREATE TRIGGER correlation_evaluations_no_update
    BEFORE UPDATE ON correlation_evaluations
    FOR EACH ROW EXECUTE FUNCTION correlation_append_only();

DROP TRIGGER IF EXISTS correlation_evaluations_no_delete ON correlation_evaluations;
CREATE TRIGGER correlation_evaluations_no_delete
    BEFORE DELETE ON correlation_evaluations
    FOR EACH ROW EXECUTE FUNCTION correlation_append_only();


-- ─────────────────────────────────────────────────────────────────────────────
-- Least privilege
--
-- The application inserts and reads. It cannot update or delete a link or a
-- cluster — the triggers refuse anyway, but the grant means the attempt never
-- reaches them. The two child tables are granted DELETE only so their
-- ON DELETE CASCADE is valid; since no parent row can ever be deleted, the
-- cascade can never fire.
-- ─────────────────────────────────────────────────────────────────────────────

GRANT SELECT, INSERT, UPDATE ON correlation_runs TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE correlation_runs_run_id_seq TO argus_app;

GRANT SELECT, INSERT ON correlation_links TO argus_app;
GRANT SELECT, INSERT, DELETE ON correlation_link_dimensions TO argus_app;

GRANT SELECT, INSERT ON correlation_clusters TO argus_app;
GRANT SELECT, INSERT, DELETE ON correlation_cluster_members TO argus_app;

GRANT SELECT ON correlation_latest_run TO argus_app;
GRANT SELECT ON correlation_current_links TO argus_app;
GRANT SELECT ON correlation_current_clusters TO argus_app;

GRANT SELECT, INSERT ON correlation_evaluations TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE correlation_evaluations_evaluation_id_seq TO argus_app;
