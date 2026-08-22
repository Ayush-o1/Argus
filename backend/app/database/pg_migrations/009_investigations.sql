-- Migration 009: investigations — what a human concluded, and how they got there.
--
-- Phases 5 to 8 built things ARGUS believes. Phase 7 built a queue of things it
-- wants looked at. Nothing until now recorded what a person decided, which
-- means nothing has ever measured whether any of it was right.
--
-- The one field this whole schema exists for
-- ─────────────────────────────────────────
-- `outcome`. Every other column here is supporting structure. An investigation
-- that closes without one is the failure this migration is built to make
-- impossible, so it is a CHECK constraint rather than a validation in a route:
--
--     CHECK (state <> 'closed' OR outcome IS NOT NULL)
--
-- Calibration (the next phase) has exactly one input, and it is this column
-- joined to the alerts that started the investigation. Phase 7's dismissal
-- vocabulary covers alerts nobody worked; this covers the ones somebody did.
--
-- Why this is not a second object above `Case`
-- ────────────────────────────────────────────
-- The audit proposed an `Investigation` between alert and case, with the case
-- retained beneath it. Building both would double the surface and add no
-- property: an object with a hypothesis, findings, evidence, an assignee, a
-- history and an outcome *is* a case. There is one object here, and it is this.
--
-- What happens to the `Case` nodes already in the graph
-- ────────────────────────────────────────────────────
-- Nothing is deleted. All twenty of them were written by the scenario generator
-- from its own storylines — titled after the storyline, noted "Auto-seeded
-- from storyline STL-…", linked to exactly the entity list the storyline
-- planted, and assigned to one of five invented analyst names. They are records
-- from a synthetic source, and they are relabelled as such, which is the same
-- treatment Phase 7 gave `Incident`. What they are not is analyst work, and
-- nothing in this schema reads them.
--
-- Why PostgreSQL
-- ──────────────
-- The same reason as 003 and 008, and it is stronger here than anywhere: the
-- history of an investigation has to be tamper-evident to be worth keeping, and
-- Neo4j Community has no per-label privilege model — any process with write
-- credentials can rewrite a node. `investigation_events` is append-only by
-- trigger, so the record holds even against the application itself.


-- ─────────────────────────────────────────────────────────────────────────────
-- Reference vocabularies
--
-- Both are enforced by CHECK rather than by an application enum, for the reason
-- Phase 7 gave: a value that only application code validates is one direct
-- write away from being unmeasurable, and these two columns are the entire
-- input to calibration.
-- ─────────────────────────────────────────────────────────────────────────────

-- Outcomes. The four the audit named, and they are not interchangeable:
--
--   confirmed     the hypothesis held up
--   unfounded     it did not — there was nothing there
--   inconclusive  the evidence available could not settle it either way
--   referred      handed to someone else with the authority to act
--
-- `inconclusive` is the one that matters most and is easiest to get wrong. It
-- is NOT a soft `unfounded`: an investigation that could not be settled says
-- something about the evidence, not about the alert that started it, and
-- counting it against a rule's precision would punish detectors for gaps in
-- collection. Calibration reads `counts_as_correct` (below) rather than
-- inferring from the label.

-- ─────────────────────────────────────────────────────────────────────────────
-- Investigations
--
-- Mutable current row, complete append-only history beside it — the shape
-- Phase 8's alerting schema established, and for the same reason: an analyst
-- has to be able to read the current state without folding an event log, and a
-- reviewer has to be able to reconstruct any past state without trusting the
-- current row.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE SEQUENCE IF NOT EXISTS investigation_ref_seq;

