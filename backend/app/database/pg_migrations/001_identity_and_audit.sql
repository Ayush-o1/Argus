-- Migration 001: identity, authorization and the audit log.
--
-- Ordering note: roles and grants are applied at the end, after every table
-- exists, so the application role can never briefly hold privileges on a table
-- that has not yet been protected.

-- ─────────────────────────────────────────────────────────────────────────────
-- Users
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    -- Argon2id encoded hash. Never a plaintext or reversible value.
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    -- TOTP secret, null until the user enrols. Encrypted at rest is a Phase 12
    -- concern; storing it here at all is gated on is_active and admin-only reads.
    mfa_secret      TEXT,
    mfa_enrolled    BOOLEAN NOT NULL DEFAULT FALSE,
    failed_logins   INTEGER NOT NULL DEFAULT 0,
    locked_until    TIMESTAMPTZ,
    password_changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT users_role_valid CHECK (
        role IN ('viewer', 'analyst', 'investigator', 'supervisor', 'administrator', 'auditor')
    ),
    CONSTRAINT users_username_shape CHECK (char_length(username) BETWEEN 3 AND 64)
);

CREATE INDEX IF NOT EXISTS users_role_idx ON users (role) WHERE is_active;

-- ─────────────────────────────────────────────────────────────────────────────
-- Sessions
--
-- The session token is stored only as a SHA-256 hash. A database read — via
-- backup, replica, or SQL injection elsewhere — therefore does not yield a
-- usable credential, the same reasoning that applies to passwords.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sessions (
    id              UUID PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL UNIQUE,
    -- Absolute expiry. Distinct from idle expiry (last_seen_at + idle window),
    -- so a session cannot be kept alive indefinitely by activity alone.
    expires_at      TIMESTAMPTZ NOT NULL,
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at      TIMESTAMPTZ,
    revoked_reason  TEXT,
    ip_address      INET,
    user_agent      TEXT
);

CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id);
CREATE INDEX IF NOT EXISTS sessions_expiry_idx ON sessions (expires_at) WHERE revoked_at IS NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- Audit log
--
-- Append-only and hash-chained. Each row carries the hash of its predecessor,
-- so removing or altering a row breaks the chain from that point onward and the
-- break is detectable by recomputation — even by someone who has acquired
-- enough privilege to bypass the triggers below.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS audit_events (
    seq             BIGSERIAL PRIMARY KEY,
    id              UUID NOT NULL UNIQUE,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    actor_id        UUID,          -- null only for unauthenticated events (failed login)
    actor_username  TEXT,          -- denormalised: the answer must survive user deletion
    actor_role      TEXT,

    action          TEXT NOT NULL, -- e.g. 'case.update', 'auth.login_failed'
    resource_type   TEXT,          -- e.g. 'Case'
    resource_id     TEXT,          -- e.g. 'CASE-0042'
    outcome         TEXT NOT NULL, -- 'success' | 'denied' | 'failure'

    -- Before/after state for mutations. JSONB so a change can be inspected
    -- without a schema migration per audited field.
    before_state    JSONB,
    after_state     JSONB,

    request_id      TEXT,
    ip_address      INET,
    user_agent      TEXT,
    detail          TEXT,

    prev_hash       TEXT NOT NULL,
    entry_hash      TEXT NOT NULL,

    CONSTRAINT audit_outcome_valid CHECK (outcome IN ('success', 'denied', 'failure'))
);

CREATE INDEX IF NOT EXISTS audit_actor_idx ON audit_events (actor_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS audit_resource_idx ON audit_events (resource_type, resource_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS audit_action_idx ON audit_events (action, occurred_at DESC);
CREATE INDEX IF NOT EXISTS audit_occurred_idx ON audit_events (occurred_at DESC);

-- Reject mutation of audit rows at the database, not in application code.
-- An application-level rule is only as strong as the application; this holds
-- even when the caller is the application itself.
CREATE OR REPLACE FUNCTION audit_events_immutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only: % is not permitted', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events;
CREATE TRIGGER audit_events_no_update
    BEFORE UPDATE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();

DROP TRIGGER IF EXISTS audit_events_no_delete ON audit_events;
CREATE TRIGGER audit_events_no_delete
    BEFORE DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();

-- TRUNCATE bypasses row-level triggers entirely, so it needs its own statement
-- -level guard. Without this the whole log could be erased in one statement.
DROP TRIGGER IF EXISTS audit_events_no_truncate ON audit_events;
CREATE TRIGGER audit_events_no_truncate
    BEFORE TRUNCATE ON audit_events
    FOR EACH STATEMENT EXECUTE FUNCTION audit_events_immutable();
