---
mode: plan
task: frontend p1 page split phase2
created_at: "2026-03-04T02:38:39+08:00"
complexity: complex
---

# Plan: 前端 P1-8 核心页面拆分（二阶段）

## Goal
- 在保持功能完整的前提下，继续拆分 `SettingsPage`、`PromptsPage`、`StructuredMemoryPage`、`TaskCenterPage`，降低单文件职责聚合与维护成本。
- 按 Issue CSV 逐条交付，每条一个 commit 并 push。

## Scope
- In:
  - `frontend/src/pages/SettingsPage.tsx`
  - `frontend/src/pages/PromptsPage.tsx`
  - `frontend/src/pages/StructuredMemoryPage.tsx`
  - `frontend/src/pages/TaskCenterPage.tsx`
  - `frontend/src/pages/settings/*`（新增）
  - `frontend/src/pages/prompts/*`（新增）
  - `frontend/src/pages/structuredMemory/*`（新增）
  - `frontend/src/pages/taskCenter/*`（新增）
  - `issues/2026-03-04_02-37-28-frontend-p1-page-split-phase2.csv`
- Out:
  - 页面视觉改版
  - 后端 API 契约变更
  - 与 P1-8 无关的业务逻辑调整

## Assumptions / Dependencies
- 继续在 `test` 分支开发。
- 拆分优先“抽取类型/工具函数/子组件/hooks”，避免改变行为。

## Phases
1. 建立计划与 Issue CSV（通过校验）。
2. 拆分 SettingsPage 与 PromptsPage 的业务模型/辅助逻辑。
3. 拆分 StructuredMemoryPage 的重型业务块。
4. 拆分 TaskCenterPage 的辅助模块并执行回归。

## Tests & Verification
- 每个 issue 至少执行 `cd frontend && npm run build`。
- 批次回归：
  - `cd frontend && npm run lint`
  - `cd frontend && npm test`
  - `cd frontend && npm run build`

## Issue CSV
- Path: issues/2026-03-04_02-37-28-frontend-p1-page-split-phase2.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] SettingsPage 提取独立模型/默认值/映射逻辑模块。
- [ ] PromptsPage 提取独立模型与解析工具模块。
- [ ] StructuredMemoryPage 拆出重型业务块（组件或 hooks）。
- [ ] TaskCenterPage 拆出状态呈现/统计辅助模块。
- [ ] 拆分后 lint/test/build 全通过，功能行为不回归。

## Risks / Blockers
- 页面状态与回调链较长，拆分时可能出现 props/依赖遗漏。
- 类型移动后可能触发循环依赖或 import 路径错误。

## Rollback / Recovery
- 以 issue 为粒度执行 `git revert <commit>`。

## Checkpoints
- Commit after: MVP-501
- Commit after: MVP-502
- Commit after: MVP-503
- Commit after: MVP-504

## References
- `前端细节查漏补缺与优化.md`
- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/pages/PromptsPage.tsx`
- `frontend/src/pages/StructuredMemoryPage.tsx`
- `frontend/src/pages/TaskCenterPage.tsx`
