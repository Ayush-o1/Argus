from fastapi import Header, HTTPException, status

from app.config import get_settings


async def require_api_token(authorization: str | None = Header(default=None)) -> None:
    """Single-user demo auth: a static bearer token (see ARGUS_PLAN.md Phase 11)."""
    settings = get_settings()
    expected = f"Bearer {settings.argus_api_token}"
    if authorization != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API token")
