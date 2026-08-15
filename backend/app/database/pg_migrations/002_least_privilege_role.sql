-- Migration 002: the least-privilege application role.
--
-- This migration is the security boundary the audit log depends on. It runs as
-- the superuser (migrations connect with the admin DSN); the application then
-- connects as `argus_app`, which is deliberately weaker.
--
-- The property being bought: an attacker who fully compromises the ARGUS
-- process gets the `argus_app` role, and `argus_app` cannot UPDATE or DELETE an
-- audit row. Erasing evidence of what they did requires separately compromising
-- the database superuser. The triggers in 001 enforce this even for roles that
-- do hold the privilege; the grants here mean the application never holds it.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'argus_app') THEN
        -- Password is set separately by the migration runner, which reads it
        -- from configuration. It is never written into a migration file.
        CREATE ROLE argus_app LOGIN;
    END IF;
END
$$;

-- The database name is configurable, and GRANT ... ON DATABASE requires a
-- literal identifier, so it is built dynamically from current_database().
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO argus_app', current_database());
END
$$;

GRANT USAGE ON SCHEMA public TO argus_app;

-- Identity tables: full read/write. Sessions are created and revoked, users are
-- updated on password change and lockout.
GRANT SELECT, INSERT, UPDATE, DELETE ON users TO argus_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON sessions TO argus_app;

-- The audit log: INSERT and SELECT only. No UPDATE. No DELETE. No TRUNCATE.
-- This single line is most of the reason Postgres is in this project.
GRANT SELECT, INSERT ON audit_events TO argus_app;
GRANT USAGE, SELECT ON SEQUENCE audit_events_seq_seq TO argus_app;

-- Schema changes remain the migration runner's job, under the admin role.
REVOKE CREATE ON SCHEMA public FROM argus_app;
