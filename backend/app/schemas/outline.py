from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OutlineOut(BaseModel):
    id: str
    project_id: str
    title: str
    content_md: str
    structure: Any | None = None
    created_at: datetime
    updated_at: datetime


class OutlineUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content_md: str | None = None
    structure: Any | None = None


class OutlineCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content_md: str | None = None
    structure: Any | None = None


class OutlineListItem(BaseModel):
    id: str
    title: str
    updated_at: datetime
    created_at: datetime
    has_chapters: bool = False
