---
mode: plan
task: Wave C-1 project SSE self-heal
created_at: "2026-03-07T02:08:34+08:00"
complexity: complex
status: in_progress
---

## Goal
- Finish `T07 + T08` on top of the completed Wave B chapter data layer without regressing current chapter, batch-generation, or generation-run flows.
- Add a replayable project-level `ProjectTask` event stream with `Last-Event-ID`, active snapshot, and a TaskCenter consumer path.
- Add `heartbeat / attempt / watchdog / reconcile / startup self-heal` so background `ProjectTask` rows no longer get stuck forever after restarts, worker exits, or queue jitter.

## Scope
- In:
  - Add a persisted project task event model/table with monotonic replay cursor.
  - Emit lifecycle/system events for `ProjectTask` scheduling, retry, cancel, run, failure, timeout, and recovery.
  - Add a project SSE endpoint with `Last-Event-ID`, replay, and active snapshot.
  - Connect `frontend/src/pages/TaskCenterPage.tsx` to the new SSE stream while keeping manual refresh as fallback.
  - Extend `ProjectTask` with `heartbeat_at` and `attempt` plus runtime self-heal hooks on startup/watchdog.
  - Add backend + Playwright coverage targeted at replay/recovery/regression.
- Out:
  - `T09 / T10 / T11 / T12 / T13 / T14 / T15`.
  - Replacing legacy `generation_runs` / `batch_generation` / chapter SSE protocols.
  - Rewriting the Writing runtime or chapter shared-store foundation from Wave B.

## Issue Breakdown
1. `MVP-633`: add `ProjectTaskEvent` persistence, schema fields (`heartbeat_at` / `attempt`), lifecycle emit helpers, and migrate existing schedulers.
2. `MVP-634`: add project SSE stream with `Last-Event-ID`, replay, active snapshot, and backend replay tests.
3. `MVP-635`: connect `TaskCenterPage` to project SSE with low-risk refresh fallback and UI regression coverage.
4. `MVP-636`: add heartbeat thread, watchdog timeout handling, queued orphan reconcile, and startup self-heal hooks.
5. `MVP-637`: run Wave C-1 regression, update plan/issues/status, append objective writeback to `5.4大调查详细记录.md`, and close out.

## Verification
- Backend baseline:
  - `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic`
  - `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- DB snapshot after schema change:
  - `pwsh test/scripts/snapshot-db.ps1`
- Frontend baseline:
  - `cd frontend && npm run lint`
  - `cd frontend && npm test`
  - `cd frontend && npm run build`
- Mandatory task regressions:
  - `cd test && npx playwright test specs/ui/task-center.spec.ts specs/ui/taskcenter-projecttasks.spec.ts specs/ui/batch-generation.spec.ts specs/ui/taskcenter-projecttasks-sse.spec.ts`
  - `cd test && npx playwright test specs/api/generation-runs.contract.spec.ts specs/api/batch-generation-cancel.contract.spec.ts specs/api/taskcenter-structured-memory.contract.spec.ts`
- Port fallback if `127.0.0.1:8000` is occupied:
  - `E2E_BACKEND_URL=http://127.0.0.1:51116`
  - `E2E_FRONTEND_URL=http://127.0.0.1:51117`

## Acceptance Checklist
- [ ] `ProjectTaskEvent` exists with stable project replay ordering and lifecycle/system event coverage.
- [ ] `GET /api/projects/{project_id}/task-events/stream` supports `Last-Event-ID`, replay, and active snapshot.
- [ ] `TaskCenterPage` receives live task updates without relying only on manual refresh.
- [ ] `ProjectTask` rows track `heartbeat_at` and `attempt`, and stale `running` rows are recovered or failed deterministically.
- [ ] Startup/periodic reconcile handles queued orphans without duplicating unsafe side effects.
- [ ] Legacy chapter/batch/generation-run flows remain compatible.
- [ ] Required backend/frontend/Playwright regression commands complete successfully.
- [ ] `5.4大调查详细记录.md` includes an objective Wave C-1 writeback.

## Risks / Blockers
- `ProjectTask` creation is distributed across several services, so lifecycle event emission must be patched consistently without broad refactors.
- SSE must not hold a long-lived request DB session under SQLite; streaming must re-open short sessions and avoid long transactions.
- Auto-requeueing `running` tasks is side-effect sensitive, so stale-running recovery must default to fail/observe unless explicitly safe.

## Rollback
- Revert by issue commit (`[MVP-633]` ... `[MVP-637]`) if needed.
- `MVP-634` keeps the new SSE endpoint additive; rollback does not require reverting legacy generation SSE routes.
- `MVP-636` keeps stale-running auto-requeue behind a guarded setting so rollback can stop at failure-only recovery.

## References
- `AGENTS.md:1`
- `5.4大调查详细记录.md:1412`
- `5.4大调查详细记录.md:1460`
- `5.4大调查详细记录.md:1508`
- `5.4大调查详细记录.md:1555`
- `5.4大调查详细记录.md:1900`
- `5.4大调查详细记录.md:1981`
- `5.4大调查详细记录.md:1996`
- `5.4大调查详细记录.md:2078`
- `issues/README.md:1`
- `docs/testing-policy.md:1`
- `README.md:1`
- `backend/app/models/project_task.py:1`
- `backend/app/services/project_task_service.py:150`
- `backend/app/services/project_task_service.py:821`
- `backend/app/services/project_task_service.py:909`
- `backend/app/services/task_queue.py:122`
- `backend/app/services/batch_generation_service.py:191`
- `backend/app/api/routes/tasks.py:13`
- `backend/app/api/routes/batch_generation.py:20`
- `backend/app/api/routes/generation_runs.py:63`
- `backend/app/utils/sse_response.py:9`
- `frontend/src/pages/TaskCenterPage.tsx:82`
- `frontend/src/pages/writing/useBatchGeneration.ts:9`
- `frontend/src/services/chapterStore.ts:93`
