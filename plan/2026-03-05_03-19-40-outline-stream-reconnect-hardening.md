---
mode: plan
task: outline stream reconnect and timeout tolerance hardening
created_at: "2026-03-05T03:19:40+08:00"
complexity: medium
---

# Plan: 大纲流式自动重连与容错窗口增强

## Goal
- 减少“流式失败，回退非流式...”误触发概率，尤其在分段重试导致链路变长时。
- 在已有可用结果的情况下避免误判为失败。

## Scope
- In:
  - 前端流式连接增加自动重连（默认多次、间隔退避）。
  - SSE 客户端在 `done` 丢失但已收到 `result` 时直接返回成功。
  - 保持当前业务 API 与产出结构兼容。
- Out:
  - 不改后端分段算法和 LLM 参数。

## Tests
- `cd frontend && npm run lint && npm test`
- `cd backend && .\.venv\Scripts\python.exe -m unittest -v tests.test_outline_generation_guidance`
- `cd test && npx playwright test specs/ui/outline-stream.spec.ts`

## Issue CSV
- `issues/2026-03-05_03-19-40-outline-stream-reconnect-hardening.csv`
