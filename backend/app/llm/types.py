from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class LLMCallResult:
    text: str
    latency_ms: int
    dropped_params: list[str]
    finish_reason: str | None = None


@dataclass(slots=True)
class LLMStreamState:
    finish_reason: str | None = None
    latency_ms: int | None = None
    dropped_params: list[str] = field(default_factory=list)

