from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.guards.base import build_context
from scripts.guards.registry import REGISTRY


class TestDeploymentSecurityGuard(unittest.TestCase):
    def test_registry_contains_deployment_guard(self) -> None:
        self.assertIn("deployment-security-guard", REGISTRY)

    def test_deployment_guard_passes_repo_baseline(self) -> None:
        result = REGISTRY["deployment-security-guard"][1](build_context())
        self.assertFalse(result.has_errors, result.findings)


if __name__ == "__main__":
    unittest.main()
