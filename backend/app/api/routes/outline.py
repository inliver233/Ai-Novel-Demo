from __future__ import annotations

import json
from collections.abc import Callable

from fastapi import APIRouter, Header, Request
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep, require_project_editor, require_project_viewer
from app.api.routes.outline_route_chapter_helpers import (
    _build_missing_neighbor_context,
    _build_outline_segment_chapter_index,
    _build_outline_segment_recent_window,
    _chapter_beats_count,
    _chapter_score,
    _clone_outline_chapters,
    _collect_missing_chapter_numbers,
    _compact_neighbor_chapter,
    _dedupe_warnings,
    _enforce_outline_chapter_coverage,
    _extract_outline_chapter_numbers,
    _format_chapter_number_ranges,
    _merge_segment_chapters,
    _normalize_outline_chapters,
    _outline_fill_detail_rule,
    _outline_fill_style_samples,
    _shrink_outline_segment_items,
)
from app.api.routes.outline_route_policy import (
    OUTLINE_FILL_HEARTBEAT_INTERVAL_SECONDS,
    OUTLINE_FILL_MAX_BATCH_SIZE,
    OUTLINE_FILL_MAX_TOTAL_ATTEMPTS,
    OUTLINE_FILL_MIN_BATCH_SIZE,
    OUTLINE_FILL_POLL_INTERVAL_SECONDS,
    OUTLINE_FILL_STAGNANT_ROUNDS_LIMIT,
    OUTLINE_GAP_REPAIR_BATCH_SIZE,
    OUTLINE_GAP_REPAIR_FINAL_SWEEP_ATTEMPTS_PER_CHAPTER,
    OUTLINE_GAP_REPAIR_FINAL_SWEEP_MAX_MISSING,
    OUTLINE_GAP_REPAIR_MAX_MISSING,
    OUTLINE_GAP_REPAIR_STAGNANT_LIMIT,
    OUTLINE_SEGMENT_DEFAULT_BATCH_SIZE,
    OUTLINE_SEGMENT_INDEX_MAX_CHARS,
    OUTLINE_SEGMENT_INDEX_MAX_ITEMS,
    OUTLINE_SEGMENT_MAX_ATTEMPTS_PER_BATCH,
    OUTLINE_SEGMENT_MAX_BATCH_SIZE,
    OUTLINE_SEGMENT_MIN_BATCH_SIZE,
    OUTLINE_SEGMENT_RECENT_CONTEXT_WINDOW,
    OUTLINE_SEGMENT_RECENT_WINDOW_MAX_CHARS,
    OUTLINE_SEGMENT_STAGNANT_ATTEMPTS_LIMIT,
    OUTLINE_SEGMENT_TRIGGER_CHAPTER_COUNT,
    OUTLINE_STREAM_RAW_PREVIEW_MAX_CHARS,
    _build_outline_generation_guidance,
    _extract_target_chapter_count,
    _outline_fill_batch_size_for_missing,
    _outline_fill_max_attempts_for_missing,
    _outline_fill_progress_message,
    _outline_gap_repair_max_attempts,
    _outline_segment_batch_size_for_target,
    _outline_segment_batches,
    _outline_segment_max_attempts_for_batch,
    _outline_segment_progress_message,
    _recommend_outline_max_tokens,
    _recommend_outline_segment_max_tokens,
    _should_use_outline_segmented_mode,
)
from app.api.routes.outline_route_prompt_helpers import (
    _build_outline_gap_repair_prompts,
    _build_outline_missing_chapters_prompts,
    _build_outline_segment_prompts,
    _build_outline_stream_raw_preview,
    _parse_outline_batch_output,
    _strip_segment_conflicting_prompt_sections,
)
from app.core.errors import ok_payload
from app.models.outline import Outline
from app.models.project_settings import ProjectSettings
from app.schemas.outline import OutlineOut, OutlineUpdate
from app.schemas.outline_generate import OutlineGenerateRequest
from app.services.outline_generation_app_service import (
    generate_outline as generate_outline_service,
    generate_outline_stream_events,
    prepare_outline_stream_request,
)
from app.services.outline_payload_normalizer import normalize_outline_content_and_structure, parse_outline_structure_json
from app.services.outline_store import ensure_active_outline
from app.services.search_index_service import schedule_search_rebuild_task
from app.services.vector_rag_service import schedule_vector_rebuild_task
from app.utils.sse_response import create_sse_response

router = APIRouter()

OutlineFillProgressHook = Callable[[dict[str, object]], None]
OutlineSegmentProgressHook = Callable[[dict[str, object]], None]

