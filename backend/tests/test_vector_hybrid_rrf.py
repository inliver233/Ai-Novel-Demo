from __future__ import annotations

import unittest

from app.services import vector_rag_service


class TestVectorHybridRrf(unittest.TestCase):
    def test_rrf_score_prefers_better_rank(self) -> None:
        a = vector_rag_service._rrf_score(vector_rank=1, fts_rank=None, k=60)
        b = vector_rag_service._rrf_score(vector_rank=10, fts_rank=None, k=60)
        self.assertGreater(a, b)

    def test_rrf_score_combines_two_lists(self) -> None:
        only_vec = vector_rag_service._rrf_score(vector_rank=1, fts_rank=None, k=60)
        only_fts = vector_rag_service._rrf_score(vector_rank=None, fts_rank=1, k=60)
        both = vector_rag_service._rrf_score(vector_rank=1, fts_rank=1, k=60)
        self.assertGreater(both, only_vec)
        self.assertGreater(both, only_fts)

    def test_pgvector_literal_format(self) -> None:
        lit = vector_rag_service._pgvector_literal([1.0, 2.5, -3.125])
        self.assertTrue(lit.startswith("["))
        self.assertTrue(lit.endswith("]"))
        self.assertIn(",", lit)

