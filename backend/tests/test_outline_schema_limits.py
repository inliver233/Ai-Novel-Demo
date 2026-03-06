from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.schemas.limits import MAX_JSON_CHARS_MEDIUM, MAX_OUTLINE_MD_CHARS, MAX_OUTLINE_STRUCTURE_JSON_CHARS
from app.schemas.outline import OutlineCreate, OutlineUpdate


class TestOutlineSchemaLimits(unittest.TestCase):
    def test_outline_create_accepts_content_beyond_general_markdown_limit(self) -> None:
        content = "x" * 200_001

        payload = OutlineCreate(title="Long outline", content_md=content)

        self.assertEqual(len(payload.content_md or ""), 200_001)

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

    def test_outline_create_accepts_structure_beyond_general_json_limit(self) -> None:
        structure = {"blob": "x" * (MAX_JSON_CHARS_MEDIUM + 1)}

        payload = OutlineCreate(title="Long outline", structure=structure)

        self.assertEqual(len((payload.structure or {}).get("blob", "")), MAX_JSON_CHARS_MEDIUM + 1)

    def test_outline_update_accepts_structure_at_outline_cap(self) -> None:
        structure = {"blob": "x" * (MAX_OUTLINE_STRUCTURE_JSON_CHARS - 11)}

        payload = OutlineUpdate(structure=structure)

        self.assertEqual(len((payload.structure or {}).get("blob", "")), MAX_OUTLINE_STRUCTURE_JSON_CHARS - 11)

    def test_outline_update_rejects_structure_above_outline_cap(self) -> None:
        structure = {"blob": "x" * MAX_OUTLINE_STRUCTURE_JSON_CHARS}

        with self.assertRaises(ValidationError) as ctx:
            OutlineUpdate(structure=structure)

        errors = ctx.exception.errors()
        self.assertTrue(any(err.get("loc") == ("structure",) for err in errors))
        self.assertTrue(any(err.get("type") == "value_error" for err in errors))



if __name__ == "__main__":
    unittest.main()
