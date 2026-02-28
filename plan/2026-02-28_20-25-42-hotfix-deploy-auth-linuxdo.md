---
mode: plan
task: P0 Hotfix Deploy/Auth/LinuxDo
created_at: "2026-02-28T20:25:42+08:00"
complexity: complex
---

# Plan: P0 Hotfix Deploy/Auth/LinuxDo

## Goal
- Fix Docker Compose + Postgres startup failure caused by Alembic migration boolean default (Postgres type mismatch).
- Improve migration stability under concurrent startup (backend + rq_worker), avoid migration races.
- Auth pages: always show LinuxDo login button; when not configured, show a friendly toast instead of silently hiding or navigating to a JSON error page.

## Scope
- In:
  - backend: fix Alembic migration for `batch_generation_tasks.cancel_requested`; add a Postgres advisory lock around `alembic upgrade`.
  - frontend: Login/Register pages LinuxDo button visibility + not-configured handling.
- Out:
  - Advanced OAuth UI flows.
  - Full production reverse-proxy/TLS guidance.

## Assumptions / Dependencies
- Target DB is Postgres (Compose default). SQLite remains for local single-user debug.
- LinuxDo OIDC requires user-provided client_id/client_secret and correct redirect_uri.

## Phases
1. Add plan + issue CSV.
2. Backend migration fix + backend tests.
3. Frontend auth UI fix + frontend lint/test/build.

## Tests & Verification
- backend: `cd backend; .\\.venv\\Scripts\\python.exe -m compileall -q app alembic; .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- frontend: `cd frontend; npm run lint; npm test; npm run build`
- manual (compose): `docker compose up -d --build`, confirm backend/rq_worker can finish migrations and stay up; `/api/health` works; LinuxDo button is visible.

## Issue CSV
- Path: issues/2026-02-28_20-25-42-hotfix-deploy-auth-linuxdo.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] Postgres Alembic migration no longer fails on boolean default.
- [ ] Concurrent startup does not race migrations (serialized via lock).
- [ ] Login/Register pages always show LinuxDo button; when not configured, a toast explains what to set.

## Risks / Blockers
- If a DB volume was created during a failed migration, it may require `docker compose down -v` to rebuild.

## Rollback / Recovery
- One issue = one commit. `git revert <commit>` to rollback.

## Checkpoints
- Commit after: each Issue row

## References
- backend/alembic/versions/8b4c2f3a1d9e_add_batch_generation_tasks.py
- backend/app/db/migrations.py
- frontend/src/pages/LoginPage.tsx
- frontend/src/pages/RegisterPage.tsx