_OUTLINE_ROUTE_EXPORTS = (
    _build_missing_neighbor_context,
    _build_outline_segment_chapter_index,
    _build_outline_segment_recent_window,
    _chapter_beats_count,
    _chapter_score,
    _clone_outline_chapters,
    _collect_missing_chapter_numbers,
    _compact_neighbor_chapter,
    _dedupe_warnings,
    _enforce_outline_chapter_coverage,
    _extract_outline_chapter_numbers,
    _format_chapter_number_ranges,
    _merge_segment_chapters,
    _normalize_outline_chapters,
    _outline_fill_detail_rule,
    _outline_fill_style_samples,
    _shrink_outline_segment_items,
    OUTLINE_FILL_HEARTBEAT_INTERVAL_SECONDS,
    OUTLINE_FILL_MAX_BATCH_SIZE,
    OUTLINE_FILL_MAX_TOTAL_ATTEMPTS,
    OUTLINE_FILL_MIN_BATCH_SIZE,
    OUTLINE_FILL_POLL_INTERVAL_SECONDS,
    OUTLINE_FILL_STAGNANT_ROUNDS_LIMIT,
    OUTLINE_GAP_REPAIR_BATCH_SIZE,
    OUTLINE_GAP_REPAIR_FINAL_SWEEP_ATTEMPTS_PER_CHAPTER,
    OUTLINE_GAP_REPAIR_FINAL_SWEEP_MAX_MISSING,
    OUTLINE_GAP_REPAIR_MAX_MISSING,
    OUTLINE_GAP_REPAIR_STAGNANT_LIMIT,
    OUTLINE_SEGMENT_DEFAULT_BATCH_SIZE,
    OUTLINE_SEGMENT_INDEX_MAX_CHARS,
    OUTLINE_SEGMENT_INDEX_MAX_ITEMS,
    OUTLINE_SEGMENT_MAX_ATTEMPTS_PER_BATCH,
    OUTLINE_SEGMENT_MAX_BATCH_SIZE,
    OUTLINE_SEGMENT_MIN_BATCH_SIZE,
    OUTLINE_SEGMENT_RECENT_CONTEXT_WINDOW,
    OUTLINE_SEGMENT_RECENT_WINDOW_MAX_CHARS,
    OUTLINE_SEGMENT_STAGNANT_ATTEMPTS_LIMIT,
    OUTLINE_SEGMENT_TRIGGER_CHAPTER_COUNT,
    OUTLINE_STREAM_RAW_PREVIEW_MAX_CHARS,
    _build_outline_generation_guidance,
    _extract_target_chapter_count,
    _outline_fill_batch_size_for_missing,
    _outline_fill_max_attempts_for_missing,
    _outline_fill_progress_message,
    _outline_gap_repair_max_attempts,
    _outline_segment_batch_size_for_target,
    _outline_segment_batches,
    _outline_segment_max_attempts_for_batch,
    _outline_segment_progress_message,
    _recommend_outline_max_tokens,
    _recommend_outline_segment_max_tokens,
    _should_use_outline_segmented_mode,
    _build_outline_gap_repair_prompts,
    _build_outline_missing_chapters_prompts,
    _build_outline_segment_prompts,
    _build_outline_stream_raw_preview,
    _parse_outline_batch_output,
    _strip_segment_conflicting_prompt_sections,
)


def _outline_out(row: Outline) -> dict[str, object]:
    parsed_structure = parse_outline_structure_json(row.structure_json)
    content_md, structure, _ = normalize_outline_content_and_structure(content_md=row.content_md or "", structure=parsed_structure)
    return OutlineOut(
        id=row.id,
        project_id=row.project_id,
        title=row.title,
        content_md=content_md,
        structure=structure,
        created_at=row.created_at,
        updated_at=row.updated_at,
    ).model_dump()


def _mark_vector_index_dirty(db: DbDep, *, project_id: str) -> None:
    row = db.get(ProjectSettings, project_id)
    if row is None:
        row = ProjectSettings(project_id=project_id)
        db.add(row)
        db.flush()
    row.vector_index_dirty = True


@router.get("/projects/{project_id}/outline")
def get_outline(request: Request, db: DbDep, user_id: UserIdDep, project_id: str) -> dict:
    request_id = request.state.request_id
    project = require_project_viewer(db, project_id=project_id, user_id=user_id)
    row = db.get(Outline, project.active_outline_id) if project.active_outline_id else None
    if row is None:
        row = (
            db.execute(select(Outline).where(Outline.project_id == project_id).order_by(Outline.updated_at.desc()).limit(1))
            .scalars()
            .first()
        )
    if row is None:
        row = ensure_active_outline(db, project=project)
    return ok_payload(request_id=request_id, data={"outline": _outline_out(row)})


@router.put("/projects/{project_id}/outline")
def put_outline(request: Request, db: DbDep, user_id: UserIdDep, project_id: str, body: OutlineUpdate) -> dict:
    request_id = request.state.request_id
    project = require_project_editor(db, project_id=project_id, user_id=user_id)
    row = ensure_active_outline(db, project=project)

    if body.title is not None:
        row.title = body.title

    if body.content_md is not None:
        content_md, structure, normalized = normalize_outline_content_and_structure(
            content_md=body.content_md,
            structure=body.structure,
        )
        row.content_md = content_md
        if body.structure is not None or normalized:
            row.structure_json = json.dumps(structure, ensure_ascii=False) if structure is not None else None
    elif body.structure is not None:
        row.structure_json = json.dumps(body.structure, ensure_ascii=False)

    _mark_vector_index_dirty(db, project_id=project_id)
    db.commit()
    db.refresh(row)
    schedule_vector_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="outline_update")
    schedule_search_rebuild_task(db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="outline_update")
    return ok_payload(request_id=request_id, data={"outline": _outline_out(row)})


@router.post("/projects/{project_id}/outline/generate")
def generate_outline(
    request: Request,
    project_id: str,
    body: OutlineGenerateRequest,
    user_id: UserIdDep,
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider", max_length=64),
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key", max_length=4096),
) -> dict:
    request_id = request.state.request_id
    data = generate_outline_service(
        request_id=request_id,
        project_id=project_id,
        body=body,
        user_id=user_id,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
    )
    return ok_payload(request_id=request_id, data=data)


@router.post("/projects/{project_id}/outline/generate-stream")
def generate_outline_stream(
    request: Request,
    project_id: str,
    body: OutlineGenerateRequest,
    user_id: UserIdDep,
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider", max_length=64),
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key", max_length=4096),
):
    request_id = request.state.request_id
    prepared = prepare_outline_stream_request(
        project_id=project_id,
        body=body,
        user_id=user_id,
        request_id=request_id,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
    )
    return create_sse_response(
        generate_outline_stream_events(
            request_id=request_id,
            project_id=project_id,
            body=body,
            user_id=user_id,
            prepared=prepared,
        )
    )
