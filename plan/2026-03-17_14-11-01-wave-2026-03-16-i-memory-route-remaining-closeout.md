---
mode: plan
task: Wave 2026-03-16 I memory route remaining closeout
created_at: "2026-03-17T14:11:01+08:00"
complexity: complex
---

# Plan: Wave 2026-03-16 I memory route remaining closeout

## Goal
- 以 compatibility-first 方式收尾 `backend/app/api/routes/memory.py` 的剩余 route-helper shrink，只继续拆 `story_memories/import_all`、`story_memories/foreshadows/open_loops`、`story_memories/foreshadows/{id}/resolve`、`/memory/structured` 中仍留在 route 内的 normalize / validation / count / query builder / cursor / mapper / response 包装。
- 保持 `memory_retrieval_service.py`、`memory_update_service.py`、`memory_auto_update_app_service.py` 的既有边界，不把本批扩成 memory 子域统一工程。
- 补齐本批新增 helper / mapper / route-local module 的 backend unittest，并完成后端、前端、定向 Playwright、全量 Playwright 与文档 / issue 状态闭环。

## Scope
- In:
  - `/memory/structured` 的 table 参数校验、keyword/before normalize、count 查询、各表 query builder、cursor 计算、row -> response mapping 抽到 memory route feature-local helper / mapper / model 模块。
  - `story_memories/import_all`、`foreshadows/open_loops`、`foreshadows/{id}/resolve` 的 schema/version 校验、query/order normalize、chapter 校验、dirty mark、response 包装与 preview mapper 抽到 story-memory feature-local helper / mapper 模块。
  - `memory.py` 接入新模块后继续压薄为鉴权、request 参数接入、helper/service 调用、最薄响应与错误边界。
  - 本批新增 helper / mapper / route-local module 的 backend unittest，和用户指定的 frontend / Playwright / regression / docs / CSV 闭环。
- Out:
  - `T12` 知识子域统一、`T13` 任务系统工业化、`T14+` 基础设施/部署/观测/CI/压测升级。
  - 无关热点：`auth.py`、`batch_generation.py`、`prompts.py`、`vector_rag_service.py`、`project_task_service.py` 等。
  - 改 API contract、status code、error code、response schema、pack structure、fail-soft 语义、前端 URL/search params/ARIA/按钮文案、guard 规则。
  - 覆盖/删除用户未跟踪文件，或丢失 `5.4大调查详细记录.md` 现有本地 handoff 记录。

## Assumptions / Dependencies
- 当前分支已确认是 `test`；当前工作树存在用户未跟踪文件与 `5.4大调查详细记录.md` 的本地修改，本批不会触碰未跟踪文件，只在 final docs commit 中基于现有修改追加 Wave I 客观结果。
- 允许新增 `memory_route_structured_*.py`、`memory_route_story_*.py` 等 feature-local route helper / mapper / model 文件，但不得把本批逻辑重新拉回 `memory.py`，也不得把 service 巨石进一步做成更大工程。
- 用户已明确要求生成 plan / issues 并继续实现，本次直接将该要求视为写入 plan file 的确认授权。

## Phases
1. 生成并校验 Wave I plan / issues，审查 `memory.py` 残余职责与相关前端/黑盒 contract。
2. 交付 `MVP-686`：抽离 `/memory/structured` 的 table normalize、count/query builder、cursor 与 row mapper，并补 backend unittest。
3. 交付 `MVP-687`：抽离 story-memory import / foreshadow open_loops / resolve 的 normalize、validation、dirty mark、mapper 与 response 包装，并补 backend unittest。
4. 交付 `MVP-688`：接入新 helper/module，把 `memory.py` 压成更薄 route shell，跑 compileall / memory unittest / quality gate 并确认 file-line warning 状态。
5. 交付 `MVP-689`：完成前端 lint / vitest / build、定向 Playwright、全量 Playwright、主辅文档与 Wave I issue 状态闭环，如实记录是否已关闭 `memory.py` 热点与剩余范围边界。

## Tests & Verification
- Structured route shrink -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_memory*_*.py" -v`
- Story-memory / foreshadow route shrink -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_memory*_*.py" -v`
- Memory route final thin -> `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_memory*_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe scripts\run_quality_gate.py`
- Batch closeout regression -> `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe scripts\run_quality_gate.py` | `cd frontend && npm run lint` | `cd frontend && npm test` | `cd frontend && npm run build` | `cd test && npx playwright test specs/api/memory-preview.contract.spec.ts` | `cd test && npx playwright test specs/api/memory-retrieve.contract.spec.ts` | `cd test && npx playwright test specs/api/taskcenter-structured-memory.contract.spec.ts` | `cd test && npx playwright test specs/ui/memory-update.spec.ts` | `cd test && npx playwright test specs/ui/structured-memory.spec.ts` | `cd test && npx playwright test specs/ui/foreshadows-page.spec.ts` | `cd test && npx playwright test specs/ui/foreshadow-drawer.spec.ts` | `cd test && npx playwright test specs/ui/import.spec.ts` | `cd test && npx playwright test specs/ui/graph-character-relations-editor.spec.ts` | `cd test && npm test` | `python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-03-17_14-11-01-wave-2026-03-16-i-memory-route-remaining-closeout.csv`

