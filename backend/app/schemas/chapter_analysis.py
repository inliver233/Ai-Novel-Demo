from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.chapter_generate import ChapterGenerateContext


class ChapterAnalyzeRequest(BaseModel):
    instruction: str = Field(default="", max_length=2000)
    context: ChapterGenerateContext = Field(default_factory=ChapterGenerateContext)

    # Allow analyzing unsaved drafts (do not persist to chapters table).
    draft_title: str | None = Field(default=None, max_length=255)
    draft_plan: str | None = None
    draft_summary: str | None = None
    draft_content_md: str | None = None


class ChapterRewriteRequest(BaseModel):
    instruction: str = Field(default="", max_length=2000)
    context: ChapterGenerateContext = Field(default_factory=ChapterGenerateContext)

    analysis: dict[str, Any] = Field(default_factory=dict)
    draft_content_md: str | None = None


class ChapterAnalysisApplyRequest(BaseModel):
    analysis: dict[str, Any] = Field(default_factory=dict)
    draft_content_md: str | None = None
