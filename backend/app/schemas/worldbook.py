from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


WorldBookPriority = Literal["drop_first", "optional", "important", "must"]


class WorldBookEntryOut(BaseModel):
    id: str
    project_id: str
    title: str
    content_md: str
    enabled: bool
    constant: bool
    keywords: list[str] = Field(default_factory=list)
    exclude_recursion: bool
    prevent_recursion: bool
    char_limit: int
    priority: WorldBookPriority
    updated_at: datetime


class WorldBookEntryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content_md: str = ""
    enabled: bool = True
    constant: bool = False
    keywords: list[str] = Field(default_factory=list)
    exclude_recursion: bool = False
    prevent_recursion: bool = False
    char_limit: int = Field(default=12000, ge=0, le=200000)
    priority: WorldBookPriority = "important"


class WorldBookEntryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content_md: str | None = None
    enabled: bool | None = None
    constant: bool | None = None
    keywords: list[str] | None = None
    exclude_recursion: bool | None = None
    prevent_recursion: bool | None = None
    char_limit: int | None = Field(default=None, ge=0, le=200000)
    priority: WorldBookPriority | None = None


class WorldBookTriggeredEntryOut(BaseModel):
    id: str
    title: str
    reason: str
    priority: WorldBookPriority


class WorldBookPreviewTriggerRequest(BaseModel):
    query_text: str = Field(default="", max_length=50000)
    include_constant: bool = True
    enable_recursion: bool = True
    char_limit: int = Field(default=12000, ge=0, le=200000)


class WorldBookPreviewTriggerOut(BaseModel):
    triggered: list[WorldBookTriggeredEntryOut] = Field(default_factory=list)
    text_md: str = ""
    truncated: bool = False
