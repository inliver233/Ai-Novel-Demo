from __future__ import annotations

from fastapi import APIRouter, Header, Query, Request

from app.api.deps import DbDep, UserIdDep, require_chapter_editor, require_project_editor, require_project_viewer
from app.api.routes.memory_route_helpers import (
    _build_memory_pack_payload,
    _normalize_memory_auto_propose_args,
)
from app.api.routes.memory_route_models import (
    MemoryAutoProposeRequest,
    StoryMemoryForeshadowResolveRequest,
    StoryMemoryImportV1Request,
)
from app.api.routes.memory_route_story_helpers import (
    _ensure_story_memory_rebuild_dirty,
    _list_story_memory_open_loop_rows,
    _normalize_story_memory_open_loops_args,
    _normalize_story_memory_resolved_at_chapter_id,
    _require_story_memory_foreshadow,
    _validate_story_memory_import_schema_version,
)
from app.api.routes.memory_route_story_mappers import (
    _build_story_memory_foreshadow_payload,
    _build_story_memory_import_row,
    _build_story_memory_open_loop_item,
)
from app.api.routes.memory_route_structured_helpers import (
    _count_structured_memory_rows,
    _list_structured_memory_table_page,
    _normalize_structured_memory_args,
)
from app.api.routes.memory_route_structured_models import STRUCTURED_MEMORY_TABLES
from app.core.errors import AppError, ok_payload
from app.db.utils import utc_now
from app.models.chapter import Chapter
from app.models.generation_run import GenerationRun
from app.models.memory_task import MemoryTask
from app.models.structured_memory import MemoryChangeSet
from app.schemas.memory_update import MemoryUpdateV1Request
from app.schemas.memory_preview import MemoryPreviewRequest
from app.services.memory_auto_update_app_service import (
    auto_propose_chapter_memory_update as auto_propose_chapter_memory_update_service,
    require_chapter_done_for_memory_update,
)
from app.services.memory_retrieval_service import retrieve_memory_context_pack
from app.services.memory_update_service import (
    apply_memory_change_set,
    list_memory_change_sets,
    list_memory_tasks,
    memory_task_to_dict,
    propose_chapter_memory_change_set,
    propose_project_table_change_set,
    retry_memory_task,
    rollback_memory_change_set,
)
from app.services.table_executor import TableUpdateV1Request
from app.services.search_index_service import schedule_search_rebuild_task
from app.services.vector_rag_service import schedule_vector_rebuild_task

router = APIRouter()


