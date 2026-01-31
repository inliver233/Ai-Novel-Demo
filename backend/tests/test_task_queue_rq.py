from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from app.core.errors import AppError
from app.services.task_queue import InlineTaskQueue, RqTaskQueue


class TestRqTaskQueue(unittest.TestCase):
    def test_enqueue_uses_task_id_as_job_id(self) -> None:
        fake_queue = MagicMock()
        fake_job = MagicMock()
        fake_job.id = "task-123"
        fake_queue.enqueue.return_value = fake_job

        with patch("app.services.task_queue._get_rq_queue", return_value=fake_queue) as get_queue:
            tq = RqTaskQueue(redis_url="redis://example:6379/0", queue_name="default")
            job_id = tq.enqueue_batch_generation_task("task-123")

        self.assertEqual(job_id, "task-123")
        get_queue.assert_called_once_with(redis_url="redis://example:6379/0", queue_name="default")

        args, kwargs = fake_queue.enqueue.call_args
        self.assertGreaterEqual(len(args), 1)
        self.assertEqual(kwargs["task_id"], "task-123")
        self.assertEqual(kwargs["job_id"], "task-123")
        self.assertIn("job_timeout", kwargs)

    def test_enqueue_maps_errors_to_app_error(self) -> None:
        fake_queue = MagicMock()
        fake_queue.enqueue.side_effect = RuntimeError("boom")

        with patch("app.services.task_queue._get_rq_queue", return_value=fake_queue):
            tq = RqTaskQueue(redis_url="redis://example:6379/0", queue_name="default")
            with self.assertRaises(AppError) as ctx:
                tq.enqueue_batch_generation_task("task-123")

        self.assertEqual(ctx.exception.code, "QUEUE_UNAVAILABLE")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.details.get("queue_backend"), "rq")
        self.assertEqual(ctx.exception.details.get("rq_queue_name"), "default")
        self.assertIn("how_to_fix", ctx.exception.details)
        self.assertNotIn("redis_url", ctx.exception.details)


class TestInlineTaskQueue(unittest.TestCase):
    def test_inline_runs_task_function(self) -> None:
        with patch("app.services.batch_generation_service.run_batch_generation_task") as run:
            tq = InlineTaskQueue()
            job_id = tq.enqueue_batch_generation_task("task-abc")

            for _ in range(200):
                if run.called:
                    break
                time.sleep(0.01)

        self.assertEqual(job_id, "task-abc")
        run.assert_called_once_with(task_id="task-abc")
