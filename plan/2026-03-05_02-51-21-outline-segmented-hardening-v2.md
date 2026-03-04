---
mode: plan
task: outline segmented robustness and stream observability hardening v2
created_at: "2026-03-05T02:51:21+08:00"
complexity: complex
---

# Plan: 大纲分段生成约束强化与流式展示稳态优化

## Goal
- 强化弱模型在分段场景下的可收敛性：降低“重复旧章节/无进展重试”概率。
- 修复流式 raw 预览标签错位与状态污染问题，提升可观测性准确度。
- 优化前端显示表现，避免长时间流式文本导致界面卡顿。

## Scope
- In:
  - 分段 prompt 增强：显式禁止已完成章号、明确本批章号数组、自检与失败反馈注入。
  - 分段重试反馈：将上一轮失败原因和输出章号注入下一轮提示词。
  - 流式进度快照修正：由 merge-update 改为 replace，避免旧字段污染新事件。
  - 前端 raw 预览缓冲做上限裁剪，减少长篇生成时 UI 性能退化。
  - 补充/更新后端单测覆盖新增约束文案与反馈逻辑。
- Out:
  - 不改业务接口协议（请求结构、主结果字段保持兼容）。

## Tests & Verification
- `cd backend && .\.venv\Scripts\python.exe -m unittest -v tests.test_outline_generation_guidance`
- `cd frontend && npm run lint && npm test`
- `cd test && npx playwright test specs/ui/outline-stream.spec.ts`

## Issue CSV
- `issues/2026-03-05_02-51-21-outline-segmented-hardening-v2.csv`

## Risks
- 提示词约束过强可能降低创造性，需要在“约束/质量”之间平衡。
- 前端 raw 裁剪需保留最近上下文，避免排障信息丢失。
