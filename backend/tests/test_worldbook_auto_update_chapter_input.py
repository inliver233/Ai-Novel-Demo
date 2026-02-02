from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.services.worldbook_auto_update_service import build_worldbook_auto_update_prompt_v1


def _section_text(user_prompt: str, *, section_name: str) -> str:
    marker = f"=== {section_name} ===\n"
    if marker not in user_prompt:
        return ""
    after = user_prompt.split(marker, 1)[1]
    next_idx = after.find("\n\n===")
    if next_idx >= 0:
        return after[:next_idx].strip("\n")
    return after.strip("\n")


class TestWorldbookAutoUpdateChapterInput(unittest.TestCase):
    def test_prompt_includes_summary_and_content(self) -> None:
        _, user = build_worldbook_auto_update_prompt_v1(
            project_id="p1",
            world_setting="",
            chapter_summary_md="SUM",
            chapter_content_md="CONTENT",
            outline_md="",
            existing_worldbook_titles=[],
        )

        self.assertIn("=== chapter_summary ===", user)
        self.assertIn("SUM", _section_text(user, section_name="chapter_summary"))
        self.assertIn("=== chapter_content_md ===", user)
        self.assertIn("CONTENT", _section_text(user, section_name="chapter_content_md"))

    def test_prompt_truncates_summary_and_content_with_env_overrides(self) -> None:
        with patch.dict(
            os.environ,
            {
                "WORLDBOOK_AUTO_UPDATE_CHAPTER_SUMMARY_MAX_CHARS": "5",
                "WORLDBOOK_AUTO_UPDATE_CHAPTER_CONTENT_MAX_CHARS": "7",
            },
            clear=False,
        ):
            _, user = build_worldbook_auto_update_prompt_v1(
                project_id="p1",
                world_setting="",
                chapter_summary_md="S" * 20,
                chapter_content_md="C" * 20,
                outline_md="",
                existing_worldbook_titles=[],
            )

        self.assertEqual(len(_section_text(user, section_name="chapter_summary")), 5)
        self.assertEqual(len(_section_text(user, section_name="chapter_content_md")), 7)

