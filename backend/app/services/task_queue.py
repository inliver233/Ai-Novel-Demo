from __future__ import annotations

import logging
import os
import queue as queue_mod
import threading
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Literal, Protocol

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import exception_log_fields, log_event


TaskQueueBackend = Literal["rq", "inline"]
TaskKind = Literal["batch_generation", "memory_task", "import_task", "project_task"]

logger = logging.getLogger("ainovel")

_REDIS_PING_CACHE: dict[str, tuple[float, bool, str | None]] = {}
_REDIS_PING_TTL_SECONDS = 2.0
_RQ_INSPECT_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_RQ_INSPECT_TTL_SECONDS = 2.0
_INLINE_WORKER_MAX_CONCURRENCY = 8


def _get_inline_worker_concurrency() -> int:
    raw = str(os.environ.get("INLINE_WORKER_CONCURRENCY") or "").strip()
    if raw:
        try:
            n = int(raw)
        except Exception:
            n = 1
    else:
        app_env = str(getattr(settings, "app_env", "dev") or "dev").strip().lower()
        if app_env == "prod":
            n = 1
        else:
            cpu = os.cpu_count() or 4
            n = min(4, int(cpu))
    if n < 1:
        n = 1
    if n > _INLINE_WORKER_MAX_CONCURRENCY:
        n = _INLINE_WORKER_MAX_CONCURRENCY
    return n


def _redis_ping(redis_url: str, *, timeout_seconds: float) -> tuple[bool, str | None]:
    redis_url_norm = str(redis_url or "").strip()
    if not redis_url_norm:
        return False, "missing_redis_url"
    try:
        from redis import Redis

        conn = Redis.from_url(
            redis_url_norm,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
            retry_on_timeout=False,
        )
        conn.ping()
        return True, None
    except Exception as exc:  # pragma: no cover - env dependent
        return False, type(exc).__name__


def _redis_ping_cached(redis_url: str, *, timeout_seconds: float) -> tuple[bool, str | None]:
    now = time.monotonic()
    cached = _REDIS_PING_CACHE.get(redis_url)
    if cached is not None and (now - cached[0]) < _REDIS_PING_TTL_SECONDS:
        return cached[1], cached[2]
    ok, error_type = _redis_ping(redis_url, timeout_seconds=timeout_seconds)
    _REDIS_PING_CACHE[redis_url] = (now, ok, error_type)
    return ok, error_type


def _rq_inspect(redis_url: str, *, queue_name: str, timeout_seconds: float) -> dict[str, Any]:
    redis_url_norm = str(redis_url or "").strip()
    queue_name_norm = str(queue_name or "").strip() or "default"
    if not redis_url_norm:
        return {"rq_inspect_ok": False, "rq_inspect_error_type": "missing_redis_url"}
    try:
        from redis import Redis
        from rq import Queue, Worker

        conn = Redis.from_url(
            redis_url_norm,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
            retry_on_timeout=False,
        )
        q = Queue(queue_name_norm, connection=conn)
        queue_size = int(q.count)

        worker_count = 0
        for w in Worker.all(connection=conn):
            try:
                queues = list(getattr(w, "queues", []) or [])
            except Exception:
                queues = []
            if any(str(getattr(item, "name", "") or "").strip() == queue_name_norm for item in queues):
                worker_count += 1

        return {"rq_inspect_ok": True, "rq_queue_size": queue_size, "rq_worker_count": worker_count}
    except Exception as exc:  # pragma: no cover - env dependent
        return {"rq_inspect_ok": False, "rq_inspect_error_type": type(exc).__name__}


def _rq_inspect_cached(redis_url: str, *, queue_name: str, timeout_seconds: float) -> dict[str, Any]:
    now = time.monotonic()
    key = (redis_url, queue_name)
    cached = _RQ_INSPECT_CACHE.get(key)
    if cached is not None and (now - cached[0]) < _RQ_INSPECT_TTL_SECONDS:
        return dict(cached[1])
    out = dict(_rq_inspect(redis_url, queue_name=queue_name, timeout_seconds=timeout_seconds))
    _RQ_INSPECT_CACHE[key] = (now, out)
    return dict(out)


