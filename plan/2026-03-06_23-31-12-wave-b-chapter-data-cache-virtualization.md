---
mode: plan
task: Wave B chapter data cache virtualization
created_at: "2026-03-06T23:31:59+08:00"
complexity: complex
status: done
---

## Goal
- Finish `T05 + T06` on top of the Wave A chapter `meta/detail` contract.
- Unify frontend chapter data access, cache invalidation, and prefetch semantics.
- Make `Writing / Preview / Reader` usable for 100~800 chapters without full DOM rendering.

## Scope
- In:
  - Keep `frontend/src/services/chaptersApi.ts` as the transport layer.
  - Add shared chapter store/hooks for `ChapterListItem` and `ChapterDetail`.
  - Migrate `Writing / Preview / Reader / Wizard / Foreshadows` to the shared read path.
  - Window the chapter list UI for `Writing / Preview / Reader`.
  - Add a dedicated large-list Playwright regression.
- Out:
  - Removing legacy `GET /api/projects/{id}/chapters`.
  - `T07 / T08 / T09 / T10`.
  - Introducing a heavyweight state-management framework.

## Issue Breakdown
1. `MVP-628`: shared chapter data layer and cache/invalidation contract.
2. `MVP-629`: Writing CRUD + save flow migrated to the shared store.
3. `MVP-630`: Preview / Reader / Wizard / Foreshadows share chapter reads and neighbor prefetch.
4. `MVP-631`: windowed chapter lists with preserved active/mobile/keyboard behavior.
5. `MVP-632`: regression, plan/issues/docs updates, and final closeout.

## Verification
- Frontend baseline: `cd frontend && npm run lint && npm test && npm run build`
- Chapter regressions:
  - `cd test && npx playwright test specs/api/chapters-meta.contract.spec.ts`
  - `cd test && npx playwright test specs/ui/chapter-reader.spec.ts specs/ui/preview-navigation.spec.ts specs/ui/xss-markdown.spec.ts specs/ui/writing-save-status.spec.ts specs/ui/chapter-scale-navigation.spec.ts`
- Port fallback if `8000/5173` is occupied:
  - `E2E_BACKEND_URL=http://127.0.0.1:51116`
  - `E2E_FRONTEND_URL=http://127.0.0.1:51117`

## Outcome
- [x] Shared chapter store/hooks are in place and type boundaries are explicit.
- [x] `create / update / delete / bulk_create / outline switch` now trigger real cache sync/invalidation.
- [x] `Writing / Preview / Reader / Wizard / Foreshadows` share the same chapter read semantics.
- [x] `Writing / Preview / Reader` no longer render 100~800 chapter buttons all at once.
- [x] Active scroll-into-view, mobile drawer behavior, and keyboard navigation remain intact.
- [x] Frontend baseline checks and chapter-related Playwright regressions were executed.

## Rollback
- Revert by issue (`[MVP-628]` ... `[MVP-632]`) if needed.
- `MVP-631` is isolated so the virtual-list rollout can be backed out without losing the shared data layer.

## References
- `5.4???????.md:1315`
- `5.4???????.md:1364`
- `5.4???????.md:1900`
- `5.4???????.md:1981`
- `frontend/src/services/chaptersApi.ts:1`
- `frontend/src/services/chapterStore.ts:1`
- `frontend/src/components/writing/ChapterVirtualList.tsx:1`
- `frontend/src/pages/PreviewPage.tsx:1`
- `frontend/src/pages/ChapterReaderPage.tsx:1`
