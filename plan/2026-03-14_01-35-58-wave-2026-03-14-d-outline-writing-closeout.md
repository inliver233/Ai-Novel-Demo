---
mode: plan
task: Wave 2026-03-14 D outline writing closeout
created_at: "2026-03-14T01:35:57+08:00"
complexity: complex
---

# Plan: Wave 2026-03-14 D outline writing closeout

## Goal
- Reduce `OutlinePage` and `WritingPage` from hotspot entry pages into compatibility-first page-local modules with clearer state and rendering boundaries.
- Keep every current user-facing contract intact: routes, `chapterId` / `applyRunId` semantics, AI stream/fallback behavior, save/autosave/dirty guards, buttons, aria labels, confirms, navigation jumps, and visual snapshots.
- Close the batch with truthful issue tracking, factual investigation-doc updates, and full backend/frontend/Playwright regression evidence.

## Scope
- In:
  - `frontend/src/pages/OutlinePage.tsx` plus new page-local modules under `frontend/src/pages/outline/`.
  - `frontend/src/pages/WritingPage.tsx` plus new page-local modules under `frontend/src/pages/writing/`.
  - Touched copy/state-expression cleanup for Outline and Writing and low-risk semantic token cleanup in the same surface.
  - Matching vitest additions for extracted logic plus factual documentation and issue CSV updates.
- Out:
  - Global frontend data-layer unification (`T09`).
  - Outline structured-editor product rewrite (`T06`) or Writing advanced-mode product rewrite (`T07`).
  - Backend/API contract changes, global store introduction, route/search-param/ARIA/button contract changes.
  - Full multi-theme engineering, theme registry expansion, or repo-wide copy centralization.

## Assumptions / Dependencies
- The repo stays on `test`; unrelated untracked user files remain untouched.
- `5.4大调查详细记录.md` already has a local user-side Wave D recommendation block; final updates must merge on top of that content instead of overwriting it.
- Existing Playwright coverage for Outline and Writing is the compatibility guard and must not be weakened.
- The batch will be executed as four issue rows and four commits, each commit updating the shared issue CSV in the same commit.

## Phases
1. Create the batch plan and issues contract and complete source/test review for Outline and Writing.
2. Split `OutlinePage` into page-local state, section, model, and copy modules without changing route, generate/apply/save/save-as-new/skeleton/guard behavior.
3. Split `WritingPage` entry orchestration into page-local state and section modules without changing URL params, chapter CRUD/save/done/generate/history/batch/context/memory/foreshadow/tables/analysis behavior.
4. Unify touched Outline and Writing copy plus semantic styling, update docs/issues, and run the full required regression set.

## Tests & Verification
- Outline targeted verification -> `cd frontend && npm test -- --run src/pages/outline/*.test.ts src/pages/outlineParsing.test.ts` | `cd test && npx playwright test specs/ui/outline-stream.spec.ts` | `cd test && npx playwright test specs/ui/outline-fallback.spec.ts` | `cd test && npx playwright test specs/ui/blocker-warning.spec.ts` | `cd test && npx playwright test specs/ui/navigation.spec.ts` | `cd test && npx playwright test specs/ui/a11y-form-fields.spec.ts` | `cd test && npx playwright test specs/ui/visual.spec.ts`
- Writing targeted verification -> `cd frontend && npm test -- --run src/pages/writing/*.test.ts` | `cd test && npx playwright test specs/ui/chapter-stream.spec.ts` | `cd test && npx playwright test specs/ui/chapter-stream-cancel.spec.ts` | `cd test && npx playwright test specs/ui/chapter-stream-unsupported-provider.spec.ts` | `cd test && npx playwright test specs/ui/chapter-fallback.spec.ts` | `cd test && npx playwright test specs/ui/chapter-create-conflict.spec.ts` | `cd test && npx playwright test specs/ui/chapter-scale-navigation.spec.ts` | `cd test && npx playwright test specs/ui/writing-unsaved-confirm.spec.ts` | `cd test && npx playwright test specs/ui/writing-save-status.spec.ts` | `cd test && npx playwright test specs/ui/writing-done-status.spec.ts` | `cd test && npx playwright test specs/ui/writing-generate-validation-error.spec.ts` | `cd test && npx playwright test specs/ui/writing-auto-updates-after-generate.spec.ts` | `cd test && npx playwright test specs/ui/writing-advanced-generate-reliability.spec.ts` | `cd test && npx playwright test specs/ui/content-optimize-flow.spec.ts` | `cd test && npx playwright test specs/ui/context-preview-sync.spec.ts` | `cd test && npx playwright test specs/ui/memory-context-preview.spec.ts` | `cd test && npx playwright test specs/ui/prompt-inspector.spec.ts` | `cd test && npx playwright test specs/ui/tables-panel.spec.ts` | `cd test && npx playwright test specs/ui/tables-injection.spec.ts` | `cd test && npx playwright test specs/ui/memory-update.spec.ts` | `cd test && npx playwright test specs/ui/chapter-analysis-apply.spec.ts` | `cd test && npx playwright test specs/ui/chapter-analysis-rewrite.spec.ts` | `cd test && npx playwright test specs/ui/foreshadow-drawer.spec.ts` | `cd test && npx playwright test specs/ui/batch-generation.spec.ts` | `cd test && npx playwright test specs/ui/batch-generation-runtime-sync.spec.ts` | `cd test && npx playwright test specs/ui/xss-markdown.spec.ts`
- Batch verification -> `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe scripts\run_quality_gate.py` | `cd frontend && npm run lint` | `cd frontend && npm test` | `cd frontend && npm run build` | `cd test && npm test`
- Plan and issue contract validation -> `python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-03-14_01-35-58-wave-2026-03-14-d-outline-writing-closeout.csv`

