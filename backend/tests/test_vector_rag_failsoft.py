from __future__ import annotations

import unittest

from app.core.config import settings
from app.services.vector_rag_service import query_project, vector_rag_status


class TestVectorRagFailSoft(unittest.TestCase):
    def test_status_is_safe_when_embedding_missing(self) -> None:
        orig_base_url = settings.vector_embedding_base_url
        orig_model = settings.vector_embedding_model
        orig_key = settings.vector_embedding_api_key
        try:
            settings.vector_embedding_base_url = None
            settings.vector_embedding_model = None
            settings.vector_embedding_api_key = None

            out = vector_rag_status(project_id="p1")
            self.assertIsInstance(out, dict)
            self.assertFalse(out.get("enabled"))
            self.assertIsInstance(out.get("candidates"), list)
        finally:
            settings.vector_embedding_base_url = orig_base_url
            settings.vector_embedding_model = orig_model
            settings.vector_embedding_api_key = orig_key

    def test_query_is_safe_when_embedding_missing(self) -> None:
        orig_base_url = settings.vector_embedding_base_url
        orig_model = settings.vector_embedding_model
        orig_key = settings.vector_embedding_api_key
        try:
            settings.vector_embedding_base_url = None
            settings.vector_embedding_model = None
            settings.vector_embedding_api_key = None

            out = query_project(project_id="p1", query_text="hello")
            self.assertIsInstance(out, dict)
            self.assertFalse(out.get("enabled"))
            self.assertIsInstance(out.get("candidates"), list)
            self.assertIsInstance(out.get("final"), dict)
        finally:
            settings.vector_embedding_base_url = orig_base_url
            settings.vector_embedding_model = orig_model
            settings.vector_embedding_api_key = orig_key

