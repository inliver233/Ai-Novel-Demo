---
mode: plan
task: admin users management detailed stats
created_at: "2026-03-05T13:05:17+08:00"
complexity: complex
---

# Plan: Admin users detailed stats and scalable management

## Goal
- Add reliable online and usage statistics to the admin users page without breaking existing users or data.
- Keep admin user list responsive for large user sets via server-side pagination and filtering.
- Ensure Docker Compose upgrade path is safe and backward compatible.

## Scope
- In:
  - Add backend tables/indexes for user activity and aggregated usage stats.
  - Update generation run write path to maintain usage aggregates.
  - Upgrade `GET /api/auth/admin/users` to support pagination, filters, and summary stats.
  - Update admin users frontend to show summary cards and per-user stats.
  - Add/update tests and DB schema snapshot.
- Out:
  - No login/register flow redesign.
  - No unrelated feature refactor.

## Assumptions / Dependencies
- Work stays on `test` branch.
- `generation_runs` is the authoritative source for historical usage backfill.
- Online status is derived from a recent-activity window.

## Phases
1. Create plan/issue contract and finalize schema/API design.
2. Implement backend models, migration, stats update path, and admin API enhancement.
3. Implement frontend admin page stats UI with pagination/filtering.
4. Run tests, update schema snapshot, and commit/push.

## Tests & Verification
- Backend:
  - `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic`
  - `cd backend && .\.venv\Scripts\python.exe -m unittest -v tests.test_auth_session tests.test_admin_user_stats tests.test_user_usage_stats`
- Frontend:
  - `cd frontend && npm run lint`
  - `cd frontend && npm test`
  - `cd frontend && npm run build`
- E2E:
  - `cd test && npx playwright test specs/ui/admin-users.spec.ts`
- DB snapshot:
  - `pwsh test/scripts/snapshot-db.ps1`

## Issue CSV
- Path: issues/2026-03-05_13-05-17-admin-users-detailed-stats.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] Admin page shows total users, online users, total calls, and generated character totals.
- [ ] Per user shows online flag, last active time, total calls, generated chars, and error calls.
- [ ] User list supports pagination and filtering and avoids full-table rendering.
- [ ] Migration is additive and existing data remains usable.
- [ ] Related tests pass and schema snapshot is updated.

## Risks / Blockers
- Activity tracking can create DB pressure if write frequency is not throttled.
- Backfill query may be expensive on very large `generation_runs` tables.

## Rollback / Recovery
- Roll back by commit: `git revert <commit>`.
- New stats tables are additive and isolated from core business tables.

## Checkpoints
- Commit after: MVP-616

## References
- AGENTS.md
- issues/README.md
- docs/testing-policy.md
- frontend/src/pages/AdminUsersPage.tsx
- backend/app/api/routes/auth.py
- backend/app/services/run_store.py