## Issue CSV
- Path: issues/2026-03-14_01-35-58-wave-2026-03-14-d-outline-writing-closeout.csv
- Must share the same timestamp and slug as this plan.

## Tools / MCP
- none: local code inspection, vitest, backend commands, and Playwright provide enough coverage for this batch.

## Acceptance Checklist
- [ ] `OutlinePage.tsx` and `WritingPage.tsx` shrink materially and stop owning all state, render, and copy responsibilities directly.
- [ ] Routes, search params, stream/fallback, preview/apply, save/autosave/guards, batch/history/context/memory/tables/analysis flows, and navigation links do not regress.
- [ ] Touched Outline and Writing helper text, warnings, disabled reasons, confirms, empty-state/fail-soft messaging, and advanced-mode hints become more consistent.
- [ ] Touched Outline and Writing styling stops using obvious hard-coded danger or foreground colors and reuses existing semantic tokens.
- [ ] Backend compileall, unittest, quality gate, frontend lint, vitest, build, directed Playwright, and final full Playwright all pass.
- [ ] Investigation docs and the matching issue CSV are updated factually with done and not-done scope for this batch only.

## Risks / Blockers
- Extracting only JSX without moving state boundaries would leave the hotspot complexity intact and fail the batch intent.
- `OutlinePage` mixes outline lifecycle, generate modal, stream/fallback state, and wizard/save behavior; careless refactors could silently change confirm or apply contracts.
- `WritingPage` mixes query-param semantics, chapter orchestration, drawer state, task-center/runtime handoff, and readonly/done UX; careless refactors could break main-path recovery and cross-page jumps.

## Rollback / Recovery
- Revert the specific issue commit if a page-local extraction changes route behavior, search params, aria labels, preview semantics, or black-box selectors.
- Keep staged changes isolated to the active issue, the shared issue CSV, and any factual docs updated in the final closure commit.

## Checkpoints
- Commit after: MVP-666 OutlinePage hotspot split.
- Commit after: MVP-667 WritingPage hotspot split.
- Commit after: MVP-668 Outline and Writing copy plus token cleanup.
- Commit after: MVP-669 docs and regression closure.

## References
- AGENTS.md
- issues/README.md
- docs/testing-policy.md
- 5.4大调查详细记录.md
- 3.13调查详细全面报告所有问题.md
- frontend/src/pages/OutlinePage.tsx
- frontend/src/pages/outlineParsing.ts
- frontend/src/pages/WritingPage.tsx
- frontend/src/pages/writing/useChapterEditor.ts
- frontend/src/pages/writing/useChapterGeneration.ts
- frontend/src/components/writing/AiGenerateDrawer.tsx
- frontend/src/components/writing/ContextPreviewDrawer.tsx
- test/specs/ui/outline-stream.spec.ts
- test/specs/ui/outline-fallback.spec.ts
- test/specs/ui/blocker-warning.spec.ts
- test/specs/ui/navigation.spec.ts
- test/specs/ui/visual.spec.ts
- test/specs/ui/chapter-stream.spec.ts
- test/specs/ui/chapter-stream-cancel.spec.ts
- test/specs/ui/chapter-stream-unsupported-provider.spec.ts
- test/specs/ui/chapter-fallback.spec.ts
- test/specs/ui/chapter-create-conflict.spec.ts
- test/specs/ui/chapter-scale-navigation.spec.ts
- test/specs/ui/writing-unsaved-confirm.spec.ts
- test/specs/ui/writing-save-status.spec.ts
- test/specs/ui/writing-done-status.spec.ts
- test/specs/ui/writing-generate-validation-error.spec.ts
- test/specs/ui/writing-auto-updates-after-generate.spec.ts
- test/specs/ui/writing-advanced-generate-reliability.spec.ts
- test/specs/ui/content-optimize-flow.spec.ts
- test/specs/ui/context-preview-sync.spec.ts
- test/specs/ui/memory-context-preview.spec.ts
- test/specs/ui/prompt-inspector.spec.ts
- test/specs/ui/tables-panel.spec.ts
- test/specs/ui/tables-injection.spec.ts
- test/specs/ui/memory-update.spec.ts
- test/specs/ui/chapter-analysis-apply.spec.ts
- test/specs/ui/chapter-analysis-rewrite.spec.ts
- test/specs/ui/foreshadow-drawer.spec.ts
- test/specs/ui/batch-generation.spec.ts
- test/specs/ui/batch-generation-runtime-sync.spec.ts
- test/specs/ui/xss-markdown.spec.ts
