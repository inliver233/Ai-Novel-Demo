from __future__ import annotations

import logging
import unittest
from types import SimpleNamespace
from unittest.mock import ANY, patch

from app.core.errors import AppError
from app.llm.messages import ChatMessage
from app.schemas.chapter_generate import ChapterGenerateRequest
from app.services.chapter_generation_app_service import (
    generate_chapter,
    generate_chapter_precheck,
    run_plan_first_step,
)
from app.services.chapter_generation_models import (
    ChapterMemoryPreparation,
    PreparedChapterGenerateRequest,
)
from app.services.generation_service import PreparedLlmCall


def _prepared_llm_call() -> PreparedLlmCall:
    return PreparedLlmCall(
        provider="openai",
        model="gpt-test",
        base_url="",
        timeout_seconds=30,
        params={"temperature": 0.7},
        params_json='{"temperature": 0.7}',
        extra={},
    )


class TestChapterGenerationAppService(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("test.chapter_generation_app_service")

    def test_generate_chapter_precheck_rejects_plan_first(self) -> None:
        body = ChapterGenerateRequest(mode="replace", instruction="draft", plan_first=True)

        with self.assertRaises(AppError) as ctx:
            generate_chapter_precheck(
                logger=self.logger,
                request_id="rid-precheck",
                chapter_id="chapter-1",
                body=body,
                user_id="user-1",
                x_llm_provider=None,
                x_llm_api_key=None,
            )

        self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")
        self.assertIn("plan_first", ctx.exception.message)

    @patch("app.services.chapter_generation_app_service.prepare_chapter_generate_request")
    def test_generate_chapter_precheck_returns_compatible_payload(self, prepare_request) -> None:
        prepared = PreparedChapterGenerateRequest(
            request_id="rid-precheck",
            chapter_id="chapter-1",
            project_id="project-1",
            macro_seed="macro-1",
            resolved_api_key="",
            llm_call=_prepared_llm_call(),
            prompt_system="system",
            prompt_user="user",
            prompt_messages=[ChatMessage(role="system", content="system"), ChatMessage(role="user", content="user")],
            prompt_render_log={"task": "chapter_generate"},
            style_resolution={"style_mode": "project_default"},
            memory_preparation=ChapterMemoryPreparation(
                memory_pack={"summary": "memory"},
                memory_injection_config={"query_text": "memory query"},
                memory_retrieval_log_json={"enabled": True},
            ),
            mcp_research={"applied": True, "warnings": []},
            prompt_overridden=True,
        )
        prepare_request.return_value = prepared

        data = generate_chapter_precheck(
            logger=self.logger,
            request_id="rid-precheck",
            chapter_id="chapter-1",
            body=ChapterGenerateRequest(mode="replace", instruction="draft"),
            user_id="user-1",
            x_llm_provider=None,
            x_llm_api_key=None,
        )

        precheck = data["precheck"]
        self.assertEqual(precheck["task"], "chapter_generate")
        self.assertEqual(precheck["macro_seed"], "macro-1")
        self.assertEqual(precheck["prompt_system"], "system")
        self.assertEqual(precheck["prompt_user"], "user")
        self.assertEqual(precheck["messages"][0]["role"], "system")
        self.assertEqual(precheck["render_log"], {"task": "chapter_generate"})
        self.assertEqual(precheck["style_resolution"], {"style_mode": "project_default"})
        self.assertEqual(precheck["memory_pack"], {"summary": "memory"})
        self.assertEqual(precheck["memory_injection_config"], {"query_text": "memory query"})
        self.assertEqual(precheck["memory_retrieval_log_json"], {"enabled": True})
        self.assertEqual(precheck["mcp_research"], {"applied": True, "warnings": []})
        self.assertTrue(precheck["prompt_overridden"])

    @patch("app.services.chapter_generation_app_service._append_post_process_steps")
    @patch("app.services.chapter_generation_app_service.run_chapter_generate_llm_step")
    @patch("app.services.chapter_generation_app_service.apply_target_word_count")
    @patch("app.services.chapter_generation_app_service.run_plan_first_step")
    @patch("app.services.chapter_generation_app_service.prepare_chapter_generate_request")
    def test_generate_chapter_merges_plan_and_generation_metadata(
        self,
        prepare_request,
        run_plan_step,
        apply_target_word_count_mock,
        run_generate_step,
        append_post_process,
    ) -> None:
        prepared = PreparedChapterGenerateRequest(
            request_id="rid-generate",
            chapter_id="chapter-1",
            project_id="project-1",
            macro_seed="macro-1",
            resolved_api_key="key",
            llm_call=_prepared_llm_call(),
            render_values={"instruction": "draft"},
            prompt_system="system",
            prompt_user="user",
            prompt_messages=[ChatMessage(role="user", content="user")],
            prompt_render_log_json='{"task":"chapter_generate"}',
            run_params_extra_json={"prompt_inspector": {"macro_seed": "macro-1"}},
        )
        prepare_request.return_value = prepared
        run_plan_step.return_value = (
            {"plan": "first outline", "finish_reason": "stop"},
            ["plan_warning"],
            {"code": "PLAN_PARSE_ERROR"},
        )
        run_generate_step.return_value = SimpleNamespace(
            data={"content_md": "chapter body"},
            warnings=["gen_warning"],
            parse_error={"code": "CHAPTER_PARSE_ERROR"},
            run_id="run-1",
            latency_ms=321,
            dropped_params=["temperature"],
            finish_reason="length",
        )

        data = generate_chapter(
            logger=self.logger,
            request_id="rid-generate",
            chapter_id="chapter-1",
            body=ChapterGenerateRequest(mode="replace", instruction="draft", plan_first=True),
            user_id="user-1",
            x_llm_provider=None,
            x_llm_api_key=None,
        )

        self.assertEqual(data["content_md"], "chapter body")
        self.assertEqual(data["plan"], "first outline")
        self.assertEqual(data["plan_warnings"], ["plan_warning"])
        self.assertEqual(data["plan_parse_error"], {"code": "PLAN_PARSE_ERROR"})
        self.assertEqual(data["warnings"], ["gen_warning"])
        self.assertEqual(data["parse_error"], {"code": "CHAPTER_PARSE_ERROR"})
        self.assertEqual(data["generation_run_id"], "run-1")
        self.assertEqual(data["latency_ms"], 321)
        self.assertEqual(data["dropped_params"], ["temperature"])
        self.assertEqual(data["finish_reason"], "length")
        append_post_process.assert_called_once()
        apply_target_word_count_mock.assert_called_once_with(prepared=prepared, body=ANY)

    @patch("app.services.chapter_generation_app_service.render_main_prompt")
    @patch("app.services.chapter_generation_app_service.inject_plan_into_render_values")
    @patch("app.services.chapter_generation_app_service.run_plan_llm_step")
    def test_run_plan_first_step_rerenders_prompt_with_plan(
        self,
        run_plan_llm_step_mock,
        inject_plan_into_render_values_mock,
        render_main_prompt_mock,
    ) -> None:
        prepared = PreparedChapterGenerateRequest(
            request_id="rid-plan-first",
            chapter_id="chapter-1",
            project_id="project-1",
            macro_seed="macro-1",
            resolved_api_key="key",
            llm_call=_prepared_llm_call(),
            render_values={"instruction": "draft"},
            context_optimizer_enabled=True,
            plan_prompt_system="plan system",
            plan_prompt_user="plan user",
            plan_prompt_messages=[ChatMessage(role="user", content="plan")],
            plan_prompt_render_log_json='{"task":"plan_chapter"}',
            plan_api_key="plan-key",
        )
        body = ChapterGenerateRequest(mode="replace", instruction="draft", plan_first=True)
        run_plan_llm_step_mock.return_value = SimpleNamespace(
            plan_out={"plan": "new plan"},
            warnings=["plan_warning"],
            parse_error={"code": "PLAN_PARSE_ERROR"},
            finish_reason="stop",
        )
        inject_plan_into_render_values_mock.return_value = {"instruction": "draft", "chapter_plan": "new plan"}

        plan_out, plan_warnings, plan_parse_error = run_plan_first_step(
            logger=self.logger,
            prepared=prepared,
            body=body,
            actor_user_id="user-1",
        )

        self.assertEqual(plan_out["plan"], "new plan")
        self.assertEqual(plan_out["finish_reason"], "stop")
        self.assertEqual(plan_warnings, ["plan_warning"])
        self.assertEqual(plan_parse_error, {"code": "PLAN_PARSE_ERROR"})
        self.assertEqual(
            prepared.render_values,
            {"instruction": "draft", "chapter_plan": "new plan", "context_optimizer_enabled": True},
        )
        inject_plan_into_render_values_mock.assert_called_once_with({"instruction": "draft"}, plan_text="new plan")
        render_main_prompt_mock.assert_called_once_with(prepared=prepared, body=body, values=prepared.render_values)


if __name__ == "__main__":
    unittest.main()
