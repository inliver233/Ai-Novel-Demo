---
mode: plan
task: frontend historical prettier blockers cleanup
created_at: "2026-03-03T04:44:32+08:00"
complexity: simple
---

# Plan: Frontend Historical Prettier Blockers Cleanup

## Goal
- Clean the three historical frontend files that block `npm run lint`.

## Scope
- In:
  - frontend/src/pages/OutlinePage.tsx
  - frontend/src/services/unauthorizedPolicy.ts
  - frontend/src/services/unauthorizedPolicy.test.ts
  - issues/2026-03-03_04-44-32-lint-historical-prettier-blockers.csv
- Out:
  - any feature logic changes.

## Phases
1. Create plan + issue CSV contract.
2. Apply formatting-only cleanup to the three files.
3. Run `cd frontend && npm run lint`.
4. Commit code + CSV status update in one commit, then push `test`.

## Tests & Verification
- `cd frontend && npm run lint`

## Risks / Rollback
- Risk: accidental semantic edits while formatting.
- Rollback: `git revert <commit>`.