class _InlineWorker:
    def __init__(self) -> None:
        self._queue: queue_mod.Queue[tuple[TaskKind, str]] = queue_mod.Queue()
        self._metrics_lock = threading.Lock()
        self._last_processed_at: float | None = None
        self._queued_task_ids: set[str] = set()
        self._active_task_ids: set[str] = set()
        self._concurrency = _get_inline_worker_concurrency()
        self._threads: list[threading.Thread] = []
        for i in range(self._concurrency):
            t = threading.Thread(target=self._run, name=f"ainovel-inline-worker-{i+1}", daemon=True)
            t.start()
            self._threads.append(t)

    def enqueue(self, *, kind: TaskKind, task_id: str) -> None:
        with self._metrics_lock:
            self._queued_task_ids.add(str(task_id))
        self._queue.put((kind, task_id))

    def get_health_metrics(self) -> dict[str, Any]:
        with self._metrics_lock:
            last_processed_at = self._last_processed_at
            queued_count = len(self._queued_task_ids)
            active_count = len(self._active_task_ids)
        return {
            "inline_queue_size": int(self._queue.qsize()),
            "inline_last_processed_at": (
                datetime.fromtimestamp(last_processed_at, tz=timezone.utc).isoformat() if last_processed_at else None
            ),
            "inline_concurrency": int(self._concurrency),
            "inline_pending_project_tasks": int(queued_count + active_count),
        }

    def has_task(self, task_id: str) -> bool:
        task_id_norm = str(task_id or "").strip()
        if not task_id_norm:
            return False
        with self._metrics_lock:
            return task_id_norm in self._queued_task_ids or task_id_norm in self._active_task_ids

    def _run(self) -> None:
        while True:
            kind, task_id = self._queue.get()
            with self._metrics_lock:
                self._queued_task_ids.discard(str(task_id))
                self._active_task_ids.add(str(task_id))
            try:
                if kind == "batch_generation":
                    from app.services.batch_generation_service import run_batch_generation_task

                    run_batch_generation_task(task_id=task_id)
                elif kind == "import_task":
                    from app.services.import_export_service import run_import_task

                    run_import_task(task_id=task_id)
                elif kind == "memory_task":
                    from app.services.memory_update_service import run_memory_task

                    run_memory_task(task_id=task_id)
                elif kind == "project_task":
                    from app.services.project_task_service import run_project_task

                    run_project_task(task_id=task_id)
                else:
                    raise ValueError(f"Unsupported task kind: {kind!r}")
            except Exception as exc:
                try:
                    log_event(
                        logger,
                        "error",
                        event="INLINE_TASK_ERROR",
                        task_kind=kind,
                        task_id=str(task_id),
                        **exception_log_fields(exc),
                    )
                except Exception:
                    pass
            finally:
                with self._metrics_lock:
                    self._active_task_ids.discard(str(task_id))
                    self._last_processed_at = time.time()
                try:
                    self._queue.task_done()
                except Exception:
                    pass


@lru_cache(maxsize=1)
def _get_inline_worker() -> _InlineWorker:
    return _InlineWorker()


class TaskQueue(Protocol):
    def enqueue(self, *, kind: TaskKind, task_id: str) -> str: ...
    def enqueue_batch_generation_task(self, task_id: str) -> str: ...


class InlineTaskQueue:
    """
    Test/dev fallback. Runs the task in-process and is NOT production reliable.
    """

    def enqueue(self, *, kind: TaskKind, task_id: str) -> str:
        # Inline backend should behave like a real queue: return quickly and execute in a single background worker.
        _get_inline_worker().enqueue(kind=kind, task_id=task_id)
        return task_id

    def enqueue_batch_generation_task(self, task_id: str) -> str:
        return self.enqueue(kind="batch_generation", task_id=task_id)


@lru_cache(maxsize=8)
def _get_rq_queue(*, redis_url: str, queue_name: str):
    from redis import Redis
    from rq import Queue

    conn = Redis.from_url(redis_url)
    return Queue(queue_name, connection=conn)


