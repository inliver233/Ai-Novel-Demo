from __future__ import annotations

import unittest

from app.services.post_edit_validation import validate_content_optimize_output, validate_post_edit_output


class TestPostEditValidation(unittest.TestCase):
    def test_empty_is_invalid(self) -> None:
        warnings = validate_post_edit_output(raw_content="hello", edited_content="")
        self.assertIn("post_edit_no_content", warnings)

    def test_too_short_is_invalid(self) -> None:
        raw = "a" * 600
        edited = "b" * 60
        warnings = validate_post_edit_output(raw_content=raw, edited_content=edited)
        self.assertIn("post_edit_too_short", warnings)

    def test_missing_paragraphs_is_invalid(self) -> None:
        raw = "\n\n".join(["p" * 60, "q" * 60, "r" * 60, "s" * 60])
        edited = "p" * 120
        warnings = validate_post_edit_output(raw_content=raw, edited_content=edited)
        self.assertIn("post_edit_missing_paragraphs", warnings)

    def test_reasonable_output_is_ok(self) -> None:
        raw = "\n\n".join(["p" * 120, "q" * 120, "r" * 120])
        edited = "\n\n".join(["p" * 110, "q" * 130, "r" * 105])
        warnings = validate_post_edit_output(raw_content=raw, edited_content=edited)
        self.assertEqual(warnings, [])


class TestContentOptimizeValidation(unittest.TestCase):
    def test_empty_is_invalid(self) -> None:
        warnings = validate_content_optimize_output(raw_content="hello", optimized_content="")
        self.assertIn("content_optimize_no_content", warnings)

    def test_too_short_is_invalid(self) -> None:
        raw = "a" * 600
        edited = "b" * 60
        warnings = validate_content_optimize_output(raw_content=raw, optimized_content=edited)
        self.assertIn("content_optimize_too_short", warnings)

    def test_missing_paragraphs_is_invalid(self) -> None:
        raw = "\n\n".join(["p" * 60, "q" * 60, "r" * 60, "s" * 60])
        edited = "p" * 120
        warnings = validate_content_optimize_output(raw_content=raw, optimized_content=edited)
        self.assertIn("content_optimize_missing_paragraphs", warnings)

    def test_reasonable_output_is_ok(self) -> None:
        raw = "\n\n".join(["p" * 120, "q" * 120, "r" * 120])
        edited = "\n\n".join(["p" * 110, "q" * 130, "r" * 105])
        warnings = validate_content_optimize_output(raw_content=raw, optimized_content=edited)
        self.assertEqual(warnings, [])
