from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_chapter_editor
from app.core.errors import AppError
from app.db.session import SessionLocal
from app.llm.messages import ChatMessage, coalesce_system, flatten_messages
from app.llm.redaction import redact_text
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.outline import Outline
from app.models.project import Project
from app.models.project_settings import ProjectSettings
from app.schemas.chapter_generate import ChapterGenerateRequest
from app.schemas.chapter_plan import ChapterPlanRequest
from app.services.chapter_context_service import (
    build_chapter_generate_render_values,
    inject_plan_into_render_values,
    load_previous_chapter_context,
)
from app.services.chapter_generation_models import (
    ChapterMemoryPreparation,
    PreparedChapterGenerateRequest,
    PreparedChapterPlanRequest,
)
from app.services.generation_pipeline import (
    run_chapter_generate_llm_step,
    run_content_optimize_step,
    run_mcp_research_step,
    run_plan_llm_step,
    run_post_edit_step,
)
from app.services.generation_service import build_run_params_json, prepare_llm_call, with_param_overrides
from app.services.length_control import estimate_max_tokens
from app.services.llm_task_preset_resolver import resolve_task_llm_config, resolve_task_preset
from app.services.mcp.service import McpResearchConfig as McpResearchConfigSvc
from app.services.mcp.service import McpToolCall as McpToolCallSvc
from app.services.memory_query_service import normalize_query_text, parse_query_preprocessing_config
from app.services.memory_retrieval_service import build_memory_retrieval_log_json, retrieve_memory_context_pack
from app.services.prompt_presets import ensure_default_plan_preset, render_preset_for_task
from app.services.prompt_store import format_characters

_MAX_MACRO_SEED_CHARS = 256


def resolve_macro_seed(*, request_id: str, body: object) -> str:
    seed = str(getattr(body, "macro_seed", "") or "").strip()
    if not seed:
        return request_id
    return seed[:_MAX_MACRO_SEED_CHARS]


def apply_prompt_override(
    *,
    prompt_system: str,
    prompt_user: str,
    prompt_messages: list[ChatMessage],
    body: ChapterGenerateRequest,
) -> tuple[str, str, list[ChatMessage], bool]:
    override = body.prompt_override
    if override is None:
        return prompt_system, prompt_user, prompt_messages, False

    override_messages: list[ChatMessage] = []
    for item in override.messages or []:
        role = str(item.role or "user").strip() or "user"
        content = str(item.content or "")
        name = str(item.name).strip() if isinstance(item.name, str) and item.name.strip() else None
        override_messages.append(ChatMessage(role=role, content=content, name=name))
    if override_messages:
        system, non_system = coalesce_system(override_messages)
        user = flatten_messages(non_system)
        return system, user, override_messages, True

    next_system = prompt_system if override.system is None else str(override.system or "")
    next_user = prompt_user if override.user is None else str(override.user or "")
    next_messages: list[ChatMessage] = []
    if next_system.strip():
        next_messages.append(ChatMessage(role="system", content=next_system))
    if next_user.strip():
        next_messages.append(ChatMessage(role="user", content=next_user))
    return next_system, next_user, next_messages, True


def _redact_prompt_override_for_params(body: ChapterGenerateRequest) -> dict[str, object] | None:
    override = body.prompt_override
    if override is None:
        return None
    data = override.model_dump()
    if isinstance(data.get("system"), str):
        data["system"] = redact_text(data["system"])
    if isinstance(data.get("user"), str):
        data["user"] = redact_text(data["user"])

    messages = data.get("messages")
    if isinstance(messages, list):
        for item in messages:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("content"), str):
                item["content"] = redact_text(item["content"])
    return data


def _redact_prompt_preview_for_params(
    *, prompt_system: str, prompt_user: str, prompt_messages: list[ChatMessage]
) -> dict[str, object]:
    return {
        "system": redact_text(prompt_system or ""),
        "user": redact_text(prompt_user or ""),
        "messages": [{"role": m.role, "content": redact_text(m.content or ""), "name": m.name} for m in prompt_messages],
    }