CREATE TABLE IF NOT EXISTS investigations (
    investigation_id    UUID PRIMARY KEY,

    -- Human-facing identifier. Allocated from a sequence rather than by the
    -- read-then-write the Neo4j case id used, which needed a lock on a counter
    -- node and a self-healing reconciliation against the highest existing id to
    -- survive concurrent creates (audit B-02, B-22). A sequence is atomic,
    -- monotonic and gapless enough, and needs neither.
    inv_ref             TEXT NOT NULL UNIQUE,

    title               TEXT NOT NULL,

    -- What the analyst thinks is happening. Required at creation: an
    -- investigation without a stated hypothesis cannot be confirmed or found
    -- unfounded, because there is no proposition to test — and an outcome
    -- recorded against no hypothesis is not a measurement of anything.
    hypothesis          TEXT NOT NULL,

    -- How strongly, on an analytic-confidence scale (see app/investigation/
    -- outcomes.py). Deliberately NOT the Admiralty code the provenance layer
    -- uses: Admiralty rates a *source* and the credibility of a *report*, and
    -- an analyst's own hypothesis is neither. Reusing the letters would put an
    -- analytic judgement and a source rating in the same units, which is
    -- exactly the conflation `epistemic_kind` was added in 003 to prevent.
    confidence          TEXT NOT NULL,
    -- Why that level and not the one above or below it. A confidence with no
    -- stated basis is a number wearing a word.
    confidence_basis    TEXT NOT NULL,

    state               TEXT NOT NULL DEFAULT 'open',

    opened_by           TEXT NOT NULL,
    opened_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    assigned_to         TEXT,

    -- The point of the schema. Null until closure, required at closure.
    outcome             TEXT,
    -- What the outcome rests on, in the analyst's words. Required with the
    -- outcome for the same reason `reliability_basis` is required in 003: a
    -- verdict whose reasoning was never written down cannot be reviewed, and
    -- an investigation nobody can review is not evidence of anything.
    outcome_rationale   TEXT,
    closed_by           TEXT,
    closed_at           TIMESTAMPTZ,

    -- Reviews are NOT columns here. See `investigation_reviews` below; the
    -- first draft of this migration put four review columns on this row and a
    -- live walkthrough showed why that was wrong within minutes.

    CONSTRAINT investigations_state_valid
        CHECK (state IN ('open', 'active', 'closed')),

    CONSTRAINT investigations_confidence_valid
        CHECK (confidence IN ('low', 'moderate', 'high')),

    CONSTRAINT investigations_outcome_valid
        CHECK (outcome IS NULL OR outcome IN ('confirmed', 'unfounded', 'inconclusive', 'referred')),

    -- THE constraint. Everything else in this file is in service of it.
    CONSTRAINT investigations_closed_has_outcome
        CHECK (state <> 'closed' OR outcome IS NOT NULL),

    -- And an outcome is never recorded without its reasoning.
    CONSTRAINT investigations_outcome_has_rationale
        CHECK ((outcome IS NULL) = (outcome_rationale IS NULL)),

    -- `closed_at` is written by a code path, asserted by a test, and tied to
    -- the state by the database. The audit found the Neo4j equivalent declared
    -- on every case and written by nothing, so a case could be Closed and still
    -- answer "never" to when.
    CONSTRAINT investigations_closed_at_iff_closed
        CHECK ((state = 'closed') = (closed_at IS NOT NULL AND closed_by IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS investigations_state_idx ON investigations (state, opened_at DESC);
CREATE INDEX IF NOT EXISTS investigations_assigned_idx ON investigations (assigned_to)
    WHERE state <> 'closed';
CREATE INDEX IF NOT EXISTS investigations_outcome_idx ON investigations (outcome)
    WHERE outcome IS NOT NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- History
--
-- The acceptance criterion for this phase is that an investigation's full
-- history is reconstructable at any past point. That is a property of this
-- table, and `app/investigation/history.py` implements the replay against it —
-- with a test asserting that replaying to now() reproduces the current row
-- exactly, so the log cannot silently drift from what it claims to explain.
--
-- Every mutation of `investigations` writes one row here per changed field,
-- carrying both the old and the new value. Old values are stored rather than
-- inferred from the previous event because inference breaks the moment a field
-- is written outside this path, and a history that is wrong in exactly the
-- cases someone bypassed the application is worse than none.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS investigation_events (
    event_id            BIGSERIAL PRIMARY KEY,
    investigation_id    UUID NOT NULL REFERENCES investigations(investigation_id),

    event_type          TEXT NOT NULL,

    -- Set for `field_changed`; null for events that are not a field write
    -- (an alert attaching, a finding being recorded).
    field               TEXT,
    old_value           JSONB,
    new_value           JSONB,

    -- Free text from the actor. Not a substitute for a controlled vocabulary
    -- anywhere one exists — outcomes and dismissals have theirs — but a state
    -- change usually has a reason worth writing down that no vocabulary covers.
    note                TEXT,

    -- Attribution is not nullable anywhere in this schema. An investigation
    -- record with an anonymous change in it is not a record.
    actor_username      TEXT NOT NULL,
    actor_role          TEXT NOT NULL,
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT investigation_events_type_valid CHECK (
        event_type IN (
            'opened', 'field_changed', 'alert_attached', 'alert_detached',
            'entity_linked', 'entity_unlinked', 'finding_recorded',
            'finding_withdrawn', 'action_recorded', 'action_completed',
            'assessment_recorded', 'closed', 'reopened', 'reviewed'
        )
    ),
    CONSTRAINT investigation_events_field_change_complete CHECK (
        event_type <> 'field_changed' OR field IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS investigation_events_replay_idx
    ON investigation_events (investigation_id, occurred_at, event_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- What the investigation is about
-- ─────────────────────────────────────────────────────────────────────────────

-- The alerts escalated into it. This is the join calibration reads: an alert
-- that led to a `confirmed` investigation is a different signal about its rule
-- than one that led to `unfounded`, and neither is recoverable from the alert
-- alone.
CREATE TABLE IF NOT EXISTS investigation_alerts (
    link_id             BIGSERIAL PRIMARY KEY,
    investigation_id    UUID NOT NULL REFERENCES investigations(investigation_id),
    alert_key           TEXT NOT NULL REFERENCES alerts(alert_key),

    attached_by         TEXT NOT NULL,
    attached_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    attach_reason       TEXT NOT NULL DEFAULT '',

    -- Detaching is a tombstone, never a delete (audit G-11). That an alert was
    -- once thought to belong to this investigation — and who decided it did
    -- not — is part of how the conclusion was reached.
    detached_at         TIMESTAMPTZ,
    detached_by         TEXT,
    detach_reason       TEXT,

    CONSTRAINT investigation_alerts_detach_complete CHECK (
        (detached_at IS NULL AND detached_by IS NULL)
        OR (detached_at IS NOT NULL AND detached_by IS NOT NULL AND detach_reason IS NOT NULL)
    )
);

-- One live link per (investigation, alert); unlimited dead ones behind it.
--
-- The natural key is deliberately NOT the primary key. The Neo4j implementation
-- this replaces keyed the link by (case, entity) and re-attaching set
-- `removed_at = null` — which silently erased who had detached it and why, in
-- the very table G-11 added those columns to. Re-attaching here inserts a new
-- row, so every attach and detach survives, and this partial unique index is
-- what keeps "attached now" single-valued.
CREATE UNIQUE INDEX IF NOT EXISTS investigation_alerts_live_uniq
    ON investigation_alerts (investigation_id, alert_key) WHERE detached_at IS NULL;

CREATE INDEX IF NOT EXISTS investigation_alerts_by_alert_idx
    ON investigation_alerts (alert_key) WHERE detached_at IS NULL;
CREATE INDEX IF NOT EXISTS investigation_alerts_history_idx
    ON investigation_alerts (investigation_id, attached_at);


-- Entities the investigation touches. The relational equivalent of the
-- `LINKED_TO` edge, with the same tombstone discipline and one addition the
-- edge never had: `reason` is NOT NULL. An evidence link with no stated reason
-- is an assertion that two things are related, made by a named person, with no
-- recorded basis — which is precisely the kind of unexamined claim the
-- provenance layer exists to stop.
CREATE TABLE IF NOT EXISTS investigation_entities (
    link_id             BIGSERIAL PRIMARY KEY,
    investigation_id    UUID NOT NULL REFERENCES investigations(investigation_id),
    entity_ref          TEXT NOT NULL,
    entity_type         TEXT NOT NULL,

    reason              TEXT NOT NULL,
    linked_by           TEXT NOT NULL,
    linked_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    removed_at          TIMESTAMPTZ,
    removed_by          TEXT,
    removal_reason      TEXT,

    CONSTRAINT investigation_entities_reason_present CHECK (length(btrim(reason)) > 0),
    CONSTRAINT investigation_entities_removal_complete CHECK (
        (removed_at IS NULL AND removed_by IS NULL)
        OR (removed_at IS NOT NULL AND removed_by IS NOT NULL AND removal_reason IS NOT NULL)
    )
);

-- Same construction as investigation_alerts above, for the same reason:
-- re-linking evidence must not overwrite the record of it having been removed.
CREATE UNIQUE INDEX IF NOT EXISTS investigation_entities_live_uniq
    ON investigation_entities (investigation_id, entity_ref) WHERE removed_at IS NULL;

CREATE INDEX IF NOT EXISTS investigation_entities_by_entity_idx
    ON investigation_entities (entity_ref) WHERE removed_at IS NULL;
CREATE INDEX IF NOT EXISTS investigation_entities_history_idx
    ON investigation_entities (investigation_id, linked_at);


-- ─────────────────────────────────────────────────────────────────────────────
-- Findings
--
-- Attributed, timestamped, and each one citing what it rests on. Append-only:
-- a finding that turns out to be wrong is withdrawn with a reason or superseded
-- by a later one, and both versions stay. Editing a finding in place would let
-- the reasoning behind a conclusion be rewritten after the conclusion was
-- reached, which is the single most damaging thing that can happen to an
-- investigation record.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS investigation_findings (
    finding_id          UUID PRIMARY KEY,
    investigation_id    UUID NOT NULL REFERENCES investigations(investigation_id),

    statement           TEXT NOT NULL,
    confidence          TEXT NOT NULL,

    -- What this finding rests on: alert keys, entity references, observation
    -- ids — whatever the analyst is pointing at. Required and non-empty. A
    -- finding that cites nothing is an opinion, and an investigation built from
    -- uncited opinions cannot be reviewed by anyone who was not in the room.
    cites               TEXT[] NOT NULL,

    author_username     TEXT NOT NULL,
    author_role         TEXT NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Terminators, set once. `superseded_by` points at the finding that
    -- replaced this one, so the chain of how the analyst's understanding
    -- changed is walkable in both directions.
    superseded_by       UUID REFERENCES investigation_findings(finding_id),
    superseded_at       TIMESTAMPTZ,
    withdrawn_at        TIMESTAMPTZ,
    withdrawn_by        TEXT,
    withdrawal_reason   TEXT,

    CONSTRAINT investigation_findings_confidence_valid
        CHECK (confidence IN ('low', 'moderate', 'high')),
    CONSTRAINT investigation_findings_cites_present
        CHECK (cardinality(cites) > 0),
    CONSTRAINT investigation_findings_statement_present
        CHECK (length(btrim(statement)) > 0),
    CONSTRAINT investigation_findings_withdrawal_complete CHECK (
        (withdrawn_at IS NULL AND withdrawn_by IS NULL AND withdrawal_reason IS NULL)
        OR (withdrawn_at IS NOT NULL AND withdrawn_by IS NOT NULL AND withdrawal_reason IS NOT NULL)
    ),
    CONSTRAINT investigation_findings_supersession_complete CHECK (
        (superseded_by IS NULL AND superseded_at IS NULL)
        OR (superseded_by IS NOT NULL AND superseded_at IS NOT NULL)
    ),
    CONSTRAINT investigation_findings_no_self_supersede
        CHECK (superseded_by IS DISTINCT FROM finding_id)
);

CREATE INDEX IF NOT EXISTS investigation_findings_by_investigation_idx
    ON investigation_findings (investigation_id, recorded_at);
CREATE INDEX IF NOT EXISTS investigation_findings_standing_idx
    ON investigation_findings (investigation_id)
    WHERE withdrawn_at IS NULL AND superseded_at IS NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- Next actions
--
-- The audit asked for "tasks with assignment and due dates". This is that, and
-- it is deliberately smaller than a task system: no notifications, no
-- escalation, no recurrence, no scheduler. `due_at` is a date a person wrote
-- down, and the API reports an action as overdue by comparing it to the clock.
-- Nothing wakes up because of it.
--
-- Saying so is the point. A due date rendered in a UI implies something is
-- watching it, and building the implication without the mechanism would be a
-- worse outcome than not having the field.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS investigation_actions (
    action_id           UUID PRIMARY KEY,
    investigation_id    UUID NOT NULL REFERENCES investigations(investigation_id),

    description         TEXT NOT NULL,
    assigned_to         TEXT,
    due_at              TIMESTAMPTZ,

    recorded_by         TEXT NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    completed_at        TIMESTAMPTZ,
    completed_by        TEXT,
    completion_note     TEXT,

    CONSTRAINT investigation_actions_description_present
        CHECK (length(btrim(description)) > 0),
    CONSTRAINT investigation_actions_completion_complete CHECK (
        (completed_at IS NULL AND completed_by IS NULL)
        OR (completed_at IS NOT NULL AND completed_by IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS investigation_actions_open_idx
    ON investigation_actions (investigation_id) WHERE completed_at IS NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- Analyst assessments — the dissent record (audit G-15)
--
-- ARGUS assesses a subject and publishes a band. An analyst who has looked at
-- the same subject may reach a different conclusion. Before this table there
-- was nowhere to put that, so the only ways to express disagreement were to
-- ignore the machine or to change it.
--
-- The property this table exists to guarantee:
--
--     **An analyst's judgement never overwrites the machine's.**
--
-- Both stand, side by side, attributed. `assessment_current` is untouched by
-- anything here — there is no UPDATE, no trigger and no view in this migration
-- that writes to it. The assessment surface shows both and says who said which.
--
-- Why the machine's answer is copied in rather than only referenced
-- ────────────────────────────────────────────────────────────────
-- `machine_assessment_id` is a foreign key, but the band, fingerprint and time
-- are also stored flat. Assessment runs append: the next run publishes a new
-- row and `assessment_current` moves on. If only the id were kept, a dissent
-- would keep pointing at the right historical row — but "the analyst disagreed"
-- would silently become "the analyst agreed" the moment the model changed its
-- mind, because the comparison would be made against a different number than
-- the one on the analyst's screen. The snapshot freezes what was actually
-- disagreed with.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS analyst_assessments (
    analyst_assessment_id UUID PRIMARY KEY,

    subject_ref         TEXT NOT NULL,
    subject_type        TEXT NOT NULL,

    -- What the analyst concluded, in the same vocabulary the machine uses, so
    -- the two are directly comparable. `insufficient_evidence` is available to
    -- an analyst for the same reason it is available to the model: "I cannot
    -- tell" is a real conclusion and must not be forced into a band.
    analyst_band        TEXT NOT NULL,
    rationale           TEXT NOT NULL,
    confidence          TEXT NOT NULL,

    -- The machine's answer at the moment of dissent, frozen.
    machine_assessment_id UUID REFERENCES assessments(assessment_id),
    machine_band        TEXT,
    machine_fingerprint TEXT,
    machine_computed_at TIMESTAMPTZ,

    -- Generated, so it can never disagree with the two columns it summarises.
    -- Null when there was no machine assessment to differ from — an analyst
    -- assessing a subject ARGUS never assessed is not dissenting from anything.
    dissents            BOOLEAN GENERATED ALWAYS AS (
        CASE WHEN machine_band IS NULL THEN NULL ELSE analyst_band IS DISTINCT FROM machine_band END
    ) STORED,

    -- Where the judgement was formed, when it came out of case work. Nullable:
    -- an analyst may record a judgement about a subject without opening an
    -- investigation, and requiring one would suppress exactly the cheap
    -- disagreements that are most useful to calibration.
    investigation_id    UUID REFERENCES investigations(investigation_id),

    author_username     TEXT NOT NULL,
    author_role         TEXT NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    superseded_by       UUID REFERENCES analyst_assessments(analyst_assessment_id),
    superseded_at       TIMESTAMPTZ,
    withdrawn_at        TIMESTAMPTZ,
    withdrawn_by        TEXT,
    withdrawal_reason   TEXT,

    CONSTRAINT analyst_assessments_band_valid CHECK (
        analyst_band IN ('elevated', 'notable', 'routine', 'insufficient_evidence')
    ),
    CONSTRAINT analyst_assessments_machine_band_valid CHECK (
        machine_band IS NULL
        OR machine_band IN ('elevated', 'notable', 'routine', 'insufficient_evidence')
    ),
    CONSTRAINT analyst_assessments_confidence_valid
        CHECK (confidence IN ('low', 'moderate', 'high')),
    -- Disagreeing with a published machine assessment without saying why would
    -- leave the next analyst with two bands and no way to choose.
    CONSTRAINT analyst_assessments_rationale_present
        CHECK (length(btrim(rationale)) > 0),
    -- The snapshot is all-or-nothing: a machine band with no fingerprint cannot
    -- be traced back to the model that produced it.
    CONSTRAINT analyst_assessments_machine_snapshot_complete CHECK (
        (machine_assessment_id IS NULL AND machine_band IS NULL
         AND machine_fingerprint IS NULL AND machine_computed_at IS NULL)
        OR (machine_assessment_id IS NOT NULL AND machine_band IS NOT NULL
            AND machine_fingerprint IS NOT NULL AND machine_computed_at IS NOT NULL)
    ),
    CONSTRAINT analyst_assessments_withdrawal_complete CHECK (
        (withdrawn_at IS NULL AND withdrawn_by IS NULL AND withdrawal_reason IS NULL)
        OR (withdrawn_at IS NOT NULL AND withdrawn_by IS NOT NULL AND withdrawal_reason IS NOT NULL)
    ),
    CONSTRAINT analyst_assessments_supersession_complete CHECK (
        (superseded_by IS NULL AND superseded_at IS NULL)
        OR (superseded_by IS NOT NULL AND superseded_at IS NOT NULL)
    ),
    CONSTRAINT analyst_assessments_no_self_supersede
        CHECK (superseded_by IS DISTINCT FROM analyst_assessment_id)
);

CREATE INDEX IF NOT EXISTS analyst_assessments_subject_idx
    ON analyst_assessments (subject_ref, recorded_at DESC);
CREATE INDEX IF NOT EXISTS analyst_assessments_standing_idx
    ON analyst_assessments (subject_ref)
    WHERE withdrawn_at IS NULL AND superseded_at IS NULL;
CREATE INDEX IF NOT EXISTS analyst_assessments_dissent_idx
    ON analyst_assessments (subject_ref) WHERE dissents;


-- ─────────────────────────────────────────────────────────────────────────────
-- Reviews — independent judgement about a closed investigation
--
-- The first draft of this migration made this four columns on `investigations`,
-- reasoning that a review is one judgement about one investigation and that a
-- table with one row per parent is a column in disguise. Walking the API by
-- hand disproved that in two requests:
--
--   1. The analyst who closed the investigation reviewed their own conclusion.
--   2. A second review overwrote the first — a supervisor's recorded dissent,
--      with its note, was replaced by a later "concurs" and vanished.
--
-- The second is the same defect this schema exists to prevent, one level up:
-- `analyst_assessments` was built so a human's judgement could never overwrite
-- the machine's, and then the review columns let a human's judgement overwrite
-- another human's. A review is append-only for exactly the reason an assessment
-- is, and more than one person may hold a view.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS investigation_reviews (
    review_id           BIGSERIAL PRIMARY KEY,
    investigation_id    UUID NOT NULL REFERENCES investigations(investigation_id),

    reviewer            TEXT NOT NULL,
    reviewer_role       TEXT NOT NULL,
    concurs             BOOLEAN NOT NULL,
    note                TEXT,
    reviewed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- The outcome as it stood when this review was made. An investigation can
    -- be reopened and closed again with a different verdict; without this, an
    -- old review would appear to be commenting on the new one.
    outcome_reviewed    TEXT NOT NULL,

    -- Bare dissent is unactionable, and this is the row calibration will read
    -- hardest.
    CONSTRAINT investigation_reviews_dissent_has_note
        CHECK (concurs OR note IS NOT NULL),
    CONSTRAINT investigation_reviews_outcome_valid
        CHECK (outcome_reviewed IN ('confirmed', 'unfounded', 'inconclusive', 'referred'))
);

CREATE INDEX IF NOT EXISTS investigation_reviews_by_investigation_idx
    ON investigation_reviews (investigation_id, reviewed_at DESC);
CREATE INDEX IF NOT EXISTS investigation_reviews_dissenting_idx
    ON investigation_reviews (investigation_id) WHERE NOT concurs;

-- ─────────────────────────────────────────────────────────────────────────────
-- Immutability
--
-- Enforced by the database rather than by application code, so it holds even
-- when the caller is the application — the same argument migrations 001, 003
-- and 008 make.
--
-- One difference from those: the "content is immutable" check here is written
-- as a *denylist inversion* rather than as a list of frozen columns. The
-- provenance version enumerates every immutable column, which means a column
-- added later is silently mutable until someone remembers to extend the
-- trigger. Here the trigger is told which columns may move, and everything else
-- — including anything added in a future migration — is frozen by default.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION investigations_append_only() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not permitted', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

-- Argument: the columns this row is allowed to change, as a Postgres array
-- literal. Every one of them is also treated as set-once — a terminator that
-- can be reversed is not a terminator.
CREATE OR REPLACE FUNCTION investigations_terminators_only() RETURNS TRIGGER AS $$
DECLARE
    terminators TEXT[] := TG_ARGV[0]::TEXT[];
    generated   TEXT[];
    ignored     TEXT[];
    old_j       JSONB  := to_jsonb(OLD);
    new_j       JSONB  := to_jsonb(NEW);
    col         TEXT;
BEGIN
    -- Generated columns are excluded from the comparison, and finding that out
    -- cost a test: PostgreSQL computes a GENERATED ... STORED column *after*
    -- BEFORE triggers run, so inside this function NEW.<generated> is still
    -- NULL while OLD.<generated> holds the previous value. Comparing them made
    -- every legitimate update to a table with a generated column look like an
    -- attempt to edit frozen content — which is how superseding a dissent, the
    -- one supported way to change one's mind, came to be rejected.
    --
    -- Skipping them loses nothing: PostgreSQL refuses to let anyone write a
    -- generated column at all ("can only be updated to DEFAULT"), so it is
    -- already protected more strictly than this trigger could manage.
    --
    -- Read from the catalogue rather than named in the trigger arguments, so a
    -- generated column added by a later migration is handled without anyone
    -- having to remember this.
    SELECT coalesce(array_agg(attname::text), '{}')
      INTO generated
      FROM pg_attribute
     WHERE attrelid = TG_RELID AND attgenerated <> '' AND NOT attisdropped;

    ignored := terminators || generated;

    IF (new_j - ignored) IS DISTINCT FROM (old_j - ignored) THEN
        RAISE EXCEPTION
            '% is immutable except for %; supersede or withdraw the row instead of editing it',
            TG_TABLE_NAME, array_to_string(terminators, ', ')
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    FOREACH col IN ARRAY terminators LOOP
        IF (old_j -> col) <> 'null'::jsonb
           AND (old_j -> col) IS DISTINCT FROM (new_j -> col) THEN
            RAISE EXCEPTION '%.% is set once and cannot be altered or reversed',
                TG_TABLE_NAME, col
                USING ERRCODE = 'insufficient_privilege';
        END IF;
    END LOOP;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- The history log itself. Nothing may edit or remove an event: if this table
-- were mutable, every guarantee above it would be decorative.
DROP TRIGGER IF EXISTS investigation_events_no_update ON investigation_events;
CREATE TRIGGER investigation_events_no_update
    BEFORE UPDATE ON investigation_events
    FOR EACH ROW EXECUTE FUNCTION investigations_append_only();

DROP TRIGGER IF EXISTS investigation_events_no_delete ON investigation_events;
CREATE TRIGGER investigation_events_no_delete
    BEFORE DELETE ON investigation_events
    FOR EACH ROW EXECUTE FUNCTION investigations_append_only();

DROP TRIGGER IF EXISTS investigation_events_no_truncate ON investigation_events;
CREATE TRIGGER investigation_events_no_truncate
    BEFORE TRUNCATE ON investigation_events
    FOR EACH STATEMENT EXECUTE FUNCTION investigations_append_only();


DROP TRIGGER IF EXISTS investigation_findings_immutable ON investigation_findings;
CREATE TRIGGER investigation_findings_immutable
    BEFORE UPDATE ON investigation_findings
    FOR EACH ROW EXECUTE FUNCTION investigations_terminators_only(
        '{superseded_by,superseded_at,withdrawn_at,withdrawn_by,withdrawal_reason}');

DROP TRIGGER IF EXISTS investigation_findings_no_delete ON investigation_findings;
CREATE TRIGGER investigation_findings_no_delete
    BEFORE DELETE ON investigation_findings
    FOR EACH ROW EXECUTE FUNCTION investigations_append_only();


DROP TRIGGER IF EXISTS analyst_assessments_immutable ON analyst_assessments;
CREATE TRIGGER analyst_assessments_immutable
    BEFORE UPDATE ON analyst_assessments
    FOR EACH ROW EXECUTE FUNCTION investigations_terminators_only(
        '{superseded_by,superseded_at,withdrawn_at,withdrawn_by,withdrawal_reason}');

DROP TRIGGER IF EXISTS analyst_assessments_no_delete ON analyst_assessments;
CREATE TRIGGER analyst_assessments_no_delete
    BEFORE DELETE ON analyst_assessments
    FOR EACH ROW EXECUTE FUNCTION investigations_append_only();


-- Evidence links: the only legal update is the tombstone. Attaching again
-- inserts a new row (see the partial unique indexes above), so an attach is
-- never rewritten into a detach or back again.
DROP TRIGGER IF EXISTS investigation_alerts_immutable ON investigation_alerts;
CREATE TRIGGER investigation_alerts_immutable
    BEFORE UPDATE ON investigation_alerts
    FOR EACH ROW EXECUTE FUNCTION investigations_terminators_only(
        '{detached_at,detached_by,detach_reason}');

DROP TRIGGER IF EXISTS investigation_alerts_no_delete ON investigation_alerts;
CREATE TRIGGER investigation_alerts_no_delete
    BEFORE DELETE ON investigation_alerts
    FOR EACH ROW EXECUTE FUNCTION investigations_append_only();

DROP TRIGGER IF EXISTS investigation_entities_immutable ON investigation_entities;
CREATE TRIGGER investigation_entities_immutable
    BEFORE UPDATE ON investigation_entities
    FOR EACH ROW EXECUTE FUNCTION investigations_terminators_only(
        '{removed_at,removed_by,removal_reason}');

DROP TRIGGER IF EXISTS investigation_entities_no_delete ON investigation_entities;
CREATE TRIGGER investigation_entities_no_delete
    BEFORE DELETE ON investigation_entities
    FOR EACH ROW EXECUTE FUNCTION investigations_append_only();


-- Actions may be completed, and that is all. Editing the description of an
-- action after the fact would let "check the shipping manifest" become
-- "confirmed the shipping manifest" with no trace.
DROP TRIGGER IF EXISTS investigation_actions_immutable ON investigation_actions;
CREATE TRIGGER investigation_actions_immutable
    BEFORE UPDATE ON investigation_actions
    FOR EACH ROW EXECUTE FUNCTION investigations_terminators_only(
        '{completed_at,completed_by,completion_note}');

DROP TRIGGER IF EXISTS investigation_actions_no_delete ON investigation_actions;
CREATE TRIGGER investigation_actions_no_delete
    BEFORE DELETE ON investigation_actions
    FOR EACH ROW EXECUTE FUNCTION investigations_append_only();


-- A review, once given, is not revisable. Someone who changes their mind gives
-- a second review; both stand, and which came first is visible.
DROP TRIGGER IF EXISTS investigation_reviews_no_update ON investigation_reviews;
CREATE TRIGGER investigation_reviews_no_update
    BEFORE UPDATE ON investigation_reviews
    FOR EACH ROW EXECUTE FUNCTION investigations_append_only();

DROP TRIGGER IF EXISTS investigation_reviews_no_delete ON investigation_reviews;
CREATE TRIGGER investigation_reviews_no_delete
    BEFORE DELETE ON investigation_reviews
    FOR EACH ROW EXECUTE FUNCTION investigations_append_only();


-- The investigation row itself is mutable — it is a work item, like an alert —
-- but it may never be removed. An investigation that was opened is a fact about
-- what an organisation did, whatever it later concluded.
DROP TRIGGER IF EXISTS investigations_no_delete ON investigations;
CREATE TRIGGER investigations_no_delete
    BEFORE DELETE ON investigations
    FOR EACH ROW EXECUTE FUNCTION investigations_append_only();


-- ─────────────────────────────────────────────────────────────────────────────
-- Views
-- ─────────────────────────────────────────────────────────────────────────────

-- The working queue. Counts come from this, never from a page of it — the
-- audit found four separate surfaces deriving a total from a display list
-- (B-04, B-05, and the alert group count Phase 7 had to correct as well).
CREATE OR REPLACE VIEW investigation_queue AS
SELECT i.investigation_id,
       i.inv_ref,
       i.title,
       i.state,
       i.confidence,
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


-- Outcomes joined back to the rules that raised the alerts. This is the view
-- the calibration phase consumes, and it is defined here rather than there
-- because the join it needs is a property of how this schema stores outcomes.
--
-- It reports counts per rule and never a rate. A precision computed over three
-- closed investigations is a number with the same number of digits as one
-- computed over three thousand, and the two are not comparable — so the
-- denominator travels with the figure and the division is left to the reader.
CREATE OR REPLACE VIEW investigation_outcomes_by_rule AS
SELECT al.rule_id,
       al.rule_version,
       i.outcome,
       count(DISTINCT i.investigation_id) AS investigations,
       count(DISTINCT al.alert_key)       AS alerts
FROM investigations i
JOIN investigation_alerts ia
  ON ia.investigation_id = i.investigation_id AND ia.detached_at IS NULL
JOIN alerts al ON al.alert_key = ia.alert_key
WHERE i.outcome IS NOT NULL
GROUP BY al.rule_id, al.rule_version, i.outcome;


-- Standing analyst assessments, with the machine's answer beside each. The
-- name says "standing" rather than "current" because withdrawal and
-- supersession are what remove a row from it — nothing here is the latest by
-- time alone.
CREATE OR REPLACE VIEW analyst_assessments_standing AS
SELECT *
FROM analyst_assessments
WHERE withdrawn_at IS NULL AND superseded_at IS NULL;


-- ─────────────────────────────────────────────────────────────────────────────
-- Least privilege
--
-- The application may UPDATE exactly four tables, and on three of them a
-- trigger constrains the update to terminator columns. It may DELETE from none.
-- ─────────────────────────────────────────────────────────────────────────────

GRANT SELECT, INSERT, UPDATE ON investigations TO argus_app;
GRANT SELECT, INSERT ON investigation_events TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE investigation_events_event_id_seq TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE investigation_ref_seq TO argus_app;

GRANT SELECT, INSERT, UPDATE ON investigation_alerts TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE investigation_alerts_link_id_seq TO argus_app;
GRANT SELECT, INSERT, UPDATE ON investigation_entities TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE investigation_entities_link_id_seq TO argus_app;

GRANT SELECT, INSERT, UPDATE ON investigation_findings TO argus_app;
GRANT SELECT, INSERT, UPDATE ON investigation_actions TO argus_app;
GRANT SELECT, INSERT, UPDATE ON analyst_assessments TO argus_app;
-- INSERT only: a review cannot be revised, so the application has no reason to
-- hold UPDATE on it.
GRANT SELECT, INSERT ON investigation_reviews TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE investigation_reviews_review_id_seq TO argus_app;

GRANT SELECT ON investigation_queue TO argus_app;
GRANT SELECT ON investigation_outcomes_by_rule TO argus_app;
GRANT SELECT ON analyst_assessments_standing TO argus_app;
