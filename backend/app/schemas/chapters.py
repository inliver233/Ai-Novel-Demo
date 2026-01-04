from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.base import ORMModel


ChapterStatus = Literal["planned", "drafting", "done"]


class ChapterCreate(BaseModel):
    number: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=255)
    plan: str | None = None
    status: ChapterStatus = "planned"


class ChapterUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    plan: str | None = None
    content_md: str | None = None
    summary: str | None = None
    status: ChapterStatus | None = None


class BulkChapter(BaseModel):
    number: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=255)
    plan: str | None = None


class BulkCreateRequest(BaseModel):
    chapters: list[BulkChapter] = Field(min_length=1)


class ChapterOut(ORMModel):
    id: str
    project_id: str
    outline_id: str
    number: int
    title: str | None = None
    plan: str | None = None
    content_md: str | None = None
    summary: str | None = None
    status: ChapterStatus
    updated_at: datetime
