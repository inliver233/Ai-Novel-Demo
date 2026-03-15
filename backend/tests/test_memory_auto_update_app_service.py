from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core.errors import AppError
from app.services.generation_service import PreparedLlmCall
from app.services.memory_auto_update_app_service import (
    PreparedMemoryAutoProposeRequest,
    auto_propose_chapter_memory_update,
)


def _prepared_llm_call() -> PreparedLlmCall:
    return PreparedLlmCall(
        provider="openai",
        model="gpt-test",
        base_url="",
        timeout_seconds=30,
        params={"temperature": 0.2},
        params_json=json.dumps({"temperature": 0.2}, ensure_ascii=False),
        extra={},
    )


class TestMemoryAutoUpdateAppService(unittest.TestCase):
    @patch("app.services.memory_auto_update_app_service.propose_chapter_memory_change_set")
    @patch("app.services.memory_auto_update_app_service.require_chapter_editor")
    @patch("app.services.memory_auto_update_app_service.SessionLocal")
    @patch("app.services.memory_auto_update_app_service.call_llm_and_record")
    @patch("app.services.memory_auto_update_app_service.prepare_memory_auto_propose_request")
    def test_success_attaches_llm_generation_run_id(
        self,
        prepare_request,
        call_llm_and_record_mock,
        session_local_mock,
        require_chapter_editor_mock,
        propose_change_set_mock,
    ) -> None:
        prepare_request.return_value = PreparedMemoryAutoProposeRequest(
            project_id="project-1",
            resolved_api_key="key",
            prompt_system="system",
            prompt_user="user",
            prompt_messages=[],
            prompt_render_log_json='{"task":"memory_update"}',
            llm_call=_prepared_llm_call(),
            idempotency_key="idem-key-1",
        )
        call_llm_and_record_mock.return_value = SimpleNamespace(
            text='{"title":"Auto","summary_md":"sum","ops":[]}',
            finish_reason="stop",
            run_id="llm-run-1",
        )
        db = MagicMock()
        session_local_mock.return_value.__enter__.return_value = db
        require_chapter_editor_mock.return_value = SimpleNamespace(status="done")
        propose_change_set_mock.return_value = {"change_set": {"id": "cs-1"}}

        out = auto_propose_chapter_memory_update(
            request_id="rid-1",
            chapter_id="chapter-1",
            focus="focus",
            user_id="user-1",
            allow_draft=False,
            x_llm_provider=None,
            x_llm_api_key=None,
            idempotency_key="idem-key-1",
        )

        self.assertEqual(out["llm_generation_run_id"], "llm-run-1")
        payload = propose_change_set_mock.call_args.kwargs["payload"]
        self.assertEqual(payload.idempotency_key, "idem-key-1")
        self.assertEqual(payload.title, "Auto")
        self.assertEqual(payload.summary_md, "sum")
        self.assertEqual(payload.ops, [])

    @patch("app.services.memory_auto_update_app_service.contract_for_task")
    @patch("app.services.memory_auto_update_app_service.call_llm_and_record")
    @patch("app.services.memory_auto_update_app_service.prepare_memory_auto_propose_request")
    def test_parse_error_keeps_generation_run_ids_in_validation_details(
        self,
        prepare_request,
        call_llm_and_record_mock,
        contract_for_task_mock,
    ) -> None:
        prepare_request.return_value = PreparedMemoryAutoProposeRequest(
            project_id="project-1",
            resolved_api_key="key",
            prompt_system="system",
            prompt_user="user",
            prompt_messages=[],
            prompt_render_log_json='{"task":"memory_update"}',
            llm_call=_prepared_llm_call(),
            idempotency_key="idem-key-1",
        )
        call_llm_and_record_mock.return_value = SimpleNamespace(
            text="not-json",
            finish_reason="length",
            run_id="llm-run-2",
        )
        contract_for_task_mock.return_value = SimpleNamespace(
            parse=lambda *_args, **_kwargs: SimpleNamespace(
                data={},
                warnings=["memory_update_validation_failed"],
                parse_error={"code": "MEMORY_UPDATE_PARSE_ERROR", "idx": 0},
            )
        )

        with self.assertRaises(AppError) as ctx:
            auto_propose_chapter_memory_update(
                request_id="rid-2",
                chapter_id="chapter-1",
                focus="focus",
                user_id="user-1",
                allow_draft=False,
                x_llm_provider=None,
                x_llm_api_key=None,
                idempotency_key="idem-key-1",
            )

        self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")
        self.assertEqual(
            ctx.exception.details,
            {
                "parse_error": {"code": "MEMORY_UPDATE_PARSE_ERROR", "idx": 0},
                "warnings": ["memory_update_validation_failed"],
                "generation_run_id": "llm-run-2",
                "llm_generation_run_id": "llm-run-2",
                "finish_reason": "length",
            },
        )


if __name__ == "__main__":
    unittest.main()
