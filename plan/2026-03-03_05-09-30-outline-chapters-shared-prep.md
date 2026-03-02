---
mode: plan
task: 6.2 outline/chapters shared prep治理
created_at: "2026-03-03T05:09:53+08:00"
complexity: medium
---

# Plan: outline/chapters 共享准备逻辑治理

## Goal
- 在不改变功能行为的前提下，抽取并复用 outline 与 chapters 的重复准备逻辑，降低维护成本并减少后续改动回归风险。

## Scope
- In:
  - backend/app/api/routes/outline.py：抽取普通/流式接口共享的生成前置准备。
  - backend/app/api/routes/chapters.py：抽取 precheck/generate/generate-stream 共享的 memory 注入与 run params 组装逻辑。
  - issues/2026-03-03_05-09-30-outline-chapters-shared-prep.csv：按 issue 流程维护状态。
- Out:
  - 不改业务功能语义、不新增产品能力、不处理 6.2 之外的问题。

## Assumptions / Dependencies
- 当前分支保持在 test，提交按“一行 issue = 一个 commit”执行。
- 现有单测与编译检查可作为行为不变的主要验证手段。

## Phases
1. 建立 plan + issue CSV，明确边界与验收。
2. 实现 issue-1：outline 共享准备逻辑抽取并验证。
3. 实现 issue-2：chapters memory/params 共享逻辑抽取并验证。
4. 进行回归验证、更新 CSV 状态、提交并推送 test 分支。

## Tests & Verification
- outline/chapter 路由逻辑改造 -> `cd backend; .\.venv\Scripts\python.exe -m compileall -q app alembic`
- 后端行为回归 -> `cd backend; .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`

## Issue CSV
- Path: issues/2026-03-03_05-09-30-outline-chapters-shared-prep.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- manual（本任务仅本地代码与测试，不依赖 MCP）

## Acceptance Checklist
- [ ] outline 普通/流式生成的前置准备复用同一套函数。
- [ ] chapters 三条路径的 memory 注入/params 组装复用同一套函数。
- [ ] 关键后端验证命令通过。
- [ ] issue CSV 与代码变更同步提交。

## Risks / Blockers
- 大文件重构可能引入变量作用域/类型细节回归。
- 若本地测试环境波动，可能需要补充更细粒度证据。

## Rollback / Recovery
- 按 issue 级 commit 回滚；每个 commit 独立可逆，不跨 issue 混改。

## Checkpoints
- Commit after: 每个 issue 完成并更新对应 CSV 行状态。

## References
- 新项目全面调查.md
- backend/app/api/routes/outline.py
- backend/app/api/routes/chapters.py
