---
mode: plan
task: Wave 2026-03-15 H outline memory hotspot shrink
created_at: "2026-03-15T21:16:06+08:00"
complexity: complex
---

# Plan: Wave 2026-03-15 H outline memory hotspot shrink

## Goal
- 以 compatibility-first 方式继续缩小 `backend/app/services/outline_generation_stream_service.py`，把 stream request prepare / event mapping / fallback / finalize 等细节拆到 outline feature-local helper/module，同时保持 outline stream / fallback / segmented / fill / repair / generation-run / SSE contract 不变。
- 继续缩小 `backend/app/api/routes/outline.py` 与 `backend/app/api/routes/memory.py` 的 route-local helper / mapper / normalize 负担，让 route 仅保留鉴权、headers/params 接入、service 调用、最薄响应包装与错误边界。
- 补齐本批新增 helper/service/mapper 的 backend unittest、定向 Playwright、完整回归与文档/issue 记账，确保 Wave H 完成后仍满足“可直接推送生产端”的标准。

## Scope
- In:
  - `outline_generation_stream_service.py` 的 feature-local shrink：至少拆出 stream event mapping、fallback/finalize/结果组装、stream 轮询进度桥接等 2~3 块真实职责。
  - `backend/app/api/routes/outline.py` 的 route-local guidance / normalize / prompt / coverage / response helper 模块化抽离，但不重开 Wave F/G 已完成的 outline app service 边界。
  - `backend/app/api/routes/memory.py` 的 preview / retrieve / auto-update touched helper / mapper / normalize 抽离，但不把 `memory_retrieval_service.py` / `memory_update_service.py` 扩成更大巨石。
  - 本批 touched helper/service 的 backend unittest、指定 API/UI Playwright、前后端回归、全量 Playwright、quality gate、文档和 Issue CSV 状态闭环。
- Out:
  - `T11` 全量后端主链路重写、`T12` 知识子域统一、`T13` 任务系统工业化、`T14+` 基础设施/部署/观测/CI/压测升级。
  - 改 outline / memory API contract、SSE event contract、status code、error code、generation run 类型、前端 URL/search params/ARIA/按钮文案。
  - 为了消 warning 去改 `scripts/guards/no_direct_llm_call_in_api.py` 或 `scripts/guards/file_line_count_guard.py` 规则。
  - 处理未跟踪用户文件、覆盖 `5.4大调查详细记录.md` 现有本地 handoff 记录，或拆与本批无关的 `vector_rag_service.py` / `project_task_service.py` / `search_index_service.py` / `memory_update_service.py` 巨石。

## Assumptions / Dependencies
- 当前分支保持 `test`；`git status` 已确认存在用户未跟踪文件和 `5.4大调查详细记录.md` 的本地修改，本批不会触碰未跟踪文件，只在现有文档修改基础上追加 Wave H 事实记录。
- 允许新增 outline/memory feature-local helper / mapper / model / test 文件，但必须保持现有 API/SSE/UI contract、generation run / warning / parse_error / finish_reason / dropped_params 语义兼容。
- 每个 issue 继续执行 `Issue CSV 一行 = 一个 commit`，同一 commit 必须同步提交代码与当前 CSV 状态，并在 commit 后 push 到 `origin/test`。

## Phases
1. 生成并校验 Wave H plan/issues，完成 outline/memory 目标代码与 contract/UI 测试审查，锁定最小兼容切口。
2. 交付 `MVP-682`：拆分 `outline_generation_stream_service.py` 的 stream event mapping / fallback / finalize 等职责，主 service 仅保留最核心编排。
3. 交付 `MVP-683`：抽离 `backend/app/api/routes/outline.py` 的 route-local helper / mapper / prompt / coverage 逻辑到 feature-local module，并同步让 outline 相关 service 复用这些模块而不再依赖 route 巨石细节。
4. 交付 `MVP-684`：抽离 `backend/app/api/routes/memory.py` 的 preview / retrieve / auto-update touched helper / mapper / normalize，保持 `/memory/preview`、`/memory/retrieve`、memory update UI 主路径兼容。
5. 交付 `MVP-685`：补测试、补文档、跑后端/前端/定向 Playwright/全量 Playwright/quality gate，并如实记录剩余热点与出界事项。

## Tests & Verification
- Outline stream helper shrink -> `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_outline*_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe scripts\run_quality_gate.py` | `cd test && npx playwright test specs/api/outline-missing-preset.contract.spec.ts specs/ui/outline-stream.spec.ts specs/ui/outline-fallback.spec.ts`
- Outline route helper shrink -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_outline*_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe scripts\run_quality_gate.py` | `cd test && npx playwright test specs/api/outline-missing-preset.contract.spec.ts specs/ui/outline-stream.spec.ts specs/ui/outline-fallback.spec.ts`
- Memory route helper shrink -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_memory*_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe scripts\run_quality_gate.py` | `cd test && npx playwright test specs/api/memory-preview.contract.spec.ts specs/api/memory-retrieve.contract.spec.ts specs/ui/memory-update.spec.ts`
- Batch closeout regression -> `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_outline*_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_memory*_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe scripts\run_quality_gate.py` | `cd frontend && npm run lint` | `cd frontend && npm test` | `cd frontend && npm run build` | `cd test && npx playwright test specs/api/outline-missing-preset.contract.spec.ts specs/api/memory-preview.contract.spec.ts specs/api/memory-retrieve.contract.spec.ts specs/ui/outline-stream.spec.ts specs/ui/outline-fallback.spec.ts specs/ui/memory-update.spec.ts` | `cd test && npm test` | `python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-03-15_21-13-01-wave-2026-03-15-h-outline-memory-hotspot-shrink.csv`

