---
mode: plan
task: "Full system audit: tasks queue/fail + issue split"
created_at: "2026-02-03T20:23:07+08:00"
complexity: complex
---

# Plan: 全面复核并拆分 Issue（后台任务排队/失败 + LLM 合同一致性 + 功能完整性）

## Goal
- 让“章节定稿后自动更新链路（worldbook/characters/plot/tables/graph/vector/search/fractal）”在真实 LLM 场景下可稳定运行：不再大量排队、可观测、失败可重试且错误可定位。
- 把 `完整任务要求.txt` 的 6 大点 + 当前实际失败现象，拆成可逐个 commit 落地的 Issue CSV；所有 Issue DONE 后，系统在不减少功能的前提下可用。

## Scope
- In:
  - 任务系统：ProjectTask + queue（inline/rq）、调度、执行、错误记录、重试、可观测性、吞吐。
  - LLM 合同：characters/worldbook/graph/table 的 prompt/解析/修复机制，确保真实模型输出能落库。
  - UX：TaskCenter/标注回溯/高级调试关键页面的“可操作/可解释/不横向溢出”。
  - 需求项：世界书自动注入、剧情记忆与世界书边界、数值表格、RAG embedding+rerank、图谱、搜索引擎化。
- Out:
  - 本轮只做“调查→拆分→产出 plan+CSV”，不直接改业务代码（由后续对话按 Issue 执行）。

## Assumptions / Dependencies
- SQLite 模式：后端必须 `--workers 1`；所有 LLM 调用不得持有长事务（现有 services 多已分离 session）。
- 当前 dev 环境 Redis 不可用时会回落 inline；inline 默认单线程导致排队（需要优化或提示）。
- Playwright/E2E 默认使用 mock LLM；需要补充“真实 LLM”验收步骤（manual 或脚本）。
- 允许使用当前 `backend/ainovel.db` 作为复现样本（包含失败任务与 run_id）。

## Phases
1. P0 复现与可观测性：把“为什么排队/为什么失败/失败在哪”在 TaskCenter 一眼可见（queue backend、run_id、parse_error、how_to_fix）。
2. P0 合同一致性：修复 characters/worldbook/graph/table 的 prompt+parser，使真实 LLM 输出可解析；加入 repair/normalize 兜底与回归 fixture。
3. P0 吞吐与稳定性：缩短单任务耗时（prompt 收敛、timeout 策略）并减少排队（并发/合并/去重策略）。
4. P1 需求功能补齐：按 `完整任务要求.txt` 六大点，对 UI/数据模型/自动更新默认策略做收敛与增强。
5. P1/P2 回归守门：把关键体验（无横向滚动、任务可追踪、自动更新可跑）固化为 E2E/contract。

## Tests & Verification
- Backend: `cd backend; .\\.venv\\Scripts\\python.exe -m compileall -q app alembic; .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p \"test_*.py\" -v`
- Frontend: `cd frontend; npm run lint; npm test; npm run build`
- E2E/Blackbox: `cd test; $env:E2E_BACKEND_URL=\"http://127.0.0.1:32568\"; $env:E2E_FRONTEND_URL=\"http://127.0.0.1:32569\"; npm test`
- Real LLM smoke (manual): 在任务中心触发 `worldbook_auto_update/characters_auto_update/graph_auto_update/table_ai_update` 并确保全部 succeeded；若失败必须在 task.error.details 中看到 run_id + parse_error/how_to_fix。

## Issue CSV
- Path: issues/2026-02-03_20-11-11-full-system-audit.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- chrome-devtools:take_snapshot / chrome-devtools:list_network_requests：复核 UI overflow、按钮点击命中、网络请求链路（可选）。
- context7:query-docs：查询 Neo4j / graph modeling 等文档（用于图谱建模调研；可选）。

## Acceptance Checklist
- [ ] TaskCenter 能显示 queue backend（含 inline fallback）与并发/排队提示
- [ ] characters/worldbook/graph/table 自动更新在真实 LLM 下可成功（至少在样例项目）
- [ ] 失败任务包含 run_id + parse_error/how_to_fix（无空 message）
- [ ] 任务不再出现“数分钟排队后才开始”的不可用体验（有量化指标）
- [ ] 全套测试通过（backend+frontend+E2E）

## Risks / Blockers
- 真实 LLM 输出不可控：需要 repair/normalize + 更强结构化约束；否则 parse_error 仍可能出现。
- 上游代理 60s 超时：table_ai_update 等需收敛 prompt/输出，或支持分段/重试。
- SQLite 并发写入：并发策略必须设计“LLM 并行、DB apply 串行”或明确使用 rq 单 worker。

## Rollback / Recovery
- DB 操作：任何 schema 变更前备份 `backend/ainovel.db`；迁移使用 Alembic，可回滚。
- 任务与变更集：table_ai_update/graph_auto_update 已支持 change_set apply/rollback；对新增 change_set 维持同口径。

## Checkpoints
- Commit after: 每个 Issue（CSV 一行）完成后立即提交并更新 CSV 状态；每个 Phase 结束跑一次 E2E 冒烟。

## References
- `完整任务要求.txt:1`
- `backend/app/services/task_queue.py:54`
- `backend/app/services/project_task_service.py:434`
- `backend/app/services/project_task_service.py:784`
- `backend/app/services/characters_auto_update_service.py:256`
- `backend/app/schemas/characters_auto_update.py:24`
- `backend/app/services/worldbook_auto_update_service.py:120`
- `backend/app/schemas/worldbook_auto_update.py:50`
- `backend/app/services/graph_auto_update_service.py:68`
- `backend/app/schemas/memory_update.py:110`
- `frontend/src/pages/TaskCenterPage.tsx:705`
- `frontend/src/pages/ChapterAnalysisPage.tsx:109`
- `backend/ainovel.db`（样例失败任务：run_id=b497cd7a.../d8024a18.../ea1ca685...；table_ai_update timeout runs=938e0135.../7d9b53d8...）