class RqTaskQueue:
    def __init__(self, *, redis_url: str, queue_name: str = "default") -> None:
        self._redis_url = redis_url
        self._queue_name = queue_name

    def enqueue(self, *, kind: TaskKind, task_id: str) -> str:
        try:
            queue = _get_rq_queue(redis_url=self._redis_url, queue_name=self._queue_name)

            if kind == "batch_generation":
                from app.services.batch_generation_service import run_batch_generation_task

                fn = run_batch_generation_task
            elif kind == "import_task":
                from app.services.import_export_service import run_import_task

                fn = run_import_task
            elif kind == "memory_task":
                from app.services.memory_update_service import run_memory_task

                fn = run_memory_task
            elif kind == "project_task":
                from app.services.project_task_service import run_project_task

                fn = run_project_task
            else:
                raise ValueError(f"Unsupported task kind: {kind!r}")

            job = queue.enqueue(
                fn,
                task_id=task_id,
                job_id=task_id,
                job_timeout=60 * 60,
                result_ttl=7 * 24 * 60 * 60,
                failure_ttl=7 * 24 * 60 * 60,
                description=f"{kind}:{task_id}",
                meta={"task_id": task_id, "kind": kind},
            )
            return str(job.id)
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                code="QUEUE_UNAVAILABLE",
                message="任务队列不可用：请启动 Redis + worker，或切换 TASK_QUEUE_BACKEND=inline（仅 dev/test）",
                status_code=503,
                details={
                    "queue_backend": "rq",
                    "rq_queue_name": self._queue_name,
                    "how_to_fix": [
                        "启动 Redis（或修正 REDIS_URL）",
                        f"启动 RQ worker（queue={self._queue_name}；SQLite 模式建议单 worker）",
                        "或开发环境临时设置 TASK_QUEUE_BACKEND=inline（不需要 Redis；进程内线程 worker，可配 INLINE_WORKER_CONCURRENCY）",
                    ],
                    "enqueue_error_type": type(exc).__name__,
                },
            ) from exc

    def enqueue_batch_generation_task(self, task_id: str) -> str:
        return self.enqueue(kind="batch_generation", task_id=task_id)


def get_task_queue() -> TaskQueue:
    backend: str = str(getattr(settings, "task_queue_backend", "rq") or "rq").strip().lower()
    if backend == "inline":
        return InlineTaskQueue()
    if backend == "rq":
        app_env = str(getattr(settings, "app_env", "dev") or "dev").strip().lower()
        redis_url: str = str(getattr(settings, "redis_url", "redis://localhost:6379/0") or "").strip()
        queue_name: str = str(getattr(settings, "rq_queue_name", "default") or "default").strip() or "default"

        # Dev experience: allow running without Redis by falling back to the inline worker.
        # This keeps RAG rebuild and other background tasks from being permanently stuck in "dirty" state.
        if app_env != "prod":
            # Avoid surprising explicit rq setups in development environments.
            explicit_backend = str(os.environ.get("TASK_QUEUE_BACKEND") or "").strip().lower()
            if explicit_backend not in {"rq"}:
                redis_ok, redis_error_type = _redis_ping_cached(redis_url, timeout_seconds=0.2)
                if not redis_ok:
                    log_event(
                        logger,
                        "warning",
                        event="TASK_QUEUE_FALLBACK_INLINE",
                        requested_backend="rq",
                        redis_ok=False,
                        redis_error_type=redis_error_type,
                    )
                    return InlineTaskQueue()
                inspect = _rq_inspect_cached(redis_url, queue_name=queue_name, timeout_seconds=0.3)
                if bool(inspect.get("rq_inspect_ok")) and int(inspect.get("rq_worker_count") or 0) <= 0:
                    log_event(
                        logger,
                        "warning",
                        event="TASK_QUEUE_FALLBACK_INLINE_NO_WORKER",
                        requested_backend="rq",
                        redis_ok=True,
                        rq_queue_name=queue_name,
                        rq_worker_count=int(inspect.get("rq_worker_count") or 0),
                        rq_queue_size=inspect.get("rq_queue_size"),
                    )
                    return InlineTaskQueue()
        return RqTaskQueue(redis_url=redis_url, queue_name=queue_name)
    raise ValueError(f"Unsupported TASK_QUEUE_BACKEND: {backend!r}")


def _rq_job_is_pending(*, redis_url: str, task_id: str) -> bool | None:
    redis_url_norm = str(redis_url or "").strip()
    task_id_norm = str(task_id or "").strip()
    if not redis_url_norm or not task_id_norm:
        return None
    try:
        from redis import Redis
        from rq.exceptions import NoSuchJobError
        from rq.job import Job

        conn = Redis.from_url(redis_url_norm, socket_connect_timeout=0.3, socket_timeout=0.3, retry_on_timeout=False)
        try:
            job = Job.fetch(task_id_norm, connection=conn)
        except NoSuchJobError:
            return False
        status = str(job.get_status(refresh=True) or "").strip().lower()
        return status in {"queued", "started", "deferred", "scheduled"}
    except Exception:
        return None


