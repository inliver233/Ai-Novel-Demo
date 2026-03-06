from __future__ import annotations

from scripts.guards.base import Finding, GuardContext, make_result

GUARD_ID = "db-artifacts-guard"
DESCRIPTION = "Block DB files, temp artifacts, logs, and screenshot/debug outputs from entering git-visible paths."

DB_SUFFIXES = (
    ".db",
    ".db-wal",
    ".db-shm",
    ".db-journal",
    ".sqlite",
    ".sqlite-wal",
    ".sqlite-shm",
    ".sqlite-journal",
    ".sqlite3",
    ".sqlite3-wal",
    ".sqlite3-shm",
    ".sqlite3-journal",
)
LOG_SUFFIXES = (
    ".log",
    ".err.log",
    ".out.log",
    ".trace",
)
PREFIXES = (
    "tmp_",
    ".tmp_",
)
PATH_PREFIXES = (
    "test/.artifacts/",
    "test/.tmp/",
)


def run(context: GuardContext):
    findings: list[Finding] = []
    for path in context.candidate_files():
        relative = path.relative_to(context.repo_root).as_posix()
        basename = path.name
        if relative.startswith(PATH_PREFIXES) or basename.startswith(PREFIXES):
            findings.append(Finding("error", relative, "temporary artifact must stay ignored/local-only"))
            continue
        if basename.endswith(DB_SUFFIXES):
            findings.append(Finding("error", relative, "database artifact must not be git-visible"))
            continue
        if basename.endswith(LOG_SUFFIXES):
            findings.append(Finding("error", relative, "debug/runtime log must stay local-only"))
    notes = (
        "This guard inspects tracked files plus untracked non-ignored files, so it also catches newly created artifacts before commit.",
    )
    return make_result(GUARD_ID, DESCRIPTION, findings=findings, notes=notes)

