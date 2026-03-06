from __future__ import annotations

from scripts.guards.base import Finding, GuardContext, make_result, read_text_lines

GUARD_ID = "backend-no-print-guard"
DESCRIPTION = "Reject print() usage inside backend/app runtime code."


def run(context: GuardContext):
    findings: list[Finding] = []
    for path in context.repo_root.joinpath("backend", "app").rglob("*.py"):
        relative = path.relative_to(context.repo_root).as_posix()
        for line_number, line in enumerate(read_text_lines(path), start=1):
            if "print(" not in line:
                continue
            findings.append(Finding("error", relative, "use structured logging instead of print()", line=line_number))
    return make_result(GUARD_ID, DESCRIPTION, findings=findings)

