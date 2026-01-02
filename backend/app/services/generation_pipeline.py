from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.services.chapter_context_service import build_post_edit_render_values
from app.services.generation_service import PreparedLlmCall, call_llm_and_record, with_param_overrides
from app.services.output_contracts import contract_for_task
from app.services.prompt_presets import ensure_default_post_edit_preset, render_preset_for_task
from app.db.session import SessionLocal


@dataclass(frozen=True, slots=True)
class PostEditStepResult:
    applied: bool
    edited_content_md: str
    warnings: list[str]
    parse_error: dict[str, object] | None


def run_post_edit_step(
    *,
    logger: logging.Logger,
    request_id: str,
    actor_user_id: str,
    project_id: str,
    chapter_id: str | None,
    api_key: str,
    llm_call: PreparedLlmCall,
    render_values: dict[str, object],
    raw_content: str,
    macro_seed: str,
) -> PostEditStepResult:
    with SessionLocal() as db:
        ensure_default_post_edit_preset(db, project_id=project_id)
        post_values = build_post_edit_render_values(render_values, raw_content=raw_content)

        post_system, post_user, post_messages, _, _, _, post_render_log = render_preset_for_task(
            db,
            project_id=project_id,
            task="post_edit",
            values=post_values,  # type: ignore[arg-type]
            macro_seed=macro_seed,
            provider=llm_call.provider,
        )
    post_render_log_json = json.dumps(post_render_log, ensure_ascii=False)

    post_call = with_param_overrides(llm_call, {"temperature": 0.4})
    post_result = call_llm_and_record(
        logger=logger,
        request_id=request_id,
        actor_user_id=actor_user_id,
        project_id=project_id,
        chapter_id=chapter_id,
        run_type="post_edit",
        api_key=api_key,
        prompt_system=post_system,
        prompt_user=post_user,
        prompt_messages=post_messages,
        prompt_render_log_json=post_render_log_json,
        llm_call=post_call,
    )

    post_contract = contract_for_task("post_edit")
    post_parsed = post_contract.parse(post_result.text, finish_reason=post_result.finish_reason)
    warnings = list(post_parsed.warnings)
    parse_error = post_parsed.parse_error
    edited = str(post_parsed.data.get("content_md") or "").strip()
    applied = parse_error is None and bool(edited)
    if not applied:
        warnings.append("post_edit_failed")

    return PostEditStepResult(
        applied=applied,
        edited_content_md=edited,
        warnings=warnings,
        parse_error=parse_error,
    )

