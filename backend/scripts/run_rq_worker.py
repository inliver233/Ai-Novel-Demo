from __future__ import annotations

import os

from redis import Redis
from rq import Queue, Worker

from app.core.config import settings
from app.core.logging import configure_logging


def main() -> None:
    configure_logging()

    redis_url = (os.getenv("REDIS_URL") or getattr(settings, "redis_url", None) or "redis://localhost:6379/0").strip()
    queue_name = (os.getenv("RQ_QUEUE_NAME") or getattr(settings, "rq_queue_name", None) or "default").strip() or "default"
    worker_name = (os.getenv("RQ_WORKER_NAME") or "").strip() or None

    conn = Redis.from_url(redis_url)
    queue = Queue(queue_name, connection=conn)
    worker = Worker([queue], connection=conn, name=worker_name)
    worker.work()


if __name__ == "__main__":
    main()
