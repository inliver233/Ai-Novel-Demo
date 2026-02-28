from __future__ import annotations

import os
import sys
from multiprocessing import Process
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from redis import Redis  # noqa: E402
from rq import Queue, Worker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402

# Ensure RQ can import worker entrypoints for all supported kinds.
import app.services.project_task_service  # noqa: F401,E402


def _int_env(name: str, *, default: int, min_value: int, max_value: int) -> int:
    raw = str(os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except Exception:
        return default
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def _run_worker(*, name_suffix: int | None) -> None:
    redis_url = (os.getenv("REDIS_URL") or getattr(settings, "redis_url", None) or "redis://localhost:6379/0").strip()
    queue_name = (os.getenv("RQ_QUEUE_NAME") or getattr(settings, "rq_queue_name", None) or "default").strip() or "default"
    worker_name = (os.getenv("RQ_WORKER_NAME") or "").strip() or None

    if name_suffix is not None:
        worker_name = f"{worker_name}-{name_suffix}" if worker_name else f"ainovel-rq-worker-{name_suffix}"

    configure_logging()
    conn = Redis.from_url(redis_url)
    queue = Queue(queue_name, connection=conn)
    worker = Worker([queue], connection=conn, name=worker_name)
    worker.work()


def main() -> None:
    worker_processes = _int_env("RQ_WORKER_PROCESSES", default=1, min_value=1, max_value=16)
    if worker_processes <= 1:
        _run_worker(name_suffix=None)
        return

    procs: list[Process] = []
    for i in range(worker_processes):
        p = Process(target=_run_worker, kwargs={"name_suffix": i + 1}, daemon=False)
        p.start()
        procs.append(p)

    exit_code = 0
    for p in procs:
        p.join()
        if p.exitcode:
            exit_code = int(p.exitcode)
            break

    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
