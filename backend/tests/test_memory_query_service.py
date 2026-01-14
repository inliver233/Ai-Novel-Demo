from __future__ import annotations

import unittest

from app.schemas.settings import QueryPreprocessingConfig
from app.services.memory_query_service import normalize_query_text


class TestMemoryQueryService(unittest.TestCase):
    def test_disabled_passthrough(self) -> None:
        raw = "  Hello #tag\n"
        normalized, obs = normalize_query_text(query_text=raw, config=QueryPreprocessingConfig(enabled=False))
        self.assertEqual(normalized, raw)
        self.assertFalse(obs["enabled"])
        self.assertEqual(obs["raw_query_text"], raw)
        self.assertEqual(obs["normalized_query_text"], raw)

    def test_tag_extract_respects_allowlist(self) -> None:
        raw = "Hello #foo #bar world"
        cfg = QueryPreprocessingConfig(enabled=True, tags=["foo"], exclusion_rules=[], index_ref_enhance=False)
        normalized, obs = normalize_query_text(query_text=raw, config=cfg)
        self.assertEqual(obs["extracted_tags"], ["foo"])
        self.assertEqual(obs["ignored_tags"], ["bar"])
        self.assertEqual(normalized, "Hello #bar world")

    def test_exclusion_rules_remove_substrings(self) -> None:
        raw = "Hello REMOVE world"
        cfg = QueryPreprocessingConfig(enabled=True, tags=[], exclusion_rules=["REMOVE"], index_ref_enhance=False)
        normalized, obs = normalize_query_text(query_text=raw, config=cfg)
        self.assertEqual(obs["applied_exclusion_rules"], ["REMOVE"])
        self.assertEqual(normalized, "Hello world")

    def test_index_ref_enhance_appends_tokens(self) -> None:
        raw = "回顾第12章的内容"
        cfg = QueryPreprocessingConfig(enabled=True, tags=[], exclusion_rules=[], index_ref_enhance=True)
        normalized, obs = normalize_query_text(query_text=raw, config=cfg)
        self.assertIn("chapter:12", normalized)
        self.assertEqual(obs["index_refs"], ["chapter:12"])

    def test_empty_input_is_deterministic(self) -> None:
        cfg = QueryPreprocessingConfig(enabled=True)
        normalized, obs = normalize_query_text(query_text="", config=cfg)
        self.assertEqual(normalized, "")
        self.assertEqual(obs["normalized_query_text"], "")
        self.assertEqual(obs["extracted_tags"], [])
        self.assertEqual(obs["applied_exclusion_rules"], [])

