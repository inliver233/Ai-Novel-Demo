from __future__ import annotations

import unittest

from app.services.vector_rag_service import _merge_kb_candidates, _merge_kb_candidates_rrf


class TestVectorPriorityRetrieval(unittest.TestCase):
    def test_rrf_merge_prefers_higher_score_then_kb_order_then_distance(self) -> None:
        per_kb_candidates = {
            "kb1": [
                {"id": "c1", "distance": 0.2, "text": "kb1:c1", "metadata": {"kb_id": "kb1"}},
                {"id": "c2", "distance": 0.1, "text": "kb1:c2", "metadata": {"kb_id": "kb1"}},
            ],
            "kb2": [
                {"id": "c1", "distance": 0.05, "text": "kb2:c1", "metadata": {"kb_id": "kb2"}},
                {"id": "c3", "distance": 0.3, "text": "kb2:c3", "metadata": {"kb_id": "kb2"}},
            ],
        }
        weights = {"kb1": 1.0, "kb2": 1.0}
        orders = {"kb1": 0, "kb2": 1}

        candidates, obs = _merge_kb_candidates_rrf(
            kb_ids=["kb1", "kb2"],
            per_kb_candidates=per_kb_candidates,
            kb_weights=weights,
            kb_orders=orders,
            rrf_k=60,
        )

        # c1 appears in both KBs -> higher score than singletons.
        # For tied singletons (c2 vs c3), kb_order decides.
        self.assertEqual([c.get("id") for c in candidates[:3]], ["c1", "c2", "c3"])
        self.assertEqual(obs.get("mode"), "rrf")

        # For the same candidate id, prefer the instance with lower distance.
        c1 = next(c for c in candidates if c.get("id") == "c1")
        self.assertAlmostEqual(float(c1.get("distance") or 0.0), 0.05, places=6)

    def test_priority_merge_prefers_high_then_fills_from_normal(self) -> None:
        per_kb_candidates = {
            "kb_high": [
                {"id": "A", "distance": 0.1, "metadata": {"kb_id": "kb_high"}},
                {"id": "B", "distance": 0.2, "metadata": {"kb_id": "kb_high"}},
            ],
            "kb_normal": [
                {"id": "C", "distance": 0.05, "metadata": {"kb_id": "kb_normal"}},
                {"id": "D", "distance": 0.06, "metadata": {"kb_id": "kb_normal"}},
            ],
        }
        weights = {"kb_high": 1.0, "kb_normal": 1.0}
        orders = {"kb_high": 0, "kb_normal": 1}
        priority_groups = {"kb_high": "high", "kb_normal": "normal"}

        candidates, obs = _merge_kb_candidates(
            kb_ids=["kb_high", "kb_normal"],
            per_kb_candidates=per_kb_candidates,
            kb_weights=weights,
            kb_orders=orders,
            kb_priority_groups=priority_groups,
            top_k=3,
            priority_enabled=True,
            rrf_k=60,
        )

        self.assertEqual([c.get("id") for c in candidates], ["A", "B", "C"])
        self.assertEqual(obs.get("mode"), "priority")
        self.assertTrue(bool(obs.get("used_normal")))

    def test_priority_merge_skips_normal_when_high_is_enough(self) -> None:
        per_kb_candidates = {
            "kb_high": [
                {"id": "A", "distance": 0.1, "metadata": {"kb_id": "kb_high"}},
                {"id": "B", "distance": 0.2, "metadata": {"kb_id": "kb_high"}},
            ],
            "kb_normal": [
                {"id": "C", "distance": 0.05, "metadata": {"kb_id": "kb_normal"}},
            ],
        }
        weights = {"kb_high": 1.0, "kb_normal": 1.0}
        orders = {"kb_high": 0, "kb_normal": 1}
        priority_groups = {"kb_high": "high", "kb_normal": "normal"}

        candidates, obs = _merge_kb_candidates(
            kb_ids=["kb_high", "kb_normal"],
            per_kb_candidates=per_kb_candidates,
            kb_weights=weights,
            kb_orders=orders,
            kb_priority_groups=priority_groups,
            top_k=1,
            priority_enabled=True,
            rrf_k=60,
        )

        self.assertEqual([c.get("id") for c in candidates], ["A"])
        self.assertEqual(obs.get("mode"), "priority")
        self.assertFalse(bool(obs.get("used_normal")))

    def test_priority_enabled_without_high_falls_back_to_rrf(self) -> None:
        per_kb_candidates = {
            "kb1": [{"id": "A", "distance": 0.1, "metadata": {"kb_id": "kb1"}}],
            "kb2": [{"id": "B", "distance": 0.2, "metadata": {"kb_id": "kb2"}}],
        }
        weights = {"kb1": 1.0, "kb2": 1.0}
        orders = {"kb1": 0, "kb2": 1}
        priority_groups = {"kb1": "normal", "kb2": "normal"}

        candidates, obs = _merge_kb_candidates(
            kb_ids=["kb1", "kb2"],
            per_kb_candidates=per_kb_candidates,
            kb_weights=weights,
            kb_orders=orders,
            kb_priority_groups=priority_groups,
            top_k=10,
            priority_enabled=True,
            rrf_k=60,
        )

        self.assertEqual([c.get("id") for c in candidates[:2]], ["A", "B"])
        self.assertEqual(obs.get("mode"), "rrf")
        self.assertEqual(obs.get("note"), "no_high_priority_kbs")