def project_task_queue_has_task(*, task_id: str) -> bool | None:
    task_id_norm = str(task_id or "").strip()
    if not task_id_norm:
        return False

    queue = get_task_queue()
    if isinstance(queue, InlineTaskQueue):
        return _get_inline_worker().has_task(task_id_norm)
    if isinstance(queue, RqTaskQueue):
        return _rq_job_is_pending(redis_url=queue._redis_url, task_id=task_id_norm)
    return None


def get_queue_status_for_health() -> dict[str, Any]:
    """
    Health payload for queue observability.

    Security: must NOT leak redis_url (may include credentials).
    """

    backend: str = str(getattr(settings, "task_queue_backend", "rq") or "rq").strip().lower()
    db_is_sqlite = bool(getattr(settings, "is_sqlite", None) and settings.is_sqlite())

    if backend == "inline":
        return {
            "queue_backend": "inline",
            "effective_backend": "inline",
            "redis_ok": None,
            "db_is_sqlite": db_is_sqlite,
            "worker_hint": "inline 模式使用进程内线程 worker 执行任务（无需 Redis；适合 dev/test；可配 INLINE_WORKER_CONCURRENCY；生产请用 rq+worker）",
            **_get_inline_worker().get_health_metrics(),
        }

    if backend == "rq":
        app_env = str(getattr(settings, "app_env", "dev") or "dev").strip().lower()
        explicit_backend = str(os.environ.get("TASK_QUEUE_BACKEND") or "").strip().lower()
        fallback_allowed = app_env != "prod" and explicit_backend not in {"rq"}
        redis_url: str = str(getattr(settings, "redis_url", "redis://localhost:6379/0") or "").strip()
        queue_name: str = str(getattr(settings, "rq_queue_name", "default") or "default").strip() or "default"

        redis_ok, redis_error_type = _redis_ping_cached(redis_url, timeout_seconds=0.2)
        inspect: dict[str, Any] = {}
        if redis_ok:
            inspect = _rq_inspect_cached(redis_url, queue_name=queue_name, timeout_seconds=0.3)

        effective_backend: TaskQueueBackend = "rq"
        if fallback_allowed:
            if not redis_ok:
                effective_backend = "inline"
            elif bool(inspect.get("rq_inspect_ok")) and int(inspect.get("rq_worker_count") or 0) <= 0:
                effective_backend = "inline"

        hint = f"rq 模式需要 Redis + worker（SQLite 模式建议单 worker）。队列名={queue_name}。"
        if not redis_ok:
            hint += (
                f" 当前 redis_ok=false（{redis_error_type or 'unknown'}）。"
                " 可临时切换 TASK_QUEUE_BACKEND=inline（dev/test；不需要 Redis；进程内线程 worker）。"
            )
            if effective_backend == "inline":
                hint += " 当前 dev 环境将自动回落到 inline 以保证任务可执行（任务会排队处理）。"
            else:
                hint += " 当前 effective_backend=rq（不回落）。如需执行任务请确保 Redis 可用并启动 worker。"
        else:
            if bool(inspect.get("rq_inspect_ok")):
                hint += f" 当前 worker_count={int(inspect.get('rq_worker_count') or 0)} queue_size={int(inspect.get('rq_queue_size') or 0)}。"
                if effective_backend == "inline":
                    hint += (
                        " 检测到 worker_count=0：dev 环境将自动回落到 inline 执行（如需 rq 请启动 worker 或设置 TASK_QUEUE_BACKEND=rq）。"
                    )
            elif inspect.get("rq_inspect_error_type"):
                hint += f" 当前 rq_inspect 失败（{inspect.get('rq_inspect_error_type')}）。"
        return {
            "queue_backend": "rq",
            "effective_backend": effective_backend,
            "rq_queue_name": queue_name,
            "redis_ok": redis_ok,
            "redis_error_type": redis_error_type,
            "rq_inspect_ok": inspect.get("rq_inspect_ok"),
            "rq_inspect_error_type": inspect.get("rq_inspect_error_type"),
            "rq_worker_count": inspect.get("rq_worker_count"),
            "rq_queue_size": inspect.get("rq_queue_size"),
            "db_is_sqlite": db_is_sqlite,
            "worker_hint": hint,
            **(_get_inline_worker().get_health_metrics() if effective_backend == "inline" else {}),
        }

    return {
        "queue_backend": backend,
        "effective_backend": backend,
        "redis_ok": None,
        "worker_hint": "unknown task queue backend",
    }
