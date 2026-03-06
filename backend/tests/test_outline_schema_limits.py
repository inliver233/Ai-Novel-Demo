from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.schemas.limits import MAX_MD_CHARS, MAX_OUTLINE_MD_CHARS
from app.schemas.outline import OutlineCreate, OutlineUpdate


class TestOutlineSchemaLimits(unittest.TestCase):
    def test_outline_create_accepts_content_beyond_general_markdown_limit(self) -> None:
        content = "x" * (MAX_MD_CHARS + 1)

        payload = OutlineCreate(title="Long outline", content_md=content)

        self.assertEqual(len(payload.content_md or ""), MAX_MD_CHARS + 1)

    def test_outline_update_accepts_content_at_outline_cap(self) -> None:
        content = "x" * MAX_OUTLINE_MD_CHARS

        payload = OutlineUpdate(content_md=content)

        self.assertEqual(len(payload.content_md or ""), MAX_OUTLINE_MD_CHARS)

    def test_outline_update_rejects_content_above_outline_cap(self) -> None:
        content = "x" * (MAX_OUTLINE_MD_CHARS + 1)

        with self.assertRaises(ValidationError) as ctx:
            OutlineUpdate(content_md=content)

        errors = ctx.exception.errors()
        self.assertTrue(any(err.get("loc") == ("content_md",) for err in errors))
        self.assertTrue(any(err.get("type") == "string_too_long" for err in errors))


if __name__ == "__main__":
    unittest.main()
