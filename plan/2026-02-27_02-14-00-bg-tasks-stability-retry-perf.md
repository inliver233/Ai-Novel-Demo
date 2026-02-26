---
mode: plan
task: 后台任务稳定性/并发增强（LLM 重试 + 队列吞吐）
created_at: "2026-02-27T02:46:02+08:00"
complexity: complex
---

# Plan: 后台任务稳定性/并发增强（LLM 重试 + 队列吞吐）

## Goal
- 后台任务在 LLM API 出现超时/502/429 等抖动时自动重试（带退避与抖动），显著降低“一次波动就失败”的概率。
- 任务失败时 TaskCenter 的 error.details 稳定包含 run_id/attempts/how_to_fix，便于定位与复现。
- dev/单机环境下减少排队与等待：inline worker 默认并发更合理，并在健康检查与文档中明确多进程/SQLite/队列形态约束。

## Scope
- In:
  - 后端：新增通用 LLM 重试工具（可重试错误分类、request_id 续写、attempts 结构化记录、run_id 回填）。
  - 任务：worldbook_auto_update / characters_auto_update / graph_auto_update / plot_auto_update / json_repair 接入重试与更稳健的错误回传。
  - 队列：inline worker 默认并发与 health 提示优化；补充 README 运行建议（避免 --reload + --workers 误用）。
  - 单测：覆盖重试、attempts 记录、run_id 回填、错误 details 结构。
- Out:
  - 不改现有 DB 迁移策略；不强制从 SQLite 迁移到 Postgres（仅补充建议）。
  - 不引入新的队列中间件（保持 rq/inline 体系）。
  - 不做无关重构；不改动与本问题无关的业务流程。

## Assumptions / Dependencies
- 现有失败主要来自 LLM 抖动（超时/上游 5xx/限流）与缺少自动重试；通过系统侧重试与更严格的重试提示可显著改善。
- LLM 调用不持有长事务：重试循环仅发生在读库结束后/写库开始前。

## Phases
1. 基础设施：实现通用重试 helper + run_id 提取/attempts 记录，并补充单测。
2. 接入任务：逐个任务接入 helper；在重试模式下收紧输出长度与 JSON 合同（更短、更保守）。
3. 吞吐与文档：inline 默认并发优化 + health/README 提示修正；完成回归测试。

## Tests & Verification
- Backend compile: `cd backend; .\.venv\Scripts\python.exe -m compileall -q app alembic`
- Backend unit tests: `cd backend; .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`

## Issue CSV
- Path: issues/2026-02-27_02-14-00-bg-tasks-stability-retry-perf.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] 后台任务 LLM 调用具备多次重试（默认 3 次，可配置），包含退避/抖动，且不会在第一次失败即终止。
- [ ] llm_call_failed 场景稳定回填 run_id（不再为 null），并返回结构化 attempts。
- [ ] json_repair 同样具备可重试能力（避免修复阶段因为抖动直接失败）。
- [ ] inline worker 默认并发更合理；health/README 清晰提示 SQLite/--reload/--workers 与 rq+worker 的正确用法。
- [ ] 单测通过；每条 Issue 单独 commit（含 CSV 状态更新）并 push 到 `test`。

## Risks / Blockers
- 重试会增加调用成本与耗时：需限制最大次数，并对 429 采用更长退避避免恶化限流。
- SQLite 并发写锁：提高并发可能增加锁等待；需确保写事务短并维持单 worker（SQLite 模式）。

## Rollback / Recovery
- 每条 Issue 1 commit，可按 commit 回滚；不做破坏性迁移。

## Checkpoints
- Commit after: 每条 Issue 完成并通过对应测试。

## References
- backend/app/services/generation_service.py
- backend/app/llm/client.py
- backend/app/services/worldbook_auto_update_service.py
- backend/app/services/characters_auto_update_service.py
- backend/app/services/graph_auto_update_service.py
- backend/app/services/plot_analysis_service.py
- backend/app/services/json_repair_service.py
- backend/app/services/task_queue.py
- README.md
