from __future__ import annotations

from pathlib import Path
import unittest

from app.api.routes.outline import (
    _build_outline_generation_guidance,
    _enforce_outline_chapter_coverage,
    _extract_target_chapter_count,
    _recommend_outline_max_tokens,
)
from app.services.prompting import render_template


class TestOutlineGenerationGuidance(unittest.TestCase):
    def test_extract_target_chapter_count(self) -> None:
        self.assertEqual(_extract_target_chapter_count({"chapter_count": 200}), 200)
        self.assertEqual(_extract_target_chapter_count({"chapter_count": "120"}), 120)
        self.assertIsNone(_extract_target_chapter_count({"chapter_count": "abc"}))
        self.assertIsNone(_extract_target_chapter_count({"chapter_count": 0}))
        self.assertIsNone(_extract_target_chapter_count({}))
        self.assertIsNone(_extract_target_chapter_count(None))

    def test_build_outline_generation_guidance_for_long_form(self) -> None:
        guidance = _build_outline_generation_guidance(200)
        self.assertIn("200", guidance["chapter_count_rule"])
        self.assertIn("1~2", guidance["chapter_detail_rule"])

    def test_build_outline_generation_guidance_default(self) -> None:
        guidance = _build_outline_generation_guidance(None)
        self.assertEqual(guidance["chapter_count_rule"], "")
        self.assertIn("5~9", guidance["chapter_detail_rule"])

    def test_recommend_outline_max_tokens(self) -> None:
        # gpt-4o-mini output limit is 16384; 200 chapters should recommend 12000 when current max is lower.
        self.assertEqual(
            _recommend_outline_max_tokens(
                target_chapter_count=200,
                provider="openai",
                model="gpt-4o-mini",
                current_max_tokens=4096,
            ),
            12000,
        )
        # gpt-4 output limit is 8192; recommendation should be clamped.
        self.assertEqual(
            _recommend_outline_max_tokens(
                target_chapter_count=200,
                provider="openai",
                model="gpt-4",
                current_max_tokens=4096,
            ),
            8192,
        )
        # If current max_tokens is already high enough, no override is needed.
        self.assertIsNone(
            _recommend_outline_max_tokens(
                target_chapter_count=200,
                provider="openai",
                model="gpt-4o-mini",
                current_max_tokens=12000,
            )
        )
        # Small chapter count should not override.
        self.assertIsNone(
            _recommend_outline_max_tokens(
                target_chapter_count=20,
                provider="openai",
                model="gpt-4o-mini",
                current_max_tokens=4096,
            )
        )

    def test_outline_contract_template_uses_dynamic_rules(self) -> None:
        template_path = Path("app/resources/prompt_presets/outline_generate_v3/templates/sys.outline.contract.json.md")
        template = template_path.read_text(encoding="utf-8")

        rendered, _missing, error = render_template(
            template,
            values={
                "chapter_count_rule": "chapters 必须输出 200 章，number 需完整覆盖 1..200 且不缺号。",
                "chapter_detail_rule": "beats 每章 1~2 条，极简表达关键推进；若长度受限，优先保留章节覆盖与编号完整。",
            },
            macro_seed="test-seed",
        )
        self.assertIsNone(error)
        self.assertIn("200 章", rendered)
        self.assertIn("1~2 条", rendered)

        rendered_default, _missing_default, error_default = render_template(template, values={}, macro_seed="test-seed")
        self.assertIsNone(error_default)
        self.assertIn("beats 每章 5~9 条", rendered_default)

    def test_enforce_outline_chapter_coverage_autofills_missing_numbers(self) -> None:
        data = {
            "outline_md": "x",
            "chapters": [
                {"number": 1, "title": "第一章", "beats": ["a"]},
                {"number": 3, "title": "第三章", "beats": ["c"]},
            ],
        }
        out, warnings = _enforce_outline_chapter_coverage(data=data, target_chapter_count=4)
        chapters = out["chapters"]
        self.assertEqual([c["number"] for c in chapters], [1, 2, 3, 4])
        self.assertIn("outline_chapter_coverage_autofilled", warnings)
        coverage = out.get("chapter_coverage") or {}
        self.assertEqual(coverage.get("filled_missing_numbers"), [2, 4])
        self.assertEqual(coverage.get("filled_missing_count"), 2)

    def test_enforce_outline_chapter_coverage_dedupes_and_filters_extra(self) -> None:
        data = {
            "outline_md": "x",
            "chapters": [
                {"number": 2, "title": "第二章", "beats": ["b"]},
                {"number": "2", "title": "第二章完整版", "beats": ["b1", "b2"]},
                {"number": 5, "title": "超出范围", "beats": ["overflow"]},
                {"number": "bad", "title": "无效", "beats": []},
            ],
        }
        out, warnings = _enforce_outline_chapter_coverage(data=data, target_chapter_count=3)
        chapters = out["chapters"]
        self.assertEqual([c["number"] for c in chapters], [1, 2, 3])
        self.assertEqual(chapters[1]["title"], "第二章完整版")
        self.assertIn("outline_chapter_number_deduped", warnings)
        self.assertIn("outline_chapter_invalid_filtered", warnings)
        self.assertIn("outline_chapter_beyond_target_filtered", warnings)
        self.assertIn("outline_chapter_coverage_autofilled", warnings)

    def test_enforce_outline_chapter_coverage_no_target_is_noop(self) -> None:
        data = {"outline_md": "x", "chapters": [{"number": 1, "title": "第一章", "beats": ["a"]}]}
        out, warnings = _enforce_outline_chapter_coverage(data=data, target_chapter_count=None)
        self.assertEqual(out["chapters"], data["chapters"])
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