@router.get("/projects/{project_id}/memory/retrieve")
def retrieve_project_memory(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    query_text: str = Query(default="", max_length=5000),
    include_deleted: bool = Query(default=False),
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    pack = retrieve_memory_context_pack(db=db, project_id=project_id, query_text=query_text, include_deleted=include_deleted)
    return ok_payload(request_id=request_id, data=_build_memory_pack_payload(pack))


@router.post("/projects/{project_id}/memory/preview")
def preview_project_memory(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: MemoryPreviewRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    pack = retrieve_memory_context_pack(
        db=db,
        project_id=project_id,
        query_text=body.query_text,
        include_deleted=False,
        section_enabled=body.section_enabled,
        budget_overrides=body.budget_overrides,
    )
    return ok_payload(request_id=request_id, data=_build_memory_pack_payload(pack))


@router.post("/projects/{project_id}/story_memories/import_all")
def import_all_story_memories(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: StoryMemoryImportV1Request,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    _validate_story_memory_import_schema_version(body.schema_version)
    now = utc_now()
    rows = []
    for item in body.memories or []:
        row = _build_story_memory_import_row(project_id=project_id, item=item, now=now)
        if row is None:
            continue
        rows.append(row)
        db.add(row)

    created_ids = [str(row.id) for row in rows]
    if not created_ids:
        raise AppError.validation(message="未导入任何 story_memories", details={"reason": "empty"})

    _ensure_story_memory_rebuild_dirty(db, project_id=project_id)
    db.commit()
    schedule_vector_rebuild_task(
        db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="story_memory_import_all"
    )
    schedule_search_rebuild_task(
        db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="story_memory_import_all"
    )
    return ok_payload(request_id=request_id, data={"created": len(created_ids), "ids": created_ids})
@router.get("/projects/{project_id}/story_memories/foreshadows/open_loops")
def list_story_memory_foreshadow_open_loops(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, max_length=200),
    order: str = Query(default="timeline_desc", max_length=32),
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)

    args = _normalize_story_memory_open_loops_args(q=q, order=order)
    rows, has_more = _list_story_memory_open_loop_rows(db, project_id=project_id, limit=limit, args=args)
    items = [_build_story_memory_open_loop_item(row) for row in rows]

    return ok_payload(request_id=request_id, data={"items": items, "has_more": bool(has_more), "returned": len(items)})


@router.post("/projects/{project_id}/story_memories/foreshadows/{story_memory_id}/resolve")
def resolve_story_memory_foreshadow(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    story_memory_id: str,
    body: StoryMemoryForeshadowResolveRequest,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)

    row = _require_story_memory_foreshadow(db, project_id=project_id, story_memory_id=story_memory_id)
    resolved_at_chapter_id = _normalize_story_memory_resolved_at_chapter_id(
        db,
        project_id=project_id,
        resolved_at_chapter_id=body.resolved_at_chapter_id,
    )
    row.foreshadow_resolved_at_chapter_id = resolved_at_chapter_id
    _ensure_story_memory_rebuild_dirty(db, project_id=project_id, flush_on_create=True)

    db.commit()
    db.refresh(row)
    schedule_vector_rebuild_task(
        db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="story_memory_foreshadow_resolve"
    )
    schedule_search_rebuild_task(
        db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="story_memory_foreshadow_resolve"
    )

    return ok_payload(
        request_id=request_id,
        data={
            "foreshadow": _build_story_memory_foreshadow_payload(row)
        },
    )
@router.get("/projects/{project_id}/memory/structured")
def list_structured_memory(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    include_deleted: bool = Query(default=False),
    table: str | None = Query(default=None, max_length=32),
    q: str | None = Query(default=None, max_length=200),
    before: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)

    args = _normalize_structured_memory_args(table=table, q=q, before=before, limit=limit)
    counts = {
        table_name: _count_structured_memory_rows(
            db,
            project_id=project_id,
            table_name=table_name,
            include_deleted=include_deleted,
            pattern=args.pattern,
        )
        for table_name in STRUCTURED_MEMORY_TABLES
    }

    data: dict[str, object] = {"counts": counts, "cursor": {}, "table": args.table, "q": args.keyword}
    cursors: dict[str, str | None] = {table_name: None for table_name in STRUCTURED_MEMORY_TABLES}

    for table_name in STRUCTURED_MEMORY_TABLES:
        if args.table not in (None, table_name):
            data[table_name] = []
            continue
        page = _list_structured_memory_table_page(
            db,
            project_id=project_id,
            table_name=table_name,
            include_deleted=include_deleted,
            pattern=args.pattern,
            before_dt=args.before_dt if args.table == table_name else None,
            limit=limit,
        )
        data[table_name] = page.items
        cursors[table_name] = page.cursor

    data["cursor"] = cursors
    return ok_payload(request_id=request_id, data=data)


@router.post("/chapters/{chapter_id}/memory/propose")
def propose_chapter_memory_update(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    chapter_id: str,
    body: MemoryUpdateV1Request,
    allow_draft: bool = Query(default=False),
) -> dict:
    request_id = request.state.request_id
    chapter = require_chapter_editor(db, chapter_id=chapter_id, user_id=user_id)
    require_chapter_done_for_memory_update(db=db, chapter=chapter, user_id=user_id, allow_draft=allow_draft)
    out = propose_chapter_memory_change_set(db=db, request_id=request_id, actor_user_id=user_id, chapter=chapter, payload=body)
    return ok_payload(request_id=request_id, data=out)


@router.post("/projects/{project_id}/tables/change_sets/propose")
def propose_project_table_update(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: TableUpdateV1Request,
) -> dict:
    request_id = request.state.request_id
    require_project_editor(db, project_id=project_id, user_id=user_id)
    out = propose_project_table_change_set(
        db=db,
        request_id=request_id,
        actor_user_id=user_id,
        project_id=project_id,
        payload=body,
    )
    return ok_payload(request_id=request_id, data=out)


@router.post("/chapters/{chapter_id}/memory/propose/auto")
def auto_propose_chapter_memory_update(
    request: Request,
    chapter_id: str,
    body: MemoryAutoProposeRequest,
    user_id: UserIdDep,
    allow_draft: bool = Query(default=False),
    x_llm_provider: str | None = Header(default=None, alias="X-LLM-Provider", max_length=64),
    x_llm_api_key: str | None = Header(default=None, alias="X-LLM-API-Key", max_length=4096),
) -> dict:
    request_id = request.state.request_id
    focus, idempotency_key = _normalize_memory_auto_propose_args(
        focus=body.focus,
        idempotency_key=body.idempotency_key,
    )
    out = auto_propose_chapter_memory_update_service(
        request_id=request_id,
        chapter_id=chapter_id,
        focus=focus,
        user_id=user_id,
        allow_draft=allow_draft,
        x_llm_provider=x_llm_provider,
        x_llm_api_key=x_llm_api_key,
        idempotency_key=idempotency_key,
    )
    return ok_payload(request_id=request_id, data=out)


@router.post("/memory_change_sets/{change_set_id}/apply")
def apply_memory_update(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    change_set_id: str,
    allow_draft: bool = Query(default=False),
) -> dict:
    request_id = request.state.request_id
    change_set = db.get(MemoryChangeSet, change_set_id)
    if change_set is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=str(change_set.project_id), user_id=user_id)

    run = db.get(GenerationRun, str(change_set.generation_run_id)) if change_set.generation_run_id else None
    chapter_id = str(getattr(run, "chapter_id", "") or "").strip()
    if chapter_id:
        chapter = db.get(Chapter, chapter_id)
        if chapter is not None:
            require_chapter_done_for_memory_update(db=db, chapter=chapter, user_id=user_id, allow_draft=allow_draft)

    out = apply_memory_change_set(db=db, request_id=request_id, actor_user_id=user_id, change_set=change_set)
    return ok_payload(request_id=request_id, data=out)


@router.get("/projects/{project_id}/memory_change_sets")
def list_project_memory_change_sets(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    status: str | None = Query(default=None, max_length=16),
    before: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    out = list_memory_change_sets(db=db, project_id=project_id, status=status, before=before, limit=limit)
    return ok_payload(request_id=request_id, data=out)


@router.get("/projects/{project_id}/memory_tasks")
def list_project_memory_tasks(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    status: str | None = Query(default=None, max_length=16),
    before: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    out = list_memory_tasks(db=db, project_id=project_id, status=status, before=before, limit=limit)
    return ok_payload(request_id=request_id, data=out)


@router.get("/memory_tasks/{task_id}")
def get_memory_task(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    task_id: str,
) -> dict:
    request_id = request.state.request_id
    task = db.get(MemoryTask, task_id)
    if task is None:
        raise AppError.not_found()
    require_project_viewer(db, project_id=str(task.project_id), user_id=user_id)
    change_set = db.get(MemoryChangeSet, str(task.change_set_id))
    return ok_payload(request_id=request_id, data=memory_task_to_dict(task=task, change_set_request_id=change_set.request_id if change_set else None))


@router.post("/memory_tasks/{task_id}/retry")
def retry_memory_task_endpoint(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    task_id: str,
) -> dict:
    request_id = request.state.request_id
    task = db.get(MemoryTask, task_id)
    if task is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=str(task.project_id), user_id=user_id)

    retry_memory_task(db=db, request_id=request_id, task=task)
    change_set = db.get(MemoryChangeSet, str(task.change_set_id))
    return ok_payload(
        request_id=request_id,
        data=memory_task_to_dict(task=task, change_set_request_id=change_set.request_id if change_set else None),
    )


@router.post("/memory_change_sets/{change_set_id}/rollback")
def rollback_memory_update(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    change_set_id: str,
) -> dict:
    request_id = request.state.request_id
    change_set = db.get(MemoryChangeSet, change_set_id)
    if change_set is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=str(change_set.project_id), user_id=user_id)
    out = rollback_memory_change_set(db=db, request_id=request_id, actor_user_id=user_id, change_set=change_set)
    return ok_payload(request_id=request_id, data=out)