## Issue CSV
- Path: issues/2026-03-15_21-13-01-wave-2026-03-15-h-outline-memory-hotspot-shrink.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none：本批以本地代码审查、backend unittest、frontend lint/vitest/build 与 Playwright 黑盒回归为主，不依赖额外 MCP。

## Acceptance Checklist
- [ ] `backend/app/services/outline_generation_stream_service.py` 明显变薄，至少 2~3 块 stream prepare / event / fallback / finalize 职责被真实拆到 feature-local module，且 outline stream/fallback/SSE/generation-run 语义保持兼容。
- [ ] `backend/app/api/routes/outline.py` 与 `backend/app/api/routes/memory.py` 的 route-local helper / mapper / normalize 负担明显减轻，route 只保留鉴权、request 接入、service 调用、最薄响应包装与错误边界。
- [ ] 本批 touched 文件上的 file-line-count warning 明显缩小；理想情况下 `outline_generation_stream_service.py` 不再超阈值，若 `outline.py`/`memory.py` 仍有残留则文档如实记录原因与边界。
- [ ] 后端 `compileall` / outline+memory unittest / `quality_gate`，前端 `lint` / `vitest` / `build`，指定 Playwright 与最终 `cd test && npm test` 均真实通过。
- [ ] `3.13调查详细全面报告所有问题.md`、`5.4大调查详细记录.md`、Wave H issue CSV 如实记录已做、未做、剩余热点与仍不属于本批范围的事项，并维持生产可推结论的真实性。

## Risks / Blockers
- outline stream 涉及 SSE 事件、fallback、segmented/fill/gap-repair 进度桥接与 generation_run 细节，若抽离时改动字段或事件时机，会直接导致 UI/contract 回退。
- outline route helper 已被 outline generation services 间接复用；拆分时若处理不好循环依赖或兼容导出，可能影响非 stream 路径与既有单测导入。
- memory route 的 preview/retrieve pack 结构和 auto-update fail-soft 细节被 API/UI 黑盒直接依赖，若 mapper/normalize 抽离时改变字段默认值或包装层，会立刻暴露回归。

## Rollback / Recovery
- 若某个 helper/service 抽离导致 contract 回退，按 issue 粒度回滚对应 commit，仅撤销该 issue 新增模块/测试/CSV 状态。
- 若回归暴露本批触达链路阻断 bug，仅做最小兼容修复并补测试；超出 Wave H 四个任务包的缺陷只记录到文档与 CSV，不借机扩 scope。

## Checkpoints
- Commit after: MVP-682 outline stream helper shrink.
- Commit after: MVP-683 outline route helper shrink.
- Commit after: MVP-684 memory route helper shrink.
- Commit after: MVP-685 docs + regression closure.

## References
- AGENTS.md
- issues/README.md
- docs/testing-policy.md
- .codex/skills/plan/SKILL.md
- .codex/skills/testing/SKILL.md
- plan/2026-03-15_18-54-48-wave-2026-03-15-g-remaining-route-boundary-closeout.md
- issues/2026-03-15_18-54-48-wave-2026-03-15-g-remaining-route-boundary-closeout.csv
- 3.13调查详细全面报告所有问题.md
- 5.4大调查详细记录.md
- backend/app/api/routes/outline.py
- backend/app/api/routes/memory.py
- backend/app/services/outline_generation_app_service.py
- backend/app/services/outline_generation_stream_service.py
- backend/app/services/outline_generation_prepare_service.py
- backend/app/services/outline_generation_segment_service.py
- backend/app/services/outline_generation_fill_service.py
- backend/app/services/outline_generation_gap_repair_service.py
- backend/app/services/outline_generation_gap_repair_final_sweep_service.py
- backend/app/services/memory_auto_update_app_service.py
- backend/app/services/memory_retrieval_service.py
- backend/app/services/memory_update_service.py
- backend/tests/test_outline_generation_guidance.py
- backend/tests/test_memory_auto_update_app_service.py
- test/specs/api/outline-missing-preset.contract.spec.ts
- test/specs/api/memory-preview.contract.spec.ts
- test/specs/api/memory-retrieve.contract.spec.ts
- test/specs/ui/outline-stream.spec.ts
- test/specs/ui/outline-fallback.spec.ts
- test/specs/ui/memory-update.spec.ts
