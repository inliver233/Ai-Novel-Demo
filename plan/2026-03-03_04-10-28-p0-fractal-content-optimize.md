---
mode: plan
task: P0 fractal fallback and content optimize e2e
created_at: "2026-03-03T04:11:46+08:00"
complexity: complex
---

# Plan: P0 Fractal Fallback + Content Optimize E2E

## Goal
- Fix fractal-v2 fallback regression so `llm_preset_missing` reliably returns 200 with fallback payload.
- Add actionable error logs for fractal rebuild with `project_id`, `mode`, `reason`, and internal stage.
- Complete `content_optimize` end-to-end path across single generate, batch generate, and prompt maintenance UI.

## Scope
- In:
  - backend/app/api/routes/fractal.py
  - backend/app/services/fractal_memory_service.py (if needed)
  - backend/app/schemas/batch_generation.py
  - backend/app/api/routes/prompts.py
  - backend/app/services/prompt_presets.py
  - frontend/src/components/writing/*
  - frontend/src/pages/writing/*
  - frontend/src/pages/PromptStudioPage.tsx
  - frontend/src/pages/PromptTemplatesPage.tsx
  - frontend/src/lib/uiCopy.ts
  - related backend/frontend/e2e tests
  - issues/2026-03-03_04-10-28-p0-fractal-content-optimize.csv
- Out:
  - unrelated refactors and non-P0 changes.

## Assumptions / Dependencies
- Work is done on `test` branch.
- Local backend/frontend/test environment can run required checks.

## Phases
1. Create plan and issue CSV contract, validate CSV format.
2. Issue 1: harden fractal-v2 fallback behavior and logging, run focused tests.
3. Issue 2: wire `content_optimize` through writing flow, batch flow, and prompt UI, then run regression checks.

## Tests & Verification
- Fractal contract: `cd test && npx playwright test specs/api/fractal-v2.contract.spec.ts`
- Backend baseline:
  - `cd backend && .\\.venv\\Scripts\\python.exe -m compileall -q app alembic`
  - `cd backend && .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- Frontend baseline:
  - `cd frontend && npm run lint`
  - `cd frontend && npm test`
  - `cd frontend && npm run build`
- Content optimize focused e2e/contract: `cd test && npx playwright test <target specs>`

## Issue CSV
- Path: issues/2026-03-03_04-10-28-p0-fractal-content-optimize.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] fractal-v2 `llm_preset_missing` returns 200 with fallback payload.
- [ ] fractal rebuild error logs include `project_id`, `mode`, `reason`, `stage`.
- [ ] writing single generation supports `content_optimize` option, payload, response parse, and compare/revert display.
- [ ] batch generation request and frontend payload support `content_optimize`.
- [ ] Prompt Studio and Prompt Templates include `content_optimize` task and preview support.
- [ ] issue-level commits include matching CSV status updates.

## Risks / Blockers
- E2E stability may vary with local runtime load.
- post_edit and content_optimize step interactions can cause wrong compare state if not isolated.

## Rollback / Recovery
- Revert by issue commit (`git revert <commit>`).

## Checkpoints
- Commit after: Issue 1 complete and verified.
- Commit after: Issue 2 complete and verified.

## References
- xinxiangmu-quanmian-diaochA.md
- backend/app/api/routes/fractal.py
- backend/app/services/fractal_memory_service.py
- backend/app/api/routes/chapters.py
- backend/app/schemas/batch_generation.py
- frontend/src/components/writing/AiGenerateDrawer.tsx
- frontend/src/pages/writing/useChapterGeneration.ts
- frontend/src/pages/writing/useBatchGeneration.ts
- backend/app/api/routes/prompts.py
- frontend/src/pages/PromptStudioPage.tsx
- frontend/src/pages/PromptTemplatesPage.tsx
