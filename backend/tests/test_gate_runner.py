from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_gate import COVERAGE_AREAS, LAYER_ORDER, build_layers, layer_coverage
from scripts.run_regression import PROFILE_LAYERS


class TestGateRunner(unittest.TestCase):
    def test_layers_cover_expected_names(self) -> None:
        layers = build_layers(REPO_ROOT)
        self.assertEqual(tuple(layers.keys()), LAYER_ORDER)

    def test_contract_matrix_covers_route_task_config_prompt(self) -> None:
        layers = build_layers(REPO_ROOT)
        covered = set()
        for layer_name in ("smoke", "contract", "critical", "full"):
            covered.update(layer_coverage(layers, layer_name))
        self.assertTrue(set(COVERAGE_AREAS).issubset(covered))

    def test_gate_cli_supports_dry_run_for_multiple_layers(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts/run_gate.py"), "--layer", "smoke", "--layer", "contract", "--dry-run"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("backend-quality", proc.stdout)
        self.assertIn("playwright-api-contracts", proc.stdout)

    def test_gate_cli_supports_full_layer_dry_run(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts/run_gate.py"), "--layer", "full", "--dry-run"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("playwright-full-regression", proc.stdout)
        self.assertIn("db-snapshot-release", proc.stdout)

    def test_regression_profiles_reference_known_layers(self) -> None:
        for layers in PROFILE_LAYERS.values():
            for layer_name in layers:
                self.assertIn(layer_name, LAYER_ORDER)

    def test_gate_cli_supports_perf_smoke_dry_run(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts/run_gate.py"), "--layer", "perf-smoke", "--dry-run"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("playwright-perf-quick", proc.stdout)

    def test_regression_cli_supports_custom_layers_dry_run(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts/run_regression.py"), "--layers", "smoke,contract,full", "--dry-run"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[regression] layers=smoke -> contract -> full", proc.stdout)
        self.assertIn("playwright-full-regression", proc.stdout)


if __name__ == "__main__":
    unittest.main()
