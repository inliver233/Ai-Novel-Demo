from __future__ import annotations

from pathlib import Path
import subprocess
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run_step(*args: str) -> None:
    cmd = [PYTHON, *args]
    print(f"[quality] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=BACKEND_ROOT, check=True)


def main() -> int:
    run_step("-m", "compileall", "-q", "app", "alembic", "tests", "scripts", "..\\scripts\\guards")
    run_step("-m", "ruff", "check", "app", "tests", "scripts", "..\\scripts\\guards")
    run_step("..\\scripts\\guards\\run.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
