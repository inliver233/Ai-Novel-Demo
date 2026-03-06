from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.schemas.chapters import BulkCreateRequest
from app.schemas.limits import MAX_BULK_CREATE_CHAPTERS


class TestChapterBulkCreateSchemaLimits(unittest.TestCase):
    def test_bulk_create_accepts_800_chapters(self) -> None:
        payload = BulkCreateRequest(
            chapters=[{"number": index + 1, "title": f"Chapter {index + 1}", "plan": None} for index in range(800)]
        )

        self.assertEqual(len(payload.chapters), 800)

    def test_bulk_create_accepts_at_cap(self) -> None:
        payload = BulkCreateRequest(
            chapters=[{"number": index + 1, "title": None, "plan": None} for index in range(MAX_BULK_CREATE_CHAPTERS)]
        )

        self.assertEqual(len(payload.chapters), MAX_BULK_CREATE_CHAPTERS)

    def test_bulk_create_rejects_above_cap(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            BulkCreateRequest(
                chapters=[{"number": index + 1, "title": None, "plan": None} for index in range(MAX_BULK_CREATE_CHAPTERS + 1)]
            )

        errors = ctx.exception.errors()
        self.assertTrue(any(err.get("loc") == ("chapters",) for err in errors))
        self.assertTrue(any(err.get("type") == "too_long" for err in errors))


if __name__ == "__main__":
    unittest.main()
