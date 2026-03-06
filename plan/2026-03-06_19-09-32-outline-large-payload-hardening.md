---
mode: plan
task: outline large payload hardening
created_at: "2026-03-06T19:09:32+08:00"
complexity: medium
---

# Plan: Outline large-payload hardening

## Goal
- Eliminate the current `413 Request Entity Too Large` failure for ultra-long outlines and remove adjacent payload/validation bottlenecks in the outline-to-chapter skeleton workflow.

## Scope
- In:
  - Raise frontend Nginx request-body limit for proxied API calls.
  - Disable proxy request buffering for large outline save/generate payloads.
  - Add dedicated larger outline structure JSON limit.
  - Raise chapter bulk-create list cap so 800-chapter skeleton creation remains valid.
  - Add targeted regression tests for the new outline/chapters limits.
- Out:
  - No unrelated request limit changes for other domains.
  - No refactor of outline generation prompt/output logic.

## Assumptions / Dependencies
- Branch is `test`.
- The observed `413` HTML response is emitted by frontend Nginx before the backend request handler runs.
- Long-form outline save may also exceed current outline structure and chapter bulk-create schema caps.

## Phases
1. Harden proxy/body-size config for large outline API payloads.
2. Raise outline structure and chapter bulk-create schema caps.
3. Add targeted regression tests for accept/reject boundaries.
4. Run backend compile/tests and frontend build/config verification.

## Tests & Verification
- `cd backend && .\.venv\Scripts\python.exe -m compileall -q app`
- `cd backend && .\.venv\Scripts\python.exe -m unittest tests.test_outline_schema_limits tests.test_chapter_bulk_create_schema_limits -v`
- `cd frontend && npm run build`

## Issue CSV
- Path: issues/2026-03-06_19-09-32-outline-large-payload-hardening.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] Proxied API requests for ultra-long outlines are no longer rejected by default 1MB Nginx body limit.
- [ ] Outline create/update accepts large `content_md` and large `structure` payloads needed by long-form outlines.
- [ ] Chapter bulk-create accepts at least 800 skeleton chapters in one request.
- [ ] Targeted verification passes.

## Risks / Blockers
- Larger request bodies increase proxy memory/disk buffering pressure; mitigate by explicit body-size limit and disabling proxy request buffering for API uploads.

## Rollback / Recovery
- Revert by commit: `git revert <commit>`.

## Checkpoints
- Commit after: MVP-621

## References
- `frontend/nginx.conf`
- `backend/app/schemas/outline.py`
- `backend/app/schemas/chapters.py`

