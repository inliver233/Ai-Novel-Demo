from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.schemas.chapter_generate import ChapterGenerateContext
from app.schemas.limits import MAX_JSON_CHARS_MEDIUM, MAX_MD_CHARS, MAX_TEXT_CHARS, validate_json_chars


class ChapterAnalyzeRequest(BaseModel):
    instruction: str = Field(default="", max_length=2000)
    context: ChapterGenerateContext = Field(default_factory=ChapterGenerateContext)

    # Allow analyzing unsaved drafts (do not persist to chapters table).
    draft_title: str | None = Field(default=None, max_length=255)
    draft_plan: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    draft_summary: str | None = Field(default=None, max_length=MAX_TEXT_CHARS)
    draft_content_md: str | None = Field(default=None, max_length=MAX_MD_CHARS)

    # Optional: after analysis finishes, auto propose a Memory Update ChangeSet (never auto-apply).
    auto_propose_memory_update: bool = Field(default=False)
    memory_update_focus: str | None = Field(default=None, max_length=4000)
    memory_update_idempotency_key: str | None = Field(default=None, max_length=64)


class ChapterRewriteRequest(BaseModel):
    instruction: str = Field(default="", max_length=2000)
    context: ChapterGenerateContext = Field(default_factory=ChapterGenerateContext)

    analysis: dict[str, Any] = Field(default_factory=dict, max_length=200)
    draft_content_md: str | None = Field(default=None, max_length=MAX_MD_CHARS)

    @field_validator("analysis")
    @classmethod
    def _validate_analysis(cls, v: dict[str, Any]) -> dict[str, Any]:
        return validate_json_chars(v, max_chars=MAX_JSON_CHARS_MEDIUM, field_name="analysis") or {}


class ChapterAnalysisApplyRequest(BaseModel):
    analysis: dict[str, Any] = Field(default_factory=dict, max_length=200)
    draft_content_md: str | None = Field(default=None, max_length=MAX_MD_CHARS)

    @field_validator("analysis")
    @classmethod
    def _validate_analysis(cls, v: dict[str, Any]) -> dict[str, Any]:
        return validate_json_chars(v, max_chars=MAX_JSON_CHARS_MEDIUM, field_name="analysis") or {}
