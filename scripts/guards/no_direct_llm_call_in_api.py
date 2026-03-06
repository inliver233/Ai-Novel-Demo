from __future__ import annotations

import re

from scripts.guards.base import Finding, GuardContext, make_result, read_text_lines

GUARD_ID = "no-direct-llm-call-in-api"
DESCRIPTION = "Flag direct LLM client/service calls in API routes; Wave A keeps legacy hotspots on warning-only allowlist."

DISALLOWED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "direct llm client import",
        re.compile(r"from\s+app\.llm\.client\s+import\s+.*(?:call_llm|call_llm_messages|call_llm_stream_messages)"),
    ),
    (
        "direct generation service llm call",
        re.compile(r"from\s+app\.services\.generation_service\s+import\s+.*(?:call_llm_and_record|prepare_llm_call)"),
    ),
    (
        "direct llm step invocation",
        re.compile(r"\b(?:call_llm_messages|call_llm_stream_messages|call_llm_and_record|prepare_llm_call|run_[a-z_]*llm_step)\b"),
    ),
)
WARNING_ALLOWLIST = {
    "backend/app/api/routes/chapter_analysis.py",
    "backend/app/api/routes/chapters.py",
    "backend/app/api/routes/llm.py",
    "backend/app/api/routes/memory.py",
    "backend/app/api/routes/outline.py",
}


def run(context: GuardContext):
    findings: list[Finding] = []
    route_root = context.repo_root / "backend" / "app" / "api" / "routes"
    for path in route_root.rglob("*.py"):
        relative = path.relative_to(context.repo_root).as_posix()
        for line_number, line in enumerate(read_text_lines(path), start=1):
            for label, pattern in DISALLOWED_PATTERNS:
                if not pattern.search(line):
                    continue
                severity = "warning" if relative in WARNING_ALLOWLIST else "error"
                message = f"{label}; route should call an application/service boundary instead"
                if severity == "warning":
                    message += " (legacy allowlist)"
                findings.append(Finding(severity, relative, message, line=line_number))
    notes = (
        "Legacy direct-LLM routes stay warning-only in Wave A; new violations outside allowlist fail the guard.",
    )
    return make_result(GUARD_ID, DESCRIPTION, findings=findings, notes=notes)