def build_prompt_inspector_params(
    *,
    macro_seed: str,
    prompt_overridden: bool,
    body: ChapterGenerateRequest,
    precheck_prompt_system: str,
    precheck_prompt_user: str,
    precheck_prompt_messages: list[ChatMessage],
    final_prompt_system: str,
    final_prompt_user: str,
    final_prompt_messages: list[ChatMessage],
) -> dict[str, object]:
    out: dict[str, object] = {
        "macro_seed": macro_seed,
        "prompt_overridden": bool(prompt_overridden),
        "precheck": _redact_prompt_preview_for_params(
            prompt_system=precheck_prompt_system,
            prompt_user=precheck_prompt_user,
            prompt_messages=precheck_prompt_messages,
        ),
        "final": _redact_prompt_preview_for_params(
            prompt_system=final_prompt_system,
            prompt_user=final_prompt_user,
            prompt_messages=final_prompt_messages,
        ),
    }
    override = _redact_prompt_override_for_params(body)
    if override is not None:
        out["override"] = override
    return out


def build_mcp_research_config(body: ChapterGenerateRequest) -> McpResearchConfigSvc:
    cfg = getattr(body, "mcp_research", None)
    if cfg is None:
        return McpResearchConfigSvc(enabled=False, allowlist=[], calls=[])

    calls: list[McpToolCallSvc] = []
    for item in getattr(cfg, "calls", None) or []:
        tool_name = str(getattr(item, "tool_name", "") or "").strip()
        if not tool_name:
            continue
        args = getattr(item, "args", None)
        calls.append(McpToolCallSvc(tool_name=tool_name, args=args if isinstance(args, dict) else {}))

    allowlist = list(getattr(cfg, "allowlist", None) or [])
    return McpResearchConfigSvc(
        enabled=bool(getattr(cfg, "enabled", False)),
        allowlist=[str(x).strip() for x in allowlist if isinstance(x, str) and str(x).strip()],
        calls=calls,
        timeout_seconds=getattr(cfg, "timeout_seconds", None),
        max_output_chars=getattr(cfg, "max_output_chars", None),
    )


def inject_mcp_research_into_values(*, values: dict[str, object], context_md: str) -> None:
    text = str(context_md or "").strip()
    if not text:
        return

    base_instruction = str(values.get("instruction") or "").rstrip()
    user_obj = values.get("user")
    if isinstance(user_obj, dict):
        base = str(user_obj.get("instruction") or "").rstrip()
        user_obj["instruction"] = (base + "\n\n【资料收集 - 参考资料】\n" + text).strip()
    values["instruction"] = (base_instruction + "\n\n【资料收集 - 参考资料】\n" + text).strip()
    values["mcp_research"] = text


def build_mcp_research_params(
    *, cfg: McpResearchConfigSvc, applied: bool, tool_run_ids: list[str], warnings: list[str]
) -> dict[str, object]:
    return {
        "enabled": bool(cfg.enabled),
        "applied": bool(applied),
        "allowlist": list(cfg.allowlist or []),
        "tool_run_ids": list(tool_run_ids),
        "warnings": list(warnings or []),
    }


def resolve_memory_modules(raw_modules: dict[str, bool]) -> dict[str, bool]:
    return {
        "worldbook": bool(raw_modules.get("worldbook", True)),
        "story_memory": bool(raw_modules.get("story_memory", True)),
        "semantic_history": bool(raw_modules.get("semantic_history", False)),
        "foreshadow_open_loops": bool(raw_modules.get("foreshadow_open_loops", False)),
        "structured": bool(raw_modules.get("structured", True)),
        "tables": bool(raw_modules.get("tables", True)),
        "vector_rag": bool(raw_modules.get("vector_rag", True)),
        "graph": bool(raw_modules.get("graph", True)),
        "fractal": bool(raw_modules.get("fractal", True)),
    }


