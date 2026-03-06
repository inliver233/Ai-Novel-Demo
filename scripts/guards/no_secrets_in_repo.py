from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
import re

from scripts.guards.base import Finding, GuardContext, is_text_file, make_result, read_text_lines

GUARD_ID = "no-secrets-in-repo"
DESCRIPTION = "Detect obvious secret files and suspicious secret literals in non-test source/config files."

FORBIDDEN_FILE_PATTERNS = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "id_rsa",
    "id_ed25519",
)
ALLOWED_FILE_NAMES = {
    ".env.example",
    ".env.docker.example",
}
TEXT_SCAN_EXCLUDES = (
    "backend/tests/",
    "test/",
    "issues/",
    "plan/",
)
TEXT_SCAN_SUFFIX_EXCLUDES = (
    ".md",
)

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_like_key", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{10,}\b")),
    ("google_api_key", re.compile(r"(?<![A-Za-z0-9])AIza[0-9A-Za-z_-]{20,}\b")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}")),
    (
        "api_key_literal",
        re.compile(r"(?i)\bapi[_-]?key\b\s*[:=]\s*[\"']([^\"']{8,})[\"']"),
    ),
)


def run(context: GuardContext):
    findings: list[Finding] = []
    for path in context.candidate_files():
        relative = path.relative_to(context.repo_root).as_posix()
        if _is_forbidden_secret_file(path.name):
            findings.append(Finding("error", relative, "forbidden secret-bearing local file is visible to git"))
            continue
        if not _should_scan_text(relative, path):
            continue
        for line_number, line in enumerate(read_text_lines(path), start=1):
            for secret_name, pattern in SECRET_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                if _is_allowed_match(secret_name, match.group(0), match.groups()):
                    continue
                findings.append(
                    Finding(
                        "error",
                        relative,
                        f"suspicious {secret_name} literal detected",
                        line=line_number,
                    )
                )
    notes = (
        "v1 excludes markdown/issues/plan/test trees from text scanning to reduce false positives; tighten later if needed.",
    )
    return make_result(GUARD_ID, DESCRIPTION, findings=findings, notes=notes)


def _is_forbidden_secret_file(name: str) -> bool:
    if name in ALLOWED_FILE_NAMES or name.endswith(".example"):
        return False
    return any(fnmatch(name, pattern) for pattern in FORBIDDEN_FILE_PATTERNS)


def _should_scan_text(relative: str, path: Path) -> bool:
    if any(relative.startswith(prefix) for prefix in TEXT_SCAN_EXCLUDES):
        return False
    if relative.endswith(TEXT_SCAN_SUFFIX_EXCLUDES):
        return False
    return is_text_file(path)


def _is_allowed_match(secret_name: str, raw: str, groups: tuple[str, ...]) -> bool:
    lowered = raw.lower()
    placeholders = ("dummy", "masked", "example", "test-key", "changeme", "your_", "<")
    if any(marker in lowered for marker in placeholders):
        return True
    if "***" in raw:
        return True
    if secret_name == "api_key_literal" and groups:
        value = groups[0].lower()
        return any(marker in value for marker in placeholders) or value in {"", "null", "none"}
    return False

