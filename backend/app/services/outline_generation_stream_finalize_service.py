from __future__ import annotations

import json
from collections.abc import Callable

from app.services.generation_service import PreparedLlmCall
from app.services.outline_generation_models import OutlineSegmentGenerationResult
from app.services.run_store import write_generation_run


OutlineWarningsDedupe = Callable[[list[str]], list[str]]


def sanitize_outline_stream_result(data: dict[str, object]) -> dict[str, object]:
    result_data = dict(data)
    result_data.pop("raw_output", None)
    result_data.pop("raw_json", None)
    result_data.pop("fixed_json", None)
    return result_data


def finalize_segmented_outline_stream_result(
    *,
    segmented: OutlineSegmentGenerationResult,
    aggregate_run_id: str,
    dedupe_warnings: OutlineWarningsDedupe,
) -> dict[str, object]:
    data = dict(segmented.data)
    warnings = dedupe_warnings(segmented.warnings)
    if warnings:
        data["warnings"] = warnings
    if segmented.parse_error is not None:
        data["parse_error"] = segmented.parse_error
    data["generation_run_id"] = aggregate_run_id
    if segmented.run_ids:
        data["generation_sub_run_ids"] = segmented.run_ids
        data["generation_run_ids"] = [aggregate_run_id, *segmented.run_ids]
    if segmented.latency_ms > 0:
        data["latency_ms"] = segmented.latency_ms
    if segmented.dropped_params:
        data["dropped_params"] = segmented.dropped_params
    if segmented.finish_reasons:
        data["finish_reason"] = segmented.finish_reasons[-1]
        data["finish_reasons"] = segmented.finish_reasons
    data["segmented_generation"] = segmented.meta
    return sanitize_outline_stream_result(data)


def finalize_outline_stream_result(
    *,
    data: dict[str, object],
    warnings: list[str],
    parse_error: dict[str, object] | None,
    finish_reason: str | None,
    latency_ms: int | None,
    dropped_params: list[str],
    generation_run_id: str | None,
    dedupe_warnings: OutlineWarningsDedupe,
) -> dict[str, object]:
    finalized = dict(data)
    warnings_out = dedupe_warnings(warnings)
    if warnings_out:
        finalized["warnings"] = warnings_out
    if parse_error is not None:
        finalized["parse_error"] = parse_error
    if finish_reason is not None:
        finalized["finish_reason"] = finish_reason
    if latency_ms is not None:
        finalized["latency_ms"] = latency_ms
    if dropped_params:
        finalized["dropped_params"] = dropped_params
    if generation_run_id is not None:
        finalized["generation_run_id"] = generation_run_id
    return sanitize_outline_stream_result(finalized)


def write_outline_stream_error_run(
    *,
    stream_run_written: bool,
    request_id: str,
    actor_user_id: str,
    project_id: str,
    llm_call: PreparedLlmCall,
    prompt_system: str,
    prompt_user: str,
    prompt_render_log_json: str | None,
    run_params_json: str,
    output_text: str | None,
    error_payload: dict[str, object],
) -> None:
    if stream_run_written:
        return
    write_generation_run(
        request_id=request_id,
        actor_user_id=actor_user_id,
        project_id=project_id,
        chapter_id=None,
        run_type="outline_stream",
        provider=llm_call.provider,
        model=llm_call.model,
        prompt_system=prompt_system,
        prompt_user=prompt_user,
        prompt_render_log_json=prompt_render_log_json,
        params_json=run_params_json,
        output_text=output_text,
        error_json=json.dumps(error_payload, ensure_ascii=False),
    )
