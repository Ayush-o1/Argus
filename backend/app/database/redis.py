from redis.asyncio import Redis

from app.config import get_settings

_redis: Redis | None = None


async def connect_redis() -> Redis:
    """Create the process-wide Redis async client. Called once at app startup."""
    global _redis
    settings = get_settings()
    _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    await _redis.ping()
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("Redis client not initialized — app startup did not run.")
    return _redis
