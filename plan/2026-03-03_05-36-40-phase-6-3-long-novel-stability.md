---
mode: plan
task: 6.3中期演进-长篇稳定性
created_at: "2026-03-03T05:36:40+08:00"
complexity: complex
---

# Plan: 6.3 长篇稳定性治理

## Goal
- 按《新项目全面调查.md》6.3 完成三项中期演进：分层记忆归档、graph/fractal/vector 上限统一治理、功能可达性一致性检查，并保持现有功能可用与测试可通过。

## Scope
- In:
  - `backend/app/services/fractal_memory_service.py` 与 `memory_retrieval_service.py`：实现千章分层记忆归档（最近窗口/中期摘要/长期总纲索引）及可检索命中输出。
  - `backend/app/services/graph_context_service.py`、`vector_rag_service.py`、`fractal_memory_service.py`：统一预算配置/观测/dropped explain 结构。
  - `backend/app/api/routes/prompts.py` + 前端 PromptStudio/PromptTemplates + UI copy + 新增一致性检查测试：确保后端 task 与前端/预览/E2E 登记同步。
  - `issues/2026-03-03_05-36-40-phase-6-3-long-novel-stability.csv`：按 issue 流程维护状态。
- Out:
  - 不处理 6.3 之外的问题（如其它调查项、无关重构、风格性大改）。
  - 不引入与本任务无关的数据库结构重构。

## Assumptions / Dependencies
- 当前分支为 `test`，所有提交在 `test` 分支完成并推送。
- 采用“一行 issue = 一个 commit”，每次 commit 同步更新当前 CSV 状态。
- SQLite 并发约束保持不变；LLM 调用不持有长事务。

## Phases
1. 建立 plan 与 issue CSV，锁定 6.3 三条交付边界。
2. 实现 `LMEM-701`：分层记忆归档与长期索引可检索能力。
3. 实现 `LMEM-702`：graph/fractal/vector 预算策略统一（可配置/可观测/可解释 dropped）。
4. 实现 `LMEM-703`：任务可达性一致性检查与前后端任务目录统一。
5. 执行验证、回归、逐 issue 提交并推送。

## Tests & Verification
- 后端语法检查：`cd backend; .\.venv\Scripts\python.exe -m compileall -q app alembic`
- 分层记忆与 fractal 回归：`cd backend; .\.venv\Scripts\python.exe -m unittest -v tests.test_fractal_memory_service`
- budget 策略回归：`cd backend; .\.venv\Scripts\python.exe -m unittest -v tests.test_graph_context_prompt_block_limits tests.test_vector_rag_failsoft`
- 可达性一致性检查：`cd backend; .\.venv\Scripts\python.exe -m unittest -v tests.test_prompt_task_reachability_registry`
- 前端校验：`cd frontend; npm test`

## Issue CSV
- Path: issues/2026-03-03_05-36-40-phase-6-3-long-novel-stability.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none（本任务以本地代码与测试为主，不依赖 MCP）

## Acceptance Checklist
- [ ] 分层记忆归档可覆盖千章场景，并包含最近/中期/长期三层结构与长期索引。
- [ ] graph/fractal/vector 均输出统一预算观测与 dropped explain，且上限可配置。
- [ ] 后端 task 新增时可自动检查 PromptStudio、Preview、UI 文案、E2E 登记一致性。
- [ ] 关键后端/前端验证命令通过，且 issue CSV 状态与代码提交同步。

## Risks / Blockers
- 分层记忆输出变化可能影响历史 prompt 长度与注入顺序，需要控制兼容策略。
- 跨前后端一致性检查若实现过严，可能导致误报并阻塞开发流。

## Rollback / Recovery
- 按 issue 级 commit 回滚，每个 issue 独立可逆，避免跨 issue 混改。

## Checkpoints
- Commit after: LMEM-701 / LMEM-702 / LMEM-703 各自完成并通过对应测试。

## References
- 新项目全面调查.md:498
- backend/app/services/fractal_memory_service.py
- backend/app/services/graph_context_service.py
- backend/app/services/vector_rag_service.py
- backend/app/api/routes/prompts.py
- frontend/src/pages/PromptStudioPage.tsx
- frontend/src/pages/PromptTemplatesPage.tsx
- frontend/src/lib/uiCopy.ts
