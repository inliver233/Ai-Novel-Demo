from __future__ import annotations

import re
import unittest

from app.services import vector_rag_service


class TestVectorChromaCollectionNaming(unittest.TestCase):
    def test_hash_collection_name_is_stable_and_safe(self) -> None:
        a = vector_rag_service._hash_collection_name("project-123", "kb-1")
        b = vector_rag_service._hash_collection_name("project-123", "kb-1")
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("ainovel_"))
        self.assertLessEqual(len(a), 60)
        self.assertRegex(a, r"^[A-Za-z0-9_\\-]+$")

    def test_hash_collection_name_changes_with_kb_id(self) -> None:
        a = vector_rag_service._hash_collection_name("project-123", "kb-1")
        b = vector_rag_service._hash_collection_name("project-123", "kb-2")
        self.assertNotEqual(a, b)

    def test_hash_collection_name_defaults_kb_id(self) -> None:
        a = vector_rag_service._hash_collection_name("project-123", None)
        b = vector_rag_service._hash_collection_name("project-123", "")
        self.assertEqual(a, b)

    def test_legacy_collection_name_is_sanitized_and_bounded(self) -> None:
        name = vector_rag_service._legacy_collection_name("你好 world !!!")
        self.assertLessEqual(len(name), 60)
        self.assertTrue(name)
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9_\\-]+", name))

