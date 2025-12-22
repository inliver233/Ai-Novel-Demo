from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PromptPresetOut(BaseModel):
    id: str
    project_id: str
    name: str
    scope: str
    version: int
    active_for: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class PromptPresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scope: str = Field(default="project", min_length=1, max_length=32)
    version: int = Field(default=1, ge=1)
    active_for: list[str] = Field(default_factory=list)


class PromptPresetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    scope: str | None = Field(default=None, min_length=1, max_length=32)
    version: int | None = Field(default=None, ge=1)
    active_for: list[str] | None = None


class PromptBlockOut(BaseModel):
    id: str
    preset_id: str
    identifier: str
    name: str
    role: str
    enabled: bool
    template: str | None = None
    marker_key: str | None = None
    injection_position: str
    injection_depth: int | None = None
    injection_order: int
    triggers: list[str] = Field(default_factory=list)
    forbid_overrides: bool = False
    budget: dict[str, Any] = Field(default_factory=dict)
    cache: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class PromptBlockCreate(BaseModel):
    identifier: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=16)
    enabled: bool = True
    template: str | None = None
    marker_key: str | None = Field(default=None, max_length=255)
    injection_position: str = Field(default="relative", min_length=1, max_length=16)
    injection_depth: int | None = None
    injection_order: int = 0
    triggers: list[str] = Field(default_factory=list)
    forbid_overrides: bool = False
    budget: dict[str, Any] = Field(default_factory=dict)
    cache: dict[str, Any] = Field(default_factory=dict)


class PromptBlockUpdate(BaseModel):
    identifier: str | None = Field(default=None, min_length=1, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = Field(default=None, min_length=1, max_length=16)
    enabled: bool | None = None
    template: str | None = None
    marker_key: str | None = Field(default=None, max_length=255)
    injection_position: str | None = Field(default=None, min_length=1, max_length=16)
    injection_depth: int | None = None
    injection_order: int | None = None
    triggers: list[str] | None = None
    forbid_overrides: bool | None = None
    budget: dict[str, Any] | None = None
    cache: dict[str, Any] | None = None


class PromptBlockReorderRequest(BaseModel):
    ordered_block_ids: list[str] = Field(min_length=1)


class PromptPreviewRequest(BaseModel):
    task: str = Field(min_length=1, max_length=64)
    preset_id: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)


class PromptPreviewBlock(BaseModel):
    id: str
    identifier: str
    role: str
    enabled: bool
    text: str
    missing: list[str] = Field(default_factory=list)
    token_estimate: int = 0


class PromptPreviewOut(BaseModel):
    preset_id: str
    task: str
    system: str
    user: str
    prompt_tokens_estimate: int = 0
    prompt_budget_tokens: int | None = None
    missing: list[str] = Field(default_factory=list)
    blocks: list[PromptPreviewBlock] = Field(default_factory=list)


class PromptPresetExportBlock(BaseModel):
    identifier: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=16)
    enabled: bool = True
    template: str | None = None
    marker_key: str | None = Field(default=None, max_length=255)
    injection_position: str = Field(default="relative", min_length=1, max_length=16)
    injection_depth: int | None = None
    injection_order: int = 0
    triggers: list[str] = Field(default_factory=list)
    forbid_overrides: bool = False
    budget: dict[str, Any] = Field(default_factory=dict)
    cache: dict[str, Any] = Field(default_factory=dict)


class PromptPresetExportPreset(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scope: str = Field(default="project", min_length=1, max_length=32)
    version: int = Field(default=1, ge=1)
    active_for: list[str] = Field(default_factory=list)


class PromptPresetExportOut(BaseModel):
    preset: PromptPresetExportPreset
    blocks: list[PromptPresetExportBlock] = Field(default_factory=list)


class PromptPresetImportRequest(BaseModel):
    preset: PromptPresetExportPreset
    blocks: list[PromptPresetExportBlock] = Field(default_factory=list)
