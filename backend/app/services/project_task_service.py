from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.logging import exception_log_fields, log_event, redact_secrets_text
from app.core.secrets import redact_api_keys
from app.db.session import SessionLocal
from app.db.utils import new_id, utc_now
from app.models.project_task import ProjectTask

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


def schedule_worldbook_auto_update_task(
    *,
    db: Session | None = None,
    project_id: str,
    actor_user_id: str | None,
    request_id: str | None,
    chapter_id: str | None,
    chapter_token: str | None,
    reason: str,
) -> str | None:
    """
    Fail-soft scheduler: ensure/enqueue a ProjectTask(kind=worldbook_auto_update).

    Idempotency key is chapter-scoped when chapter_id is provided, so a chapter can be marked done and re-triggered
    later (with a new token) without creating duplicate tasks for the same chapter version.
    """

    pid = str(project_id or "").strip()
    if not pid:
        return None

    cid = str(chapter_id or "").strip() or None
    token_norm = str(chapter_token or "").strip() or utc_now().isoformat().replace("+00:00", "Z")
    reason_norm = str(reason or "").strip() or "dirty"

    if cid:
        idempotency_key = f"worldbook:chapter:{cid}:since:{token_norm}:v1"
    else:
        idempotency_key = f"worldbook:project:since:{token_norm}:v1"

    owns_session = db is None
    if db is None:
        db = SessionLocal()
    try:
        task = (
            db.execute(
                select(ProjectTask).where(
                    ProjectTask.project_id == pid,
                    ProjectTask.idempotency_key == idempotency_key,
                )
            )
            .scalars()
            .first()
        )

        if task is None:
            task = ProjectTask(
                id=new_id(),
                project_id=pid,
                actor_user_id=actor_user_id,
                kind="worldbook_auto_update",
                status="queued",
                idempotency_key=idempotency_key,
                params_json=_compact_json_dumps(
                    {
                        "reason": reason_norm,
                        "request_id": (str(request_id or "").strip() or None),
                        "chapter_id": cid,
                        "chapter_token": token_norm,
                        "triggered_at": utc_now().isoformat().replace("+00:00", "Z"),
                    }
                ),
                result_json=None,
                error_json=None,
            )
            db.add(task)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                task = (
                    db.execute(
                        select(ProjectTask).where(
                            ProjectTask.project_id == pid,
                            ProjectTask.idempotency_key == idempotency_key,
                        )
                    )
                    .scalars()
                    .first()
                )

        if task is None:
            return None

        from app.services.task_queue import get_task_queue

        queue = get_task_queue()
        try:
            queue.enqueue(kind="project_task", task_id=str(task.id))
        except Exception as exc:
            fields = exception_log_fields(exc)
            safe_message = redact_secrets_text(str(exc)).replace("\n", " ").strip()
            if not safe_message:
                safe_message = type(exc).__name__
            task.status = "failed"
            task.finished_at = utc_now()
            if isinstance(exc, AppError):
                details = exc.details if isinstance(exc.details, dict) else {}
                error_payload = {
                    "error_type": type(exc).__name__,
                    "code": str(exc.code),
                    "message": safe_message[:200],
                    "details": redact_api_keys(details),
                }
            else:
                error_payload = {"error_type": type(exc).__name__, "message": safe_message[:200]}

            task.error_json = _compact_json_dumps(error_payload)
            db.commit()
            log_event(
                logger,
                "warning",
                event="PROJECT_TASK_ENQUEUE_ERROR",
                task_id=str(task.id),
                project_id=str(task.project_id),
                kind=str(task.kind),
                error_type=type(exc).__name__,
                **fields,
            )

        return str(task.id)
    finally:
        if owns_session:
            db.close()


