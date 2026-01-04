from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GenerationRunOut(BaseModel):
    id: str
    project_id: str
    actor_user_id: str | None = None
    chapter_id: str | None = None
    type: str
    provider: str | None = None
    model: str | None = None
    request_id: str | None = None
    prompt_system: str | None = None
    prompt_user: str | None = None
    prompt_render_log: dict[str, Any] | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    output_text: str | None = None
    error: dict[str, Any] | None = None
    created_at: datetime
