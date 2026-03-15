from __future__ import annotations

import logging
import unittest
from unittest.mock import MagicMock, patch

from app.core.errors import AppError
from app.services.chapter_generation_models import PreparedChapterGenerateRequest
from app.services.chapter_generation_stream_service import prepare_chapter_stream_request
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


class TestChapterGenerationStreamService(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("test.chapter_generation_stream_service")

    @patch("app.services.chapter_generation_stream_service.prepare_chapter_generate_request")
    def test_prepare_stream_request_returns_prepared_request(self, prepare_request) -> None:
        prepared = PreparedChapterGenerateRequest(
            request_id="rid-stream",
            chapter_id="chapter-1",
            project_id="project-1",
            macro_seed="macro-1",
            resolved_api_key="key",
            llm_call=_prepared_llm_call(),
            render_values={"instruction": "draft"},
        )
        prepare_request.return_value = prepared

        result = prepare_chapter_stream_request(
            logger=self.logger,
            request_id="rid-stream",
            chapter_id="chapter-1",
            body=MagicMock(),
            user_id="user-1",
            x_llm_provider=None,
            x_llm_api_key=None,
        )

        self.assertIs(result, prepared)

    @patch("app.services.chapter_generation_stream_service.prepare_chapter_generate_request")
    def test_prepare_stream_request_raises_when_render_values_missing(self, prepare_request) -> None:
        prepare_request.return_value = PreparedChapterGenerateRequest(
            request_id="rid-stream",
            chapter_id="chapter-1",
            project_id="project-1",
            macro_seed="macro-1",
            resolved_api_key="key",
            llm_call=_prepared_llm_call(),
        )

        with self.assertRaises(AppError) as ctx:
            prepare_chapter_stream_request(
                logger=self.logger,
                request_id="rid-stream",
                chapter_id="chapter-1",
                body=MagicMock(),
                user_id="user-1",
                x_llm_provider=None,
                x_llm_api_key=None,
            )

        self.assertEqual(ctx.exception.code, "INTERNAL_ERROR")


if __name__ == "__main__":
    unittest.main()
