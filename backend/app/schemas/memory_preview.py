from __future__ import annotations

from pydantic import Field

from app.schemas.base import RequestModel


class MemoryPreviewRequest(RequestModel):
    query_text: str = Field(default="", max_length=5000)
    section_enabled: dict[str, bool] = Field(default_factory=dict)
    budget_overrides: dict[str, int] = Field(default_factory=dict)

