---
mode: plan
task: Wave 2026-03-17 J prompts + numeric tables route closeout
created_at: "2026-03-17T15:36:10+08:00"
complexity: complex
---

# Plan: Wave 2026-03-17 J prompts + numeric tables route closeout

## Goal
- 以 compatibility-first 方式收尾 `backend/app/api/routes/prompts.py` 与 `backend/app/api/routes/tables.py` 两个剩余 route hotspot，只继续拆 route-local 的 normalize / validate / mapper / export-import / preview / payload builder 负担。
- 保持 `prompt_presets.py`、`prompt_preset_resources.py`、`table_ai_update_service.py`、`project_seed_service.py` 的既有服务边界，不把本批扩成 prompt 域统一工程或 numeric tables 域统一工程。
- 完成 prompts/tables 新增 helper / mapper / route-local module 的 backend unittest、后端/前端/Playwright 回归、主辅文档与 issue 状态闭环。

## Scope
- In:
  - `prompts.py` 中 preset/block mapper、baseline preset ensure、resource metadata join、export/export_all builder、import/import_all schema/version/conflict/action/dry_run 逻辑、preview task/provider/render_log mapper、block reorder 校验等 route-local 重逻辑抽到 feature-local helper / mapper 模块。
  - `tables.py` 中 schema normalize、row validate、table/row public mapper、list/detail/count/row_count builder、row create/update builder、ai_update chapter resolve/token/payload wrapper 等 route-local 重逻辑抽到 feature-local helper / mapper / model 模块。
  - `prompts.py` 与 `tables.py` 接入新模块后继续压薄为鉴权、request params/body/header 接入、helper/service 调用、最薄响应与错误边界。
  - 为新增 helper / mapper / route-local module 补 backend unittest，并完成用户指定的 backend / frontend / Playwright / docs / CSV 闭环。
- Out:
  - `auth.py`、`batch_generation.py`、`memory.py`、`outline.py`、`vector_rag_service.py`、`project_task_service.py` 等无关热点。
  - `T12` 知识子域统一、`T13` 任务系统工业化、`T14+` 基础设施 / 部署 / 观测 / CI / 压测升级。
  - 改 API contract、status code、error code、response schema、pack structure、fail-soft 语义、前端 URL/search params/ARIA/按钮文案、guard 规则。
  - 覆盖/删除用户未跟踪文件，或丢失 `5.4大调查详细记录.md` 已有 handoff 内容。

## Assumptions / Dependencies
- 当前分支已确认是 `test`；当前工作树存在用户未跟踪文件与 `5.4大调查详细记录.md` 本地修改，本批不会碰未跟踪文件，只在 final docs commit 中基于现有内容追加 Wave J 客观结果。
- 允许新增 `prompt_route_helpers.py`、`prompt_route_mappers.py`、`table_route_helpers.py`、`table_route_mappers.py`、`table_route_models.py` 等 feature-local route 模块，但不得把本批逻辑重新堆成新的 route-local 巨石，也不得把复杂逻辑并回现有 service 形成更大 service。
- 用户已明确要求生成 plan / issues 并继续实现，本次直接将该要求视为写入 plan file 与 issues file 的确认授权。

## Phases
1. 生成并校验 Wave J plan / issues，审查 `prompts.py`、`tables.py` 残余职责与相关前端/黑盒 contract。
2. 交付 `MVP-690`：抽离 prompts route 的 preset/block mapper、baseline/resource join、export/import/import_all/reorder/preview helper，并补 backend unittest。
3. 交付 `MVP-691`：抽离 tables route 的 schema normalize、row validate、table/row mapper、list/detail/rows builder、ai_update resolve helper，并补 backend unittest。
4. 交付 `MVP-692`：接入新 helper/module，把 `prompts.py` 与 `tables.py` 压成更薄 route shell，跑 compileall / prompts+tables unittest / quality gate 并确认 file-line warning 状态。
5. 交付 `MVP-693`：完成后端全量、前端三件套、指定 Playwright、全量 Playwright、主辅文档与 Wave J issue 状态闭环，如实记录 prompts/tables 热点关闭状态与仍不属于本批范围的项。

## Tests & Verification
- Prompts helper shrink -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_prompt*_*.py" -v`
- Tables helper shrink -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_table*_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_project_seed_service_numeric_tables.py" -v`
- Route shell final thin -> `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_prompt*_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_table*_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe scripts
un_quality_gate.py`
- Batch closeout regression -> `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe scripts
un_quality_gate.py` | `cd frontend && npm run lint` | `cd frontend && npm test` | `cd frontend && npm run build` | `cd test && npx playwright test specs/api/prompt-preview.contract.spec.ts` | `cd test && npx playwright test specs/api/prompt-presets-export-all.contract.spec.ts` | `cd test && npx playwright test specs/api/prompt-task-reachability.contract.spec.ts` | `cd test && npx playwright test specs/api/generation-runs-prompt-inspector.contract.spec.ts` | `cd test && npx playwright test specs/api/tables.contract.spec.ts` | `cd test && npx playwright test specs/ui/prompt-inspector.spec.ts` | `cd test && npx playwright test specs/ui/prompt-studio-import-export-all.spec.ts` | `cd test && npx playwright test specs/ui/prompt-studio-import-export.spec.ts` | `cd test && npx playwright test specs/ui/prompt-studio-preview.spec.ts` | `cd test && npx playwright test specs/ui/prompt-studio-reorder.spec.ts` | `cd test && npx playwright test specs/ui/prompt-templates.spec.ts` | `cd test && npx playwright test specs/ui/prompts-rag-config.spec.ts` | `cd test && npx playwright test specs/ui/prompts-test-connection.spec.ts` | `cd test && npx playwright test specs/ui/context-preview-sync.spec.ts` | `cd test && npx playwright test specs/ui/numeric-tables-ai-update.spec.ts` | `cd test && npx playwright test specs/ui/tables-panel.spec.ts` | `cd test && npx playwright test specs/ui/tables-injection.spec.ts` | `cd test && npm test` | `python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-03-17_15-36-10-wave-2026-03-17-j-prompts-tables-route-closeout.csv`

