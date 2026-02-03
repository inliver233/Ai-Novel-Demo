from __future__ import annotations

import os
import time
import unittest
from threading import Event
from unittest.mock import patch

from app.services.task_queue import InlineTaskQueue


class TestInlineWorkerConcurrency(unittest.TestCase):
    def test_inline_worker_can_run_two_tasks_concurrently(self) -> None:
        from app.services import task_queue as mod

        mod._get_inline_worker.cache_clear()

        allow_first_finish = Event()
        saw_second = Event()

        def _run_batch_generation_task(*, task_id: str) -> None:
            if task_id == "t1":
                # t1 blocks until t2 runs.
                if not allow_first_finish.wait(timeout=3.0):
                    raise AssertionError("expected concurrent execution but t2 never ran")
            elif task_id == "t2":
                saw_second.set()
                allow_first_finish.set()

        with patch.dict(os.environ, {"INLINE_WORKER_CONCURRENCY": "2"}, clear=False), patch(
            "app.services.batch_generation_service.run_batch_generation_task",
            side_effect=_run_batch_generation_task,
        ):
            tq = InlineTaskQueue()
            tq.enqueue_batch_generation_task("t1")
            tq.enqueue_batch_generation_task("t2")

            for _ in range(300):
                if saw_second.is_set():
                    break
                time.sleep(0.01)

        self.assertTrue(saw_second.is_set())

