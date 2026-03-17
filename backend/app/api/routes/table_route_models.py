from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TableCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    table_key: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    auto_update_enabled: bool | None = Field(default=None)
    table_schema: dict[str, Any] = Field(default_factory=dict, alias="schema")


class TableUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, max_length=255)
    auto_update_enabled: bool | None = Field(default=None)
    table_schema: dict[str, Any] | None = Field(default=None, alias="schema")


class TableRowCreateRequest(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class TableRowUpdateRequest(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class TableAiUpdateRequest(BaseModel):
    focus: str | None = Field(default=None, max_length=4000)