def prepare_chapter_memory_injection(
    *,
    db: Session,
    project_id: str,
    chapter: Chapter,
    body: ChapterGenerateRequest,
    settings_row: ProjectSettings | None,
    base_instruction: str,
    values: dict[str, object],
) -> ChapterMemoryPreparation:
    if not body.memory_injection_enabled:
        return ChapterMemoryPreparation(
            memory_pack=None,
            memory_injection_config=None,
            memory_retrieval_log_json=None,
        )

    memory_query_text = ""
    query_text_source = "auto"
    requested_query_text = str(body.memory_query_text or "").strip()
    if requested_query_text:
        memory_query_text = requested_query_text[:5000]
        query_text_source = "user"
    else:
        memory_query_text = base_instruction
        if chapter.plan:
            memory_query_text = f"{memory_query_text}\n\n{chapter.plan}".strip()
        memory_query_text = memory_query_text[:5000]

    memory_modules = resolve_memory_modules(body.memory_modules or {})
    raw_query_text = memory_query_text
    qp_cfg = parse_query_preprocessing_config(
        (settings_row.query_preprocessing_json or "").strip() if settings_row is not None else None
    )
    memory_query_text, preprocess_obs = normalize_query_text(query_text=raw_query_text, config=qp_cfg)

    pack = None
    pack_errors = None
    try:
        pack = retrieve_memory_context_pack(
            db=db,
            project_id=project_id,
            query_text=memory_query_text,
            section_enabled=memory_modules,
        )
    except Exception:
        pack = None
        pack_errors = ["memory_pack_error"]

    memory_pack = pack.model_dump() if pack is not None else None
    if memory_pack is not None:
        values["memory"] = memory_pack

    memory_injection_config: dict[str, object] = {
        "query_text": memory_query_text,
        "query_text_source": query_text_source,
        "modules": memory_modules,
        "raw_query_text": raw_query_text,
        "normalized_query_text": memory_query_text,
        "preprocess_obs": preprocess_obs,
    }
    memory_retrieval_log_json = build_memory_retrieval_log_json(
        enabled=True,
        query_text=memory_query_text,
        pack=pack,
        errors=pack_errors,
    )
    return ChapterMemoryPreparation(
        memory_pack=memory_pack,
        memory_injection_config=memory_injection_config,
        memory_retrieval_log_json=memory_retrieval_log_json,
    )


def build_memory_run_params_extra_json(
    *,
    style_resolution: dict[str, object],
    memory_injection_enabled: bool,
    memory_preparation: ChapterMemoryPreparation,
) -> dict[str, object]:
    params: dict[str, object] = {
        "style_resolution": style_resolution,
        "memory_injection_enabled": memory_injection_enabled,
    }
    if memory_injection_enabled and memory_preparation.memory_injection_config is not None:
        params["memory_injection_config"] = memory_preparation.memory_injection_config
        params["memory_retrieval_log_json"] = memory_preparation.memory_retrieval_log_json
    return params


def resolve_task_llm_for_call(
    *,
    db: Session,
    project: Project,
    user_id: str,
    task_key: str,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
):
    resolved = resolve_task_llm_config(
        db,
        project=project,
        user_id=user_id,
        task_key=task_key,
        header_api_key=x_llm_api_key,
    )
    if resolved is None:
        raise AppError(code="LLM_CONFIG_ERROR", message="请先在 Prompts 页保存 LLM 配置", status_code=400)
    if x_llm_api_key and x_llm_provider and resolved.llm_call.provider != x_llm_provider:
        raise AppError(code="LLM_CONFIG_ERROR", message="当前任务 provider 与请求头不一致，请先保存/切换", status_code=400)
    return resolved


