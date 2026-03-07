from __future__ import annotations

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.prompt_preset_integrity import collect_prompt_preset_integrity
from scripts.guards.base import Finding, GuardContext, make_result

GUARD_ID = "prompt-preset-integrity-guard"
DESCRIPTION = "Validate default prompt preset resources, template bindings, and high-value canaries."


def run(context: GuardContext):
    report = collect_prompt_preset_integrity()
    findings: list[Finding] = []
    for issue in report.issues:
        findings.append(Finding(issue.severity, issue.path, f"{issue.resource_key}: {issue.message}"))
    for canary in report.canaries:
        if canary.passed:
            continue
        message = f"{canary.resource_key}/{canary.block_identifier}: canary failed"
        extras: list[str] = []
        if canary.error:
            extras.append(f"error={canary.error}")
        if canary.missing:
            extras.append(f"missing={','.join(canary.missing)}")
        if canary.missing_substrings:
            extras.append(f"missing_substrings={','.join(canary.missing_substrings)}")
        if extras:
            message = f"{message} ({'; '.join(extras)})"
        findings.append(Finding("error", canary.path, message))
    notes = (
        f"checked_resources={len(report.checked_resources)}",
        f"checked_canaries={len(report.canaries)}",
        "audit-first: structure drift, orphan templates, and contract marker drift fail fast here before runtime reset/upgrade paths.",
    )
    return make_result(GUARD_ID, DESCRIPTION, findings=findings, notes=notes)
