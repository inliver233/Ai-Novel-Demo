from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.limits import MAX_MD_CHARS


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
    content_md: str = Field(default="", max_length=MAX_MD_CHARS)
    enabled: bool = True
    constant: bool = False
    keywords: list[str] = Field(default_factory=list, max_length=100)
    exclude_recursion: bool = False
    prevent_recursion: bool = False
    char_limit: int = Field(default=12000, ge=0, le=200000)
    priority: WorldBookPriority = "important"

    @field_validator("keywords")
    @classmethod
    def _validate_keywords(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for item in v or []:
            if not isinstance(item, str):
                raise ValueError("keywords must be strings")
            item = item.strip()
            if not item:
                raise ValueError("keywords cannot contain empty strings")
            if len(item) > 64:
                raise ValueError("keyword too long")
            out.append(item)
        return out


class WorldBookEntryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    content_md: str | None = Field(default=None, max_length=MAX_MD_CHARS)
    enabled: bool | None = None
    constant: bool | None = None
    keywords: list[str] | None = Field(default=None, max_length=100)
    exclude_recursion: bool | None = None
    prevent_recursion: bool | None = None
    char_limit: int | None = Field(default=None, ge=0, le=200000)
    priority: WorldBookPriority | None = None

    @field_validator("keywords")
    @classmethod
    def _validate_keywords(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        out: list[str] = []
        for item in v or []:
            if not isinstance(item, str):
                raise ValueError("keywords must be strings")
            item = item.strip()
            if not item:
                raise ValueError("keywords cannot contain empty strings")
            if len(item) > 64:
                raise ValueError("keyword too long")
            out.append(item)
        return out


class WorldBookBulkUpdateRequest(BaseModel):
    entry_ids: list[str] = Field(min_length=1, max_length=200)
    enabled: bool | None = None
    constant: bool | None = None
    exclude_recursion: bool | None = None
    prevent_recursion: bool | None = None
    char_limit: int | None = Field(default=None, ge=0, le=200000)
    priority: WorldBookPriority | None = None


class WorldBookBulkDeleteRequest(BaseModel):
    entry_ids: list[str] = Field(min_length=1, max_length=200)


class WorldBookDuplicateRequest(BaseModel):
    entry_ids: list[str] = Field(min_length=1, max_length=200)


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


WorldBookImportMode = Literal["merge", "overwrite"]


class WorldBookExportEntryV1(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content_md: str = Field(default="", max_length=MAX_MD_CHARS)
    enabled: bool = True
    constant: bool = False
    keywords: list[str] = Field(default_factory=list, max_length=100)
    exclude_recursion: bool = False
    prevent_recursion: bool = False
    char_limit: int = Field(default=12000, ge=0, le=200000)
    priority: WorldBookPriority = "important"

    @field_validator("keywords")
    @classmethod
    def _validate_keywords(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for item in v or []:
            if not isinstance(item, str):
                raise ValueError("keywords must be strings")
            item = item.strip()
            if not item:
                raise ValueError("keywords cannot contain empty strings")
            if len(item) > 64:
                raise ValueError("keyword too long")
            out.append(item)
        return out


class WorldBookExportAllOut(BaseModel):
    schema_version: str = Field(default="worldbook_export_all_v1", max_length=64)
    entries: list[WorldBookExportEntryV1] = Field(default_factory=list, max_length=2000)


class WorldBookImportAllRequest(BaseModel):
    schema_version: str = Field(default="worldbook_export_all_v1", max_length=64)
    dry_run: bool = False
    mode: WorldBookImportMode = "merge"
    entries: list[WorldBookExportEntryV1] = Field(default_factory=list, max_length=2000)
