from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_gate import LAYER_ORDER, build_layers, execute_layers

PROFILE_LAYERS: dict[str, list[str]] = {
    "prepush": ["smoke", "contract"],
    "release": ["critical"],
    "full": ["full"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ordered regression profiles built from repo-local gate layers.")
    parser.add_argument("--profile", choices=sorted(PROFILE_LAYERS.keys()), default="prepush")
    parser.add_argument("--layers", help="Override profile with a comma-separated custom layer list.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    parser.add_argument("--list", action="store_true", help="List profiles and exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list:
        for name, layers in PROFILE_LAYERS.items():
            print(f"{name}	{' -> '.join(layers)}")
        return 0

    requested = _requested_layers(args)
    unknown = [layer for layer in requested if layer not in LAYER_ORDER]
    if unknown:
        print(f"Unknown layer(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    print(f"[regression] layers={' -> '.join(requested)}")
    return execute_layers(build_layers(), requested, dry_run=args.dry_run)


def _requested_layers(args: argparse.Namespace) -> list[str]:
    if args.layers:
        layers = [item.strip() for item in args.layers.split(",") if item.strip()]
        return layers
    return list(PROFILE_LAYERS[args.profile])


if __name__ == "__main__":
    raise SystemExit(main())
