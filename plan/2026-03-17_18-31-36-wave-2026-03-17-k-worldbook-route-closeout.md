---
mode: plan
task: Wave 2026-03-17 K worldbook route closeout
created_at: "2026-03-17T18:31:36+08:00"
complexity: complex
---

# Plan: Wave 2026-03-17 K worldbook route closeout

## Goal
- 以 compatibility-first 方式收尾 `backend/app/api/routes/worldbook.py` 这个当前剩余的 route hotspot，只继续拆 route-local 的 import/export、bulk、mapper、preview、auto_update chapter resolve、CRUD payload builder 与 dirty/schedule wrapper 负担。
- 保持 `worldbook_service.py`、`project_task_service.py`、`vector_rag_service.py`、`search_index_service.py` 的既有服务边界，不把本批扩成 worldbook 子域统一工程，也不把复杂逻辑回塞到 service 巨石中。
- 完成 worldbook 新增 helper / mapper / route-local module 的 backend unittest、后端/前端/Playwright 回归、主辅文档与 issue 状态闭环。

## Scope
- In:
  - `worldbook.py` 中 row -> response mapping、keywords / entry_ids normalize、export_all builder、import_all schema/version 校验与 action/conflict collector、bulk update/delete/duplicate builder、dirty mark + vector/search rebuild schedule wrapper 的 route-local 逻辑抽到 feature-local helper / mapper / import-export 模块。
  - `worldbook.py` 中 auto_update chapter resolve / latest done fallback / token build / schedule_failed 与 chapter_not_done details、preview_trigger preprocess + normalized/raw/preprocess_obs/match_config wrapper、create/update/delete payload builder 抽到 route-local preview / mutation helper 模块。
  - `worldbook.py` 接入新 helper 后压薄为鉴权、request params/body/header 接入、helper/service 调用、最薄 `ok_payload(...)` 与错误边界。
  - 为新增 helper / mapper / route-local module 补 backend unittest，并完成用户指定的 backend / frontend / Playwright / docs / CSV 闭环。
- Out:
  - `auth.py`、`batch_generation.py`、`prompts.py`、`tables.py`、`memory.py`、`outline.py` 等已关闭或更高风险热点。
  - `T12` 知识子域统一、`T13` 任务系统工业化、`T14+` 基础设施 / 部署 / 观测 / CI / 压测升级。
  - 改 API contract、status code、error code、response schema、pack structure、fail-soft 语义、前端 URL/search params/ARIA/按钮文案、guard 规则。
  - 覆盖/删除用户未跟踪文件，或丢失 `5.4大调查详细记录.md` 已有 handoff 内容。

## Assumptions / Dependencies
- 当前分支已确认是 `test`；当前工作树存在用户未跟踪文件与 `5.4大调查详细记录.md` 本地修改，本批不会碰未跟踪文件，只在 final docs commit 中在保留既有内容基础上追加 Wave K 客观结果。
- 允许新增 `worldbook_route_helpers.py`、`worldbook_route_mappers.py`、`worldbook_route_import_export.py`、`worldbook_route_models.py`、`worldbook_route_preview.py`、`worldbook_route_mutations.py` 等 feature-local route 模块，但不得把本批逻辑重新堆成新的 route-local 巨石，也不得把复杂逻辑并回现有 service 形成更大 service。
- 用户已明确要求生成 plan / issues 并继续实现，本次直接将该要求视为写入 plan file 与 issues file 的确认授权。

## Phases
1. 生成并校验 Wave K plan / issues，审查 `worldbook.py` 残余职责与相关 frontend / unittest / Playwright contract。
2. 交付 `MVP-694`：抽离 worldbook route 的 row mapper、normalize、export/import/import_all、bulk update/delete/duplicate helper 与 builder，并补 backend unittest。
3. 交付 `MVP-695`：抽离 worldbook route 的 preview_trigger、manual auto_update、create/update/delete payload builder 与 dirty/schedule wrapper，并补 backend unittest。
4. 交付 `MVP-696`：接入新 helper/module，把 `worldbook.py` 压成更薄 route shell，跑 compileall / worldbook 相关 unittest / quality gate 并确认 file-line warning 状态。
5. 交付 `MVP-697`：完成后端全量、前端三件套、指定 Playwright、全量 Playwright、主辅文档与 Wave K issue 状态闭环，如实记录 worldbook 热点关闭状态与仍不属于本批范围的项。