def find_missing_prereq_numbers(
    db: Session,
    *,
    project_id: str,
    outline_id: str,
    chapter_number: int,
) -> list[int]:
    if chapter_number <= 1:
        return []

    rows = db.execute(
        select(Chapter.number, Chapter.content_md, Chapter.summary)
        .where(
            Chapter.project_id == project_id,
            Chapter.outline_id == outline_id,
            Chapter.number < chapter_number,
        )
        .order_by(Chapter.number.asc())
    ).all()

    existing: dict[int, tuple[str | None, str | None]] = {int(r[0]): (r[1], r[2]) for r in rows}
    missing: list[int] = []
    for n in range(1, int(chapter_number)):
        content_md, summary = existing.get(n, (None, None))
        if not ((content_md or "").strip() or (summary or "").strip()):
            missing.append(n)
    return missing


def _require_chapter_prereqs_if_needed(*, db: Session, chapter: Chapter, body_context: object) -> None:
    if not bool(getattr(body_context, "require_sequential", False)):
        return
    missing_numbers = find_missing_prereq_numbers(
        db,
        project_id=str(chapter.project_id),
        outline_id=str(chapter.outline_id),
        chapter_number=int(chapter.number),
    )
    if missing_numbers:
        raise AppError(
            code="CHAPTER_PREREQ_MISSING",
            message=f"缺少前置章节内容：第 {', '.join(str(n) for n in missing_numbers)} 章",
            status_code=400,
            details={"missing_numbers": missing_numbers},
        )


def prepare_chapter_plan_request(
    *,
    request_id: str,
    chapter_id: str,
    body: ChapterPlanRequest,
    user_id: str,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
) -> PreparedChapterPlanRequest:
    with SessionLocal() as db:
        chapter = require_chapter_editor(db, chapter_id=chapter_id, user_id=user_id)
        _require_chapter_prereqs_if_needed(db=db, chapter=chapter, body_context=body.context)
        project_id = str(chapter.project_id)
        project = db.get(Project, project_id)
        if project is None:
            raise AppError.not_found()

        resolved_plan = resolve_task_llm_for_call(
            db=db,
            project=project,
            user_id=user_id,
            task_key="plan_chapter",
            x_llm_provider=x_llm_provider,
            x_llm_api_key=x_llm_api_key,
        )
        ensure_default_plan_preset(db, project_id=project_id)

        settings_row = db.get(ProjectSettings, project_id)
        outline_row = db.get(Outline, chapter.outline_id)

        world_setting = (settings_row.world_setting if settings_row else "") or ""
        style_guide = (settings_row.style_guide if settings_row else "") or ""
        constraints = (settings_row.constraints if settings_row else "") or ""

        if not body.context.include_world_setting:
            world_setting = ""
        if not body.context.include_style_guide:
            style_guide = ""
        if not body.context.include_constraints:
            constraints = ""

        outline_text = (outline_row.content_md if outline_row else "") or ""
        if not body.context.include_outline:
            outline_text = ""

        chars: list[Character] = []
        if body.context.character_ids:
            chars = (
                db.execute(
                    select(Character).where(
                        Character.project_id == project_id,
                        Character.id.in_(body.context.character_ids),
                    )
                )
                .scalars()
                .all()
            )
        characters_text = format_characters(chars)

        prev_text, prev_ending = load_previous_chapter_context(
            db,
            project_id=project_id,
            outline_id=str(chapter.outline_id),
            chapter_number=int(chapter.number),
            previous_chapter=body.context.previous_chapter,
        )

        values: dict[str, object] = {
            "project_name": project.name or "",
            "genre": project.genre or "",
            "logline": project.logline or "",
            "world_setting": world_setting,
            "style_guide": style_guide,
            "constraints": constraints,
            "characters": characters_text,
            "outline": outline_text,
            "chapter_number": str(chapter.number),
            "chapter_title": (chapter.title or ""),
            "chapter_plan": (chapter.plan or ""),
            "instruction": body.instruction.strip(),
            "previous_chapter": prev_text,
            "previous_chapter_ending": prev_ending,
        }
        values["project"] = {
            "name": project.name or "",
            "genre": project.genre or "",
            "logline": project.logline or "",
            "world_setting": world_setting,
            "style_guide": style_guide,
            "constraints": constraints,
            "characters": characters_text,
        }
        values["story"] = {
            "outline": outline_text,
            "chapter_number": int(chapter.number),
            "chapter_title": (chapter.title or ""),
            "chapter_plan": (chapter.plan or ""),
            "previous_chapter": prev_text,
            "previous_chapter_ending": prev_ending,
        }
        values["user"] = {"instruction": body.instruction.strip()}
        values["context_optimizer_enabled"] = bool(getattr(settings_row, "context_optimizer_enabled", False))

        macro_seed = resolve_macro_seed(request_id=request_id, body=body)
        prompt_system, prompt_user, prompt_messages, _, _, _, render_log = render_preset_for_task(
            db,
            project_id=project_id,
            task="plan_chapter",
            values=values,  # type: ignore[arg-type]
            macro_seed=f"{macro_seed}:plan",
            provider=resolved_plan.llm_call.provider,
        )
        prompt_render_log_json = json.dumps(render_log, ensure_ascii=False)

    return PreparedChapterPlanRequest(
        project_id=project_id,
        resolved_api_key=str(resolved_plan.api_key),
        llm_call=resolved_plan.llm_call,
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        prompt_messages=prompt_messages,
        prompt_render_log_json=prompt_render_log_json,
    )


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


