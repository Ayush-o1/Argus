from fastapi import Header, HTTPException, status
from neo4j import AsyncDriver

from app.config import get_settings
from app.database.neo4j import get_driver


async def require_api_token(authorization: str | None = Header(default=None)) -> None:
    """Single-user demo auth: a static bearer token (see ARGUS_PLAN.md Phase 11)."""
    settings = get_settings()
    expected = f"Bearer {settings.argus_api_token}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API token")


def get_db() -> AsyncDriver:
    return get_driver()
