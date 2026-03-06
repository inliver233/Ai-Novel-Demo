---
mode: plan
task: outline markdown limit to 2m
created_at: "2026-03-06T18:10:43+08:00"
complexity: medium
---

# Plan: Raise outline markdown limit to 2M chars

## Goal
- Allow very long-form outline generation and saving without hitting the current 200,000-character validation ceiling.

## Scope
- In:
  - Add an outline-specific markdown length limit of 2,000,000 characters.
  - Update outline create/update schema validation to use the new limit.
  - Add targeted backend regression tests for the new threshold.
- Out:
  - No chapter/worldbook/global markdown limit changes.
  - No frontend UX copy changes.

## Assumptions / Dependencies
- Branch is `test`.
- The reported validation error is triggered by outline `content_md` request-body validation.

## Phases
1. Add a dedicated outline markdown limit constant.
2. Switch outline schemas to the dedicated limit.
3. Add targeted unit tests for accept/reject boundaries.
4. Run backend compile + targeted unittest verification.

## Tests & Verification
- `cd backend && .\.venv\Scripts\python.exe -m compileall -q app`
- `cd backend && .\.venv\Scripts\python.exe -m unittest tests.test_outline_schema_limits -v`

## Issue CSV
- Path: issues/2026-03-06_18-10-43-outline-markdown-limit-2m.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] Outline create/update accepts `content_md` up to 2,000,000 characters.
- [ ] Outline create/update still reject content beyond 2,000,000 characters.
- [ ] Other markdown domains remain on their existing limits.

## Risks / Blockers
- Larger outlines increase request payload size and downstream memory usage, but the change stays scoped to outline endpoints only.

## Rollback / Recovery
- Revert by commit: `git revert <commit>`.

## Checkpoints
- Commit after: MVP-620

## References
- `backend/app/schemas/limits.py`
- `backend/app/schemas/outline.py`

