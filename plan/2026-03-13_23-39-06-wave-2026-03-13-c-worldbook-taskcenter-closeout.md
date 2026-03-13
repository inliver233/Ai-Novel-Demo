---
mode: plan
task: Wave 2026-03-13 C worldbook taskcenter closeout
created_at: "2026-03-13T23:42:14+08:00"
complexity: complex
---

# Plan: Wave 2026-03-13 C worldbook taskcenter closeout

## Goal
- Reduce `WorldBookPage` and `TaskCenterPage` from hotspot god-pages into page-local state and section modules with clearer responsibility boundaries.
- Keep every current user-facing contract intact: routes, query/search-param semantics, button text, aria labels, drawer behavior, preview behavior, TaskCenter SSE/runtime flows, and navigation links.
- Close the batch with truthful issue tracking, factual investigation-doc updates, and full backend/frontend/Playwright regression evidence.

## Scope
- In:
  - `frontend/src/pages/WorldBookPage.tsx` plus new page-local modules under `frontend/src/pages/worldbook/`.
  - `frontend/src/pages/TaskCenterPage.tsx` plus new page-local modules under `frontend/src/pages/taskCenter/`.
  - Touched copy/state-expression cleanup for WorldBook and TaskCenter and low-risk semantic token cleanup in the same surface.
  - Matching vitest additions for extracted logic plus factual documentation and issue CSV updates.
- Out:
  - Global frontend data-layer unification (`T09`).
  - `OutlinePage` / `WritingPage` / main-path refactors (`T06` and `T07`).
  - Backend route/service decomposition (`T11+`) or deployment/data-layer upgrades (`T14+`).
  - Full multi-theme engineering, theme registry expansion, or cross-site copy centralization.

## Assumptions / Dependencies
- The repo stays on `test`; unrelated untracked user files remain untouched.
- Existing Playwright coverage for WorldBook and TaskCenter is the compatibility guard and must not be weakened.
- The batch will be executed as four issue rows and four commits, each commit updating the shared issue CSV in the same commit.

## Phases
1. Create the batch plan and issues contract and complete source/test review for the two hotspot pages.
2. Split `WorldBookPage` into page-local state, section, and copy modules without changing route, preview, bulk, import/export, or auto-update behavior.
3. Split `TaskCenterPage` into page-local state, section, and copy modules without changing filters, details, queue health, project-task SSE/runtime, or generation-run behavior.
4. Unify touched WorldBook and TaskCenter copy and semantic styling, update docs/issues, and run the full required regression set.

## Tests & Verification
- WorldBook targeted verification -> `cd frontend && npm test -- --run src/pages/worldbook/*.test.ts` | `cd test && npx playwright test specs/ui/worldbook.spec.ts` | `cd test && npx playwright test specs/ui/worldbook-bulk-disable.spec.ts` | `cd test && npx playwright test specs/ui/worldbook-import-export.spec.ts` | `cd test && npx playwright test specs/ui/worldbook-large-list-pagination.spec.ts` | `cd test && npx playwright test specs/ui/worldbook-auto-update-success.spec.ts` | `cd test && npx playwright test specs/ui/worldbook-auto-update-failsoft.spec.ts`
- TaskCenter targeted verification -> `cd frontend && npm test -- --run src/pages/taskCenter/*.test.ts` | `cd test && npx playwright test specs/ui/task-center.spec.ts` | `cd test && npx playwright test specs/ui/taskcenter-projecttasks.spec.ts` | `cd test && npx playwright test specs/ui/taskcenter-projecttasks-sse.spec.ts` | `cd test && npx playwright test specs/ui/batch-generation-runtime-sync.spec.ts` | `cd test && npx playwright test specs/ui/graph-auto-update-manual.spec.ts` | `cd test && npx playwright test specs/ui/writing-auto-updates-after-generate.spec.ts`
- Cross-page UI regression -> `cd test && npx playwright test specs/ui/navigation.spec.ts` | `cd test && npx playwright test specs/ui/a11y-form-fields.spec.ts` | `cd test && npx playwright test specs/ui/visual.spec.ts`
- Batch verification -> `cd backend && .\\.venv\\Scripts\\python.exe -m compileall -q app alembic` | `cd backend && .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py" -v` | `cd backend && .\\.venv\\Scripts\\python.exe scripts\\run_quality_gate.py` | `cd frontend && npm run lint` | `cd frontend && npm test` | `cd frontend && npm run build` | `cd test && npm test`
- Plan and issue contract validation -> `python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-03-13_23-39-06-wave-2026-03-13-c-worldbook-taskcenter-closeout.csv`

## Issue CSV
- Path: issues/2026-03-13_23-39-06-wave-2026-03-13-c-worldbook-taskcenter-closeout.csv
- Must share the same timestamp and slug as this plan.

## Tools / MCP
- none: local code inspection, vitest, backend commands, and Playwright provide enough coverage for this batch.