## Tests & Verification
- Worldbook import/export/bulk shrink -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_worldbook_route*.py" -v`
- Worldbook preview/auto_update/CRUD shrink -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_worldbook_route*.py" -v | cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_worldbook_auto_update*.py" -v | cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_output_contract_worldbook_auto_update_validation_details.py" -v`
- Route shell final thin -> `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_worldbook*.py" -v` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_output_contract_worldbook_auto_update_validation_details.py" -v` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_search_index_service.py" -v` | `cd backend && .\.venv\Scripts\python.exe scripts\run_quality_gate.py`
- Batch closeout regression -> `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe scripts\run_quality_gate.py` | `cd frontend && npm run lint` | `cd frontend && npm test` | `cd frontend && npm run build` | `cd test && npx playwright test specs/api/worldbook-bulk.contract.spec.ts` | `cd test && npx playwright test specs/api/worldbook-import-export.contract.spec.ts` | `cd test && npx playwright test specs/api/worldbook-preview.contract.spec.ts` | `cd test && npx playwright test specs/api/vector-datalifecycle.contract.spec.ts` | `cd test && npx playwright test specs/ui/worldbook.spec.ts` | `cd test && npx playwright test specs/ui/worldbook-import-export.spec.ts` | `cd test && npx playwright test specs/ui/worldbook-bulk-disable.spec.ts` | `cd test && npx playwright test specs/ui/worldbook-auto-update-failsoft.spec.ts` | `cd test && npx playwright test specs/ui/worldbook-auto-update-success.spec.ts` | `cd test && npx playwright test specs/ui/worldbook-large-list-pagination.spec.ts` | `cd test && npx playwright test specs/ui/memory-context-preview.spec.ts` | `cd test && npx playwright test specs/ui/search-page.spec.ts` | `cd test && npx playwright test specs/ui/writing-auto-updates-after-generate.spec.ts` | `cd test && npm test` | `python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-03-17_18-31-36-wave-2026-03-17-k-worldbook-route-closeout.csv`

## Issue CSV
- Path: issues/2026-03-17_18-31-36-wave-2026-03-17-k-worldbook-route-closeout.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none：本批以本地代码审查、backend unittest、frontend lint/vitest/build 与 Playwright 黑盒回归为主，不依赖额外 MCP。

## Acceptance Checklist
- [ ] `backend/app/api/routes/worldbook.py` 明显变薄，且不是只挪注释或改函数名。
- [ ] worldbook route-local helper / mapper / payload builder 已真实抽离到 feature-local route 模块，未改 response schema / status code / error code / fail-soft 语义。
- [ ] 理想情况下 `worldbook.py` 压回 `file-line-count-guard` 阈值内；若仍残留，主辅文档必须如实记录强证据与剩余边界。
- [ ] 后端 `compileall` / 全量 unittest / `quality_gate`，前端 `lint` / `vitest` / `build`，指定 Playwright 与最终 `cd test && npm test` 均真实通过。
- [ ] `3.13调查详细全面报告所有问题.md`、`5.4大调查详细记录.md`、Wave K issue CSV 如实记录本批拆分职责、测试结果、热点关闭状态、为何优先 worldbook 而非 auth/batch_generation，以及仍不属于本批范围的项。

## Risks / Blockers
- WorldBookPage / ContextPreviewDrawer / Search / TaskCenter 同时依赖 worldbook import/export、bulk、preview_trigger、auto_update、dirty rebuild 语义；任何字段、actions/conflicts、task_id/chapter_id、match_config 或 reason 漂移都会直接造成 API/UI 回归。
- 若 route shrink 只是“换文件名继续堆逻辑”，则 guard 风险会转移而不是关闭；因此必须控制新增 helper/module 的职责边界与体量。
- vector/search rebuild 调度与 worldbook_auto_update chapter resolve 都与现有任务/索引链路耦合；若错误扩大到 service 层，就会超出 Wave K 范围。

## Rollback / Recovery
- 若 import/export/bulk 或 preview/auto_update/helper 抽离导致 contract / UI 回退，按 issue 粒度回滚对应 commit，只撤销该 issue 的 helper / mapper / route shell 接线 / 测试 / CSV 状态更新。
- 若定向或全量回归暴露出与本批直接相关的阻断 bug，仅做最小兼容修复并补测试；超出 Wave K 范围的问题只记录到文档与 CSV，不借机扩 scope。

## Checkpoints
- Commit after: MVP-694 worldbook import/export/bulk helper/mappers shrink.
- Commit after: MVP-695 worldbook preview/auto_update/CRUD helper shrink.
- Commit after: MVP-696 worldbook final thin.
- Commit after: MVP-697 docs + regression closure.

## References
- AGENTS.md
- issues/README.md
- docs/testing-policy.md
- .codex/skills/plan/SKILL.md
- .codex/skills/testing/SKILL.md
- plan/2026-03-17_15-36-10-wave-2026-03-17-j-prompts-tables-route-closeout.md
- issues/2026-03-17_15-36-10-wave-2026-03-17-j-prompts-tables-route-closeout.csv
- 3.13调查详细全面报告所有问题.md
- 5.4大调查详细记录.md
- backend/app/api/routes/worldbook.py
- backend/app/services/worldbook_service.py
- backend/app/services/memory_query_service.py
- backend/app/services/project_task_service.py
- backend/app/services/vector_rag_service.py
- backend/app/services/search_index_service.py
- backend/app/models/worldbook_entry.py
- backend/app/models/project_settings.py
- backend/app/schemas/worldbook.py
- frontend/src/pages/WorldBookPage.tsx
- frontend/src/pages/worldbook/useWorldBookPageState.ts
- frontend/src/pages/worldbook/WorldBookPageSections.tsx
- frontend/src/services/worldbookApi.ts
- frontend/src/components/writing/contextPreview/WorldbookPreviewPanel.tsx
- frontend/src/components/writing/ContextPreviewDrawer.tsx
- backend/tests/test_worldbook_auto_update_apply_ops.py
- backend/tests/test_worldbook_auto_update_chapter_input.py
- backend/tests/test_worldbook_auto_update_contract.py
- backend/tests/test_worldbook_auto_update_existing_entries_preview.py
- backend/tests/test_worldbook_auto_update_service_repair.py
- backend/tests/test_worldbook_auto_update_task_error_details.py
- backend/tests/test_worldbook_auto_update_task_scheduling.py
- backend/tests/test_worldbook_service_trigger.py
- backend/tests/test_output_contract_worldbook_auto_update_validation_details.py
- backend/tests/test_search_index_service.py
- test/specs/api/worldbook-bulk.contract.spec.ts
- test/specs/api/worldbook-import-export.contract.spec.ts
- test/specs/api/worldbook-preview.contract.spec.ts
- test/specs/api/vector-datalifecycle.contract.spec.ts
- test/specs/ui/worldbook.spec.ts
- test/specs/ui/worldbook-import-export.spec.ts
- test/specs/ui/worldbook-bulk-disable.spec.ts
- test/specs/ui/worldbook-auto-update-failsoft.spec.ts
- test/specs/ui/worldbook-auto-update-success.spec.ts
- test/specs/ui/worldbook-large-list-pagination.spec.ts
- test/specs/ui/memory-context-preview.spec.ts
- test/specs/ui/search-page.spec.ts
- test/specs/ui/writing-auto-updates-after-generate.spec.ts
