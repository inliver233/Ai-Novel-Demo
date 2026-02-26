---
mode: plan
task: ops empty no-op worldbook/graph
created_at: "2026-02-27T06:02:12+08:00"
complexity: medium
---

# Plan: [P0][backend] 允许 ops 为空（no-op）并提升任务稳定性

## Goal
- worldbook_auto_update / graph_auto_update 不再因 `ops 为空或缺失` 触发 parse_error 而失败。
- 当模型确实无可更新内容时，系统将其视为 no-op 成功，并记录 warning 便于观察。
- 避免 no-op 仍触发不必要的索引重建/变更集写入，提升效率。

## Scope
- In:
  - Output contract：`worldbook_auto_update_json`、`memory_update_json` 解析允许 `ops=[]` 或缺失时视为 no-op（warning，不再报 parse_error）。
  - Worldbook apply：无实际变更时不标记 `vector_index_dirty`，不调度 rebuild 任务。
  - Graph auto update：当 `ops` 为空时直接返回 ok(no-op)，不创建空的 MemoryChangeSet。
- Out:
  - 重新设计 JSON schema / 引入新协议版本
  - 引入新的外部队列/数据库迁移

## Assumptions / Dependencies
- 部分模型在“没有确定更新”时会返回 `ops: []`（或漏字段），这是合理 no-op，而不是系统错误。
- 现有业务允许 no-op：worldbook/graph 本次不更新即可。

## Phases
1. 调查：定位 parse_error 触发点与影响面（contract + service）。
2. 合同修复：放宽 ops 为空的解析规则，并更新/新增单测。
3. 业务修复：worldbook/graph 针对 no-op 做性能优化（不触发无意义任务/写入）。

## Tests & Verification
- `cd backend; .\\.venv\\Scripts\\python.exe -m compileall -q app alembic`
- `cd backend; .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py" -v`

## Issue CSV
- Path: issues/2026-02-27_05-59-14-ops-empty-noop-worldbook-graph.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] `ops=[]/ops 缺失` 不再导致 worldbook/graph 任务失败。
- [ ] no-op worldbook 不会触发 vector/search rebuild。
- [ ] no-op graph 不会创建空 change set。
- [ ] backend tests 全绿。

## Risks / Blockers
- 放宽合同可能掩盖“模型偷懒不输出 ops”的问题；通过 warning 记录并在 UI/日志可观测。

## Rollback / Recovery
- 回滚对应 commits。

## Checkpoints
- Commit after: 每条 Issue 完成 + 测试通过 + CSV 更新后立刻 commit+push。

## References
- backend/app/services/output_contracts.py
- backend/app/services/worldbook_auto_update_service.py
- backend/app/services/graph_auto_update_service.py
- backend/tests/test_worldbook_auto_update_contract.py
- backend/tests/test_graph_auto_update_service.py
