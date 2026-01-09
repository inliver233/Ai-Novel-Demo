from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MemoryContextPackOut(BaseModel):
    """
    Phase 0 contract: keep a stable top-level shape while allowing empty packs.
    Later phases will progressively populate these sections.
    """

    worldbook: dict[str, Any] = Field(default_factory=dict)
    story_memory: dict[str, Any] = Field(default_factory=dict)
    structured: dict[str, Any] = Field(default_factory=dict)
    vector_rag: dict[str, Any] = Field(default_factory=dict)
    graph: dict[str, Any] = Field(default_factory=dict)
    fractal: dict[str, Any] = Field(default_factory=dict)
    logs: list[dict[str, Any]] = Field(default_factory=list)

