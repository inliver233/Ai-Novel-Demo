---
mode: plan
task: MCP UI 全流程实测与修复清单
created_at: "2026-01-24T04:08:27+08:00"
complexity: medium
---

# Plan: MCP UI 全流程实测与修复清单

## Goal
- 让「创建项目 → 配置设定/角色 → 模型配置 → 大纲 → 章节 → 预览 → 导出」在 **mock LLM** 与 **真实 LLM（人工粘贴 Key）** 两种模式下都可稳定跑通。
- 把发现的问题收口为可执行 Issue CSV，并确保每个 Issue 都有可验证的 Test_Method。

## Scope
- In:
  - 建立稳定的本地“手工冒烟环境”（mock-llm + backend + frontend），便于用 chrome-devtools MCP 做人工式 UI 复现。
  - 修复/改善模型配置页的交互与状态提示（避免未绑定配置/未保存 Key 时误导点击）。
  - 处理测试过程中暴露的弃用/警告（仅限不影响行为的警告治理）。
- Out:
  - 大规模重构 / 重命名
  - 新增业务功能（RAG/提示词/记忆系统逻辑保持向后兼容）

## Assumptions / Dependencies
- Node/npm、Python venv 已就绪（见 `README.md`）。
- 默认使用 `test/mock-llm/server.js` 作为无密钥的 LLM mock（避免把真实 Key 放入命令/日志/提交）。
- chrome-devtools MCP 可能出现挂起，需要提供可复现与恢复指引；必要时用 Playwright E2E 作为回退证据。

## Phases
1. 建立稳定的“手工冒烟环境”（mock-llm + backend + frontend + 一键清理）
2. 修复/增强 UI 交互（模型配置页等）
3. 回归验证与文档收口（lint/unit/E2E + 手工 checklist）

## Tests & Verification
- Backend:
  - `cd backend; .\.venv\Scripts\python.exe -m compileall -q app alembic`
  - `cd backend; .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- Frontend:
  - `cd frontend; npm run lint`
  - `cd frontend; npm test`
  - `cd frontend; npm run build`
- E2E:
  - `cd test; npm test`
- Manual (Chrome DevTools MCP):
  - 按 Issue 的步骤完成一次完整流程，并记录关键页面截图/网络请求（如需要）。

## Issue CSV
- Path: `issues/2026-01-24_04-03-32-mcp-ui-full-flow-audit.csv`
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- `chrome-devtools:take_snapshot` / `chrome-devtools:click` / `chrome-devtools:fill` / `chrome-devtools:list_network_requests`（UI 复现/排障）
- `context7:query-docs`（核对弃用 API / 推荐写法）

## Acceptance Checklist
- [ ] 提供 1 条可执行脚本/步骤，在不配置真实 Key 的情况下可跑通全流程（mock）。
- [ ] 模型配置页在配置未就绪时不会误导用户“测试连接/下一步”。
- [ ] 每个 Issue：实现后按 `Test_Method` 验证；批次结束后跑一次回归（E2E）。
- [ ] 记录 chrome-devtools MCP 挂起的复现与恢复步骤（可运行/可验证）。

## Risks / Blockers
- chrome-devtools MCP 进程挂起导致无法继续 UI 自动化（需要恢复流程 + Playwright 回退）。
- 真实 LLM Key 不得进入 repo / 日志（只允许 `has_api_key` / `masked_api_key`）。

## Rollback / Recovery
- 每行 Issue 一次提交：必要时逐个 `git revert <sha>` 回滚。
- 若端口占用（`5173/8000/4010`），按端口查 PID 并停止进程。

## Checkpoints
- Commit after: 每个 Issue（同一提交必须包含代码改动 + CSV 状态更新）。

## References
- `README.md`
- `docs/mcp-tools.md`
- `test/run-all.ps1`
- `backend/app/main.py`（已使用 FastAPI lifespan，避免 `@app.on_event` 弃用）
