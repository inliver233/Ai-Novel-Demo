from __future__ import annotations

import time
from typing import Iterator

from fastapi import APIRouter, Query, Request

from app.api.deps import DbDep, UserIdDep, require_project_editor, require_project_viewer
from app.core.errors import AppError, ok_payload
from app.db.session import SessionLocal
from app.models.project_task import ProjectTask
from app.services.project_task_event_service import (
    build_project_task_active_snapshot,
    list_project_task_events_after,
    project_task_event_to_dict,
)
from app.services.project_task_runtime_view_service import build_project_task_runtime_view
from app.services.project_task_service import cancel_project_task, list_project_tasks, project_task_to_dict, retry_project_task
from app.utils.sse_response import create_sse_response, format_sse, sse_heartbeat

router = APIRouter()

_PROJECT_TASK_SSE_RETRY_MS = 1500
_PROJECT_TASK_SSE_POLL_INTERVAL_SECONDS = 1.0
_PROJECT_TASK_SSE_HEARTBEAT_SECONDS = 10.0
_PROJECT_TASK_SSE_TIMEOUT_SECONDS = 25.0


def _parse_event_cursor(value: str | None) -> int:
    raw = str(value or "").strip()
    if not raw:
        return 0
    try:
        parsed = int(raw)
    except Exception:
        return 0
    return parsed if parsed > 0 else 0


@router.get("/projects/{project_id}/task-events/stream")
def stream_project_task_events(
    request: Request,
    db: DbDep,
    user_id: UserIdDep,
    project_id: str,
    last_event_id: str | None = Query(default=None, alias="lastEventId", max_length=64),
    stream_timeout_seconds: float = Query(default=_PROJECT_TASK_SSE_TIMEOUT_SECONDS, ge=0.1, le=120.0),
):
    require_project_viewer(db, project_id=project_id, user_id=user_id)
    db.close()

    after_seq = _parse_event_cursor(request.headers.get("Last-Event-ID") or last_event_id)

    def event_stream() -> Iterator[str]:
        cursor = after_seq
        last_emit_at = time.monotonic()
        deadline = time.monotonic() + float(stream_timeout_seconds)

        if cursor <= 0:
            snapshot_db = SessionLocal()
            try:
                snapshot = build_project_task_active_snapshot(snapshot_db, project_id=project_id)
            finally:
                snapshot_db.close()
            cursor = int(snapshot.get("cursor") or 0)
            last_emit_at = time.monotonic()
            yield format_sse(
                {"type": "snapshot", **snapshot},
                event="snapshot",
                event_id=str(cursor),
                retry=_PROJECT_TASK_SSE_RETRY_MS,
            )

        while time.monotonic() < deadline:
            stream_db = SessionLocal()
            try:
                events = list_project_task_events_after(stream_db, project_id=project_id, after_seq=cursor)
            finally:
                stream_db.close()

            if events:
                for event in events:
                    payload = {"type": "event", **project_task_event_to_dict(event)}
                    cursor = int(payload.get("seq") or cursor)
                    last_emit_at = time.monotonic()
                    yield format_sse(
                        payload,
                        event="project_task",
                        event_id=str(cursor),
                        retry=_PROJECT_TASK_SSE_RETRY_MS,
                    )
                continue

            now = time.monotonic()
            if now - last_emit_at >= _PROJECT_TASK_SSE_HEARTBEAT_SECONDS:
                last_emit_at = now
                yield sse_heartbeat()
            time.sleep(_PROJECT_TASK_SSE_POLL_INTERVAL_SECONDS)

    return create_sse_response(event_stream())


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


@router.get("/tasks/{task_id}/runtime")
def get_project_task_runtime_endpoint(
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
    return ok_payload(request_id=request_id, data=build_project_task_runtime_view(db, task_id=task_id))


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
