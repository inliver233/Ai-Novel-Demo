from __future__ import annotations

from scripts.guards.base import Finding, GuardContext, make_result, read_text_lines

GUARD_ID = "file-line-count-guard"
DESCRIPTION = "Warn on oversized backend Python files so hotspots are visible before enforce mode."

WARNING_THRESHOLD = 400
SHOW_TOP = 20


def run(context: GuardContext):
    findings: list[Finding] = []
    backend_root = context.repo_root / "backend" / "app"
    oversized: list[tuple[int, str]] = []
    for path in backend_root.rglob("*.py"):
        relative = path.relative_to(context.repo_root).as_posix()
        line_count = len(read_text_lines(path))
        if line_count > WARNING_THRESHOLD:
            oversized.append((line_count, relative))
    for line_count, relative in sorted(oversized, reverse=True)[:SHOW_TOP]:
        findings.append(Finding("warning", relative, f"file has {line_count} lines (>{WARNING_THRESHOLD})"))
    hidden = max(0, len(oversized) - SHOW_TOP)
    notes = [
        f"warning-only in Wave A; threshold={WARNING_THRESHOLD} lines; shown_top={SHOW_TOP}",
    ]
    if hidden:
        notes.append(f"{hidden} additional oversized files omitted from output")
    return make_result(GUARD_ID, DESCRIPTION, findings=findings, notes=notes)