## Acceptance Checklist
- [x] `WorldBookPage.tsx` and `TaskCenterPage.tsx` shrink materially and stop owning all state, render, and copy responsibilities directly.
- [x] Routes, search params, preview flows, drawer behavior, bulk/import/export, auto-update, TaskCenter filters/details/runtime/SSE, and navigation flows do not regress.
- [x] Touched WorldBook and TaskCenter helper text, warnings, confirms, disabled reasons, queue/live/fail-soft messaging become more consistent.
- [x] Touched WorldBook and TaskCenter styling stops using obvious hard-coded danger colors and reuses existing semantic tokens.
- [x] Backend compileall, unittest, quality gate, frontend lint, vitest, build, directed Playwright, and final full Playwright all pass.
- [x] Investigation docs and the matching issue CSV are updated factually with done and not-done scope for this batch only.

## Execution Result
- `MVP-662` completed in commit `0e4c753`: `WorldBookPage.tsx` shrank to `26` lines and moved page-local state/section/model/copy responsibilities into `frontend/src/pages/worldbook/`.
- `MVP-663` completed in commit `8094d7a`: `TaskCenterPage.tsx` shrank to `41` lines and moved filters/detail/runtime/SSE responsibilities into `frontend/src/pages/taskCenter/`.
- `MVP-664` completed in commit `4307c40`: touched WorldBook and TaskCenter copy/loading/error/confirm messaging was unified locally, and the remaining WorldBook selection token leak moved from `text-white` to `color-on-accent`.
- Full batch verification finished on `2026-03-14` with:
  - Backend `compileall`: pass
  - Backend `unittest`: `429 passed, 1 skipped`
  - Backend `quality_gate`: pass, with existing legacy allowlist and oversized-file warnings only
  - Frontend `lint`: pass
  - Frontend `vitest`: `23` files / `83` tests passed
  - Frontend `build`: pass
  - Directed Playwright for the 15 required spec files: `20/20` passed
  - Final `cd test && npm test`: `139/139` passed
- Honest out-of-scope items remain unchanged:
  - No global data-layer unification (`T09`)
  - No `OutlinePage` / `WritingPage` split
  - No main-path refactor (`T06` / `T07`)
  - No repo-wide copy or theme system project
  - No backend service decomposition or deployment upgrade
- Production-readiness conclusion:
  - This batch preserved route/search-param/ARIA/button/API contracts and passed the full required regression set, so the repo remains fit for direct production push.

## Risks / Blockers
- Extracting only JSX without moving state boundaries would leave the hotspot complexity intact and fail the batch intent.
- WorldBook mixes editor, bulk, preview, and import/export state; careless refactors could silently change drawer/save/preview contracts.
- TaskCenter mixes list filters, detail drawers, SSE recovery, and runtime actions; careless refactors could break reload recovery or task actions.

## Rollback / Recovery
- Revert the specific issue commit if a page-local extraction changes route behavior, preview semantics, search params, or black-box selectors.
- Keep staged changes isolated to the active issue, the shared issue CSV, and any factual docs updated in the final closure commit.

## Checkpoints
- Commit after: MVP-662 WorldBookPage hotspot split.
- Commit after: MVP-663 TaskCenterPage hotspot split.
- Commit after: MVP-664 WorldBook and TaskCenter copy plus token cleanup.
- Commit after: MVP-665 docs and regression closure.

## References
- AGENTS.md
- issues/README.md
- docs/testing-policy.md
- 5.4 investigation record
- 3.13 investigation report
- frontend/src/pages/WorldBookPage.tsx
- frontend/src/pages/worldbook/useWorldBookFilters.ts
- frontend/src/pages/worldbook/useWorldBookPagination.ts
- frontend/src/services/worldbookApi.ts
- frontend/src/pages/TaskCenterPage.tsx
- frontend/src/pages/taskCenter/ProjectTaskRuntimePanel.tsx
- frontend/src/pages/taskCenter/StatusBadge.tsx
- frontend/src/pages/taskCenter/helpers.ts
- frontend/src/hooks/useProjectTaskEvents.ts
- test/specs/ui/worldbook.spec.ts
- test/specs/ui/worldbook-bulk-disable.spec.ts
- test/specs/ui/worldbook-import-export.spec.ts
- test/specs/ui/worldbook-large-list-pagination.spec.ts
- test/specs/ui/worldbook-auto-update-success.spec.ts
- test/specs/ui/worldbook-auto-update-failsoft.spec.ts
- test/specs/ui/task-center.spec.ts
- test/specs/ui/taskcenter-projecttasks.spec.ts
- test/specs/ui/taskcenter-projecttasks-sse.spec.ts
- test/specs/ui/batch-generation-runtime-sync.spec.ts
- test/specs/ui/graph-auto-update-manual.spec.ts
- test/specs/ui/writing-auto-updates-after-generate.spec.ts
- test/specs/ui/navigation.spec.ts
- test/specs/ui/a11y-form-fields.spec.ts
- test/specs/ui/visual.spec.ts
