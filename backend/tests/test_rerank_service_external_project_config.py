from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import rerank_service


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class _FakeClient:
    def __init__(self, resp: _FakeResponse | None = None, boom: Exception | None = None) -> None:
        self.resp = resp
        self.boom = boom
        self.last_post: dict[str, object] | None = None

    def post(self, url: str, headers: dict[str, str], json: dict[str, object], timeout: float):  # type: ignore[no-untyped-def]
        self.last_post = {"url": url, "headers": headers, "json": json, "timeout": timeout}
        if self.boom is not None:
            raise self.boom
        assert self.resp is not None
        return self.resp


class TestRerankServiceExternalProjectConfig(unittest.TestCase):
    def test_external_rerank_uses_override_config_and_builds_payload(self) -> None:
        candidates = [
            {"id": "a", "text": "apple banana", "metadata": {}},
            {"id": "b", "text": "dragon castle", "metadata": {}},
        ]
        fake = _FakeClient(
            resp=_FakeResponse(
                {
                    "results": [
                        {"index": 1, "score": 0.9},
                        {"index": 0, "score": 0.1},
                    ]
                }
            )
        )

        external = {
            "base_url": "http://127.0.0.1:4011",
            "model": "rerank-mock",
            "api_key": "rk-test",
            "timeout_seconds": 12,
        }

        with patch.object(rerank_service, "get_llm_http_client", return_value=fake):
            reranked, obs = rerank_service.rerank_candidates(
                query_text="dragon castle",
                candidates=candidates,
                method="external_rerank_api",
                top_k=20,
                hybrid_alpha=None,
                external=external,
                score_fn=lambda **_: 0.0,
            )

        self.assertEqual([c.get("id") for c in reranked], ["b", "a"])
        self.assertEqual(obs.get("method"), "external_rerank_api")
        self.assertEqual(obs.get("provider"), "external_rerank_api")
        self.assertEqual(obs.get("model"), "rerank-mock")

        self.assertIsNotNone(fake.last_post)
        assert fake.last_post is not None
        self.assertEqual(fake.last_post["url"], "http://127.0.0.1:4011/rerank")
        self.assertEqual(fake.last_post["headers"], {"Authorization": "Bearer rk-test"})
        self.assertEqual(
            fake.last_post["json"],
            {"model": "rerank-mock", "query": "dragon castle", "documents": ["apple banana", "dragon castle"]},
        )
        self.assertEqual(fake.last_post["timeout"], 12.0)

    def test_external_rerank_failsoft_falls_back(self) -> None:
        candidates = [
            {"id": "x", "text": "dragon", "metadata": {}},
            {"id": "y", "text": "dragon", "metadata": {}},
        ]
        fake = _FakeClient(boom=RuntimeError("boom"))

        with patch.object(rerank_service, "get_llm_http_client", return_value=fake):
            reranked, obs = rerank_service.rerank_candidates(
                query_text="dragon",
                candidates=candidates,
                method="external_rerank_api",
                top_k=20,
                hybrid_alpha=None,
                external={"base_url": "http://127.0.0.1:4011", "api_key": "rk-test"},
                score_fn=lambda **_: 0.0,
            )

        self.assertEqual([c.get("id") for c in reranked], ["x", "y"])
        self.assertIsInstance(obs.get("errors"), list)
        self.assertGreaterEqual(len(obs.get("errors") or []), 1)
        self.assertNotEqual(obs.get("method"), "external_rerank_api")
