# Wave D Performance Baseline

## Goals

- Measure usability at `100 / 300 / 800` chapter scales.
- Measure backend latency at concurrency `1 / 5 / 20`.
- Keep perf runs isolated from normal regression and production databases.

## Entry Points

- Quick smoke: `python scripts/run_gate.py --layer perf-smoke`
- Full sampling: `cd test && pwsh scripts/run-perf-baseline.ps1 -Scenario full`
- Custom output path: `cd test && pwsh scripts/run-perf-baseline.ps1 -Scenario full -OutputPath ..\docs\performance-results\wave-d-baseline.full.json`

## Coverage

### Backend API

- `GET /api/projects/{project_id}/chapters/meta` full list scan
- `GET /api/chapters/{chapter_id}` detail fetch
- `GET /api/tasks/{task_id}/runtime` runtime aggregation
- `GET /api/projects/{project_id}/memory/retrieve` high-frequency memory pack

### Frontend

- `Preview` open: list load + first usable paint surrogate
- `Preview` chapter switch: keyboard `ArrowRight`
- `Writing` open
- `TaskCenter` open

## Environment Notes

- Runner: `test/playwright.perf.config.ts`
- Database: isolated E2E SQLite created by `test/global-setup.ts`
- Backend: single-worker uvicorn
- Frontend: Vite dev server
- Concurrency `1 / 5 / 20` applies to backend HTTP requests only; frontend metrics remain single-session interactive timings.

## Output Artifacts

- Default JSON: `test/.artifacts/perf-results/wave-d-baseline.full.json`
- Archived JSON: `docs/performance-results/wave-d-baseline.full.json`
- Human summary: `docs/performance-results/2026-03-07-wave-d-baseline.md`
