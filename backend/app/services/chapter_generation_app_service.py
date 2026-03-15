from __future__ import annotations

import logging

from app.core.errors import AppError
from app.schemas.chapter_generate import ChapterGenerateRequest
from app.schemas.chapter_plan import ChapterPlanRequest
from app.services.chapter_context_service import inject_plan_into_render_values
from app.services.chapter_generation_models import PreparedChapterGenerateRequest
from app.services.chapter_generation_post_process_service import _append_post_process_steps
from app.services.chapter_generation_plan_prepare_service import prepare_chapter_plan_request
from app.services.chapter_generation_prepare_service import (
    find_missing_prereq_numbers,
    prepare_chapter_generate_request,
    render_main_prompt,
    resolve_task_llm_for_call,
)
from app.services.generation_pipeline import run_chapter_generate_llm_step, run_plan_llm_step
from app.services.generation_service import with_param_overrides
from app.services.length_control import estimate_max_tokens


def plan_chapter(
    *,
    logger: logging.Logger,
    request_id: str,
    chapter_id: str,
    body: ChapterPlanRequest,
    user_id: str,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
) -> dict[str, object]:
    prepared = prepare_chapter_plan_request(
        request_id=request_id,
        chapter_id=chapter_id,
        body=body,
        user_id=user_id,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
    )
    if not prepared.prompt_system.strip() and not prepared.prompt_user.strip():
        raise AppError(code="PROMPT_CONFIG_ERROR", message="缺少 plan_chapter 提示词预设/提示块", status_code=400)

    plan_step = run_plan_llm_step(
        logger=logger,
        request_id=request_id,
        actor_user_id=user_id,
        project_id=prepared.project_id,
        chapter_id=chapter_id,
        api_key=prepared.resolved_api_key,
        llm_call=prepared.llm_call,
        prompt_system=prepared.prompt_system,
        prompt_user=prepared.prompt_user,
        prompt_messages=prepared.prompt_messages,
        prompt_render_log_json=prepared.prompt_render_log_json,
    )

    data = dict(plan_step.plan_out)
    if plan_step.warnings:
        data["warnings"] = plan_step.warnings
    if plan_step.parse_error is not None:
        data["parse_error"] = plan_step.parse_error
    if plan_step.finish_reason is not None:
        data["finish_reason"] = plan_step.finish_reason
    return data

def generate_chapter_precheck(
    *,
    logger: logging.Logger,
    request_id: str,
    chapter_id: str,
    body: ChapterGenerateRequest,
    user_id: str,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
) -> dict[str, object]:
    if body.plan_first:
        raise AppError.validation(message="生成预检不支持 plan_first（该模式依赖 LLM 产出的 plan）")

    prepared = prepare_chapter_generate_request(
        logger=logger,
        request_id=request_id,
        chapter_id=chapter_id,
        body=body,
        user_id=user_id,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
        require_api_key=False,
    )
    if prepared.prompt_render_log is None:
        raise AppError(code="INTERNAL_ERROR", message="提示词渲染失败", status_code=500)
    if not prepared.prompt_system.strip() and not prepared.prompt_user.strip():
        raise AppError(code="PROMPT_CONFIG_ERROR", message="缺少 chapter_generate 提示词预设/提示块", status_code=400)

    return {
        "precheck": {
            "task": "chapter_generate",
            "macro_seed": prepared.macro_seed,
            "prompt_system": prepared.prompt_system,
            "prompt_user": prepared.prompt_user,
            "messages": [{"role": m.role, "content": m.content, "name": m.name} for m in prepared.prompt_messages],
            "render_log": prepared.prompt_render_log,
            "style_resolution": prepared.style_resolution,
            "memory_pack": prepared.memory_preparation.memory_pack,
            "memory_injection_config": prepared.memory_preparation.memory_injection_config,
            "memory_retrieval_log_json": prepared.memory_preparation.memory_retrieval_log_json,
            "mcp_research": prepared.mcp_research,
            "prompt_overridden": prepared.prompt_overridden,
        }
    }

