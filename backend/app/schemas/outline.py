from __future__ import annotations

from pydantic import BaseModel


class OutlineOut(BaseModel):
    project_id: str
    content_md: str
    updated_at: str


class OutlineUpdate(BaseModel):
    content_md: str | None = None

