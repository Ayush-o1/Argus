from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, sourced from environment variables / .env.

    pydantic-settings resolves values in this priority order:
      1. Actual environment variables (highest — used by Docker, CI, hosting platforms)
      2. .env file in the parent directory (../env — local dev, running from backend/)
      3. .env file in the current directory (.env — Docker WORKDIR /app)
      4. Defaults defined below (lowest)
    """

    model_config = SettingsConfigDict(
        # Check both locations: ../env works when running `uvicorn` from backend/;
        # .env works when the process CWD is /app inside Docker (where .env may be mounted).
        env_file=["../.env", ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "argus_dev_password"

    redis_url: str = "redis://localhost:6379/0"

    # --- PostgreSQL: identity, authorization, audit ---
    # Two DSNs by design. Migrations connect as the admin role to create the
    # schema, the triggers and the least-privilege role; the application then
    # connects as `argus_app`, which cannot UPDATE or DELETE an audit row. If
    # the app used the admin DSN, the audit log's tamper-resistance would be
    # decorative.
    postgres_host: str = "localhost"
    postgres_port: int = 55432
    postgres_db: str = "argus"

    postgres_superuser: str = "argus_admin"
    postgres_superuser_password: str = "argus_dev_password"

    postgres_app_user: str = "argus_app"
    postgres_app_password: str = "argus_dev_app_password"

    postgres_command_timeout_seconds: float = 10.0

    # Empty by default — the local docker-compose Postgres speaks plain TCP and
    # has no certificate to verify. A managed provider (Neon, RDS, etc.) both
    # requires TLS and rejects a plaintext connection outright, so deploying
    # against one needs this set — "require" at minimum, "verify-full" where
    # the provider supplies a CA chain worth pinning to. asyncpg parses
    # `sslmode` directly out of the DSN query string (verified against the
    # installed asyncpg's own `connect_utils` parser), so this is the one
    # setting that turns TLS on; no other code change is needed.
    postgres_sslmode: str = ""

    @property
    def _postgres_sslmode_qs(self) -> str:
        return f"?sslmode={self.postgres_sslmode}" if self.postgres_sslmode else ""

    @property
    def postgres_admin_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_superuser}:{self.postgres_superuser_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}{self._postgres_sslmode_qs}"
        )

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_app_user}:{self.postgres_app_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}{self._postgres_sslmode_qs}"
        )

    # --- Sessions ---
    # Absolute lifetime: a session cannot outlive this regardless of activity.
    session_absolute_hours: int = 12
    # Idle lifetime: a session unused for this long is dead even if within the
    # absolute window. Both are enforced; the shorter one wins.
    session_idle_minutes: int = 60
    # Cookie Secure flag. False for local http development only; any deployment
    # reachable over a network must set this true.
    session_cookie_secure: bool = False

    # SameSite policy for the session and CSRF cookies. "strict" is correct
    # whenever the frontend and backend share a registrable domain (including
    # local dev — a different port is still the same *site*). It is wrong the
    # moment they don't: a Vercel frontend (*.vercel.app) and a Render backend
    # (*.onrender.com) are different sites, and a Strict cookie is never sent
    # on that cross-site request — login would appear to succeed (the response
    # carries Set-Cookie) while the browser silently drops it, so every
    # subsequent request looks unauthenticated. Set to "none" for that
    # deployment shape, which requires `session_cookie_secure=true` (enforced
    # below) because browsers reject `SameSite=None` without `Secure`.
    session_cookie_samesite: Literal["strict", "lax", "none"] = "strict"

    @model_validator(mode="after")
    def _samesite_none_requires_secure(self) -> "Settings":
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError(
                "SESSION_COOKIE_SAMESITE=none requires SESSION_COOKIE_SECURE=true "
                "— browsers reject SameSite=None cookies without Secure, so this "
                "combination would silently break authentication rather than "
                "just being insecure."
            )
        return self

    # --- Brute-force protection ---
    max_failed_logins: int = 5
    lockout_minutes: int = 15

    # Optional local LLM assistant (see docs/ai-layer.md). ARGUS Core never
    # requires this — probed at runtime, all other features work without it.
    ollama_base_url: str = "http://localhost:11434"

    # No `argus_api_token`. The single static bearer token was removed in the
    # identity phase and deliberately not replaced: the frontend also shipped it
    # to the browser via NEXT_PUBLIC_ARGUS_API_TOKEN, so the credential guarding
    # every endpoint was public to anyone who loaded the page. A setting left
    # here after the code stopped reading it is worse than no setting — it reads
    # as a control that exists.

    cors_origins: str = "http://localhost:3000"

    # Path to the generator directory. Empty string = auto-detect from file location
    # (correct for local development). Set to /generator in Docker (see backend/Dockerfile).
    generator_dir: str = ""

    # Logging level. Use "INFO" in production, "DEBUG" for verbose local dev output.
    log_level: str = "INFO"

    # Emit logs as one JSON object per line. Off by default because it is far
    # less readable at a local terminal; turn on wherever logs are shipped to an
    # aggregator, which is the only place the structure pays off.
    log_json: bool = False

    # --- Durable job worker (ingestion) ---
    # Off switch rather than a code change, so an instance can serve the API
    # without also being a worker — the split every deployment eventually wants,
    # available before it needs a second service.
    job_worker_enabled: bool = True
    job_poll_seconds: float = 2.0
    job_worker_concurrency: int = 2
    # How often to check which connectors are due. Concurrent schedulers are
    # safe: each queued job carries an idempotency key, so two instances ticking
    # together produce one run.
    ingest_schedule_seconds: float = 30.0

    # Ceiling on analytics/scenario jobs running at once. Each GDS job holds an
    # in-memory graph projection and real CPU, and jobs are startable by a single
    # client in a loop — without a ceiling that exhausts the host (audit B-07).
    max_concurrent_jobs: int = 4

    # How long the driver keeps retrying a transient transaction failure before
    # giving up. The default is 30s, which is longer than any ARGUS request
    # should ever hold a connection.
    neo4j_transaction_retry_seconds: float = 8.0

    # Wall-clock ceiling for a single user-facing query. Anything slower is a bug
    # or an abusive request; either way the caller gets a clear error instead of
    # a hung connection.
    neo4j_query_timeout_seconds: float = 20.0

    # Scenario generation shells out to the generator. Bounded so a wedged
    # subprocess cannot hold a job slot forever.
    scenario_timeout_seconds: float = 300.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
