from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]
for candidate in (str(BACKEND_DIR), str(REPO_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from app.core.config import settings
from app.llm.audit import audit_database_url, audit_rows, audit_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit LLM provider/model/capability/pricing contracts.")
    parser.add_argument("--database-url", default=None, help="Optional database URL to audit stored llm profiles/presets.")
    parser.add_argument("--mode", choices=["audit", "enforce"], default="audit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    findings = list(audit_registry())
    database_url = args.database_url or settings.database_url
    if database_url:
        report = audit_database_url(database_url, mode=args.mode)
        findings.extend(report.findings)
    else:
        findings.extend(audit_rows([], mode=args.mode))

    for finding in findings:
        provider = finding.provider or "(none)"
        model = finding.model or "(none)"
        model_key = f" [{finding.model_key}]" if finding.model_key else ""
        print(f"[{finding.severity.upper()}] {finding.source} :: provider={provider} model={model}{model_key} :: {finding.message}")

    if args.mode == "enforce":
        return 1 if findings else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
