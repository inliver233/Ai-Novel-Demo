from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.core.errors import AppError
from app.schemas.chapter_analysis import ChapterAnalyzeRequest, ChapterRewriteRequest
from app.services.chapter_analysis_app_service import analyze_chapter, prepare_chapter_rewrite_request, rewrite_chapter
from app.services.chapter_analysis_models import (
    PreparedChapterAnalyzeRequest,
    PreparedChapterAutoMemoryUpdateRequest,
    PreparedChapterRewriteRequest,
)
from app.services.generation_service import PreparedLlmCall


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


class TestChapterAnalysisAppService(unittest.TestCase):
    @patch("app.services.chapter_analysis_app_service.contract_for_task")
    @patch("app.services.chapter_analysis_app_service.call_llm_and_record")
    @patch("app.services.chapter_analysis_app_service.prepare_chapter_analyze_request")
    def test_analyze_chapter_attaches_contract_metadata(
        self,
        prepare_request,
        call_llm_and_record_mock,
        contract_for_task_mock,
    ) -> None:
        prepare_request.return_value = PreparedChapterAnalyzeRequest(
            project_id="project-1",
            resolved_api_key="key",
            prompt_system="system",
            prompt_user="user",
            prompt_messages=[],
            prompt_render_log_json='{"task":"chapter_analyze"}',
            llm_call=_prepared_llm_call(),
        )
        call_llm_and_record_mock.return_value = SimpleNamespace(
            text="{}",
            finish_reason="length",
            run_id="run-1",
            latency_ms=234,
            dropped_params=["temperature"],
        )
        contract_for_task_mock.return_value = SimpleNamespace(
            parse=lambda *_args, **_kwargs: SimpleNamespace(
                data={"chapter_summary": "summary"},
                warnings=["analysis_warning"],
                parse_error={"code": "ANALYSIS_PARSE_ERROR"},
            )
        )

        out = analyze_chapter(
            request_id="rid-1",
            chapter_id="chapter-1",
            body=ChapterAnalyzeRequest(instruction="analyze"),
            user_id="user-1",
            x_llm_provider=None,
            x_llm_api_key=None,
        )

        self.assertEqual(out["chapter_summary"], "summary")
        self.assertEqual(out["generation_run_id"], "run-1")
        self.assertEqual(out["latency_ms"], 234)
        self.assertEqual(out["dropped_params"], ["temperature"])
        self.assertEqual(out["warnings"], ["analysis_warning"])
        self.assertEqual(out["parse_error"], {"code": "ANALYSIS_PARSE_ERROR"})
        self.assertEqual(out["finish_reason"], "length")

    @patch("app.services.chapter_analysis_app_service.contract_for_task")
    @patch("app.services.chapter_analysis_app_service.call_llm_and_record")
    @patch("app.services.chapter_analysis_app_service.prepare_chapter_analyze_request")
    def test_analyze_chapter_auto_memory_update_parse_error_is_fail_soft(
        self,
        prepare_request,
        call_llm_and_record_mock,
        contract_for_task_mock,
    ) -> None:
        prepare_request.return_value = PreparedChapterAnalyzeRequest(
            project_id="project-1",
            resolved_api_key="key",
            prompt_system="system",
            prompt_user="user",
            prompt_messages=[],
            prompt_render_log_json='{"task":"chapter_analyze"}',
            llm_call=_prepared_llm_call(),
            auto_memory_update=PreparedChapterAutoMemoryUpdateRequest(
                enabled=True,
                resolved_api_key="key-2",
                prompt_system="mem-system",
                prompt_user="mem-user",
                prompt_messages=[],
                prompt_render_log_json='{"task":"memory_update"}',
                llm_call=_prepared_llm_call(),
            ),
        )
        call_llm_and_record_mock.side_effect = [
            SimpleNamespace(text="analysis-json", finish_reason="stop", run_id="run-analyze", latency_ms=1, dropped_params=[]),
            SimpleNamespace(text="bad-json", finish_reason="length", run_id="run-memupd", latency_ms=2, dropped_params=[]),
        ]

        def _contract(task: str):
            if task == "chapter_analyze":
                return SimpleNamespace(
                    parse=lambda *_args, **_kwargs: SimpleNamespace(
                        data={"chapter_summary": "summary"},
                        warnings=[],
                        parse_error=None,
                    )
                )
            return SimpleNamespace(
                parse=lambda *_args, **_kwargs: SimpleNamespace(
                    data={},
                    warnings=["memory_update_validation_failed"],
                    parse_error={"code": "MEMORY_UPDATE_PARSE_ERROR"},
                )
            )

        contract_for_task_mock.side_effect = _contract

        out = analyze_chapter(
            request_id="rid-2",
            chapter_id="chapter-1",
            body=ChapterAnalyzeRequest(instruction="analyze", auto_propose_memory_update=True),
            user_id="user-1",
            x_llm_provider=None,
            x_llm_api_key=None,
        )

        self.assertEqual(out["generation_run_id"], "run-analyze")
        self.assertEqual(
            out["memory_update_auto_propose"],
            {
                "enabled": True,
                "ok": False,
                "skipped": True,
                "reason": "memupd_parse_error",
                "llm_generation_run_id": "run-memupd",
                "finish_reason": "length",
                "parse_error": {"code": "MEMORY_UPDATE_PARSE_ERROR"},
                "warnings": ["memory_update_validation_failed"],
            },
        )

    def test_prepare_chapter_rewrite_request_requires_analysis(self) -> None:
        with self.assertRaises(AppError) as ctx:
            prepare_chapter_rewrite_request(
                request_id="rid-3",
                chapter_id="chapter-1",
                body=ChapterRewriteRequest(instruction="rewrite", analysis={}),
                user_id="user-1",
                x_llm_provider=None,
                x_llm_api_key=None,
            )

        self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")
        self.assertIn("analysis", ctx.exception.message)

    @patch("app.services.chapter_analysis_app_service.contract_for_task")
    @patch("app.services.chapter_analysis_app_service.call_llm_and_record")
    @patch("app.services.chapter_analysis_app_service.prepare_chapter_rewrite_request")
    def test_rewrite_chapter_attaches_contract_metadata(
        self,
        prepare_request,
        call_llm_and_record_mock,
        contract_for_task_mock,
    ) -> None:
        prepare_request.return_value = PreparedChapterRewriteRequest(
            project_id="project-1",
            resolved_api_key="key",
            prompt_system="system",
            prompt_user="user",
            prompt_messages=[],
            prompt_render_log_json='{"task":"chapter_rewrite"}',
            llm_call=_prepared_llm_call(),
        )
        call_llm_and_record_mock.return_value = SimpleNamespace(
            text="<rewrite>chapter body</rewrite>",
            finish_reason="stop",
            run_id="run-rewrite",
            latency_ms=88,
            dropped_params=[],
        )
        contract_for_task_mock.return_value = SimpleNamespace(
            parse=lambda *_args, **_kwargs: SimpleNamespace(
                data={"content_md": "chapter body", "raw_output": "<rewrite>chapter body</rewrite>"},
                warnings=[],
                parse_error=None,
            )
        )

        out = rewrite_chapter(
            request_id="rid-4",
            chapter_id="chapter-1",
            body=ChapterRewriteRequest(instruction="rewrite", analysis={"overall_notes": "ok"}),
            user_id="user-1",
            x_llm_provider=None,
            x_llm_api_key=None,
        )

        self.assertEqual(out["content_md"], "chapter body")
        self.assertEqual(out["generation_run_id"], "run-rewrite")
        self.assertEqual(out["latency_ms"], 88)
        self.assertEqual(out["finish_reason"], "stop")


if __name__ == "__main__":
    unittest.main()
