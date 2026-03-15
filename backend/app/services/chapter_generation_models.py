from __future__ import annotations

from dataclasses import dataclass, field

from app.llm.messages import ChatMessage
from app.services.generation_service import PreparedLlmCall


@dataclass(slots=True)
class ChapterMemoryPreparation:
    memory_pack: dict[str, object] | None
    memory_injection_config: dict[str, object] | None
    memory_retrieval_log_json: dict[str, object] | None


@dataclass(slots=True)
class PreparedChapterPlanRequest:
    project_id: str
    resolved_api_key: str
    llm_call: PreparedLlmCall
    prompt_system: str
    prompt_user: str
    prompt_messages: list[ChatMessage]
    prompt_render_log_json: str | None


@dataclass(slots=True)
class PreparedChapterGenerateRequest:
    request_id: str
    chapter_id: str
    project_id: str
    macro_seed: str
    resolved_api_key: str
    llm_call: PreparedLlmCall
    prompt_system: str = ""
    prompt_user: str = ""
    prompt_messages: list[ChatMessage] = field(default_factory=list)
    prompt_render_log: dict[str, object] | None = None
    prompt_render_log_json: str | None = None
    render_values: dict[str, object] | None = None
    run_params_extra_json: dict[str, object] | None = None
    run_params_json: str | None = None
    base_instruction: str = ""
    requirements_obj: dict[str, object] = field(default_factory=dict)
    context_optimizer_enabled: bool = False
    style_resolution: dict[str, object] = field(default_factory=dict)
    memory_preparation: ChapterMemoryPreparation = field(
        default_factory=lambda: ChapterMemoryPreparation(
            memory_pack=None,
            memory_injection_config=None,
            memory_retrieval_log_json=None,
        )
    )
    mcp_research: dict[str, object] | None = None
    prompt_overridden: bool = False
    plan_prompt_system: str = ""
    plan_prompt_user: str = ""
    plan_prompt_messages: list[ChatMessage] = field(default_factory=list)
    plan_prompt_render_log_json: str | None = None
    plan_llm_call: PreparedLlmCall | None = None
    plan_api_key: str = ""

