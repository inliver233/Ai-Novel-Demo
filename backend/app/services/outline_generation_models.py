from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.llm.messages import ChatMessage
from app.services.generation_service import PreparedLlmCall

OutlineFillProgressHook = Callable[[dict[str, object]], None]
OutlineSegmentProgressHook = Callable[[dict[str, object]], None]


@dataclass
class PreparedOutlineGeneration:
    resolved_api_key: str
    prompt_system: str
    prompt_user: str
    prompt_messages: list[ChatMessage]
    prompt_render_log_json: str
    llm_call: PreparedLlmCall
    target_chapter_count: int | None
    run_params_extra_json: dict[str, object]
    run_params_json: str

@dataclass
class OutlineSegmentGenerationResult:
    data: dict[str, object]
    warnings: list[str]
    parse_error: dict[str, object] | None
    run_ids: list[str]
    latency_ms: int
    dropped_params: list[str]
    finish_reasons: list[str]
    meta: dict[str, object]

