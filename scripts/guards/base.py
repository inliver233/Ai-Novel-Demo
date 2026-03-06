from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess
from typing import Iterable


Severity = str


@dataclass(frozen=True)
class Finding:
    severity: Severity
    path: str
    message: str
    line: int | None = None


@dataclass(frozen=True)
class GuardResult:
    guard_id: str
    description: str
    findings: tuple[Finding, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def has_errors(self) -> bool:
        return any(finding.severity == "error" for finding in self.findings)


@dataclass
class GuardContext:
    repo_root: Path
    _candidate_files: list[Path] | None = field(default=None, init=False, repr=False)

    def candidate_files(self) -> list[Path]:
        if self._candidate_files is None:
            self._candidate_files = _collect_candidate_files(self.repo_root)
        return list(self._candidate_files)


def build_context() -> GuardContext:
    repo_root = Path(__file__).resolve().parents[2]
    return GuardContext(repo_root=repo_root)


def make_result(
    guard_id: str,
    description: str,
    findings: Iterable[Finding] = (),
    notes: Iterable[str] = (),
) -> GuardResult:
    return GuardResult(
        guard_id=guard_id,
        description=description,
        findings=tuple(findings),
        notes=tuple(notes),
    )


def run_git(repo_root: Path, *args: str) -> list[str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def is_text_file(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:2048]
    except OSError:
        return False
    return b"\x00" not in chunk


def read_text_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _collect_candidate_files(repo_root: Path) -> list[Path]:
    tracked = run_git(repo_root, "ls-files", "--cached")
    untracked = run_git(repo_root, "ls-files", "--others", "--exclude-standard")
    files: list[Path] = []
    seen: set[Path] = set()
    for relative in [*tracked, *untracked]:
        path = repo_root / relative
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        files.append(path)
    return sorted(files)

