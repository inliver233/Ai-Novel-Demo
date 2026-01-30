from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.logging import exception_log_fields, log_event
from app.core.secrets import redact_api_keys
from app.db.session import SessionLocal
from app.models.project_task import ProjectTask
from app.db.utils import utc_now

logger = logging.getLogger("ainovel")


_ALLOWED_TASK_STATUSES_QUERY = {"queued", "running", "failed", "done", "succeeded"}
_TASK_DONE_ALIASES = {"succeeded", "done"}


def _compact_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _compact_json_loads(value: str | None) -> Any | None:
    if value is None:
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    s = dt.isoformat()
    return s.replace("+00:00", "Z")


def _parse_dt(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _task_status_to_public(status: str) -> str:
    s = str(status or "").strip().lower()
    return "done" if s in _TASK_DONE_ALIASES else s


def _task_error_fields(task: ProjectTask) -> tuple[str | None, str | None]:
    value = _compact_json_loads(task.error_json) if task.error_json else None
    if not isinstance(value, dict):
        return None, None
    error_type = str(value.get("error_type") or "").strip() or None
    error_message = str(value.get("message") or "").strip() or None
    return error_type, error_message


def project_task_to_dict(*, task: ProjectTask, include_payloads: bool) -> dict[str, Any]:
    error_type, error_message = _task_error_fields(task)

    data: dict[str, Any] = {
        "id": str(task.id),
        "project_id": str(task.project_id),
        "actor_user_id": task.actor_user_id,
        "kind": str(task.kind),
        "status": _task_status_to_public(str(task.status)),
        "idempotency_key": str(getattr(task, "idempotency_key", "") or ""),
        "error_type": error_type,
        "error_message": error_message,
        "timings": {
            "created_at": _iso(task.created_at),
            "started_at": _iso(task.started_at),
            "finished_at": _iso(task.finished_at),
            "updated_at": _iso(task.updated_at),
        },
    }

    if include_payloads:
        params = _compact_json_loads(task.params_json) if task.params_json else None
        result = _compact_json_loads(task.result_json) if task.result_json else None
        err = _compact_json_loads(task.error_json) if task.error_json else None
        data["params"] = redact_api_keys(params) if params is not None else None
        data["result"] = redact_api_keys(result) if result is not None else None
        data["error"] = redact_api_keys(err) if err is not None else None

    return data


def list_project_tasks(
    *,
    db: Session,
    project_id: str,
    status: str | None,
    kind: str | None,
    before: str | None,
    limit: int,
) -> dict[str, Any]:
    status_norm = str(status or "").strip().lower() or None
    if status_norm is not None:
        if status_norm == "succeeded":
            status_norm = "done"
        if status_norm not in _ALLOWED_TASK_STATUSES_QUERY:
            raise AppError.validation(details={"reason": "invalid_status", "status": status})

    kind_norm = str(kind or "").strip() or None

    before_raw = str(before or "").strip()
    before_dt = _parse_dt(before_raw) if before_raw else None
    if before_raw and before_dt is None:
        raise AppError.validation(details={"reason": "invalid_before", "before": before})

    q = select(ProjectTask).where(ProjectTask.project_id == project_id)
    if status_norm is not None:
        if status_norm == "done":
            q = q.where(ProjectTask.status.in_(sorted(_TASK_DONE_ALIASES)))
        else:
            q = q.where(ProjectTask.status == status_norm)
    if kind_norm is not None:
        q = q.where(ProjectTask.kind == kind_norm)
    if before_dt is not None:
        q = q.where(ProjectTask.created_at < before_dt)

    rows = db.execute(q.order_by(ProjectTask.created_at.desc(), ProjectTask.id.desc()).limit(limit + 1)).scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    items = [project_task_to_dict(task=t, include_payloads=False) for t in rows]
    next_before = _iso(rows[-1].created_at) if (has_more and rows) else None
    return {"items": items, "next_before": next_before}


def retry_project_task(*, db: Session, task: ProjectTask) -> ProjectTask:
    """
    Idempotent retry for failed ProjectTask.

    Note: actual enqueue/worker execution is handled by the queue backend / worker entrypoint.
    """

    status_norm = str(getattr(task, "status", "") or "").strip().lower()
    if status_norm != "failed":
        return task

    task.status = "queued"
    task.started_at = None
    task.finished_at = None
    task.result_json = None
    task.error_json = None

    try:
        value = _compact_json_loads(task.params_json) if task.params_json else {}
        if isinstance(value, dict):
            value["retry_count"] = int(value.get("retry_count") or 0) + 1
            task.params_json = _compact_json_dumps(value)
    except Exception:
        pass

    task.updated_at = utc_now()
    db.commit()
    return task


def run_project_task(*, task_id: str) -> str:
    """
    RQ worker entrypoint. Consumes ProjectTask and records result to DB.
    """

    db = SessionLocal()
    try:
        task = db.get(ProjectTask, task_id)
        if task is None:
            log_event(logger, "warning", event="PROJECT_TASK_MISSING", task_id=task_id)
            return task_id

        if str(task.status) in {"succeeded", "failed", "running"}:
            return task_id

        task.status = "running"
        task.started_at = utc_now()
        db.commit()

        kind = str(task.kind)

        result: dict[str, Any]
        if kind == "noop":
            result = {"skipped": True, "note": "noop"}
        else:
            raise ValueError(f"Unsupported ProjectTask.kind: {kind!r}")

        task.status = "succeeded"
        task.result_json = _compact_json_dumps(result)
        task.finished_at = utc_now()
        db.commit()

        log_event(
            logger,
            "info",
            event="PROJECT_TASK_SUCCEEDED",
            task_id=task_id,
            project_id=str(task.project_id),
            kind=kind,
        )
        return task_id
    except Exception as exc:
        try:
            task2 = db.get(ProjectTask, task_id)
            if task2 is not None:
                task2.status = "failed"
                task2.error_json = _compact_json_dumps({"error_type": type(exc).__name__, "message": str(exc)[:400]})
                task2.finished_at = utc_now()
                db.commit()
        except Exception:
            db.rollback()

        log_event(
            logger,
            "error",
            event="PROJECT_TASK_FAILED",
            task_id=task_id,
            error_type=type(exc).__name__,
            **exception_log_fields(exc),
        )
        return task_id
    finally:
        db.close()
