---
mode: plan
task: llm test 401 no forced logout
created_at: "2026-03-03T01:56:14+08:00"
complexity: medium
---

# Plan: prevent false logout on llm test 401

## Goal
- 修复模型配置页“测试连接”返回 LLM 鉴权错误时误触发全局登出的问题。
- 保持真实会话失效（`UNAUTHORIZED`）时的自动登出行为不变。

## Scope
- In:
  - `frontend/src/services/apiClient.ts`
  - `frontend/src/services/sseClient.ts`
  - `frontend/src/services/unauthorizedPolicy.ts`
  - `frontend/src/services/unauthorizedPolicy.test.ts`
  - `issues/2026-03-03_01-56-14-llm-test-401-no-forced-logout.csv`
  - `plan/2026-03-03_01-56-14-llm-test-401-no-forced-logout.md`
- Out:
  - 后端错误码/状态码映射调整
  - 登录态机制重构

## Assumptions / Dependencies
- 后端已区分错误码：真实登录态错误为 `UNAUTHORIZED`，LLM 测试密钥错误为 `LLM_AUTH_ERROR` / `LLM_KEY_MISSING`。
- `AuthContext` 继续仅通过 `ainovel:unauthorized` 事件执行登出。

## Phases
1. 抽离 401 未授权通知策略函数：仅 `401 + UNAUTHORIZED` 触发全局未授权事件。
2. 在 `apiClient` 与 `sseClient` 接入该策略，替换原“所有 401 都触发登出”逻辑。
3. 添加单元测试覆盖策略边界，执行前端测试与构建。

## Tests & Verification
- `cd frontend; npm test -- unauthorizedPolicy.test.ts`
- `cd frontend; npm run build`

## Issue CSV
- Path: issues/2026-03-03_01-56-14-llm-test-401-no-forced-logout.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [x] `/api/llm/test` 返回 `401 + LLM_AUTH_ERROR` 或 `LLM_KEY_MISSING` 时，不再触发自动登出
- [x] 真实 `401 + UNAUTHORIZED` 仍可触发自动登出
- [x] 新增策略测试通过，前端构建通过

## Risks / Blockers
- 若后端未来新增 401 错误码但语义并非登录失效，需要同步更新前端策略白名单。

## Rollback / Recovery
- 回滚本次前端策略改动，恢复之前“任意 401 均触发登出”的行为。

## Checkpoints
- Commit after: MVP-436

## References
- `frontend/src/contexts/AuthContext.tsx`
- `backend/app/llm/upstream_errors.py`
- `backend/app/core/errors.py`
