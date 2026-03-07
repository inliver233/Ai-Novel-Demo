from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.batch_generation_task import BatchGenerationTask, BatchGenerationTaskItem
from app.models.project_task import ProjectTask
from app.models.project_task_event import ProjectTaskEvent
from app.services.project_task_service import project_task_to_dict


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
    return dt.isoformat().replace("+00:00", "Z")


def _normalize_step(step: object) -> dict[str, Any] | None:
    if not isinstance(step, dict):
        return None
    out = dict(step)
    request_id = str(out.get("request_id") or out.get("last_request_id") or "").strip()
    if request_id:
        out["request_id"] = request_id
    return out


def _batch_task_to_dict(task: BatchGenerationTask) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "project_id": str(task.project_id),
        "outline_id": str(task.outline_id),
        "actor_user_id": task.actor_user_id,
        "project_task_id": str(task.project_task_id) if task.project_task_id else None,
        "status": str(task.status),
        "total_count": int(task.total_count or 0),
        "completed_count": int(task.completed_count or 0),
        "failed_count": int(getattr(task, "failed_count", 0) or 0),
        "skipped_count": int(getattr(task, "skipped_count", 0) or 0),
        "cancel_requested": bool(task.cancel_requested),
        "pause_requested": bool(getattr(task, "pause_requested", False)),
        "checkpoint_json": task.checkpoint_json,
        "error_json": task.error_json,
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
    }


def _batch_item_to_dict(item: BatchGenerationTaskItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "task_id": str(item.task_id),
        "chapter_id": str(item.chapter_id) if item.chapter_id else None,
        "chapter_number": int(item.chapter_number),
        "status": str(item.status),
        "attempt_count": int(getattr(item, "attempt_count", 0) or 0),
        "generation_run_id": str(item.generation_run_id) if item.generation_run_id else None,
        "last_request_id": str(getattr(item, "last_request_id", "") or "") or None,
        "error_message": str(item.error_message or "") or None,
        "last_error_json": item.last_error_json,
        "started_at": _iso(getattr(item, "started_at", None)),
        "finished_at": _iso(getattr(item, "finished_at", None)),
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def _load_linked_batch_payload(db: Session, *, task: ProjectTask) -> dict[str, Any] | None:
    params = _compact_json_loads(task.params_json) if task.params_json else None
    batch_task_id = None
    if isinstance(params, dict):
        batch_task_id = str(params.get("batch_task_id") or "").strip() or None
    if not batch_task_id:
        return None
    batch_task = db.get(BatchGenerationTask, batch_task_id)
    if batch_task is None:
        return None
    items = (
        db.execute(
            select(BatchGenerationTaskItem)
            .where(BatchGenerationTaskItem.task_id == batch_task_id)
            .order_by(BatchGenerationTaskItem.chapter_number.asc())
        )
        .scalars()
        .all()
    )
    return {
        "task": _batch_task_to_dict(batch_task),
        "items": [_batch_item_to_dict(item) for item in items],
    }


def build_project_task_runtime_view(db: Session, *, task_id: str, limit: int = 500) -> dict[str, Any]:
    task = db.get(ProjectTask, task_id)
    if task is None:
        raise LookupError(task_id)

    events = (
        db.execute(
            select(ProjectTaskEvent)
            .where(ProjectTaskEvent.task_id == task_id)
            .order_by(ProjectTaskEvent.seq.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )

    timeline: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    steps_index: dict[str, dict[str, Any]] = {}
    artifact_keys: set[tuple[str, str]] = set()
    artifacts: list[dict[str, Any]] = []

    for event in events:
        payload = _compact_json_loads(event.payload_json) if event.payload_json else None
        payload_obj = payload if isinstance(payload, dict) else {}
        step = _normalize_step(payload_obj.get("step"))
        checkpoint = payload_obj.get("checkpoint") if isinstance(payload_obj.get("checkpoint"), dict) else None
        error = payload_obj.get("error") if isinstance(payload_obj.get("error"), dict) else None
        result = payload_obj.get("result")
        source = str(payload_obj.get("source") or "").strip() or None
        reason = str(payload_obj.get("reason") or "").strip() or None

        entry = {
            "seq": int(event.seq),
            "event_type": str(event.event_type),
            "created_at": _iso(event.created_at),
            "source": source,
            "reason": reason,
            "checkpoint": checkpoint,
            "step": step,
            "error": error,
            "result": result,
        }
        timeline.append(entry)

        if checkpoint is not None:
            checkpoints.append(
                {
                    "seq": int(event.seq),
                    "created_at": _iso(event.created_at),
                    "reason": reason,
                    "checkpoint": checkpoint,
                }
            )

        if step is None:
            continue

        step_key = str(step.get("item_id") or step.get("chapter_id") or step.get("chapter_number") or event.seq)
        existing = steps_index.get(step_key)
        if existing is None:
            existing = {
                "item_id": step.get("item_id"),
                "chapter_id": step.get("chapter_id"),
                "chapter_number": step.get("chapter_number"),
                "status": step.get("status"),
                "attempt_count": step.get("attempt_count"),
                "generation_run_id": step.get("generation_run_id"),
                "request_id": step.get("request_id"),
                "error_message": step.get("error_message"),
                "started_at": step.get("started_at"),
                "finished_at": step.get("finished_at"),
                "last_event_type": str(event.event_type),
                "last_event_seq": int(event.seq),
                "timeline": [],
                "error": error,
            }
            steps_index[step_key] = existing
        else:
            existing["status"] = step.get("status") or existing.get("status")
            existing["attempt_count"] = step.get("attempt_count") or existing.get("attempt_count")
            existing["generation_run_id"] = step.get("generation_run_id") or existing.get("generation_run_id")
            existing["request_id"] = step.get("request_id") or existing.get("request_id")
            existing["error_message"] = step.get("error_message") or existing.get("error_message")
            existing["started_at"] = step.get("started_at") or existing.get("started_at")
            existing["finished_at"] = step.get("finished_at") or existing.get("finished_at")
            existing["last_event_type"] = str(event.event_type)
            existing["last_event_seq"] = int(event.seq)
            existing["error"] = error or existing.get("error")
        existing["timeline"].append(entry)

        generation_run_id = str(step.get("generation_run_id") or "").strip()
        if generation_run_id:
            artifact_key = ("generation_run", generation_run_id)
            if artifact_key not in artifact_keys:
                artifact_keys.add(artifact_key)
                artifacts.append(
                    {
                        "kind": "generation_run",
                        "id": generation_run_id,
                        "chapter_id": step.get("chapter_id"),
                        "chapter_number": step.get("chapter_number"),
                        "request_id": step.get("request_id"),
                        "event_seq": int(event.seq),
                    }
                )

    steps = sorted(
        steps_index.values(),
        key=lambda item: (
            int(item.get("chapter_number") or 0),
            str(item.get("item_id") or ""),
        ),
    )

    return {
        "run": project_task_to_dict(task=task, include_payloads=True),
        "timeline": timeline,
        "checkpoints": checkpoints,
        "steps": steps,
        "artifacts": artifacts,
        "batch": _load_linked_batch_payload(db, task=task),
    }
