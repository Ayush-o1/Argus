from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, sourced from environment variables / .env."""

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "argus_dev_password"

    redis_url: str = "redis://localhost:6379/0"

    # Optional local LLM assistant (see docs/ai-layer.md). ARGUS Core never
    # requires this — probed at runtime, all other features work without it.
    ollama_base_url: str = "http://localhost:11434"

    argus_api_token: str = "argus_dev_token"

    cors_origins: str = "http://localhost:3000"

    # Logging level. Use "INFO" in production, "DEBUG" for verbose local dev output.
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
