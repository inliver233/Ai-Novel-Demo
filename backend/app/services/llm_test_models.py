from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PreparedLlmTestRequest:
    provider: str
    model: str
    base_url: str
    resolved_api_key: str
    timeout_seconds: int
    params: dict[str, Any]
    extra: dict[str, Any]
    context: dict[str, object]
