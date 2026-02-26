from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.core.config import settings
from app.services.task_queue import InlineTaskQueue, RqTaskQueue, get_queue_status_for_health, get_task_queue


class TestTaskQueueDevFallback(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_app_env = settings.app_env
        self._orig_backend = settings.task_queue_backend
        self._orig_redis_url = settings.redis_url
        self._orig_rq_queue_name = settings.rq_queue_name

    def tearDown(self) -> None:
        settings.app_env = self._orig_app_env
        settings.task_queue_backend = self._orig_backend
        settings.redis_url = self._orig_redis_url
        settings.rq_queue_name = self._orig_rq_queue_name

    def test_dev_falls_back_to_inline_when_redis_unavailable(self) -> None:
        settings.app_env = "dev"
        settings.task_queue_backend = "rq"
        settings.redis_url = "redis://localhost:6379/0"
        settings.rq_queue_name = "default"

        from app.services import task_queue as mod

        mod._REDIS_PING_CACHE.clear()
        mod._RQ_INSPECT_CACHE.clear()
        with patch.dict(os.environ, {"TASK_QUEUE_BACKEND": ""}, clear=False), patch(
            "app.services.task_queue._redis_ping", return_value=(False, "ConnectionError")
        ):
            tq = get_task_queue()

        self.assertIsInstance(tq, InlineTaskQueue)

    def test_dev_falls_back_to_inline_when_redis_ok_but_no_worker(self) -> None:
        settings.app_env = "dev"
        settings.task_queue_backend = "rq"
        settings.redis_url = "redis://localhost:6379/0"
        settings.rq_queue_name = "default"

        from app.services import task_queue as mod

        mod._REDIS_PING_CACHE.clear()
        mod._RQ_INSPECT_CACHE.clear()
        with patch.dict(os.environ, {"TASK_QUEUE_BACKEND": ""}, clear=False), patch(
            "app.services.task_queue._redis_ping", return_value=(True, None)
        ), patch(
            "app.services.task_queue._rq_inspect",
            return_value={"rq_inspect_ok": True, "rq_queue_size": 0, "rq_worker_count": 0},
        ):
            tq = get_task_queue()

        self.assertIsInstance(tq, InlineTaskQueue)

    def test_dev_does_not_fallback_when_backend_is_explicit_rq(self) -> None:
        settings.app_env = "dev"
        settings.task_queue_backend = "rq"
        settings.redis_url = "redis://localhost:6379/0"
        settings.rq_queue_name = "default"

        from app.services import task_queue as mod

        mod._REDIS_PING_CACHE.clear()
        mod._RQ_INSPECT_CACHE.clear()
        with patch.dict(os.environ, {"TASK_QUEUE_BACKEND": "rq"}, clear=False):
            tq = get_task_queue()

        self.assertIsInstance(tq, RqTaskQueue)

    def test_prod_does_not_fallback(self) -> None:
        settings.app_env = "prod"
        settings.task_queue_backend = "rq"
        settings.redis_url = "redis://localhost:6379/0"
        settings.rq_queue_name = "default"

        from app.services import task_queue as mod

        mod._REDIS_PING_CACHE.clear()
        mod._RQ_INSPECT_CACHE.clear()
        with patch.dict(os.environ, {"TASK_QUEUE_BACKEND": ""}, clear=False), patch(
            "app.services.task_queue._redis_ping", return_value=(False, "ConnectionError")
        ):
            tq = get_task_queue()

        self.assertIsInstance(tq, RqTaskQueue)

    def test_health_reports_effective_backend_inline_on_dev_fallback(self) -> None:
        settings.app_env = "dev"
        settings.task_queue_backend = "rq"
        settings.redis_url = "redis://localhost:6379/0"
        settings.rq_queue_name = "default"

        from app.services import task_queue as mod

        mod._REDIS_PING_CACHE.clear()
        mod._RQ_INSPECT_CACHE.clear()
        with patch.dict(os.environ, {"TASK_QUEUE_BACKEND": ""}, clear=False), patch(
            "app.services.task_queue._redis_ping", return_value=(False, "TimeoutError")
        ):
            status = get_queue_status_for_health()

        self.assertEqual(status.get("queue_backend"), "rq")
        self.assertEqual(status.get("effective_backend"), "inline")
        self.assertEqual(status.get("redis_ok"), False)
        self.assertIn("inline_queue_size", status)
        self.assertIsInstance(status.get("inline_queue_size"), int)
        self.assertIn("inline_last_processed_at", status)
        self.assertTrue(
            status.get("inline_last_processed_at") is None or isinstance(status.get("inline_last_processed_at"), str)
        )

    def test_health_reports_effective_backend_inline_on_no_worker(self) -> None:
        settings.app_env = "dev"
        settings.task_queue_backend = "rq"
        settings.redis_url = "redis://localhost:6379/0"
        settings.rq_queue_name = "default"

        from app.services import task_queue as mod

        mod._REDIS_PING_CACHE.clear()
        mod._RQ_INSPECT_CACHE.clear()
        with patch.dict(os.environ, {"TASK_QUEUE_BACKEND": ""}, clear=False), patch(
            "app.services.task_queue._redis_ping", return_value=(True, None)
        ), patch(
            "app.services.task_queue._rq_inspect",
            return_value={"rq_inspect_ok": True, "rq_queue_size": 0, "rq_worker_count": 0},
        ):
            status = get_queue_status_for_health()

        self.assertEqual(status.get("queue_backend"), "rq")
        self.assertEqual(status.get("effective_backend"), "inline")
        self.assertEqual(status.get("redis_ok"), True)
        self.assertEqual(status.get("rq_worker_count"), 0)
        self.assertIn("inline_queue_size", status)

    def test_health_reports_effective_backend_rq_when_explicit(self) -> None:
        settings.app_env = "dev"
        settings.task_queue_backend = "rq"
        settings.redis_url = "redis://localhost:6379/0"
        settings.rq_queue_name = "default"

        from app.services import task_queue as mod

        mod._REDIS_PING_CACHE.clear()
        mod._RQ_INSPECT_CACHE.clear()
        with patch.dict(os.environ, {"TASK_QUEUE_BACKEND": "rq"}, clear=False), patch(
            "app.services.task_queue._redis_ping", return_value=(False, "TimeoutError")
        ):
            status = get_queue_status_for_health()

        self.assertEqual(status.get("queue_backend"), "rq")
        self.assertEqual(status.get("effective_backend"), "rq")
        self.assertEqual(status.get("redis_ok"), False)
        self.assertNotIn("inline_queue_size", status)
        self.assertNotIn("inline_last_processed_at", status)
