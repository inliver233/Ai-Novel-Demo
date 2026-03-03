---
mode: plan
task: frontend p0 phase1 polish
created_at: "2026-03-03T17:30:48+08:00"
complexity: medium
---

# Plan: 前端 P0 第一阶段细节修复

## Goal
- 完成第一阶段 5 项前端高收益低风险修复：favicon、RouteMeta、按钮对比度、统一 ProgressBar + ARIA、登录/注册标准表单提交。
- 保持现有业务功能不回退，完成最小可靠验证并按 Issue CSV 逐项提交。

## Scope
- In:
  - `frontend/index.html`
  - `frontend/public/*`
  - `frontend/src/lib/routes.ts`
  - `frontend/src/lib/uiCopy.ts`
  - `frontend/src/index.css`
  - `frontend/src/components/ui/ProgressBar.tsx`（新增）
  - 进度条使用页面/组件（Dashboard/WizardNextBar/ProjectWizard/Outline/Writing/AiGenerateDrawer/BatchGenerationModal）
  - `frontend/src/pages/LoginPage.tsx`
  - `frontend/src/pages/RegisterPage.tsx`
  - 对应最小测试文件
  - `issues/2026-03-03_17-30-02-frontend-p0-phase1-polish.csv`
- Out:
  - 文档中未纳入第一阶段的 P1/P2 问题
  - 与本批次无关的重构或后端逻辑改动

## Assumptions / Dependencies
- 当前分支保持在 `test`。
- 本地可运行 `frontend` 与 `test` 的必要命令。
- 本批次以“最小可回滚提交”为优先，每个 Issue 单独 commit 并 push。

## Phases
1. 建立计划与 Issue CSV 合同并完成 CSV 校验。
2. 按 5 个 Issue 顺序实现、验证、提交：favicon -> RouteMeta -> 对比度 -> ProgressBar -> 登录/注册 form。
3. 执行前端回归（lint/test/build + 关键 UI 用例），完成最终状态核对并 push。

## Tests & Verification
- 前端静态与单测：
  - `cd frontend && npm run lint`
  - `cd frontend && npm test`
  - `cd frontend && npm run build`
- 关键 UI 用例（认证提交行为）：
  - `cd test && npx playwright test specs/ui/auth-form-submit.spec.ts`
- 每个 Issue 按 CSV `Test_Method` 执行最小验证。

## Issue CSV
- Path: issues/2026-03-03_17-30-02-frontend-p0-phase1-polish.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] `vite.svg` 引用移除并替换为项目 favicon。
- [ ] `RouteMeta` 覆盖 `foreshadows/import/prompt-templates`。
- [ ] 主按钮/危险按钮在暗色主题对比度修复。
- [ ] 统一 `ProgressBar` 组件落地并补齐 ARIA。
- [ ] 登录/注册改为标准 `<form onSubmit>`，回车提交稳定。
- [ ] 每个 Issue 独立 commit 且包含对应 CSV 状态更新。

## Risks / Blockers
- 进度条替换涉及多页面，若遗漏 ARIA 名称可能带来可访问性回归。
- 登录/注册结构改造若处理不当，可能影响现有按钮禁用与 loading 状态。

## Rollback / Recovery
- 按 Issue 级别回滚：`git revert <issue_commit>`。

## Checkpoints
- Commit after: MVP-301
- Commit after: MVP-302
- Commit after: MVP-303
- Commit after: MVP-304
- Commit after: MVP-305

## References
- `前端细节查漏补缺与优化.md`
- `frontend/index.html`
- `frontend/src/lib/routes.ts`
- `frontend/src/index.css`
- `frontend/src/pages/LoginPage.tsx`
- `frontend/src/pages/RegisterPage.tsx`
