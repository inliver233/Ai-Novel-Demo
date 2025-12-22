from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.chapter_generate import ChapterGenerateContext


class ChapterPlanRequest(BaseModel):
    instruction: str = Field(default="", max_length=4000)
    context: ChapterGenerateContext = Field(default_factory=ChapterGenerateContext)