def run_plan_first_step(
    *,
    logger: logging.Logger,
    prepared: PreparedChapterGenerateRequest,
    body: ChapterGenerateRequest,
    actor_user_id: str,
) -> tuple[dict[str, object], list[str], dict[str, object] | None]:
    if not prepared.plan_prompt_system.strip() and not prepared.plan_prompt_user.strip():
        raise AppError(
            code="PROMPT_CONFIG_ERROR",
            message="缺少 plan_chapter 提示词预设/提示块，请在 Prompt Studio 配置",
            status_code=400,
        )

    plan_step = run_plan_llm_step(
        logger=logger,
        request_id=prepared.request_id,
        actor_user_id=actor_user_id,
        project_id=prepared.project_id,
        chapter_id=prepared.chapter_id,
        api_key=str(prepared.plan_api_key or prepared.resolved_api_key),
        llm_call=prepared.plan_llm_call or prepared.llm_call,
        prompt_system=prepared.plan_prompt_system,
        prompt_user=prepared.plan_prompt_user,
        prompt_messages=prepared.plan_prompt_messages,
        prompt_render_log_json=prepared.plan_prompt_render_log_json,
        run_params_extra_json=prepared.run_params_extra_json,
    )
    plan_out, plan_warnings, plan_parse_error = plan_step.plan_out, plan_step.warnings, plan_step.parse_error
    if plan_step.finish_reason is not None:
        plan_out["finish_reason"] = plan_step.finish_reason

    plan_text = str((plan_out or {}).get("plan") or "").strip()
    if plan_text:
        prepared.render_values = inject_plan_into_render_values(prepared.render_values or {}, plan_text=plan_text)
        if prepared.render_values is not None:
            prepared.render_values["context_optimizer_enabled"] = prepared.context_optimizer_enabled

    render_main_prompt(prepared=prepared, body=body, values=prepared.render_values or {})
    return plan_out, plan_warnings, plan_parse_error

def apply_target_word_count(*, prepared: PreparedChapterGenerateRequest, body: ChapterGenerateRequest) -> None:
    if body.target_word_count is None:
        return
    prepared.llm_call = with_param_overrides(
        prepared.llm_call,
        {
            "max_tokens": estimate_max_tokens(
                target_word_count=body.target_word_count,
                provider=prepared.llm_call.provider,
                model=prepared.llm_call.model,
            )
        },
    )

def generate_chapter(
    *,
    logger: logging.Logger,
    request_id: str,
    chapter_id: str,
    body: ChapterGenerateRequest,
    user_id: str,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
) -> dict[str, object]:
    prepared = prepare_chapter_generate_request(
        logger=logger,
        request_id=request_id,
        chapter_id=chapter_id,
        body=body,
        user_id=user_id,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
        require_api_key=True,
    )
    if prepared.render_values is None:
        raise AppError(code="INTERNAL_ERROR", message="提示词变量准备失败", status_code=500)

    plan_out: dict[str, object] | None = None
    plan_warnings: list[str] = []
    plan_parse_error: dict[str, object] | None = None
    if body.plan_first:
        plan_out, plan_warnings, plan_parse_error = run_plan_first_step(
            logger=logger,
            prepared=prepared,
            body=body,
            actor_user_id=user_id,
        )

    apply_target_word_count(prepared=prepared, body=body)

    gen_step = run_chapter_generate_llm_step(
        logger=logger,
        request_id=request_id,
        actor_user_id=user_id,
        project_id=prepared.project_id,
        chapter_id=chapter_id,
        run_type="chapter",
        api_key=prepared.resolved_api_key,
        llm_call=prepared.llm_call,
        prompt_system=prepared.prompt_system,
        prompt_user=prepared.prompt_user,
        prompt_messages=prepared.prompt_messages,
        prompt_render_log_json=prepared.prompt_render_log_json,
        run_params_extra_json=prepared.run_params_extra_json,
    )
    data, warnings, parse_error = gen_step.data, gen_step.warnings, gen_step.parse_error

    _append_post_process_steps(
        logger=logger,
        prepared=prepared,
        body=body,
        actor_user_id=user_id,
        data=data,
    )

    if warnings:
        data["warnings"] = warnings
    if parse_error is not None:
        data["parse_error"] = parse_error
    if body.plan_first:
        data["plan"] = str((plan_out or {}).get("plan") or "")
        if plan_warnings:
            data["plan_warnings"] = plan_warnings
        if plan_parse_error is not None:
            data["plan_parse_error"] = plan_parse_error
    data["generation_run_id"] = gen_step.run_id
    data["latency_ms"] = gen_step.latency_ms
    if gen_step.dropped_params:
        data["dropped_params"] = gen_step.dropped_params
    if gen_step.finish_reason is not None:
        data["finish_reason"] = gen_step.finish_reason
    return data