def schedule_chapter_done_tasks(
    *,
    db: Session,
    project_id: str,
    actor_user_id: str | None,
    request_id: str | None,
    chapter_id: str,
    chapter_token: str | None,
    reason: str,
) -> dict[str, str | None]:
    """
    Fail-soft scheduler bundle for chapter status transition -> done.

    Schedules:
    - ProjectTask(kind=vector_rebuild)
    - ProjectTask(kind=search_rebuild)
    - ProjectTask(kind=worldbook_auto_update)
    - ProjectTask(kind=graph_auto_update)

    All schedulers are idempotent; this helper never raises.
    """

    pid = str(project_id or "").strip()
    cid = str(chapter_id or "").strip()
    reason_norm = str(reason or "").strip() or "chapter_done"
    token_norm = str(chapter_token or "").strip() or utc_now().isoformat().replace("+00:00", "Z")

    out: dict[str, str | None] = {
        "vector_rebuild": None,
        "search_rebuild": None,
        "worldbook_auto_update": None,
        "graph_auto_update": None,
    }

    if not pid or not cid:
        return out

    try:
        from app.services.vector_rag_service import schedule_vector_rebuild_task

        out["vector_rebuild"] = schedule_vector_rebuild_task(
            db=db,
            project_id=pid,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason=reason_norm,
        )
    except Exception as exc:
        log_event(
            logger,
            "warning",
            event="CHAPTER_DONE_TASK_SCHEDULE_ERROR",
            project_id=pid,
            chapter_id=cid,
            kind="vector_rebuild",
            error_type=type(exc).__name__,
            **exception_log_fields(exc),
        )

    try:
        from app.services.search_index_service import schedule_search_rebuild_task

        out["search_rebuild"] = schedule_search_rebuild_task(
            db=db,
            project_id=pid,
            actor_user_id=actor_user_id,
            request_id=request_id,
            reason=reason_norm,
        )
    except Exception as exc:
        log_event(
            logger,
            "warning",
            event="CHAPTER_DONE_TASK_SCHEDULE_ERROR",
            project_id=pid,
            chapter_id=cid,
            kind="search_rebuild",
            error_type=type(exc).__name__,
            **exception_log_fields(exc),
        )

    try:
        out["worldbook_auto_update"] = schedule_worldbook_auto_update_task(
            db=db,
            project_id=pid,
            actor_user_id=actor_user_id,
            request_id=request_id,
            chapter_id=cid,
            chapter_token=token_norm,
            reason=reason_norm,
        )
    except Exception as exc:
        log_event(
            logger,
            "warning",
            event="CHAPTER_DONE_TASK_SCHEDULE_ERROR",
            project_id=pid,
            chapter_id=cid,
            kind="worldbook_auto_update",
            error_type=type(exc).__name__,
            **exception_log_fields(exc),
        )

    try:
        from app.services.graph_auto_update_service import schedule_graph_auto_update_task

        out["graph_auto_update"] = schedule_graph_auto_update_task(
            db=db,
            project_id=pid,
            actor_user_id=actor_user_id,
            request_id=request_id,
            chapter_id=cid,
            chapter_token=token_norm,
            focus=None,
            reason=reason_norm,
        )
    except Exception as exc:
        log_event(
            logger,
            "warning",
            event="CHAPTER_DONE_TASK_SCHEDULE_ERROR",
            project_id=pid,
            chapter_id=cid,
            kind="graph_auto_update",
            error_type=type(exc).__name__,
            **exception_log_fields(exc),
        )

    return out


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

    from app.services.task_queue import get_task_queue

    queue = get_task_queue()
    try:
        queue.enqueue(kind="project_task", task_id=str(task.id))
    except Exception as exc:
        fields = exception_log_fields(exc)
        safe_message = redact_secrets_text(str(exc)).replace("\n", " ").strip()
        if not safe_message:
            safe_message = type(exc).__name__
        task.status = "failed"
        task.finished_at = utc_now()
        if isinstance(exc, AppError):
            details = exc.details if isinstance(exc.details, dict) else {}
            error_payload = {
                "error_type": type(exc).__name__,
                "code": str(exc.code),
                "message": safe_message[:200],
                "details": redact_api_keys(details),
            }
        else:
            error_payload = {"error_type": type(exc).__name__, "message": safe_message[:200]}
        task.error_json = _compact_json_dumps(error_payload)
        db.commit()
        log_event(
            logger,
            "warning",
            event="PROJECT_TASK_ENQUEUE_ERROR",
            task_id=str(task.id),
            project_id=str(task.project_id),
            kind=str(task.kind),
            error_type=type(exc).__name__,
            **fields,
        )
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
        project_id = str(task.project_id)

        result: dict[str, Any]
        if kind == "noop":
            result = {"skipped": True, "note": "noop"}
        elif kind == "search_rebuild":
            from app.services.search_index_service import rebuild_project_search_index_async

            result = rebuild_project_search_index_async(project_id=project_id)
        elif kind == "worldbook_auto_update":
            params = _compact_json_loads(task.params_json) if task.params_json else None
            params_dict = params if isinstance(params, dict) else {}
            chapter_id = str(params_dict.get("chapter_id") or "").strip() or None
            request_id2 = str(params_dict.get("request_id") or "").strip() or None
            actor_user_id = str(getattr(task, "actor_user_id", "") or "").strip()
            if not actor_user_id:
                raise ValueError("Missing ProjectTask.actor_user_id for worldbook_auto_update")

            from app.services.worldbook_auto_update_service import worldbook_auto_update_v1

            res = worldbook_auto_update_v1(
                project_id=project_id,
                actor_user_id=actor_user_id,
                request_id=request_id2 or f"project_task:{task_id}",
                chapter_id=chapter_id,
            )
            if not bool(res.get("ok")):
                reason = str(res.get("reason") or "unknown").strip() or "unknown"
                run_id = str(res.get("run_id") or "").strip()
                suffix = f" run_id={run_id}" if run_id else ""
                raise RuntimeError(f"worldbook_auto_update failed: {reason}{suffix}")
            result = res
        elif kind == "vector_rebuild":
            from app.models.project_settings import ProjectSettings
            from app.services.vector_embedding_overrides import vector_embedding_overrides
            from app.services.vector_kb_service import list_kbs as list_vector_kbs
            from app.services.vector_rag_service import build_project_chunks, rebuild_project, vector_rag_status

            db2 = SessionLocal()
            kb_ids: list[str] = []
            embedding: dict[str, str | None] = {}
            chunks = []
            try:
                settings_row = db2.get(ProjectSettings, project_id)
                embedding = vector_embedding_overrides(settings_row)
                status = vector_rag_status(project_id=project_id, embedding=embedding)
                if not bool(status.get("enabled")):
                    result = {"skipped": True, **status}
                else:
                    kbs = list_vector_kbs(db2, project_id=project_id)
                    kb_ids = [str(r.kb_id) for r in kbs if bool(getattr(r, "enabled", True))]
                    if not kb_ids:
                        kb_ids = ["default"]
                    chunks = build_project_chunks(db=db2, project_id=project_id)
                    result = {}
            finally:
                db2.close()

            if not result:
                per_kb: dict[str, dict[str, Any]] = {}
                for kid in kb_ids:
                    per_kb[kid] = rebuild_project(project_id=project_id, kb_id=kid, chunks=chunks, embedding=embedding)

                results = list(per_kb.values())
                enabled = all(bool(r.get("enabled")) for r in results) if results else False
                skipped = all(bool(r.get("skipped")) for r in results) if results else True
                rebuilt = sum(int(r.get("rebuilt") or 0) for r in results)
                disabled_reason = next((r.get("disabled_reason") for r in results if r.get("disabled_reason")), None)
                backend = next((r.get("backend") for r in results if r.get("backend")), None)
                error = next((r.get("error") for r in results if r.get("error")), None)

                result = {
                    "enabled": bool(enabled),
                    "skipped": bool(skipped),
                    "disabled_reason": disabled_reason,
                    "rebuilt": int(rebuilt),
                    "backend": backend,
                    "error": error,
                    "kbs": {"selected": list(kb_ids), "per_kb": per_kb},
                }

                if bool(enabled) and not bool(skipped):
                    db3 = SessionLocal()
                    try:
                        settings_row2 = db3.get(ProjectSettings, project_id)
                        if settings_row2 is None:
                            settings_row2 = ProjectSettings(project_id=project_id)
                            db3.add(settings_row2)
                        settings_row2.vector_index_dirty = False
                        settings_row2.last_vector_build_at = utc_now()
                        db3.commit()
                    finally:
                        db3.close()
        elif kind == "table_ai_update":
            params = _compact_json_loads(task.params_json) if task.params_json else None
            params_dict = params if isinstance(params, dict) else {}
            table_id = str(params_dict.get("table_id") or "").strip()
            chapter_id = str(params_dict.get("chapter_id") or "").strip() or None
            focus = str(params_dict.get("focus") or "").strip() or None
            request_id2 = str(params_dict.get("request_id") or "").strip() or None
            change_set_idempotency_key = str(params_dict.get("change_set_idempotency_key") or "").strip() or None

            actor_user_id = str(getattr(task, "actor_user_id", "") or "").strip()
            if not actor_user_id:
                raise ValueError("Missing ProjectTask.actor_user_id for table_ai_update")
            if not table_id:
                raise ValueError("Missing ProjectTask.params_json.table_id for table_ai_update")

            from app.services.table_ai_update_service import (
                table_ai_update_v1,
                table_update_changeset_key_from_task_idempotency_key,
            )

            res = table_ai_update_v1(
                project_id=project_id,
                actor_user_id=actor_user_id,
                request_id=request_id2 or f"project_task:{task_id}",
                table_id=table_id,
                change_set_idempotency_key=change_set_idempotency_key
                or table_update_changeset_key_from_task_idempotency_key(str(task.idempotency_key)),
                chapter_id=chapter_id,
                focus=focus,
            )
            if not bool(res.get("ok")):
                reason = str(res.get("reason") or "unknown").strip() or "unknown"
                run_id = str(res.get("run_id") or "").strip()
                suffix = f" run_id={run_id}" if run_id else ""
                raise RuntimeError(f"table_ai_update failed: {reason}{suffix}")
            result = res
        elif kind == "graph_auto_update":
            params = _compact_json_loads(task.params_json) if task.params_json else None
            params_dict = params if isinstance(params, dict) else {}
            chapter_id = str(params_dict.get("chapter_id") or "").strip()
            focus = str(params_dict.get("focus") or "").strip() or None
            request_id2 = str(params_dict.get("request_id") or "").strip() or None
            change_set_idempotency_key = str(params_dict.get("change_set_idempotency_key") or "").strip() or None

            actor_user_id = str(getattr(task, "actor_user_id", "") or "").strip()
            if not actor_user_id:
                raise ValueError("Missing ProjectTask.actor_user_id for graph_auto_update")
            if not chapter_id:
                raise ValueError("Missing ProjectTask.params_json.chapter_id for graph_auto_update")

            from app.services.graph_auto_update_service import (
                graph_auto_update_v1,
                memory_update_changeset_key_from_task_idempotency_key,
            )

            res = graph_auto_update_v1(
                project_id=project_id,
                actor_user_id=actor_user_id,
                request_id=request_id2 or f"project_task:{task_id}",
                chapter_id=chapter_id,
                change_set_idempotency_key=change_set_idempotency_key
                or memory_update_changeset_key_from_task_idempotency_key(str(task.idempotency_key)),
                focus=focus,
            )
            if not bool(res.get("ok")):
                reason = str(res.get("reason") or "unknown").strip() or "unknown"
                run_id = str(res.get("run_id") or "").strip()
                suffix = f" run_id={run_id}" if run_id else ""
                raise RuntimeError(f"graph_auto_update failed: {reason}{suffix}")
            result = res
        else:
            raise ValueError(f"Unsupported ProjectTask.kind: {kind!r}")

        task.status = "succeeded"
        task.result_json = _compact_json_dumps(redact_api_keys(result))
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
                safe_message = redact_secrets_text(str(exc)).replace("\n", " ").strip()
                if not safe_message:
                    safe_message = type(exc).__name__

                if isinstance(exc, AppError):
                    details = exc.details if isinstance(exc.details, dict) else {}
                    error_payload = {
                        "error_type": type(exc).__name__,
                        "code": str(exc.code),
                        "message": safe_message[:400],
                        "details": redact_api_keys(details),
                    }
                else:
                    error_payload = {"error_type": type(exc).__name__, "message": safe_message[:400]}

                task2.status = "failed"
                task2.error_json = _compact_json_dumps(error_payload)
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