def prepare_chapter_generate_request(
    *,
    logger: logging.Logger,
    request_id: str,
    chapter_id: str,
    body: ChapterGenerateRequest,
    user_id: str,
    x_llm_provider: str | None,
    x_llm_api_key: str | None,
    require_api_key: bool,
) -> PreparedChapterGenerateRequest:
    macro_seed = resolve_macro_seed(request_id=request_id, body=body)
    with SessionLocal() as db:
        chapter = require_chapter_editor(db, chapter_id=chapter_id, user_id=user_id)
        _require_chapter_prereqs_if_needed(db=db, chapter=chapter, body_context=body.context)
        project_id = str(chapter.project_id)
        project = db.get(Project, project_id)
        if project is None:
            raise AppError.not_found()

        if require_api_key:
            resolved_chapter = resolve_task_llm_for_call(
                db=db,
                project=project,
                user_id=user_id,
                task_key="chapter_generate",
                x_llm_provider=x_llm_provider,
                x_llm_api_key=x_llm_api_key,
            )
            llm_call = resolved_chapter.llm_call
            resolved_api_key = str(resolved_chapter.api_key)
        else:
            preset_row, _ = resolve_task_preset(db, project_id=project_id, task_key="chapter_generate")
            if preset_row is None:
                raise AppError(code="LLM_CONFIG_ERROR", message="请先在 Prompts 页保存 LLM 配置", status_code=400)
            llm_call = prepare_llm_call(preset_row)
            if x_llm_api_key and x_llm_provider and llm_call.provider != x_llm_provider:
                raise AppError(code="LLM_CONFIG_ERROR", message="当前任务 provider 与请求头不一致，请先保存/切换", status_code=400)
            resolved_api_key = ""

        values, base_instruction, requirements_obj, style_resolution = build_chapter_generate_render_values(
            db,
            project=project,
            chapter=chapter,
            body=body,
            user_id=user_id,
        )
        settings_row = db.get(ProjectSettings, project_id)
        context_optimizer_enabled = bool(getattr(settings_row, "context_optimizer_enabled", False))
        values["context_optimizer_enabled"] = context_optimizer_enabled
        memory_preparation = prepare_chapter_memory_injection(
            db=db,
            project_id=project_id,
            chapter=chapter,
            body=body,
            settings_row=settings_row,
            base_instruction=base_instruction,
            values=values,
        )
        run_params_extra_json = build_memory_run_params_extra_json(
            style_resolution=style_resolution,
            memory_injection_enabled=body.memory_injection_enabled,
            memory_preparation=memory_preparation,
        )

        mcp_cfg = build_mcp_research_config(body)
        mcp_step = run_mcp_research_step(
            logger=logger,
            request_id=request_id,
            actor_user_id=user_id,
            project_id=project_id,
            chapter_id=chapter_id,
            config=mcp_cfg,
        )
        inject_mcp_research_into_values(values=values, context_md=mcp_step.context_md)
        mcp_research = None
        if mcp_cfg.enabled or mcp_step.warnings:
            run_params_extra_json = run_params_extra_json or {}
            mcp_research = build_mcp_research_params(
                cfg=mcp_cfg,
                applied=mcp_step.applied,
                tool_run_ids=[r.run_id for r in mcp_step.tool_runs],
                warnings=mcp_step.warnings,
            )
            run_params_extra_json["mcp_research"] = mcp_research

        prepared = PreparedChapterGenerateRequest(
            request_id=request_id,
            chapter_id=chapter_id,
            project_id=project_id,
            macro_seed=macro_seed,
            resolved_api_key=resolved_api_key,
            llm_call=llm_call,
            render_values=values,
            run_params_extra_json=run_params_extra_json,
            base_instruction=base_instruction,
            requirements_obj=requirements_obj,
            context_optimizer_enabled=context_optimizer_enabled,
            style_resolution=style_resolution,
            memory_preparation=memory_preparation,
            mcp_research=mcp_research,
        )

        if body.plan_first:
            resolved_plan = resolve_task_llm_for_call(
                db=db,
                project=project,
                user_id=user_id,
                task_key="plan_chapter",
                x_llm_provider=x_llm_provider,
                x_llm_api_key=x_llm_api_key,
            )
            ensure_default_plan_preset(db, project_id=project_id)
            plan_values = dict(values)
            plan_values["instruction"] = base_instruction
            plan_values["user"] = {"instruction": base_instruction, "requirements": requirements_obj}
            plan_prompt_system, plan_prompt_user, plan_prompt_messages, _, _, _, plan_render_log = render_preset_for_task(
                db,
                project_id=project_id,
                task="plan_chapter",
                values=plan_values,  # type: ignore[arg-type]
                macro_seed=f"{macro_seed}:plan",
                provider=resolved_plan.llm_call.provider,
            )
            prepared.plan_prompt_system = plan_prompt_system
            prepared.plan_prompt_user = plan_prompt_user
            prepared.plan_prompt_messages = plan_prompt_messages
            prepared.plan_prompt_render_log_json = json.dumps(plan_render_log, ensure_ascii=False)
            prepared.plan_llm_call = resolved_plan.llm_call
            prepared.plan_api_key = str(resolved_plan.api_key)
        else:
            render_main_prompt(prepared=prepared, body=body, values=values)

        prepared.run_params_json = build_run_params_json(
            params_json=prepared.llm_call.params_json,
            memory_retrieval_log_json=None,
            extra_json=prepared.run_params_extra_json,
        )
    return prepared


