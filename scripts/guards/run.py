from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.guards.base import GuardResult, build_context
from scripts.guards.registry import REGISTRY


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run repository hygiene/quality guards.")
    parser.add_argument("guards", nargs="*", help="Guard IDs to run. Default: all registered guards.")
    parser.add_argument("--list", action="store_true", help="List available guards and exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list:
        for guard_id, (description, _) in REGISTRY.items():
            print(f"{guard_id}\t{description}")
        return 0

    requested = args.guards or list(REGISTRY.keys())
    unknown = [guard_id for guard_id in requested if guard_id not in REGISTRY]
    if unknown:
        print(f"Unknown guard(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    context = build_context()
    results = [REGISTRY[guard_id][1](context) for guard_id in requested]
    _print_results(results)
    return 1 if any(result.has_errors for result in results) else 0


def _print_results(results: list[GuardResult]) -> None:
    for result in results:
        status = "FAIL" if result.has_errors else "PASS"
        print(f"[{status}] {result.guard_id} - {result.description}")
        if result.notes:
            for note in result.notes:
                print(f"  note: {note}")
        if not result.findings:
            print("  no findings")
            continue
        for finding in result.findings:
            location = finding.path
            if finding.line is not None:
                location = f"{location}:{finding.line}"
            print(f"  - {finding.severity.upper()} {location} :: {finding.message}")


if __name__ == "__main__":
    raise SystemExit(main())
