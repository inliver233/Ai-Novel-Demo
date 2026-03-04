---
mode: plan
task: outline final validation gap repair hardening
created_at: "2026-03-05T03:50:12+08:00"
complexity: medium
---

# Plan: 大纲生成终检校验与缺章补全增强

## Goal
- 在大纲生成主流程结束后增加终检补全，针对缺失章节进行二次修复与插入，降低“跳号缺章”残留概率。

## Scope
- In:
  - 强化缺章补全提示词（缺失数组、禁止章号、邻接上下文、自检）。
  - 新增 `gap_repair` 终检补全阶段（小批次、强约束、失败反馈）。
  - 流式模式支持显示 `gap_repair_applied` 的实时章节快照。
- Out:
  - 不改前端主交互流程与章节创建接口。

## Tests
- `cd backend && .\.venv\Scripts\python.exe -m unittest -v tests.test_outline_generation_guidance`
- `cd frontend && npm run lint && npm test`
- `cd test && npx playwright test specs/ui/outline-stream.spec.ts`

## Issue CSV
- `issues/2026-03-05_03-50-12-outline-final-gap-repair-hardening.csv`
