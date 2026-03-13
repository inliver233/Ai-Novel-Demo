---
mode: plan
task: Wave 2026-03-13 B prompts settings closeout
created_at: "2026-03-13T21:03:39+08:00"
complexity: complex
---

# Plan: Wave 2026-03-13 B prompts settings closeout

## Goal
- Reduce `PromptsPage` and `SettingsPage` from hotspot god-pages into page-local modules with clearer state and rendering boundaries.
- Keep every current user-facing contract intact: routes, anchors, button text, aria labels, save semantics, dry-run and test flows, and navigation links.
- Close the batch with copy and token cleanup limited to the touched Prompts and Settings surface, truthful issue tracking, and full regression evidence.

## Scope
- In:
  - `frontend/src/pages/PromptsPage.tsx` plus new page-local modules under `frontend/src/pages/prompts/`.
  - `frontend/src/pages/SettingsPage.tsx` plus new page-local modules under `frontend/src/pages/settings/`.
  - Touched copy and state-expression cleanup for Prompts and Settings and low-risk semantic token cleanup in the same surface.
  - Matching vitest additions for extracted logic plus factual documentation and issue CSV updates.
- Out:
  - Global frontend data-layer unification (`T09`).
  - Outline and writing main-path refactors (`T06` and `T07`).
  - Backend route and service decomposition (`T11+`) or deployment and data-layer upgrades (`T14+`).
  - Full multi-theme engineering, theme registry expansion, or cross-site style rewrites.

## Assumptions / Dependencies
- The repo stays on `test`; unrelated untracked user files remain untouched.
- Existing Playwright coverage for prompts and settings is the compatibility guard and must not be weakened.
- The batch will be executed as four issue rows and four commits, each commit updating the shared issue CSV in the same commit.

## Phases
1. Create the batch plan and issues contract and complete source and test review for the two hotspot pages.
2. Split `PromptsPage` into page-local state, section, and copy modules without changing route, anchor, or LLM and RAG behavior.
3. Split `SettingsPage` into page-local state, section, and copy modules without changing save, query-preprocess, rerank, or feature-default flows.
4. Unify touched Prompts and Settings copy and semantic styling, update docs and issues, and run the full required regression set.

## Tests & Verification
- Prompts targeted regression -> `cd frontend && npm test -- --run src/pages/prompts/*.test.ts src/components/prompts/llmConnectionState.test.ts` | `cd test && npx playwright test specs/ui/prompts-test-connection.spec.ts` | `cd test && npx playwright test specs/ui/prompts-rag-config.spec.ts`
- Settings targeted regression -> `cd frontend && npm test -- --run src/pages/settings/*.test.ts` | `cd test && npx playwright test specs/ui/settings-query-preprocess.spec.ts` | `cd test && npx playwright test specs/ui/settings-rerank-config.spec.ts`
- Cross-page UI regression -> `cd test && npx playwright test specs/ui/navigation.spec.ts` | `cd test && npx playwright test specs/ui/a11y-form-fields.spec.ts` | `cd test && npx playwright test specs/ui/visual.spec.ts`
- Batch verification -> `cd backend && .\\.venv\\Scripts\\python.exe -m compileall -q app alembic` | `cd backend && .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py" -v` | `cd backend && .\\.venv\\Scripts\\python.exe scripts\\run_quality_gate.py` | `cd frontend && npm run lint` | `cd frontend && npm test` | `cd frontend && npm run build` | `cd test && npm test`
- Plan and issue contract validation -> `python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-03-13_21-00-53-wave-2026-03-13-b-prompts-settings-closeout.csv`

## Issue CSV
- Path: issues/2026-03-13_21-00-53-wave-2026-03-13-b-prompts-settings-closeout.csv
- Must share the same timestamp and slug as this plan.

## Tools / MCP
- none: local code inspection, vitest, backend commands, and Playwright provide enough coverage for this batch.

## Acceptance Checklist
- [ ] `PromptsPage.tsx` and `SettingsPage.tsx` shrink materially and stop owning all state, render, and copy responsibilities directly.
- [ ] Routes, anchors, save semantics, test-connection and model-list contracts, query preprocessing, rerank, and navigation flows do not regress.
- [ ] Touched Prompts and Settings helper text, warnings, confirms, disabled reasons, and empty or fail-soft messaging become more consistent.
- [ ] Touched Prompts and Settings styling stops using obvious hard-coded danger colors and reuses existing semantic tokens.
- [ ] Backend compileall, unittest, quality gate, frontend lint, vitest, build, directed Playwright, and final full Playwright all pass.
- [ ] Investigation docs and the matching issue CSV are updated factually with done and not-done scope for this batch only.

## Risks / Blockers
- Extracting only JSX without moving state boundaries would leave the hotspot complexity intact and fail the batch intent.
- Prompts and Settings both mix saved state, draft state, and destructive confirms; careless refactors could silently change button or dirty-state contracts.
- Visual and a11y regressions are likely if names, ids, or labels drift during extraction, so selectors and screenshots must remain stable.

## Rollback / Recovery
- Revert the specific issue commit if a page-local extraction changes route behavior, save semantics, or black-box selectors.
- Keep staged changes isolated to the active issue, the shared issue CSV, and any factual docs updated in the final closure commit.

## Checkpoints
- Commit after: MVP-657 PromptsPage hotspot split.
- Commit after: MVP-658 SettingsPage hotspot split.
- Commit after: MVP-659 Prompts and Settings copy and token cleanup.
- Commit after: MVP-660 docs and regression closure.

## References
- AGENTS.md
- issues/README.md
- docs/testing-policy.md
- 5.4 investigation record
- 3.13 investigation report
- frontend/src/pages/PromptsPage.tsx
- frontend/src/pages/prompts/models.ts
- frontend/src/components/prompts/LlmPresetPanel.tsx
- frontend/src/components/prompts/llmConnectionState.ts
- frontend/src/pages/SettingsPage.tsx
- frontend/src/pages/settings/models.ts
- test/specs/ui/prompts-test-connection.spec.ts
- test/specs/ui/prompts-rag-config.spec.ts
- test/specs/ui/settings-query-preprocess.spec.ts
- test/specs/ui/settings-rerank-config.spec.ts
- test/specs/ui/navigation.spec.ts
- test/specs/ui/a11y-form-fields.spec.ts
- test/specs/ui/visual.spec.ts
