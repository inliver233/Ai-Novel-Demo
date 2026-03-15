from __future__ import annotations

from dataclasses import dataclass, field

from app.llm.messages import ChatMessage
from app.services.generation_service import PreparedLlmCall


@dataclass(slots=True)
class PreparedChapterAutoMemoryUpdateRequest:
    enabled: bool
    skip_reason: str | None = None
    resolved_api_key: str = ""
    prompt_system: str = ""
    prompt_user: str = ""
    prompt_messages: list[ChatMessage] = field(default_factory=list)
    prompt_render_log_json: str | None = None
    llm_call: PreparedLlmCall | None = None
    idempotency_key: str | None = None


@dataclass(slots=True)
class PreparedChapterAnalyzeRequest:
    project_id: str
    resolved_api_key: str
    prompt_system: str
    prompt_user: str
    prompt_messages: list[ChatMessage]
    prompt_render_log_json: str | None
    llm_call: PreparedLlmCall
    auto_memory_update: PreparedChapterAutoMemoryUpdateRequest | None = None


@dataclass(slots=True)
class PreparedChapterRewriteRequest:
    project_id: str
    resolved_api_key: str
    prompt_system: str
    prompt_user: str
    prompt_messages: list[ChatMessage]
    prompt_render_log_json: str | None
    llm_call: PreparedLlmCall
