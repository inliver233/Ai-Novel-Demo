from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChapterGenerateContext(BaseModel):
    include_world_setting: bool = True
    include_style_guide: bool = True
    include_constraints: bool = True
    include_outline: bool = True
    include_smart_context: bool = True
    require_sequential: bool = False
    character_ids: list[str] = Field(default_factory=list, max_length=200)
    previous_chapter: Literal["none", "summary", "content", "tail"] | None = None
    current_draft_tail: str | None = Field(default=None, max_length=5000)

    @field_validator("character_ids")
    @classmethod
    def _validate_character_ids(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for item in v or []:
            if not isinstance(item, str):
                raise ValueError("character_ids must be strings")
            item = item.strip()
            if not item:
                raise ValueError("character_ids cannot contain empty strings")
            if len(item) > 36:
                raise ValueError("character_id too long")
            out.append(item)
        return out


class ChapterGenerateRequest(BaseModel):
    mode: Literal["replace", "append"]
    instruction: str = Field(default="", max_length=4000)
    target_word_count: int | None = Field(default=None, ge=100, le=50000)
    plan_first: bool = False
    post_edit: bool = False
    post_edit_sanitize: bool = False
    style_id: str | None = Field(default=None, max_length=36)
    context: ChapterGenerateContext = Field(default_factory=ChapterGenerateContext)