def render_main_prompt(
    *,
    prepared: PreparedChapterGenerateRequest,
    body: ChapterGenerateRequest,
    values: dict[str, object],
) -> None:
    with SessionLocal() as db:
        prompt_system, prompt_user, prompt_messages, _, _, _, render_log = render_preset_for_task(
            db,
            project_id=prepared.project_id,
            task="chapter_generate",
            values=values,  # type: ignore[arg-type]
            macro_seed=prepared.macro_seed,
            provider=prepared.llm_call.provider,
        )
    precheck_prompt_system = prompt_system
    precheck_prompt_user = prompt_user
    precheck_prompt_messages = prompt_messages
    prompt_system, prompt_user, prompt_messages, override_applied = apply_prompt_override(
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        prompt_messages=prompt_messages,
        body=body,
    )
    prepared.prompt_system = prompt_system
    prepared.prompt_user = prompt_user
    prepared.prompt_messages = prompt_messages
    prepared.prompt_render_log = render_log
    prepared.prompt_render_log_json = json.dumps(render_log, ensure_ascii=False)
    prepared.prompt_overridden = bool(override_applied)
    prepared.run_params_extra_json = prepared.run_params_extra_json or {}
    prepared.run_params_extra_json["prompt_inspector"] = build_prompt_inspector_params(
        macro_seed=prepared.macro_seed,
        prompt_overridden=override_applied,
        body=body,
        precheck_prompt_system=precheck_prompt_system,
        precheck_prompt_user=precheck_prompt_user,
        precheck_prompt_messages=precheck_prompt_messages,
        final_prompt_system=prompt_system,
        final_prompt_user=prompt_user,
        final_prompt_messages=prompt_messages,
    )
    prepared.run_params_json = build_run_params_json(
        params_json=prepared.llm_call.params_json,
        memory_retrieval_log_json=None,
        extra_json=prepared.run_params_extra_json,
    )


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


