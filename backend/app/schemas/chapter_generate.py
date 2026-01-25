from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PromptOverrideMessage(BaseModel):
    role: str = Field(default="user", max_length=32)
    content: str = Field(default="", max_length=20000)
    name: str | None = Field(default=None, max_length=64)


class PromptOverride(BaseModel):
    system: str | None = Field(default=None, max_length=20000)
    user: str | None = Field(default=None, max_length=20000)
    messages: list[PromptOverrideMessage] = Field(default_factory=list, max_length=100)


class McpToolCall(BaseModel):
    tool_name: str = Field(default="", max_length=128)
    args: dict[str, object] = Field(default_factory=dict)

    @field_validator("tool_name")
    @classmethod
    def _validate_tool_name(cls, v: str) -> str:
        name = str(v or "").strip()
        if not name:
            return ""
        if len(name) > 128:
            raise ValueError("tool_name too long")
        return name


class McpResearchConfig(BaseModel):
    enabled: bool = False
    allowlist: list[str] = Field(default_factory=list, max_length=50)
    calls: list[McpToolCall] = Field(default_factory=list, max_length=50)
    timeout_seconds: float | None = Field(default=None, ge=0.1, le=60.0)
    max_output_chars: int | None = Field(default=None, ge=0, le=20000)

    @field_validator("allowlist")
    @classmethod
    def _validate_allowlist(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for item in v or []:
            if not isinstance(item, str):
                raise ValueError("allowlist items must be strings")
            item = item.strip()
            if not item:
                raise ValueError("allowlist cannot contain empty strings")
            if len(item) > 128:
                raise ValueError("allowlist item too long")
            out.append(item)
        return out


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
    content_optimize: bool = False
    macro_seed: str | None = Field(default=None, max_length=256)
    prompt_override: PromptOverride | None = None
    style_id: str | None = Field(default=None, max_length=36)
    memory_injection_enabled: bool = False
    memory_query_text: str | None = Field(default=None, max_length=5000)
    memory_modules: dict[str, bool] = Field(default_factory=dict)
    context: ChapterGenerateContext = Field(default_factory=ChapterGenerateContext)
    mcp_research: McpResearchConfig = Field(default_factory=McpResearchConfig)
