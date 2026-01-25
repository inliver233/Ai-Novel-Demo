import json
import logging
import unittest
from unittest.mock import patch

from app.services.generation_pipeline import run_mcp_research_step
from app.services.mcp.service import McpResearchConfig, McpToolCall


class TestMcpResearchStep(unittest.TestCase):
    def test_disabled_noop(self) -> None:
        cfg = McpResearchConfig(enabled=False, allowlist=[], calls=[])
        with patch("app.services.mcp.service.write_generation_run") as write_mock:
            res = run_mcp_research_step(
                logger=logging.getLogger("test"),
                request_id="rid",
                actor_user_id="u",
                project_id="p",
                chapter_id=None,
                config=cfg,
            )
            self.assertFalse(res.applied)
            self.assertEqual(res.context_md, "")
            self.assertEqual(res.tool_runs, [])
            self.assertEqual(res.warnings, [])
            self.assertFalse(write_mock.called)

    def test_allowlist_required(self) -> None:
        cfg = McpResearchConfig(enabled=True, allowlist=[], calls=[McpToolCall(tool_name="mock.echo", args={"text": "hi"})])
        with patch("app.services.mcp.service.write_generation_run") as write_mock:
            res = run_mcp_research_step(
                logger=logging.getLogger("test"),
                request_id="rid",
                actor_user_id="u",
                project_id="p",
                chapter_id=None,
                config=cfg,
            )
            self.assertFalse(res.applied)
            self.assertEqual(res.tool_runs, [])
            self.assertIn("mcp_allowlist_required", res.warnings)
            self.assertFalse(write_mock.called)

    def test_echo_is_recorded_and_redacted(self) -> None:
        secret = "sk-test-SECRET1234"
        cfg = McpResearchConfig(
            enabled=True,
            allowlist=["mock.echo"],
            calls=[McpToolCall(tool_name="mock.echo", args={"text": f"hello {secret}"})],
        )
        with patch("app.services.mcp.service.write_generation_run", return_value="run_1") as write_mock:
            res = run_mcp_research_step(
                logger=logging.getLogger("test"),
                request_id="rid",
                actor_user_id="u",
                project_id="p",
                chapter_id=None,
                config=cfg,
            )

            self.assertTrue(res.applied)
            self.assertEqual([r.run_id for r in res.tool_runs], ["run_1"])
            self.assertNotIn(secret, res.context_md)
            self.assertIn("sk-***", res.context_md)

            self.assertTrue(write_mock.called)
            kwargs = write_mock.call_args.kwargs
            params = json.loads(kwargs["params_json"])
            self.assertEqual(params["tool_name"], "mock.echo")
            self.assertNotIn(secret, json.dumps(params, ensure_ascii=False))

    def test_fail_soft_records_error(self) -> None:
        cfg = McpResearchConfig(
            enabled=True,
            allowlist=["mock.fail"],
            calls=[McpToolCall(tool_name="mock.fail", args={})],
        )
        with patch("app.services.mcp.service.write_generation_run", return_value="run_fail") as write_mock:
            res = run_mcp_research_step(
                logger=logging.getLogger("test"),
                request_id="rid",
                actor_user_id="u",
                project_id="p",
                chapter_id=None,
                config=cfg,
            )

            self.assertFalse(res.applied)
            self.assertEqual(res.context_md, "")
            self.assertEqual([r.run_id for r in res.tool_runs], ["run_fail"])
            self.assertTrue(any("mcp_tool_failed:mock.fail" in w for w in res.warnings))

            kwargs = write_mock.call_args.kwargs
            self.assertEqual(kwargs["run_type"], "mcp_tool")
            self.assertIsNotNone(kwargs["error_json"])


if __name__ == "__main__":
    unittest.main()

