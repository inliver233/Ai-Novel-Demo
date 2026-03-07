from __future__ import annotations

import unittest

from app.llm.audit import audit_registry, audit_rows


class TestLlmConfigAudit(unittest.TestCase):
    def test_registry_audit_has_no_errors(self) -> None:
        findings = audit_registry()
        self.assertFalse([item for item in findings if item.severity == "error"])

    def test_row_audit_warns_for_compat_alias_and_unknown_model(self) -> None:
        findings = audit_rows(
            [
                {"source": "profile:1", "provider": "anthropic", "model": "claude-3-7-sonnet", "base_url": None},
                {"source": "profile:2", "provider": "openai", "model": "gpt-test", "base_url": None},
            ],
            mode="audit",
        )
        messages = {item.message for item in findings}
        self.assertIn("compatibility alias mapped to claude-3-7-sonnet-20250219", messages)
        self.assertIn("unregistered model", messages)

    def test_row_audit_escalates_invalid_gateway_config_in_enforce_mode(self) -> None:
        findings = audit_rows(
            [{"source": "preset:p1", "provider": "openai_compatible", "model": "gpt-test", "base_url": None}],
            mode="enforce",
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "error")
        self.assertEqual(findings[0].message, "base_url_required")

    def test_row_audit_warns_for_invalid_provider_in_audit_mode(self) -> None:
        findings = audit_rows(
            [{"source": "preset:p1", "provider": "unknown", "model": "whatever", "base_url": None}],
            mode="audit",
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "warning")
        self.assertEqual(findings[0].message, "unsupported_provider")


if __name__ == "__main__":
    unittest.main()
