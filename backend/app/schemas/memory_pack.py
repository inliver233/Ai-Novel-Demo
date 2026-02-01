from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryContextSection = Literal[
    "worldbook",
    "story_memory",
    "semantic_history",
    "foreshadow_open_loops",
    "structured",
    "tables",
    "vector_rag",
    "graph",
    "fractal",
]


class MemoryContextSectionOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    disabled_reason: str | None = None


class MemoryContextLogItemOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    section: MemoryContextSection
    enabled: bool
    disabled_reason: str | None = None
    note: str | None = None


class MemoryContextPackOut(BaseModel):
    """
    Phase 0 contract: keep a stable top-level shape while allowing empty packs.
    Later phases will progressively populate these sections.
    """

    worldbook: MemoryContextSectionOut = Field(default_factory=MemoryContextSectionOut)
    story_memory: MemoryContextSectionOut = Field(default_factory=MemoryContextSectionOut)
    semantic_history: MemoryContextSectionOut = Field(default_factory=MemoryContextSectionOut)
    foreshadow_open_loops: MemoryContextSectionOut = Field(default_factory=MemoryContextSectionOut)
    structured: MemoryContextSectionOut = Field(default_factory=MemoryContextSectionOut)
    tables: MemoryContextSectionOut = Field(default_factory=MemoryContextSectionOut)
    vector_rag: MemoryContextSectionOut = Field(default_factory=MemoryContextSectionOut)
    graph: MemoryContextSectionOut = Field(default_factory=MemoryContextSectionOut)
    fractal: MemoryContextSectionOut = Field(default_factory=MemoryContextSectionOut)
    logs: list[MemoryContextLogItemOut] = Field(default_factory=list)
