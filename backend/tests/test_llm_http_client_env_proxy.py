from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import app.llm.http_client as http_client


class _DummyClient:
    def __init__(self) -> None:
        self.is_closed = False

    def close(self) -> None:
        self.is_closed = True


class TestLlmHttpClientEnvProxy(unittest.TestCase):
    def setUp(self) -> None:
        self._old_trust_env = os.environ.get("LLM_HTTP_TRUST_ENV")
        self._old_proxy = os.environ.get("LLM_HTTP_PROXY")
        os.environ.pop("LLM_HTTP_TRUST_ENV", None)
        os.environ.pop("LLM_HTTP_PROXY", None)
        http_client.close_llm_http_client()
        if hasattr(http_client._local, "client"):
            delattr(http_client._local, "client")

    def tearDown(self) -> None:
        os.environ.pop("LLM_HTTP_TRUST_ENV", None)
        os.environ.pop("LLM_HTTP_PROXY", None)
        if self._old_trust_env is not None:
            os.environ["LLM_HTTP_TRUST_ENV"] = self._old_trust_env
        if self._old_proxy is not None:
            os.environ["LLM_HTTP_PROXY"] = self._old_proxy
        http_client.close_llm_http_client()
        if hasattr(http_client._local, "client"):
            delattr(http_client._local, "client")

    def test_default_trust_env_false(self) -> None:
        dummy = _DummyClient()
        with patch("app.llm.http_client.httpx.Client", return_value=dummy) as mock_ctor:
            http_client.get_llm_http_client()
        mock_ctor.assert_called_once_with(trust_env=False)

    def test_trust_env_true(self) -> None:
        os.environ["LLM_HTTP_TRUST_ENV"] = "true"
        dummy = _DummyClient()
        with patch("app.llm.http_client.httpx.Client", return_value=dummy) as mock_ctor:
            http_client.get_llm_http_client()
        mock_ctor.assert_called_once_with(trust_env=True)

    def test_explicit_proxy_overrides(self) -> None:
        os.environ["LLM_HTTP_PROXY"] = " http://127.0.0.1:7890 "
        dummy = _DummyClient()
        with patch("app.llm.http_client.httpx.Client", return_value=dummy) as mock_ctor:
            http_client.get_llm_http_client()
        mock_ctor.assert_called_once_with(trust_env=False, proxy="http://127.0.0.1:7890")


if __name__ == "__main__":
    unittest.main()

