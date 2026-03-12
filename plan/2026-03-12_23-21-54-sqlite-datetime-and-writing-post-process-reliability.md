---
mode: plan
task: SQLite datetime and writing post-process reliability
created_at: "2026-03-12T23:28:11+08:00"
complexity: complex
---

# Plan: SQLite datetime and writing post-process reliability

## Goal
- Eliminate SQLite datetime string/object mismatch failures in backend runtime paths.
- Restore AI writing advanced-parameter generation so planning/post-edit/content-optimize complete reliably on the writing page.

## Scope
- In:
  - Backend datetime normalization for ORM-loaded SQLite timestamp fields and high-risk datetime arithmetic/serialization paths.
  - Chapter generate / generate-stream advanced-parameter reliability for plan_first, post_edit, post_edit_sanitize, and content_optimize.
  - Backend + UI/API tests covering both bug classes.
  - Matching Issue CSV updates for each commit.
- Out:
  - Unrelated refactors.
  - New product behavior outside datetime compatibility and chapter generation reliability.

## Assumptions / Dependencies
- Existing Playwright harness continues to use Mock LLM and isolated SQLite test DB.
- User-owned untracked markdown/docs files in the repo root are unrelated and must remain untouched.
- `test` branch remains the target branch for all commits and pushes.

## Phases
1. Establish plan/issues, inspect affected backend/frontend/test paths, and define commit boundaries.
2. Fix SQLite datetime compatibility globally enough to remove string-vs-datetime runtime errors and add regression tests.
3. Fix chapter advanced-parameter generation reliability across stream/non-stream transport selection and stream keepalive, then add UI/API regression coverage.
4. Run targeted backend/frontend/E2E verification, update Issue CSV statuses, commit each issue separately, then run regression and push `test`.

## Tests & Verification
- SQLite datetime compatibility -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_sqlite_datetime_compat.py" -v`
- Admin/task datetime regressions -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_admin_user_stats.py" -v` and `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_project_task_runtime_reconcile.py" -v`
- Chapter advanced-parameter backend reliability -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_chapter_generate_stream_*.py" -v`
- Writing page advanced-parameter UX -> `cd test && npx playwright test specs/ui/style-injection-post-edit.spec.ts specs/ui/content-optimize-flow.spec.ts specs/ui/chapter-fallback.spec.ts specs/ui/chapter-stream.spec.ts specs/ui/writing-advanced-generate-reliability.spec.ts`
- Final regression subset -> rerun touched backend unittest files + touched Playwright specs.

## Issue CSV
- Path: issues/2026-03-12_23-21-54-sqlite-datetime-and-writing-post-process-reliability.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none: local code inspection, unit tests, and Playwright black-box tests are sufficient.

## Acceptance Checklist
- [ ] SQLite-backed datetime fields no longer surface as strings in affected runtime paths that perform arithmetic or `.isoformat()`.
- [ ] `touch_user_activity` and admin/task datetime flows are covered by regression tests.
- [ ] Writing page advanced parameters complete without post-edit/content-optimize stalls or non-stream timeout-prone routing.
- [ ] Advanced-parameter request routing and compare/review UX are covered by regression tests.
- [ ] Each issue lands in its own commit with matching CSV status updates.

## Risks / Blockers
- A purely local patch in `user_activity_service` would leave other SQLite datetime paths vulnerable; the fix must be broad enough without destabilizing ORM behavior.
- Changing transport selection in the writing page can regress existing stream fallback behavior if not covered by tests.

## Rollback / Recovery
- Revert the specific issue commit if datetime normalization or chapter transport changes regress unrelated flows.
- Preserve user-owned root-level docs/untracked files and limit staged changes to issue-specific code plus the matching CSV.

## Checkpoints
- Commit after: Issue MVP-201 datetime compatibility fix.
- Commit after: Issue MVP-202 chapter advanced-parameter reliability fix.

## References
- backend/app/services/user_activity_service.py
- backend/app/api/routes/chapters.py
- frontend/src/pages/writing/useChapterGeneration.ts
- frontend/src/components/writing/AiGenerateDrawer.tsx
- backend/tests/test_admin_user_stats.py
- backend/tests/test_project_task_runtime_reconcile.py
- test/specs/ui/style-injection-post-edit.spec.ts
- test/specs/ui/content-optimize-flow.spec.ts
