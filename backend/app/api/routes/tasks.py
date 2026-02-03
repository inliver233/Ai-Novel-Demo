from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.api.deps import DbDep, UserIdDep, require_project_editor, require_project_viewer
from app.core.errors import AppError, ok_payload
from app.models.project_task import ProjectTask
from app.services.project_task_service import cancel_project_task, list_project_tasks, project_task_to_dict, retry_project_task

router = APIRouter()


@router.get("/projects/{project_id}/tasks")
def list_project_tasks_endpoint(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    status: str | None = Query(default=None, max_length=16),
    kind: str | None = Query(default=None, max_length=64),
    before: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    request_id = request.state.request_id
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    out = list_project_tasks(db=db, project_id=project_id, status=status, kind=kind, before=before, limit=limit)
    return ok_payload(request_id=request_id, data=out)


@router.get("/tasks/{task_id}")
def get_project_task_endpoint(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    task_id: str,
) -> dict:
    request_id = request.state.request_id
    task = db.get(ProjectTask, task_id)
    if task is None:
        raise AppError.not_found()
    require_project_viewer(db, project_id=str(task.project_id), user_id=user_id)
    return ok_payload(request_id=request_id, data=project_task_to_dict(task=task, include_payloads=True))


@router.post("/tasks/{task_id}/retry")
def retry_project_task_endpoint(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    task_id: str,
) -> dict:
    request_id = request.state.request_id
    task = db.get(ProjectTask, task_id)
    if task is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=str(task.project_id), user_id=user_id)
    retry_project_task(db=db, task=task)
    return ok_payload(request_id=request_id, data=project_task_to_dict(task=task, include_payloads=True))


@router.post("/tasks/{task_id}/cancel")
def cancel_project_task_endpoint(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    task_id: str,
) -> dict:
    request_id = request.state.request_id
    task = db.get(ProjectTask, task_id)
    if task is None:
        raise AppError.not_found()
    require_project_editor(db, project_id=str(task.project_id), user_id=user_id)
    cancel_project_task(db=db, task=task)
    return ok_payload(request_id=request_id, data=project_task_to_dict(task=task, include_payloads=True))
