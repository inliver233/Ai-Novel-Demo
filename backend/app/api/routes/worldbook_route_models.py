from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorldBookImportAllState:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    deleted: int = 0
    conflicts: list[dict[str, object]] = field(default_factory=list)
    actions: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class WorldBookAutoUpdateTarget:
    chapter_id: str | None
    chapter_token: str
