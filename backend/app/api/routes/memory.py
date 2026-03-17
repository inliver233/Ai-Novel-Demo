from __future__ import annotations

import json
from fastapi import APIRouter, Header, Query, Request
from sqlalchemy import or_, select

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
from app.api.routes.memory_route_structured_helpers import (
    _count_structured_memory_rows,
    _list_structured_memory_table_page,
    _normalize_structured_memory_args,
)
from app.api.routes.memory_route_structured_models import STRUCTURED_MEMORY_TABLES
from app.core.errors import AppError, ok_payload
from app.db.utils import new_id, utc_now
from app.models.chapter import Chapter
from app.models.generation_run import GenerationRun
from app.models.memory_task import MemoryTask
from app.models.project_settings import ProjectSettings
from app.models.story_memory import StoryMemory
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

    if str(body.schema_version or "").strip() != "story_memory_import_v1":
        raise AppError.validation(details={"reason": "unsupported_schema_version", "schema_version": body.schema_version})

    created_ids: list[str] = []
    now = utc_now()
    for item in body.memories or []:
        title = str(item.title or "").strip() or None
        content = str(item.content or "").strip()
        if not content:
            continue
        row = StoryMemory(
            id=new_id(),
            project_id=project_id,
            chapter_id=None,
            memory_type=str(item.memory_type or "").strip(),
            title=title,
            content=content,
            full_context_md=None,
            importance_score=float(item.importance_score or 0.0),
            tags_json=None,
            story_timeline=int(item.story_timeline or 0),
            text_position=-1,
            text_length=0,
            is_foreshadow=int(item.is_foreshadow or 0),
            foreshadow_resolved_at_chapter_id=None,
            metadata_json=json.dumps({"source": "import_all"}, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        created_ids.append(str(row.id))

    if not created_ids:
        raise AppError.validation(message="未导入任何 story_memories", details={"reason": "empty"})

    settings_row = db.get(ProjectSettings, project_id)
    if settings_row is None:
        settings_row = ProjectSettings(project_id=project_id)
        db.add(settings_row)
    settings_row.vector_index_dirty = True

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

    q_norm = str(q or "").strip()
    order_norm = str(order or "").strip().lower() or "timeline_desc"
    allowed_orders = {"timeline_desc", "importance_desc", "updated_desc"}
    if order_norm not in allowed_orders:
        raise AppError.validation(message="不支持的排序字段", details={"order": order_norm, "allowed": sorted(allowed_orders)})

    filters = [
        StoryMemory.project_id == project_id,
        StoryMemory.is_foreshadow == 1,  # noqa: E712
        StoryMemory.foreshadow_resolved_at_chapter_id.is_(None),
    ]
    if q_norm:
        pattern = f"%{q_norm}%"
        filters.append(or_(StoryMemory.title.ilike(pattern), StoryMemory.content.ilike(pattern)))

    if order_norm == "importance_desc":
        order_by = (StoryMemory.importance_score.desc(), StoryMemory.story_timeline.desc(), StoryMemory.updated_at.desc())
    elif order_norm == "updated_desc":
        order_by = (StoryMemory.updated_at.desc(), StoryMemory.story_timeline.desc(), StoryMemory.importance_score.desc())
    else:
        order_by = (StoryMemory.story_timeline.desc(), StoryMemory.importance_score.desc(), StoryMemory.updated_at.desc())

    rows = (
        db.execute(
            select(StoryMemory)
            .where(*filters)
            .order_by(*order_by)
            .limit(int(limit) + 1)
        )
        .scalars()
        .all()
    )
    has_more = len(rows) > int(limit)
    rows = rows[: int(limit)]

    items = []
    for m in rows:
        content = str(m.content or "").strip()
        preview = (content[:200].rstrip() + "…") if len(content) > 200 else content
        items.append(
            {
                "id": m.id,
                "chapter_id": m.chapter_id,
                "memory_type": m.memory_type,
                "title": m.title,
                "importance_score": float(m.importance_score or 0.0),
                "story_timeline": int(m.story_timeline or 0),
                "is_foreshadow": bool(m.is_foreshadow),
                "resolved_at_chapter_id": m.foreshadow_resolved_at_chapter_id,
                "content_preview": preview,
                "updated_at": m.updated_at.isoformat() if m.updated_at else None,
            }
        )

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

    m = db.get(StoryMemory, story_memory_id)
    if m is None or str(m.project_id) != str(project_id):
        raise AppError.not_found()
    if not bool(getattr(m, "is_foreshadow", 0)):
        raise AppError.validation(message="该 StoryMemory 不是伏笔（foreshadow）", details={"story_memory_id": story_memory_id})

    resolved_at_chapter_id = str(body.resolved_at_chapter_id or "").strip() or None
    if resolved_at_chapter_id:
        chapter = db.get(Chapter, resolved_at_chapter_id)
        if chapter is None or str(getattr(chapter, "project_id", "")) != str(project_id):
            raise AppError.validation(
                message="回收章节（resolved_at_chapter_id）无效或不属于当前项目",
                details={"resolved_at_chapter_id": resolved_at_chapter_id},
            )

    m.foreshadow_resolved_at_chapter_id = resolved_at_chapter_id

    settings_row = db.get(ProjectSettings, project_id)
    if settings_row is None:
        settings_row = ProjectSettings(project_id=project_id)
        db.add(settings_row)
        db.flush()
    settings_row.vector_index_dirty = True

    db.commit()
    db.refresh(m)
    schedule_vector_rebuild_task(
        db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="story_memory_foreshadow_resolve"
    )
    schedule_search_rebuild_task(
        db=db, project_id=project_id, actor_user_id=user_id, request_id=request_id, reason="story_memory_foreshadow_resolve"
    )

    return ok_payload(
        request_id=request_id,
        data={
            "foreshadow": {
                "id": m.id,
                "project_id": m.project_id,
                "chapter_id": m.chapter_id,
                "memory_type": m.memory_type,
                "title": m.title,
                "importance_score": float(m.importance_score or 0.0),
                "story_timeline": int(m.story_timeline or 0),
                "is_foreshadow": bool(m.is_foreshadow),
                "resolved_at_chapter_id": m.foreshadow_resolved_at_chapter_id,
                "updated_at": m.updated_at.isoformat() if m.updated_at else None,
            }
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
