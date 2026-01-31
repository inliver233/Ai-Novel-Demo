from __future__ import annotations

import json

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import DbDep, UserIdDep, require_chapter_editor, require_project_editor, require_project_viewer
from app.core.errors import AppError, ok_payload
from app.db.utils import new_id
from app.models.batch_generation_task import BatchGenerationTask, BatchGenerationTaskItem
from app.models.chapter import Chapter
from app.schemas.batch_generation import BatchGenerationCreateRequest, BatchGenerationTaskItemOut, BatchGenerationTaskOut
from app.services.outline_store import ensure_active_outline
from app.services.task_queue import get_task_queue

router = APIRouter()


@router.post("/projects/{project_id}/batch_generation_tasks")
def create_batch_generation_task(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    body: BatchGenerationCreateRequest,
) -> dict:
    request_id = request.state.request_id
    project = require_project_editor(db, project_id=project_id, user_id=user_id)

    existing = (
        db.execute(
            select(BatchGenerationTask)
            .where(
                BatchGenerationTask.project_id == project_id,
                BatchGenerationTask.status.in_(["queued", "running"]),
            )
            .order_by(BatchGenerationTask.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if existing is not None:
        raise AppError.conflict(message="已有进行中的批量生成任务，请先取消或等待完成", details={"task_id": existing.id})

    if body.after_chapter_id:
        after = require_chapter_editor(db, chapter_id=body.after_chapter_id, user_id=user_id)
        if after.project_id != project_id:
            raise AppError.validation(message="起始章节（after_chapter_id）不属于当前项目")
        outline_id = after.outline_id
        start_number = int(after.number) + 1
    else:
        outline_id = ensure_active_outline(db, project=project).id
        start_number = 1

    limit = max(int(body.count) * 5, int(body.count))
    candidates = (
        db.execute(
            select(Chapter)
            .where(
                Chapter.project_id == project_id,
                Chapter.outline_id == outline_id,
                Chapter.number >= start_number,
            )
            .order_by(Chapter.number.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    def _is_empty(ch: Chapter) -> bool:
        return not ((ch.content_md or "").strip() or (ch.summary or "").strip())

    selected: list[Chapter] = []
    for ch in candidates:
        if not body.include_existing and not _is_empty(ch):
            continue
        selected.append(ch)
        if len(selected) >= int(body.count):
            break

    if not selected:
        raise AppError.validation(message="没有可生成的章节（请先创建章节，或开启 include_existing）")
    if len(selected) < int(body.count):
        raise AppError.validation(
            message=f"目标章节不足：仅找到 {len(selected)} 章可生成，请减少数量或开启 include_existing",
            details={"found": len(selected), "required": int(body.count)},
        )

    if body.context.require_sequential:
        selected_numbers = {int(ch.number) for ch in selected}
        max_num = max(selected_numbers)
        if max_num > 1:
            prev_rows = db.execute(
                select(Chapter.number, Chapter.content_md, Chapter.summary).where(
                    Chapter.project_id == project_id,
                    Chapter.outline_id == outline_id,
                    Chapter.number < max_num,
                )
            ).all()
            existing = {int(r[0]): (r[1], r[2]) for r in prev_rows}
            missing_numbers: list[int] = []
            for n in range(1, max_num):
                if n in selected_numbers:
                    continue
                content_md, summary = existing.get(n, (None, None))
                if not ((content_md or "").strip() or (summary or "").strip()):
                    missing_numbers.append(n)
            if missing_numbers:
                raise AppError(
                    code="CHAPTER_PREREQ_MISSING",
                    message=f"缺少前置章节内容：第 {', '.join(str(n) for n in missing_numbers)} 章",
                    status_code=400,
                    details={"missing_numbers": missing_numbers},
                )

    task_id = new_id()
    task = BatchGenerationTask(
        id=task_id,
        project_id=project_id,
        outline_id=outline_id,
        actor_user_id=user_id,
        status="queued",
        total_count=len(selected),
        completed_count=0,
        cancel_requested=False,
        params_json=json.dumps(body.model_dump(), ensure_ascii=False),
        error_json=None,
    )
    items = [
        BatchGenerationTaskItem(
            id=new_id(),
            task_id=task_id,
            chapter_id=ch.id,
            chapter_number=int(ch.number),
            status="queued",
            generation_run_id=None,
            error_message=None,
        )
        for ch in selected
    ]

    db.add(task)
    db.add_all(items)
    db.commit()

    try:
        get_task_queue().enqueue_batch_generation_task(task_id)
    except AppError as exc:
        task.status = "failed"
        task.error_json = json.dumps({"code": exc.code, "message": exc.message, "details": exc.details}, ensure_ascii=False)
        for item in items:
            if item.status == "queued":
                item.status = "failed"
                item.error_message = f"{exc.message} ({exc.code})"
        db.commit()
        raise

    # In inline mode, the worker runs synchronously (separate session) and updates task/items.
    # Ensure we return fresh statuses/generation_run_id for the UI to apply results.
    db.expire_all()
    task = db.get(BatchGenerationTask, task_id) or task
    items = (
        db.execute(
            select(BatchGenerationTaskItem)
            .where(BatchGenerationTaskItem.task_id == task_id)
            .order_by(BatchGenerationTaskItem.chapter_number.asc())
        )
        .scalars()
        .all()
    )

    out_task = BatchGenerationTaskOut.model_validate(task).model_dump()
    out_items = [BatchGenerationTaskItemOut.model_validate(i).model_dump() for i in items]
    return ok_payload(request_id=request_id, data={"task": out_task, "items": out_items})


@router.get("/projects/{project_id}/batch_generation_tasks/active")
def get_active_batch_generation_task(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)

    task = (
        db.execute(
            select(BatchGenerationTask)
            .where(
                BatchGenerationTask.project_id == project_id,
            )
            .order_by(BatchGenerationTask.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    if task is None:
        return ok_payload(request_id=request_id, data={"task": None, "items": []})

    items = (
        db.execute(select(BatchGenerationTaskItem).where(BatchGenerationTaskItem.task_id == task.id).order_by(BatchGenerationTaskItem.chapter_number.asc()))
        .scalars()
        .all()
    )
    out_task = BatchGenerationTaskOut.model_validate(task).model_dump()
    out_items = [BatchGenerationTaskItemOut.model_validate(i).model_dump() for i in items]
    return ok_payload(request_id=request_id, data={"task": out_task, "items": out_items})


@router.get("/batch_generation_tasks/{task_id}")
def get_batch_generation_task(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    task_id: str,
) -> dict:
    request_id = request.state.request_id
    task = db.get(BatchGenerationTask, task_id)
    if task is None:
        raise AppError.not_found()
    require_project_viewer(db, project_id=task.project_id, user_id=user_id)
    items = (
        db.execute(select(BatchGenerationTaskItem).where(BatchGenerationTaskItem.task_id == task_id).order_by(BatchGenerationTaskItem.chapter_number.asc()))
        .scalars()
        .all()
    )
    out_task = BatchGenerationTaskOut.model_validate(task).model_dump()
    out_items = [BatchGenerationTaskItemOut.model_validate(i).model_dump() for i in items]
    return ok_payload(request_id=request_id, data={"task": out_task, "items": out_items})


@router.post("/batch_generation_tasks/{task_id}/cancel")
def cancel_batch_generation_task(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    task_id: str,
) -> dict:
    request_id = request.state.request_id
    task = db.get(BatchGenerationTask, task_id)
    if task is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=task.project_id, user_id=user_id)

    if task.status not in ("queued", "running"):
        return ok_payload(request_id=request_id, data={"task": BatchGenerationTaskOut.model_validate(task).model_dump(), "canceled": False})

    if task.cancel_requested:
        return ok_payload(request_id=request_id, data={"task": BatchGenerationTaskOut.model_validate(task).model_dump(), "canceled": False})

    task.cancel_requested = True
    if task.status == "queued":
        task.status = "canceled"
        items = (
            db.execute(
                select(BatchGenerationTaskItem).where(
                    BatchGenerationTaskItem.task_id == task_id, BatchGenerationTaskItem.status == "queued"
                )
            )
            .scalars()
            .all()
        )
        for item in items:
            item.status = "canceled"

    db.commit()
    return ok_payload(request_id=request_id, data={"task": BatchGenerationTaskOut.model_validate(task).model_dump(), "canceled": True})
