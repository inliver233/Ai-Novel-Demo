---
mode: plan
task: outline stream realtime event queue fix
created_at: "2026-03-05T03:09:55+08:00"
complexity: medium
---

# Plan: 大纲流式实时显示修复（事件队列）

## Goal
- 修复分段流式中“已生成内容未实时显示”的问题，保证每个分段尝试事件不会被覆盖丢失。

## Scope
- In:
  - 后端 `/outline/generate-stream` 分段与补全分支由“单快照覆盖”改为“事件队列消费”。
  - 轮询周期内按顺序发送 `result/raw/progress`，并在任务结束前清空残留队列。
  - 保持现有接口协议兼容。
- Out:
  - 不改章节生成业务规则与模型调用参数。

## Tests
- `cd backend && .\.venv\Scripts\python.exe -m unittest -v tests.test_outline_generation_guidance`
- `cd frontend && npm run lint && npm test`
- `cd test && npx playwright test specs/ui/outline-stream.spec.ts`

## Issue CSV
- `issues/2026-03-05_03-09-55-outline-stream-realtime-event-queue-fix.csv`
