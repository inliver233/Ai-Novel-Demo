---
mode: plan
task: outline stream preview visibility and raw snapshot hardening
created_at: "2026-03-05T02:30:56+08:00"
complexity: medium
---

# Plan: 大纲流式生成可视化预览增强

## Goal
- 在大纲分段/流式生成过程中，除了进度条，实时展示“已解析章节 JSON 快照 + 最近批次 raw 摘要”，让用户可感知当前生成质量与状态。
- 保持现有生成链路稳定，不引入大 payload 导致的 SSE 解析风险。

## Scope
- In:
  - 后端分段流进度事件补充可控的 raw 摘要字段（截断）。
  - 前端拆分流式显示状态：`raw` 与 `json 预览` 分离，支持实时累计展示。
  - UI 增加“实时章节预览（JSON）”与“流式原始片段（raw）”两个可见区域。
  - 增补/更新 E2E 断言，验证流式预览区域可见且有内容。
- Out:
  - 不修改大纲业务生成策略（分段批次、补全算法、模型选择逻辑）。

## Assumptions / Dependencies
- 当前在 `test` 分支开发。
- 使用现有 mock-llm 与 Playwright 用例完成回归。

## Phases
1. 增强后端分段流事件：为 batch 应用事件附带安全截断的 raw 预览。
2. 增强前端 Outline 生成弹窗：实时展示 JSON 快照与 raw 片段。
3. 跑最小可靠测试（backend targeted + frontend lint/test + Playwright outline-stream）。
4. 更新 issue csv 并提交推送。

## Tests & Verification
- `cd backend && .\.venv\Scripts\python.exe -m unittest -v tests.test_outline_generation_guidance`
- `cd frontend && npm run lint && npm test`
- `cd test && npx playwright test specs/ui/outline-stream.spec.ts`

## Issue CSV
- Path: issues/2026-03-05_02-30-56-outline-stream-preview-hardening.csv

## Risks / Notes
- 流式事件若携带过大内容会影响稳定性，因此 raw 仅传递截断摘要。
- 前端展示层改动需避免影响原有“生成后应用/另存”流程。
