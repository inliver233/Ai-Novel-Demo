from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
LAYER_ORDER = ("smoke", "contract", "critical", "full", "perf-smoke")
COVERAGE_AREAS = ("route", "task", "config", "prompt")


@dataclass(frozen=True)
class GateStep:
    step_id: str
    description: str
    cwd: Path
    command: tuple[str, ...]
    coverage: tuple[str, ...] = ()
    rerun_hint: str = ""


def backend_python(repo_root: Path = REPO_ROOT) -> str:
    candidate = repo_root / "backend/.venv/Scripts/python.exe"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def build_layers(repo_root: Path = REPO_ROOT) -> dict[str, tuple[GateStep, ...]]:
    backend_py = backend_python(repo_root)
    backend_dir = repo_root / "backend"
    frontend_dir = repo_root / "frontend"
    test_dir = repo_root / "test"

    return {
        "smoke": (
            GateStep(
                step_id="backend-quality",
                description="compile + ruff + repo guards",
                cwd=backend_dir,
                command=(backend_py, "scripts/run_quality_gate.py"),
                coverage=("config", "prompt"),
                rerun_hint=r"cd backend && .\.venv\Scripts\python.exe scripts\run_quality_gate.py",
            ),
            GateStep(
                step_id="backend-contract-smoke",
                description="T11/T12/T14 contract smoke tests",
                cwd=backend_dir,
                command=(
                    backend_py,
                    "-m",
                    "unittest",
                    "tests.test_llm_config_registry",
                    "tests.test_llm_config_audit",
                    "tests.test_llm_contract_routes",
                    "tests.test_prompt_preset_integrity",
                    "tests.test_config_env_contract",
                    "tests.test_security_guard_runner",
                    "-v",
                ),
                coverage=("config", "prompt", "route"),
                rerun_hint=r"cd backend && .\.venv\Scripts\python.exe -m unittest tests.test_llm_config_registry tests.test_llm_config_audit tests.test_llm_contract_routes tests.test_prompt_preset_integrity tests.test_config_env_contract tests.test_security_guard_runner -v",
            ),
            GateStep(
                step_id="frontend-lint",
                description="frontend lint + prettier + class guard",
                cwd=frontend_dir,
                command=("npm", "run", "lint"),
                coverage=("route",),
                rerun_hint="cd frontend && npm run lint",
            ),
            GateStep(
                step_id="frontend-unit-smoke",
                description="frontend route/auth/chapter/prompt smoke tests",
                cwd=frontend_dir,
                command=(
                    "npx",
                    "vitest",
                    "run",
                    "src/lib/routes.test.ts",
                    "src/contexts/authRefreshSchedule.test.ts",
                    "src/services/chapterStore.test.ts",
                    "src/pages/prompts/models.test.ts",
                ),
                coverage=("route", "task", "prompt"),
                rerun_hint="cd frontend && npx vitest run src/lib/routes.test.ts src/contexts/authRefreshSchedule.test.ts src/services/chapterStore.test.ts src/pages/prompts/models.test.ts",
            ),
            GateStep(
                step_id="playwright-api-smoke",
                description="API black-box smoke",
                cwd=test_dir,
                command=("npx", "playwright", "test", "specs/api/api-smoke.spec.ts", "--project", "api", "--workers=1"),
                coverage=("route", "task"),
                rerun_hint="cd test && npx playwright test specs/api/api-smoke.spec.ts --project api --workers=1",
            ),
            GateStep(
                step_id="playwright-ui-smoke",
                description="UI navigation smoke",
                cwd=test_dir,
                command=("npx", "playwright", "test", "specs/ui/navigation.spec.ts", "--project", "ui-chromium", "--workers=1"),
                coverage=("route",),
                rerun_hint="cd test && npx playwright test specs/ui/navigation.spec.ts --project ui-chromium --workers=1",
            ),
        ),
        "contract": (
            GateStep(
                step_id="backend-contract-suite",
                description="backend route/task/config/prompt contract tests",
                cwd=backend_dir,
                command=(
                    backend_py,
                    "-m",
                    "unittest",
                    "tests.test_llm_task_preset_resolver",
                    "tests.test_llm_profile_sync_preset_defaults",
                    "tests.test_prompt_preset_resources",
                    "tests.test_prompt_preset_reset_endpoints",
                    "tests.test_auth_session",
                    "tests.test_config_env_contract",
                    "-v",
                ),
                coverage=("route", "task", "config", "prompt"),
                rerun_hint=r"cd backend && .\.venv\Scripts\python.exe -m unittest tests.test_llm_task_preset_resolver tests.test_llm_profile_sync_preset_defaults tests.test_prompt_preset_resources tests.test_prompt_preset_reset_endpoints tests.test_auth_session tests.test_config_env_contract -v",
            ),
            GateStep(
                step_id="playwright-api-contracts",
                description="route/task/prompt API contracts",
                cwd=test_dir,
                command=(
                    "npx",
                    "playwright",
                    "test",
                    "specs/api/chapters-meta.contract.spec.ts",
                    "specs/api/generation-runs.contract.spec.ts",
                    "specs/api/project-task-runtime.contract.spec.ts",
                    "specs/api/prompt-preview.contract.spec.ts",
                    "specs/api/prompt-task-reachability.contract.spec.ts",
                    "--project",
                    "api",
                    "--workers=1",
                ),
                coverage=("route", "task", "prompt"),
                rerun_hint="cd test && npx playwright test specs/api/chapters-meta.contract.spec.ts specs/api/generation-runs.contract.spec.ts specs/api/project-task-runtime.contract.spec.ts specs/api/prompt-preview.contract.spec.ts specs/api/prompt-task-reachability.contract.spec.ts --project api --workers=1",
            ),
            GateStep(
                step_id="db-schema-contract",
                description="database contract smoke",
                cwd=test_dir,
                command=("npx", "playwright", "test", "specs/db/db-schema.spec.ts", "--project", "db", "--workers=1"),
                coverage=("route", "config"),
                rerun_hint="cd test && npx playwright test specs/db/db-schema.spec.ts --project db --workers=1",
            ),
        ),
        "critical": (
            GateStep(
                step_id="backend-full-suite",
                description="backend compileall + full unittest discover",
                cwd=backend_dir,
                command=(backend_py, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"),
                coverage=("route", "task", "config", "prompt"),
                rerun_hint=r'cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v',
            ),
            GateStep(
                step_id="frontend-lint-full",
                description="frontend lint",
                cwd=frontend_dir,
                command=("npm", "run", "lint"),
                coverage=("route", "task", "prompt"),
                rerun_hint="cd frontend && npm run lint",
            ),
            GateStep(
                step_id="frontend-unit-full",
                description="frontend full vitest run",
                cwd=frontend_dir,
                command=("npm", "test", "--", "--run"),
                coverage=("route", "task", "prompt"),
                rerun_hint="cd frontend && npm test -- --run",
            ),
            GateStep(
                step_id="frontend-build",
                description="frontend production build",
                cwd=frontend_dir,
                command=("npm", "run", "build"),
                coverage=("route", "task", "prompt"),
                rerun_hint="cd frontend && npm run build",
            ),
            GateStep(
                step_id="db-snapshot",
                description="schema snapshot verification",
                cwd=repo_root,
                command=("pwsh", "test/scripts/snapshot-db.ps1"),
                coverage=("config",),
                rerun_hint="pwsh test/scripts/snapshot-db.ps1",
            ),
            GateStep(
                step_id="playwright-critical-ui",
                description="critical runtime and prompt UI regression subset",
                cwd=test_dir,
                command=(
                    "npx",
                    "playwright",
                    "test",
                    "specs/ui/task-center.spec.ts",
                    "specs/ui/taskcenter-projecttasks-sse.spec.ts",
                    "specs/ui/batch-generation-runtime-sync.spec.ts",
                    "specs/ui/prompt-studio-preview.spec.ts",
                    "specs/ui/writing-auto-updates-after-generate.spec.ts",
                    "--project",
                    "ui-chromium",
                    "--workers=1",
                ),
                coverage=("route", "task", "prompt"),
                rerun_hint="cd test && npx playwright test specs/ui/task-center.spec.ts specs/ui/taskcenter-projecttasks-sse.spec.ts specs/ui/batch-generation-runtime-sync.spec.ts specs/ui/prompt-studio-preview.spec.ts specs/ui/writing-auto-updates-after-generate.spec.ts --project ui-chromium --workers=1",
            ),
        ),
        "full": (
            GateStep(
                step_id="backend-compileall",
                description="backend compileall baseline",
                cwd=backend_dir,
                command=(backend_py, "-m", "compileall", "-q", "app", "alembic"),
                coverage=("config",),
                rerun_hint=r"cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic",
            ),
            GateStep(
                step_id="backend-full-discover",
                description="backend full unittest discover",
                cwd=backend_dir,
                command=(backend_py, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"),
                coverage=("route", "task", "config", "prompt"),
                rerun_hint=r'cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v',
            ),
            GateStep(
                step_id="frontend-lint-release",
                description="frontend lint",
                cwd=frontend_dir,
                command=("npm", "run", "lint"),
                coverage=("route", "task", "prompt"),
                rerun_hint="cd frontend && npm run lint",
            ),
            GateStep(
                step_id="frontend-vitest-release",
                description="frontend full vitest run",
                cwd=frontend_dir,
                command=("npm", "test", "--", "--run"),
                coverage=("route", "task", "prompt"),
                rerun_hint="cd frontend && npm test -- --run",
            ),
            GateStep(
                step_id="frontend-build-release",
                description="frontend production build",
                cwd=frontend_dir,
                command=("npm", "run", "build"),
                coverage=("route", "task", "prompt"),
                rerun_hint="cd frontend && npm run build",
            ),
            GateStep(
                step_id="db-snapshot-release",
                description="database snapshot verification",
                cwd=repo_root,
                command=("pwsh", "test/scripts/snapshot-db.ps1"),
                coverage=("config",),
                rerun_hint="pwsh test/scripts/snapshot-db.ps1",
            ),
            GateStep(
                step_id="playwright-full-regression",
                description="full playwright regression",
                cwd=test_dir,
                command=("npx", "playwright", "test", "--workers=1"),
                coverage=("route", "task", "config", "prompt"),
                rerun_hint="cd test && npx playwright test --workers=1",
            ),
        ),
        "perf-smoke": (
            GateStep(
                step_id="playwright-perf-quick",
                description="isolated frontend+backend perf quick baseline",
                cwd=test_dir,
                command=("pwsh", "scripts/run-perf-baseline.ps1", "-Scenario", "quick"),
                coverage=("route", "task", "config", "prompt"),
                rerun_hint="cd test && pwsh scripts/run-perf-baseline.ps1 -Scenario quick",
            ),
        ),
    }


def layer_coverage(layers: dict[str, tuple[GateStep, ...]], layer_name: str) -> set[str]:
    covered: set[str] = set()
    for step in layers[layer_name]:
        covered.update(step.coverage)
    return covered


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run repo-local delivery gates by layer.")
    parser.add_argument("--layer", action="append", dest="layers", help="Layer to run. Repeatable; defaults to smoke.")
    parser.add_argument("--list", action="store_true", help="List available layers and steps.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    layers = build_layers()
    if args.list:
        _print_layers(layers)
        return 0
    requested = args.layers or ["smoke"]
    unknown = [layer for layer in requested if layer not in layers]
    if unknown:
        print(f"Unknown layer(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    return execute_layers(layers, requested, dry_run=args.dry_run)


def execute_layers(
    layers: dict[str, tuple[GateStep, ...]],
    requested_layers: list[str],
    *,
    dry_run: bool = False,
) -> int:
    for layer_name in requested_layers:
        print(f"[gate] layer={layer_name} coverage={','.join(sorted(layer_coverage(layers, layer_name)))}")
        for step in layers[layer_name]:
            rendered = subprocess.list2cmdline(list(step.command))
            print(f"[gate:{layer_name}] {step.step_id} :: {step.description}")
            print(f"  cwd={step.cwd}")
            print(f"  cmd={rendered}")
            if dry_run:
                if step.rerun_hint:
                    print(f"  rerun={step.rerun_hint}")
                continue
            try:
                subprocess.run(step.command, cwd=step.cwd, check=True)
            except subprocess.CalledProcessError as exc:
                print(f"[gate:{layer_name}] FAILED step={step.step_id} exit_code={exc.returncode}", file=sys.stderr)
                if step.rerun_hint:
                    print(f"[gate:{layer_name}] rerun={step.rerun_hint}", file=sys.stderr)
                return exc.returncode or 1
    return 0


def _print_layers(layers: dict[str, tuple[GateStep, ...]]) -> None:
    for layer_name in LAYER_ORDER:
        print(f"{layer_name}	coverage={','.join(sorted(layer_coverage(layers, layer_name)))}")
        for step in layers[layer_name]:
            print(f"  - {step.step_id}	{step.description}")


if __name__ == "__main__":
    raise SystemExit(main())
