---
mode: plan
task: admin users prod upgrade verification
created_at: "2026-03-05T13:34:00+08:00"
complexity: medium
---

# Plan: Admin users production-upgrade verification and test hardening

## Goal
- Add additional verification coverage to increase confidence for production upgrades after admin users stats changes.
- Verify migration/backfill behavior and admin users API contract with automated tests.

## Scope
- In:
  - Align usage counting semantics between runtime accumulation and migration backfill.
  - Add migration regression test for upgrade from previous head to current head.
  - Add Playwright API contract test for admin users stats endpoint.
  - Re-run broad backend/frontend/test validation and compose static checks.
- Out:
  - No new business feature changes.

## Assumptions / Dependencies
- Branch remains `test`.
- Docker daemon may be unavailable in current environment; fallback checks are acceptable with risk note.

## Phases
1. Add/adjust automated tests and usage-count consistency fix.
2. Run backend full unittest discover and frontend validation.
3. Run Playwright API/UI/DB specs for admin users and schema contracts.
4. Perform docker compose static validation and bootstrap-chain execution.

## Tests & Verification
- `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic`
- `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- `cd frontend && npm run lint && npm test && npm run build`
- `cd test && npx playwright test specs/api/admin-users-stats.contract.spec.ts specs/ui/admin-users.spec.ts specs/db/db-schema.spec.ts`
- `docker compose config`
- `cd backend && python - << bootstrap script >>` (run ensure_db_schema + ensure_admin_user)

## Issue CSV
- Path: issues/2026-03-05_13-34-00-admin-users-prod-upgrade-verification.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] Runtime generated-char counting semantics are consistent with migration backfill semantics.
- [ ] Migration regression test proves no user/generation data loss and correct usage backfill.
- [ ] API contract test validates pagination/filter/summary fields on admin users endpoint.
- [ ] Broad validation suite passes.
- [ ] Docker compose static config check passes; daemon limitation is explicitly recorded if present.

## Risks / Blockers
- Docker daemon unavailable prevents full container runtime verification in this environment.

## Rollback / Recovery
- Revert by commit: `git revert <commit>`.

## Checkpoints
- Commit after: MVP-617

## References
- backend/app/services/user_usage_service.py
- backend/tests/test_migrations_admin_user_stats.py
- test/specs/api/admin-users-stats.contract.spec.ts
- backend/scripts/entrypoint.sh
