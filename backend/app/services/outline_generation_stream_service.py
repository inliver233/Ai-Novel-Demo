from __future__ import annotations

import concurrent.futures
import json
import logging
import threading
import time

from app.core.errors import AppError
from app.core.logging import log_event
from app.llm.client import call_llm_stream_messages
from app.schemas.outline_generate import OutlineGenerateRequest
from app.services.generation_service import call_llm_and_record, with_param_overrides
from app.services.outline_generation_fill_service import _fill_outline_missing_chapters_with_llm
from app.services.outline_generation_models import PreparedOutlineGeneration
from app.services.outline_generation_prepare_service import _write_outline_segmented_aggregate_run
from app.services.outline_generation_route_bridge import _outline_route
from app.services.outline_generation_segment_service import _generate_outline_segmented_with_llm
from app.services.output_contracts import build_repair_prompt_for_task, contract_for_task
from app.services.run_store import write_generation_run
from app.utils.sse_response import (
    sse_chunk,
    sse_done,
    sse_error,
    sse_heartbeat,
    sse_progress,
    sse_result,
)

logger = logging.getLogger("ainovel")


def generate_outline_stream_events(
    *,
    request_id: str,
    project_id: str,
    body: OutlineGenerateRequest,
    user_id: str,
    prepared: PreparedOutlineGeneration,
):
    outline_route = _outline_route()

    yield sse_progress(message="准备生成...", progress=0)

    prompt_system = prepared.prompt_system
    prompt_user = prepared.prompt_user
    prompt_messages = prepared.prompt_messages
    prompt_render_log_json = prepared.prompt_render_log_json
    llm_call = prepared.llm_call
    resolved_api_key = prepared.resolved_api_key
    target_chapter_count = prepared.target_chapter_count
    run_params_extra_json = prepared.run_params_extra_json
    run_params_json = prepared.run_params_json

    if outline_route._should_use_outline_segmented_mode(target_chapter_count):
        if target_chapter_count is None:
            yield sse_error(error="长篇分段模式参数异常", code=500)
            yield sse_done()
            return
        yield sse_progress(message="长篇模式：分段生成中...", progress=10)
        segment_progress_lock = threading.Lock()
        segment_progress_events: list[dict[str, object]] = []

        def _on_segment_progress(update: dict[str, object]) -> None:
            if not isinstance(update, dict):
                return
            with segment_progress_lock:
                segment_progress_events.append(dict(update))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                _generate_outline_segmented_with_llm,
                request_id=request_id,
                actor_user_id=user_id,
                project_id=project_id,
                api_key=str(resolved_api_key),
                llm_call=llm_call,
                prompt_system=prompt_system,
                prompt_user=prompt_user,
                target_chapter_count=target_chapter_count,
                run_params_extra_json=run_params_extra_json,
                progress_hook=_on_segment_progress,
            )

            last_ping = 0.0
            last_message = ""
            last_snapshot_key: tuple[str, int, int, int] | None = None
            last_raw_preview_key: tuple[str, int, int, int] | None = None
            while True:
                now = time.monotonic()
                if now - last_ping >= outline_route.OUTLINE_FILL_HEARTBEAT_INTERVAL_SECONDS:
                    yield sse_heartbeat()
                    last_ping = now
                with segment_progress_lock:
                    pending_snapshots = list(segment_progress_events)
                    segment_progress_events.clear()
                for snapshot in pending_snapshots:
                    event_name = str(snapshot.get("event") or "")
                    batch_idx = int(snapshot.get("batch_index") or 0)
                    attempt = int(snapshot.get("attempt") or 0)
                    completed_count = int(snapshot.get("completed_count") or 0)
                    snapshot_chapters = snapshot.get("chapters_snapshot")
                    snapshot_outline_md = str(snapshot.get("outline_md") or "")
                    if event_name in (
                        "batch_applied",
                        "fill_attempt_applied",
                        "fill_gap_repair_applied",
                        "fill_gap_repair_final_sweep_applied",
                    ) and isinstance(snapshot_chapters, list):
                        snapshot_key = (event_name, batch_idx, attempt, completed_count)
                        if snapshot_key != last_snapshot_key:
                            yield sse_result({"outline_md": snapshot_outline_md, "chapters": snapshot_chapters})
                            last_snapshot_key = snapshot_key
                    raw_preview = str(snapshot.get("raw_output_preview") or "").strip()
                    raw_chars_raw = snapshot.get("raw_output_chars")
                    try:
                        raw_chars = int(raw_chars_raw) if raw_chars_raw is not None else len(raw_preview)
                    except Exception:
                        raw_chars = len(raw_preview)
                    if raw_preview:
                        raw_key = (event_name, batch_idx, attempt, raw_chars)
                        if raw_key != last_raw_preview_key:
                            batch_count_raw = snapshot.get("batch_count")
                            try:
                                batch_count = int(batch_count_raw) if batch_count_raw is not None else 0
                            except Exception:
                                batch_count = 0
                            title_parts = [event_name or "segment"]
                            if batch_idx > 0 and batch_count > 0:
                                title_parts.append(f"batch {batch_idx}/{batch_count}")
                            elif batch_idx > 0:
                                title_parts.append(f"batch {batch_idx}")
                            if attempt > 0:
                                title_parts.append(f"attempt {attempt}")
                            title = " | ".join(title_parts)
                            yield sse_chunk(f"\n\n[{title}]\n{raw_preview}\n")
                            last_raw_preview_key = raw_key
                    progress_percent = snapshot.get("progress_percent")
                    if isinstance(progress_percent, int):
                        progress_num = max(10, min(98, progress_percent))
                    else:
                        progress_num = 10
                    message = outline_route._outline_segment_progress_message(snapshot)
                    if message != last_message:
                        yield sse_progress(message=message, progress=progress_num)
                        last_message = message
                if future.done():
                    break
                time.sleep(outline_route.OUTLINE_FILL_POLL_INTERVAL_SECONDS)

            segmented = future.result()

        aggregate_run_id = _write_outline_segmented_aggregate_run(
            request_id=request_id,
            actor_user_id=user_id,
            project_id=project_id,
            run_type="outline_stream_segmented",
            llm_call=llm_call,
            prompt_system=prompt_system,
            prompt_user=prompt_user,
            prompt_render_log_json=prompt_render_log_json,
            run_params_json=run_params_json,
            data=segmented.data,
            warnings=segmented.warnings,
            parse_error=segmented.parse_error,
            segmented_run_ids=segmented.run_ids,
            meta=segmented.meta,
        )
        data = dict(segmented.data)
        warnings = outline_route._dedupe_warnings(segmented.warnings)
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

        result_data = dict(data)
        result_data.pop("raw_output", None)
        result_data.pop("raw_json", None)
        result_data.pop("fixed_json", None)

        yield sse_progress(message="完成", progress=100, status="success")
        yield sse_result(result_data)
        yield sse_done()
        return

    yield sse_progress(message="调用模型...", progress=10)

    raw_output = ""
    generation_run_id: str | None = None
    finish_reason: str | None = None
    dropped_params: list[str] = []
    latency_ms: int | None = None
    stream_run_written = False

    try:
        stream_iter, state = call_llm_stream_messages(
            provider=llm_call.provider,
            base_url=llm_call.base_url,
            model=llm_call.model,
            api_key=str(resolved_api_key),
            messages=prompt_messages,
            params=llm_call.params,
            timeout_seconds=llm_call.timeout_seconds,
            extra=llm_call.extra,
        )

        last_progress = 10
        last_progress_ts = 0.0
        chunk_count = 0
        try:
            for delta in stream_iter:
                raw_output += delta
                yield sse_chunk(delta)
                chunk_count += 1
                if chunk_count % 12 == 0:
                    yield sse_heartbeat()
                now = time.monotonic()
                if now - last_progress_ts >= 0.8:
                    next_progress = 10 + int(min(1.0, len(raw_output) / 6000.0) * 80)
                    next_progress = max(last_progress, min(90, next_progress))
                    if next_progress != last_progress:
                        last_progress = next_progress
                        yield sse_progress(message="生成中...", progress=next_progress)
                    last_progress_ts = now
        finally:
            close = getattr(stream_iter, "close", None)
            if callable(close):
                close()

        finish_reason = state.finish_reason
        dropped_params = state.dropped_params
        latency_ms = state.latency_ms

        log_event(
            logger,
            "info",
            llm={
                "provider": llm_call.provider,
                "model": llm_call.model,
                "timeout_seconds": llm_call.timeout_seconds,
                "prompt_chars": len(prompt_system) + len(prompt_user),
                "output_chars": len(raw_output or ""),
                "dropped_params": dropped_params,
                "finish_reason": finish_reason,
                "stream": True,
            },
        )
        generation_run_id = write_generation_run(
            request_id=request_id,
            actor_user_id=user_id,
            project_id=project_id,
            chapter_id=None,
            run_type="outline_stream",
            provider=llm_call.provider,
            model=llm_call.model,
            prompt_system=prompt_system,
            prompt_user=prompt_user,
            prompt_render_log_json=prompt_render_log_json,
            params_json=run_params_json,
            output_text=raw_output,
            error_json=None,
        )
        stream_run_written = True

        yield sse_progress(message="解析输出...", progress=90)
        contract = contract_for_task("outline_generate")
        parsed = contract.parse(raw_output, finish_reason=finish_reason)
        data, warnings, parse_error = parsed.data, parsed.warnings, parsed.parse_error

        if parse_error is not None and llm_call.provider in (
            "openai",
            "openai_responses",
            "openai_compatible",
            "openai_responses_compatible",
        ):
            yield sse_progress(message="尝试修复 JSON...", progress=92)
            repair = build_repair_prompt_for_task("outline_generate", raw_output=raw_output)
            if repair is None:
                warnings.append("outline_fix_json_failed")
                repair = None
            if repair is None:
                raise AppError(code="OUTLINE_FIX_UNSUPPORTED", message="该任务不支持输出修复", status_code=400)
            fix_system, fix_user, fix_run_type = repair
            fix_call = with_param_overrides(llm_call, {"temperature": 0, "max_tokens": 1024})
            try:
                fixed = call_llm_and_record(
                    logger=logger,
                    request_id=request_id,
                    actor_user_id=user_id,
                    project_id=project_id,
                    chapter_id=None,
                    run_type=fix_run_type,
                    api_key=str(resolved_api_key),
                    prompt_system=fix_system,
                    prompt_user=fix_user,
                    llm_call=fix_call,
                    run_params_extra_json=run_params_extra_json,
                )
                fixed_parsed = contract.parse(fixed.text)
                fixed_data, fixed_warnings, fixed_error = (
                    fixed_parsed.data,
                    fixed_parsed.warnings,
                    fixed_parsed.parse_error,
                )
                if fixed_error is None and fixed_data.get("chapters"):
                    fixed_data["raw_output"] = raw_output
                    fixed_data["fixed_json"] = fixed_data.get("raw_json") or fixed.text
                    data = fixed_data
                    warnings.extend(["json_fixed_via_llm", *fixed_warnings])
                    parse_error = None
            except AppError:
                warnings.append("outline_fix_json_failed")

        if parse_error is None:
            data, coverage_warnings = outline_route._enforce_outline_chapter_coverage(
                data=data,
                target_chapter_count=target_chapter_count,
            )
            warnings.extend(coverage_warnings)
            preview_outline_md = str(data.get("outline_md") or "")
            preview_chapters, _preview_warnings = outline_route._normalize_outline_chapters(data.get("chapters"))
            if preview_chapters:
                yield sse_result(
                    {
                        "outline_md": preview_outline_md,
                        "chapters": outline_route._clone_outline_chapters(preview_chapters),
                    }
                )
            if target_chapter_count:
                yield sse_progress(message="补全缺失章节...", progress=94)
            fill_progress_lock = threading.Lock()
            fill_progress_events: list[dict[str, object]] = []

            def _on_fill_progress(update: dict[str, object]) -> None:
                if not isinstance(update, dict):
                    return
                with fill_progress_lock:
                    fill_progress_events.append(dict(update))

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                fill_future = executor.submit(
                    _fill_outline_missing_chapters_with_llm,
                    data=data,
                    target_chapter_count=target_chapter_count,
                    request_id=request_id,
                    actor_user_id=user_id,
                    project_id=project_id,
                    api_key=str(resolved_api_key),
                    llm_call=llm_call,
                    run_params_extra_json=run_params_extra_json,
                    progress_hook=_on_fill_progress,
                )

                last_ping = 0.0
                last_message = ""
                last_snapshot_marker: tuple[str, int] | None = None
                while True:
                    now = time.monotonic()
                    if now - last_ping >= outline_route.OUTLINE_FILL_HEARTBEAT_INTERVAL_SECONDS:
                        yield sse_heartbeat()
                        last_ping = now
                    with fill_progress_lock:
                        pending_fill_snapshots = list(fill_progress_events)
                        fill_progress_events.clear()
                    for snapshot in pending_fill_snapshots:
                        snapshot_event = str(snapshot.get("event") or "")
                        snapshot_attempt_raw = snapshot.get("attempt")
                        if isinstance(snapshot_attempt_raw, int):
                            snapshot_attempt = snapshot_attempt_raw
                        else:
                            try:
                                snapshot_attempt = (
                                    int(snapshot_attempt_raw) if snapshot_attempt_raw is not None else 0
                                )
                            except Exception:
                                snapshot_attempt = 0
                        snapshot_chapters = snapshot.get("chapters_snapshot")
                        snapshot_marker = (snapshot_event, snapshot_attempt)
                        if (
                            snapshot_event in (
                                "attempt_applied",
                                "gap_repair_applied",
                                "gap_repair_final_sweep_applied",
                            )
                            and snapshot_marker != last_snapshot_marker
                            and isinstance(snapshot_chapters, list)
                        ):
                            yield sse_result({"outline_md": preview_outline_md, "chapters": snapshot_chapters})
                            last_snapshot_marker = snapshot_marker
                        message = outline_route._outline_fill_progress_message(snapshot)
                        if message != last_message:
                            yield sse_progress(message=message, progress=94)
                            last_message = message
                    if fill_future.done():
                        break
                    time.sleep(outline_route.OUTLINE_FILL_POLL_INTERVAL_SECONDS)

                data, fill_warnings, fill_run_ids = fill_future.result()
            warnings.extend(fill_warnings)
            if fill_run_ids:
                coverage = data.get("chapter_coverage")
                if isinstance(coverage, dict):
                    coverage["fill_run_ids"] = fill_run_ids
                    data["chapter_coverage"] = coverage

        warnings = outline_route._dedupe_warnings(warnings)
        if warnings:
            data["warnings"] = warnings
        if parse_error is not None:
            data["parse_error"] = parse_error
        if finish_reason is not None:
            data["finish_reason"] = finish_reason
        if latency_ms is not None:
            data["latency_ms"] = latency_ms
        if dropped_params:
            data["dropped_params"] = dropped_params
        if generation_run_id is not None:
            data["generation_run_id"] = generation_run_id

        result_data = dict(data)
        result_data.pop("raw_output", None)
        result_data.pop("raw_json", None)
        result_data.pop("fixed_json", None)

        yield sse_progress(message="完成", progress=100, status="success")
        yield sse_result(result_data)
        yield sse_done()
    except GeneratorExit:
        return
    except AppError as exc:
        if not stream_run_written:
            write_generation_run(
                request_id=request_id,
                actor_user_id=user_id,
                project_id=project_id,
                chapter_id=None,
                run_type="outline_stream",
                provider=llm_call.provider,
                model=llm_call.model,
                prompt_system=prompt_system,
                prompt_user=prompt_user,
                prompt_render_log_json=prompt_render_log_json,
                params_json=run_params_json,
                output_text=raw_output or None,
                error_json=json.dumps({"code": exc.code, "message": exc.message, "details": exc.details}, ensure_ascii=False),
            )
        yield sse_error(error=f"{exc.message} ({exc.code})", code=exc.status_code)
        yield sse_done()
    except Exception:
        if not stream_run_written:
            write_generation_run(
                request_id=request_id,
                actor_user_id=user_id,
                project_id=project_id,
                chapter_id=None,
                run_type="outline_stream",
                provider=llm_call.provider,
                model=llm_call.model,
                prompt_system=prompt_system,
                prompt_user=prompt_user,
                prompt_render_log_json=prompt_render_log_json,
                params_json=run_params_json,
                output_text=raw_output or None,
                error_json=json.dumps({"code": "INTERNAL_ERROR", "message": "服务器内部错误"}, ensure_ascii=False),
            )
        yield sse_error(error="服务器内部错误", code=500)
        yield sse_done()

