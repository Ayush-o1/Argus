from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Meta(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 50


class Envelope(BaseModel, Generic[T]):
    """Consistent response shape for every ARGUS endpoint (see ARGUS_PLAN.md Phase 13)."""

    data: T
    meta: Meta | None = None
    error: str | None = None
