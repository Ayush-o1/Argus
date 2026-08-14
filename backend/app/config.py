from functools import lru_cache

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

    # Optional local LLM assistant (see docs/ai-layer.md). ARGUS Core never
    # requires this — probed at runtime, all other features work without it.
    ollama_base_url: str = "http://localhost:11434"

    argus_api_token: str = "argus_dev_token"

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
