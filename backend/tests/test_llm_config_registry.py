from __future__ import annotations

import unittest

from app.llm.registry import (
    LLMContractLookupError,
    canonical_model_key,
    pricing_contract,
    resolve_base_url,
    resolve_llm_contract,
)


class TestLlmConfigRegistry(unittest.TestCase):
    def test_openai_alias_maps_to_canonical_model_key(self) -> None:
        resolution = resolve_llm_contract("openai", "gpt-4o-mini-2024-07-18", mode="enforce")
        self.assertEqual(resolution.model, "gpt-4o-mini")
        self.assertEqual(resolution.model_key, "openai::gpt-4o-mini")
        self.assertEqual(canonical_model_key("openai", "gpt-4o-mini-2024-07-18", mode="enforce"), "openai::gpt-4o-mini")

    def test_anthropic_alias_maps_to_canonical_model(self) -> None:
        resolution = resolve_llm_contract("anthropic", "claude-3-7-sonnet", mode="enforce")
        self.assertEqual(resolution.model, "claude-3-7-sonnet-20250219")
        self.assertEqual(resolution.compatibility_alias, "claude-3-7-sonnet")

    def test_gateway_provider_allows_unknown_models_in_enforce_mode(self) -> None:
        resolution = resolve_llm_contract("openai_compatible", "gpt-test", mode="enforce")
        self.assertTrue(resolution.is_unknown_model)
        self.assertEqual(resolution.model_key, "openai_compatible::gpt-test")
        self.assertIn("gateway_passthrough", resolution.notes)

    def test_official_provider_unknown_model_is_warning_in_audit_mode(self) -> None:
        resolution = resolve_llm_contract("openai", "gpt-test", mode="audit")
        self.assertTrue(resolution.is_unknown_model)
        self.assertIn("unregistered_model", resolution.notes)

    def test_official_provider_unknown_model_fails_in_enforce_mode(self) -> None:
        with self.assertRaises(LLMContractLookupError) as ctx:
            resolve_llm_contract("openai", "gpt-test", mode="enforce")
        self.assertEqual(ctx.exception.code, "unsupported_model")

    def test_base_url_resolution_uses_provider_default(self) -> None:
        resolution = resolve_base_url("openai", None, mode="enforce")
        self.assertEqual(resolution.base_url, "https://api.openai.com/v1")
        self.assertTrue(resolution.used_default)

    def test_base_url_resolution_requires_gateway_base_url(self) -> None:
        with self.assertRaises(LLMContractLookupError) as ctx:
            resolve_base_url("openai_compatible", None, mode="enforce")
        self.assertEqual(ctx.exception.code, "base_url_required")

    def test_pricing_contract_exists_for_known_model_slot(self) -> None:
        pricing = pricing_contract("openai", "gpt-4o-mini", mode="enforce")
        self.assertIsNotNone(pricing)
        assert pricing is not None
        self.assertEqual(pricing.currency, "USD")
        self.assertEqual(pricing.source, "pending_verification")


if __name__ == "__main__":
    unittest.main()
