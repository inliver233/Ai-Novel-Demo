from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChapterGenerateContext(BaseModel):
    include_world_setting: bool = True
    include_style_guide: bool = True
    include_constraints: bool = True
    include_outline: bool = True
    character_ids: list[str] = Field(default_factory=list)
    previous_chapter: str | None = None


class ChapterGenerateRequest(BaseModel):
    mode: Literal["replace", "append"]
    instruction: str = Field(default="", max_length=4000)
    target_word_count: int | None = Field(default=None, ge=100, le=50000)
    context: ChapterGenerateContext = Field(default_factory=ChapterGenerateContext)
