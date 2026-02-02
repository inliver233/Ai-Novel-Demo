from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.services.worldbook_auto_update_service import _build_existing_worldbook_entries_preview_for_prompt


class TestWorldbookAutoUpdateExistingEntriesPreview(unittest.TestCase):
    def test_preview_limits_and_truncates_and_redacts(self) -> None:
        rows = [
            ("A", '["k1","k2","k3"]', "line1\nsk-1234567890abcd\nline2"),
            ("B", None, "B content"),
            ("C", '["c1"]', "C content"),
        ]

        with patch.dict(
            os.environ,
            {
                "WORLDBOOK_AUTO_UPDATE_EXISTING_ENTRIES_PREVIEW_LIMIT": "2",
                "WORLDBOOK_AUTO_UPDATE_EXISTING_ENTRY_KEYWORDS_LIMIT": "2",
                "WORLDBOOK_AUTO_UPDATE_EXISTING_ENTRY_CONTENT_PREVIEW_CHARS": "8",
            },
            clear=False,
        ):
            out = _build_existing_worldbook_entries_preview_for_prompt(rows)

        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].get("title"), "A")
        self.assertEqual(out[0].get("keywords"), ["k1", "k2"])

        preview = str(out[0].get("content_preview") or "")
        self.assertNotIn("\n", preview)
        self.assertLessEqual(len(preview), 8)
        self.assertNotIn("sk-1234567890abcd", preview)

