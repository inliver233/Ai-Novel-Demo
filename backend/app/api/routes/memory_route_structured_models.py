from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

StructuredMemoryTableName = Literal["entities", "relations", "events", "foreshadows", "evidence"]

STRUCTURED_MEMORY_TABLES: tuple[StructuredMemoryTableName, ...] = (
    "entities",
    "relations",
    "events",
    "foreshadows",
    "evidence",
)


@dataclass(frozen=True)
class StructuredMemoryQueryArgs:
    table: StructuredMemoryTableName | None
    keyword: str | None
    pattern: str | None
    before: str | None
    before_dt: datetime | None
    limit: int


@dataclass(frozen=True)
class StructuredMemoryTablePage:
    items: list[dict[str, object]]
    cursor: str | None