## Issue CSV
- Path: issues/2026-03-17_14-11-01-wave-2026-03-16-i-memory-route-remaining-closeout.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none：本批以本地代码审查、backend unittest、frontend lint/vitest/build 与 Playwright 黑盒回归为主，不依赖额外 MCP。

## Acceptance Checklist
- [ ] `backend/app/api/routes/memory.py` 明显变薄，且剩余逻辑只保留鉴权、request 参数接入、helper/service 调用、最薄响应与错误边界。
- [ ] `/memory/structured` 的 query/count/cursor/mapper 与 story-memory import/foreshadow helper 被真实抽离到 feature-local module，未改 response schema / status code / error code / fail-soft 语义。
- [ ] `memory.py` 理想情况下压回 `file-line-count-guard` 阈值内；若仍残留，主辅文档必须如实记录强证据与剩余边界。
- [ ] 后端 `compileall` / 全量 unittest / `quality_gate`，前端 `lint` / `vitest` / `build`，指定 Playwright 与最终 `cd test && npm test` 均真实通过。
- [ ] `3.13调查详细全面报告所有问题.md`、`5.4大调查详细记录.md`、Wave I issue CSV 如实记录本批拆分职责、测试结果、热点关闭状态与仍不属于本批范围的项。

## Risks / Blockers
- `/memory/structured` 同时被 StructuredMemoryPage、CharacterRelationsView、MemoryUpdateDrawer 与 contract / UI 黑盒依赖；若 cursor、counts、empty-table key 或 attributes mapping 有任何变化，会立即造成回归。
- story-memory import / foreshadow 路由会触发 vector/search dirty 标记与 schedule；若 helper 抽离改变 commit / schedule 时机，可能引入隐藏回归。
- `memory.py` 若想压回阈值，必须是真正移出逻辑而非只改函数名；否则会留下名义搬家但实际仍耦合在 route 内的问题。

## Rollback / Recovery
- 若单个 helper 抽离导致 contract / UI 回退，按 issue 粒度回滚对应 commit，仅撤销该 issue 的新 helper / mapper / 测试 / CSV 状态更新。
- 若定向或全量回归暴露出本批直接相关阻断 bug，仅做最小兼容修复并补测试；超出 Wave I 范围的问题只记录到文档与 CSV，不借机扩 scope。

## Checkpoints
- Commit after: MVP-686 structured route shrink.
- Commit after: MVP-687 story-memory route shrink.
- Commit after: MVP-688 memory route final thin.
- Commit after: MVP-689 docs + regression closure.

## References
- AGENTS.md
- issues/README.md
- docs/testing-policy.md
- .codex/skills/plan/SKILL.md
- .codex/skills/testing/SKILL.md
- plan/2026-03-15_21-13-01-wave-2026-03-15-h-outline-memory-hotspot-shrink.md
- issues/2026-03-15_21-13-01-wave-2026-03-15-h-outline-memory-hotspot-shrink.csv
- 3.13调查详细全面报告所有问题.md
- 5.4大调查详细记录.md
- backend/app/api/routes/memory.py
- backend/app/api/routes/memory_route_helpers.py
- backend/app/api/routes/memory_route_models.py
- backend/app/services/memory_auto_update_app_service.py
- backend/app/services/memory_retrieval_service.py
- backend/app/services/memory_update_service.py
- frontend/src/pages/StructuredMemoryPage.tsx
- frontend/src/pages/structuredMemory/CharacterRelationsView.tsx
- frontend/src/components/writing/MemoryUpdateDrawer.tsx
- frontend/src/pages/ImportPage.tsx
- frontend/src/pages/ForeshadowsPage.tsx
- frontend/src/components/writing/ForeshadowDrawer.tsx
- backend/tests/test_memory_auto_update_app_service.py
- backend/tests/test_memory_route_helpers.py
- test/specs/api/memory-preview.contract.spec.ts
- test/specs/api/memory-retrieve.contract.spec.ts
- test/specs/api/taskcenter-structured-memory.contract.spec.ts
- test/specs/ui/memory-update.spec.ts
- test/specs/ui/structured-memory.spec.ts
- test/specs/ui/foreshadows-page.spec.ts
- test/specs/ui/foreshadow-drawer.spec.ts
- test/specs/ui/import.spec.ts
- test/specs/ui/graph-character-relations-editor.spec.ts