## Issue CSV
- Path: issues/2026-03-17_15-36-10-wave-2026-03-17-j-prompts-tables-route-closeout.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none：本批以本地代码审查、backend unittest、frontend lint/vitest/build 与 Playwright 黑盒回归为主，不依赖额外 MCP。

## Acceptance Checklist
- [ ] `backend/app/api/routes/prompts.py` 与 `backend/app/api/routes/tables.py` 明显变薄，且不是只挪注释或改函数名。
- [ ] prompts/tables route-local helper / mapper / payload builder 已真实抽离到 feature-local route 模块，未改 response schema / status code / error code / fail-soft 语义。
- [ ] 理想情况下 `prompts.py` 与 `tables.py` 都压回 `file-line-count-guard` 阈值内；若仍残留，主辅文档必须如实记录强证据与剩余边界。
- [ ] 后端 `compileall` / 全量 unittest / `quality_gate`，前端 `lint` / `vitest` / `build`，指定 Playwright 与最终 `cd test && npm test` 均真实通过。
- [ ] `3.13调查详细全面报告所有问题.md`、`5.4大调查详细记录.md`、Wave J issue CSV 如实记录本批拆分职责、测试结果、热点关闭状态、为何优先 prompts/tables 而非 auth/batch_generation，以及仍不属于本批范围的项。

## Risks / Blockers
- Prompt Studio / Prompt Templates / Prompt Inspector / Context Preview 同时依赖 prompt preview、export/import、resource join 与 reorder 语义；任何字段、actions/conflicts、render_log shape 漂移都会直接造成 UI / contract 回归。
- Numeric Tables / Tables Panel / table_ai_update 同时依赖 schema alias、row_count、rows 列表、chapter resolve、schedule_failed / chapter_not_done details；若 helper 抽离改变细节，会立即造成回归。
- 若 route shrink 只是“换文件名继续堆逻辑”，则 guard 风险会转移而不是关闭；因此必须控制新增 helper/module 的职责边界与体量。

## Rollback / Recovery
- 若 prompts 或 tables 任一 helper 抽离导致 contract / UI 回退，按 issue 粒度回滚对应 commit，只撤销该 issue 的 helper / mapper / route shell 接线 / 测试 / CSV 状态更新。
- 若定向或全量回归暴露出与本批直接相关的阻断 bug，仅做最小兼容修复并补测试；超出 Wave J 范围的问题只记录到文档与 CSV，不借机扩 scope。

## Checkpoints
- Commit after: MVP-690 prompts route helper/mappers shrink.
- Commit after: MVP-691 tables route helper/mappers shrink.
- Commit after: MVP-692 prompts/tables final thin.
- Commit after: MVP-693 docs + regression closure.

## References
- AGENTS.md
- issues/README.md
- docs/testing-policy.md
- .codex/skills/plan/SKILL.md
- .codex/skills/testing/SKILL.md
- plan/2026-03-17_14-11-01-wave-2026-03-16-i-memory-route-remaining-closeout.md
- issues/2026-03-17_14-11-01-wave-2026-03-16-i-memory-route-remaining-closeout.csv
- 3.13调查详细全面报告所有问题.md
- 5.4大调查详细记录.md
- backend/app/api/routes/prompts.py
- backend/app/api/routes/tables.py
- backend/app/services/prompt_presets.py
- backend/app/services/prompt_preset_resources.py
- backend/app/services/prompt_task_catalog.py
- backend/app/schemas/prompt_presets.py
- backend/app/services/table_ai_update_service.py
- backend/app/services/project_seed_service.py
- backend/app/models/project_table.py
- backend/app/models/chapter.py
- frontend/src/pages/PromptStudioPage.tsx
- frontend/src/pages/PromptTemplatesPage.tsx
- frontend/src/components/writing/PromptInspectorDrawer.tsx
- frontend/src/components/writing/ContextPreviewDrawer.tsx
- frontend/src/pages/NumericTablesPage.tsx
- frontend/src/components/writing/TablesPanel.tsx
- test/specs/api/prompt-preview.contract.spec.ts
- test/specs/api/prompt-presets-export-all.contract.spec.ts
- test/specs/api/prompt-task-reachability.contract.spec.ts
- test/specs/api/generation-runs-prompt-inspector.contract.spec.ts
- test/specs/api/tables.contract.spec.ts
- test/specs/ui/prompt-inspector.spec.ts
- test/specs/ui/prompt-studio-import-export-all.spec.ts
- test/specs/ui/prompt-studio-import-export.spec.ts
- test/specs/ui/prompt-studio-preview.spec.ts
- test/specs/ui/prompt-studio-reorder.spec.ts
- test/specs/ui/prompt-templates.spec.ts
- test/specs/ui/prompts-rag-config.spec.ts
- test/specs/ui/prompts-test-connection.spec.ts
- test/specs/ui/context-preview-sync.spec.ts
- test/specs/ui/numeric-tables-ai-update.spec.ts
- test/specs/ui/tables-panel.spec.ts
- test/specs/ui/tables-injection.spec.ts
