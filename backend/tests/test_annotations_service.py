from __future__ import annotations

import unittest

from app.services.annotations_service import apply_position_fallback


class TestAnnotationsService(unittest.TestCase):
    def test_position_fallback_uses_keyword(self) -> None:
        annotations = [
            {
                "id": "m1",
                "type": "hook",
                "title": None,
                "content": "some content",
                "importance": 0.5,
                "position": -1,
                "length": 0,
                "tags": [],
                "metadata": {"keyword": "ABC"},
            }
        ]

        stats = apply_position_fallback(annotations, content_md="XX ABC YY", max_attempts=10)
        self.assertEqual(stats["found"], 1)
        self.assertEqual(annotations[0]["position"], 3)
        self.assertEqual(annotations[0]["length"], 3)

    def test_position_fallback_clamps_invalid_span(self) -> None:
        annotations = [
            {
                "id": "m1",
                "type": "hook",
                "title": "ABC",
                "content": "some content",
                "importance": 0.5,
                "position": 999,
                "length": 10,
                "tags": [],
                "metadata": {},
            }
        ]

        stats = apply_position_fallback(annotations, content_md="Hello ABC world", max_attempts=10)
        self.assertEqual(stats["found"], 1)
        self.assertEqual(annotations[0]["position"], 6)
        self.assertEqual(annotations[0]["length"], 3)

    def test_position_fallback_no_content_is_noop(self) -> None:
        annotations = [{"id": "m1", "type": "hook", "position": -1, "length": 0, "metadata": {"keyword": "ABC"}}]
        stats = apply_position_fallback(annotations, content_md="")
        self.assertEqual(stats["attempted"], 0)
        self.assertEqual(annotations[0]["position"], -1)
        self.assertEqual(annotations[0]["length"], 0)

    def test_position_fallback_does_not_invalidate_valid_spans_beyond_scan_limit(self) -> None:
        content = ("a" * 20005) + "XYZ" + ("b" * 10)
        annotations = [
            {
                "id": "m1",
                "type": "hook",
                "title": "XYZ",
                "content": "some content",
                "importance": 0.5,
                "position": 20005,
                "length": 3,
                "tags": [],
                "metadata": {"keyword": "XYZ"},
            }
        ]

        stats = apply_position_fallback(annotations, content_md=content, max_attempts=10, max_scan_chars=20000)
        self.assertEqual(stats["need_fallback"], 0)
        self.assertEqual(stats["attempted"], 0)
        self.assertEqual(annotations[0]["position"], 20005)
        self.assertEqual(annotations[0]["length"], 3)
