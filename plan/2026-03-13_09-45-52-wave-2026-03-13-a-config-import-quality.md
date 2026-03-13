---
mode: plan
task: Wave 2026-03-13 A config import quality closeout
created_at: "2026-03-13T09:48:22+08:00"
complexity: complex
---

# Plan: Wave 2026-03-13 A config import quality closeout

## Goal
- Restore the import flow so list, detail, and proposal actions stay in sync and the known Playwright failure is removed.
- Make the model configuration page explain its three core states and expose consistent button contracts for fetching models and testing connections in both main and task modules.
- Remove the backend `schema` field Pydantic warning without breaking the external API contract.
- Close the batch with regression evidence, updated issue status, and factual documentation updates.

## Scope
- In:
  - `frontend/src/pages/ImportPage.tsx` and related tests for import list/detail synchronization.
  - `frontend/src/components/prompts/LlmPresetPanel.tsx`, `frontend/src/pages/PromptsPage.tsx`, and related backend routes/services for model configuration state clarity.
  - `backend/app/api/routes/tables.py` plus compatible schema/test updates.
  - Matching doc updates in the two investigation markdown files and issue CSV status tracking.
- Out:
  - Theme expansion, prompts/settings large-page splits, outline or writing major restructures, route-layer LLM architecture refactors, multi-agent/plugin work, and deployment stack upgrades.

## Assumptions / Dependencies
- Existing root markdown files with user-owned edits must not be overwritten outside the sections updated for this batch.
- Mock LLM and the current Playwright harness remain the verification path for UI flows.
- The batch will be split into four issue rows and four commits, each updating the shared issue CSV status in the same commit.

## Phases
1. Create the batch plan/issues contract, inspect current frontend/backend/test paths, and confirm the minimal impact surface.
2. Fix import flow state synchronization and add regression coverage for list/detail/proposal consistency.
3. Unify model configuration state copy and button contracts across main/task modules, then add regression coverage.
4. Apply the compatible `schema` warning fix in `tables.py`, validate backend/frontend contracts, update docs/issues, and run full regression.

## Tests & Verification
- Import flow targeted regression -> `cd test && npx playwright test specs/ui/import.spec.ts`
- Model configuration targeted regression -> `cd test && npx playwright test specs/ui/prompts-test-connection.spec.ts specs/ui/navigation.spec.ts specs/api/api-smoke.spec.ts`
- Backend batch verification -> `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe scripts\run_quality_gate.py`
- Frontend batch verification -> `cd frontend && npm run lint` | `cd frontend && npm test` | `cd frontend && npm run build`
- Final black-box regression -> `cd test && npm test`

## Issue CSV
- Path: issues/2026-03-13_09-45-52-wave-2026-03-13-a-config-import-quality.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none: local code inspection, backend/frontend tests, and Playwright black-box coverage are sufficient for this batch.

## Acceptance Checklist
- [ ] `ImportPage` no longer presents a detail-visible/list-empty race and the known Playwright failure is gone without relaxing timeouts.
- [ ] Model configuration clearly distinguishes unbound profile, unsaved key, and remotely callable states, with consistent button disable reasons across main/task modules.
- [ ] `backend/app/api/routes/tables.py` stops emitting the Pydantic `schema` shadow warning while keeping the public response field compatible.
- [ ] Backend compileall/unittest/quality gate, frontend lint/vitest/build, and full Playwright regression all pass.
- [ ] Investigation docs and the matching issue CSV are updated with factual results only.

## Risks / Blockers
- ImportPage likely has split state sources for the list and selected detail; a local patch that only refreshes one path could preserve the race.
- Model configuration copy/button logic may be duplicated between main/task modules; partial fixes would create a UX contract mismatch.
- The `schema` compatibility change must preserve serialized field names or frontend/tests will silently regress.

## Rollback / Recovery
- Revert the specific issue commit if import synchronization, model configuration state logic, or table contract compatibility causes a regression.
- Keep staged changes isolated to the active issue, the shared issue CSV, and any required factual doc updates.

## Checkpoints
- Commit after: MVP-652 import flow stabilization.
- Commit after: MVP-653 model configuration UX contract closeout.
- Commit after: MVP-654 tables warning compatibility fix.
- Commit after: MVP-655 docs and regression closure.

## References
- AGENTS.md
- issues/README.md
- docs/testing-policy.md
- 5.4 investigation record
- 3.13 investigation report
- frontend/src/pages/ImportPage.tsx
- frontend/src/components/prompts/LlmPresetPanel.tsx
- frontend/src/pages/PromptsPage.tsx
- backend/app/api/routes/llm_models.py
- backend/app/api/routes/llm_profiles.py
- backend/app/api/routes/tables.py
- test/specs/ui/import.spec.ts
