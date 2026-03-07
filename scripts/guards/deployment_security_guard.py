from __future__ import annotations

from pathlib import Path

from scripts.guards.base import Finding, GuardContext, make_result

GUARD_ID = "deployment-security-guard"
DESCRIPTION = "Validate prod env contract, compose exposure boundaries, and deployment docs stay in sync."


def run(context: GuardContext):
    findings: list[Finding] = []
    prod_compose = context.repo_root / "docker-compose.prod.yml"
    security_doc = context.repo_root / "docs/deployment/security-checklist.md"
    compose_doc = context.repo_root / "docs/deployment/docker-compose-prod.md"
    main_path = context.repo_root / "backend/app/main.py"

    prod_text = prod_compose.read_text(encoding="utf-8")
    security_text = security_doc.read_text(encoding="utf-8")
    compose_text = compose_doc.read_text(encoding="utf-8")
    main_text = main_path.read_text(encoding="utf-8")

    _require_substring(context, findings, prod_compose, prod_text, 'APP_ENV: prod', "prod overlay must pin APP_ENV=prod for backend and rq_worker", expected_count=2)
    _require_substring(context, findings, prod_compose, prod_text, 'AUTH_DEV_FALLBACK_USER_ID: ""', "prod overlay must explicitly disable AUTH_DEV_FALLBACK_USER_ID", expected_count=2)
    _require_substring(context, findings, prod_compose, prod_text, '127.0.0.1:${BACKEND_PORT:-8000}:8000', "backend host port must stay loopback-bound in prod overlay")
    _require_substring(context, findings, prod_compose, prod_text, 'SECRET_ENCRYPTION_KEY:?set SECRET_ENCRYPTION_KEY', "prod overlay must require SECRET_ENCRYPTION_KEY", expected_count=2)
    _require_substring(context, findings, prod_compose, prod_text, 'AUTH_SESSION_SIGNING_KEY:?set AUTH_SESSION_SIGNING_KEY', "prod overlay must require AUTH_SESSION_SIGNING_KEY", expected_count=2)
    _require_substring(context, findings, prod_compose, prod_text, 'CORS_ORIGINS:?set CORS_ORIGINS', "prod overlay must require explicit CORS_ORIGINS allowlist")
    _require_substring(context, findings, prod_compose, prod_text, 'AUTH_ADMIN_PASSWORD:?set AUTH_ADMIN_PASSWORD', "prod overlay must require non-default AUTH_ADMIN_PASSWORD")
    _require_substring(context, findings, prod_compose, prod_text, 'ports: !reset []', "prod overlay must remove public Postgres/Redis port exposure", expected_count=2)

    _require_substring(context, findings, security_doc, security_text, 'APP_ENV=dev|test|prod', "security checklist must document dev/test/prod env contract")
    _require_substring(context, findings, security_doc, security_text, 'deployment-security-guard', "security checklist must reference deployment guard runner")
    _require_substring(context, findings, compose_doc, compose_text, 'docker compose -f docker-compose.yml -f docker-compose.prod.yml config', "compose doc must document merged config validation command")
    _require_substring(context, findings, compose_doc, compose_text, '127.0.0.1:${BACKEND_PORT:-8000}:8000', "compose doc must explain loopback backend exposure boundary")
    _require_substring(context, findings, main_path, main_text, 'settings.app_env == "prod"', "main.py must preserve explicit prod boundary in runtime checks")

    notes = (
        'audit-first: prod deployment checks stay scriptable and reversible through the guard runner.',
        'scope: env contract, CORS/session boundary, backend exposure, and secret placeholders.',
    )
    return make_result(GUARD_ID, DESCRIPTION, findings=findings, notes=notes)


def _require_substring(
    context: GuardContext,
    findings: list[Finding],
    path: Path,
    text: str,
    needle: str,
    message: str,
    *,
    expected_count: int = 1,
) -> None:
    if text.count(needle) >= expected_count:
        return
    findings.append(Finding("error", path.relative_to(context.repo_root).as_posix(), message))
