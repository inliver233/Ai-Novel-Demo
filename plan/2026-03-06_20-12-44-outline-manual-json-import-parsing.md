---
mode: plan
task: outline manual json import parsing
created_at: "2026-03-06T20:12:44+08:00"
complexity: medium
---

# Plan: Parse manually pasted outline JSON on save/load

## Goal
- Make manually pasted outline JSON payloads (with `outline_md` + `chapters`) behave like AI-generated outlines after save, without requiring the user to rerun AI generation.

## Scope
- In:
  - Reuse backend outline JSON parser on outline save/create/update when `structure` is absent.
  - Derive normalized `content_md`/`structure` on outline reads for legacy rows saved as raw JSON text.
  - Add frontend fallback parsing so current/legacy content can still drive chapter-skeleton creation.
  - Add backend + frontend regression tests using manual pasted JSON payload shape.
- Out:
  - No changes to AI generation contract.
  - No unrelated outline editor redesign.

## Assumptions / Dependencies
- Branch is `test`.
- `NovelOutline.json.txt` reflects the real pasted payload shape from the editor.
- Current failure happens because pasted JSON is stored only in `content_md`, while chapter skeleton logic reads `structure.chapters`.

## Phases
1. Add backend normalization helper for outline JSON payloads.
2. Wire helper into outline read/save/create/update routes.
3. Add frontend parser fallback for stored/manual content.
4. Add targeted backend/frontend tests and run verification.

## Tests & Verification
- `cd backend && .\.venv\Scripts\python.exe -m compileall -q app tests`
- `cd backend && .\.venv\Scripts\python.exe -m unittest tests.test_outline_large_payload_endpoints tests.test_outline_manual_json_parse_endpoints -v`
- `cd frontend && npm test -- src/pages/outlineParsing.test.ts`
- `cd frontend && npm run build`

## Issue CSV
- Path: issues/2026-03-06_20-12-44-outline-manual-json-import-parsing.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] Saving pasted outline JSON automatically extracts and stores chapter structure.
- [ ] Reading legacy outline rows saved as raw JSON still yields usable outline text + chapter structure.
- [ ] “从大纲创建章节骨架” can work from manually imported outline payloads.
- [ ] Targeted backend/frontend verification passes.

## Risks / Blockers
- Over-eager parsing could accidentally reinterpret arbitrary JSON-like editor content; mitigate by only normalizing when the payload successfully parses to outline contract with chapters.

## Rollback / Recovery
- Revert by commit: `git revert <commit>`.

## Checkpoints
- Commit after: MVP-622

## References
- `NovelOutline.json.txt`
- `backend/app/api/routes/outline.py`
- `backend/app/api/routes/outlines.py`
- `frontend/src/pages/OutlinePage.tsx`

