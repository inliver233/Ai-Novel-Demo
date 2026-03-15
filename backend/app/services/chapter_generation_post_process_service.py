from __future__ import annotations

import logging

from app.schemas.chapter_generate import ChapterGenerateRequest
from app.services.chapter_generation_models import PreparedChapterGenerateRequest
from app.services.generation_pipeline import run_content_optimize_step, run_post_edit_step


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