def _append_post_process_steps(
    *,
    logger: logging.Logger,
    prepared: PreparedChapterGenerateRequest,
    body: ChapterGenerateRequest,
    actor_user_id: str,
    data: dict[str, object],
) -> None:
    if body.post_edit:
        raw_content = str(data.get("content_md") or "").strip()
        post_edit_applied = False
        post_edit_warnings: list[str] = []
        post_edit_parse_error: dict[str, object] | None = None

        if raw_content:
            data["post_edit_raw_content_md"] = raw_content
            step = run_post_edit_step(
                logger=logger,
                request_id=prepared.request_id,
                actor_user_id=actor_user_id,
                project_id=prepared.project_id,
                chapter_id=prepared.chapter_id,
                api_key=prepared.resolved_api_key,
                llm_call=prepared.llm_call,
                render_values=prepared.render_values or {},
                raw_content=raw_content,
                macro_seed=f"{prepared.macro_seed}:post_edit",
                post_edit_sanitize=bool(body.post_edit_sanitize),
                run_params_extra_json={
                    **(prepared.run_params_extra_json or {}),
                    "post_edit_sanitize": bool(body.post_edit_sanitize),
                },
            )
            post_edit_warnings = step.warnings
            post_edit_parse_error = step.parse_error
            data["post_edit_run_id"] = step.run_id
            data["post_edit_edited_content_md"] = step.edited_content_md
            if step.applied:
                data["content_md"] = step.edited_content_md
                post_edit_applied = True
        else:
            post_edit_warnings.append("post_edit_no_content")

        data["post_edit_applied"] = post_edit_applied
        if post_edit_warnings:
            data["post_edit_warnings"] = post_edit_warnings
        if post_edit_parse_error is not None:
            data["post_edit_parse_error"] = post_edit_parse_error

    if body.content_optimize:
        raw_content = str(data.get("content_md") or "").strip()
        content_optimize_applied = False
        content_optimize_warnings: list[str] = []
        content_optimize_parse_error: dict[str, object] | None = None

        if raw_content:
            data["content_optimize_raw_content_md"] = raw_content
            step = run_content_optimize_step(
                logger=logger,
                request_id=prepared.request_id,
                actor_user_id=actor_user_id,
                project_id=prepared.project_id,
                chapter_id=prepared.chapter_id,
                api_key=prepared.resolved_api_key,
                llm_call=prepared.llm_call,
                render_values=prepared.render_values or {},
                raw_content=raw_content,
                macro_seed=f"{prepared.macro_seed}:content_optimize",
                run_params_extra_json={**(prepared.run_params_extra_json or {}), "content_optimize": True},
            )
            content_optimize_warnings = step.warnings
            content_optimize_parse_error = step.parse_error
            data["content_optimize_run_id"] = step.run_id
            data["content_optimize_optimized_content_md"] = step.optimized_content_md
            if step.applied:
                data["content_md"] = step.optimized_content_md
                content_optimize_applied = True
        else:
            content_optimize_warnings.append("content_optimize_no_content")

        data["content_optimize_applied"] = content_optimize_applied
        if content_optimize_warnings:
            data["content_optimize_warnings"] = content_optimize_warnings
        if content_optimize_parse_error is not None:
            data["content_optimize_parse_error"] = content_optimize_parse_error


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
