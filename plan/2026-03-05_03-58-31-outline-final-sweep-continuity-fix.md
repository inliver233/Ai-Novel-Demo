---
mode: plan
task: outline final sweep continuity fix
created_at: "2026-03-05T03:58:31+08:00"
complexity: medium
---

# Plan: 大纲终检连续性兜底修复

## Goal
- 针对偶发“跳过连续章节（如跳 10 章）”场景，增加补全后的最终一致性校验与兜底插入修复，尽量将缺章收敛到 0。

## Scope
- In:
  - 在 `gap_repair` 后增加 `final_sweep` 单章兜底修复阶段。
  - 终检后再次覆盖率校验，按最终缺章结果更新告警。
  - 流式补全事件增加 `final_sweep_applied` 实时章节快照。
- Out:
  - 不改章节创建接口与主业务数据结构。

## Tests
- `cd backend && .\.venv\Scripts\python.exe -m unittest -v tests.test_outline_generation_guidance`
- `cd test && npx playwright test specs/ui/outline-stream.spec.ts`

## Issue CSV
- `issues/2026-03-05_03-58-31-outline-final-sweep-continuity-fix.csv`
