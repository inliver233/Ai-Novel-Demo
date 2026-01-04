from __future__ import annotations

from functools import lru_cache
from typing import Literal, Protocol

from app.core.config import settings
from app.core.errors import AppError


TaskQueueBackend = Literal["rq", "inline"]


class TaskQueue(Protocol):
    def enqueue_batch_generation_task(self, task_id: str) -> str: ...


class InlineTaskQueue:
    """
    Test/dev fallback. Runs the task in-process and is NOT production reliable.
    """

    def enqueue_batch_generation_task(self, task_id: str) -> str:
        from app.services.batch_generation_service import run_batch_generation_task

        run_batch_generation_task(task_id=task_id)
        return task_id


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

    def enqueue_batch_generation_task(self, task_id: str) -> str:
        try:
            queue = _get_rq_queue(redis_url=self._redis_url, queue_name=self._queue_name)

            from app.services.batch_generation_service import run_batch_generation_task

            job = queue.enqueue(
                run_batch_generation_task,
                task_id=task_id,
                job_id=task_id,
                job_timeout=60 * 60,
                result_ttl=7 * 24 * 60 * 60,
                failure_ttl=7 * 24 * 60 * 60,
                description=f"batch_generation:{task_id}",
                meta={"task_id": task_id, "kind": "batch_generation"},
            )
            return str(job.id)
        except AppError:
            raise
        except Exception as exc:
            raise AppError(
                code="QUEUE_UNAVAILABLE",
                message="任务队列不可用：请确认 Redis 与 worker 已启动",
                status_code=503,
            ) from exc


def get_task_queue() -> TaskQueue:
    backend: str = str(getattr(settings, "task_queue_backend", "rq") or "rq").strip().lower()
    if backend == "inline":
        return InlineTaskQueue()
    if backend == "rq":
        redis_url: str = str(getattr(settings, "redis_url", "redis://localhost:6379/0") or "").strip()
        queue_name: str = str(getattr(settings, "rq_queue_name", "default") or "default").strip() or "default"
        return RqTaskQueue(redis_url=redis_url, queue_name=queue_name)
    raise ValueError(f"Unsupported TASK_QUEUE_BACKEND: {backend!r}")
