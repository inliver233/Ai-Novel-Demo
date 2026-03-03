---
mode: plan
task: frontend p1 full polish
created_at: "2026-03-04T01:53:24+08:00"
complexity: complex
---

# Plan: 前端 P1 中优先级全量修复（phase 2）

## Goal
- 完成 `前端细节查漏补缺与优化.md` 中 P1-1 到 P1-8 的代码修复与结构优化。
- 保持现有功能可用、可回归，并按 Issue CSV 做“一条 Issue 一次提交”。

## Scope
- In:
  - `frontend/src/components/layout/AppShell.tsx`
  - `frontend/src/components/layout/appShellNavConfig.tsx`（新增）
  - `frontend/src/components/layout/appShellNavConfig.test.tsx`（新增）
  - `frontend/src/App.tsx`
  - `frontend/src/lib/uiCopy.ts`
  - `frontend/src/pages/GlossaryPage.tsx`（删除）
  - `frontend/src/components/ui/ProgressBar.tsx` / `ProgressBar.test.tsx`
  - `frontend/src/components/atelier/MarkdownEditor.tsx`
  - `frontend/src/components/atelier/GhostwriterIndicator.tsx`
  - `frontend/src/index.css`
  - `frontend/src/services/storageKeys.ts`
  - `frontend/src/pages/WorldBookPage.tsx`
  - `frontend/src/pages/SearchPage.tsx`
  - `frontend/src/pages/LoginPage.tsx`
  - `frontend/src/pages/RegisterPage.tsx`
  - `frontend/src/pages/worldbook/useWorldBookFilters.ts`（新增）
  - `issues/2026-03-03_18-12-00-frontend-p1-full-polish.csv`
- Out:
  - 后端接口语义变更
  - 与 P1 无关的 UI 重构与样式大改

## Assumptions / Dependencies
- 当前分支保持在 `test`。
- 前端依赖可在本地完成 `lint/test/build`。
- 以最小风险演进方式处理大页面拆分，优先对 `WorldBookPage` 落地 hooks 化拆分。

## Phases
1. 建立计划与 Issue CSV，并通过 CSV 校验。
2. 导航系统改造与信息架构清理（P1-1/P1-2/P1-3）。
3. 可访问性与动效无障碍补齐（P1-4/P1-5/P1-7）。
4. 存储键与页面解耦 + 大页拆分（P1-6/P1-8）。
5. 回归验证、CSV 状态收口、逐条 commit 与 push。

## Tests & Verification
- 导航与结构相关单测：
  - `cd frontend && npm test -- src/components/layout/appShellNavConfig.test.tsx`
- 进度条单测：
  - `cd frontend && npm test -- src/components/ui/ProgressBar.test.tsx`
- 前端回归：
  - `cd frontend && npm run lint`
  - `cd frontend && npm test`
  - `cd frontend && npm run build`
- 登录/注册回车提交黑盒：
  - `cd test && npx playwright test specs/ui/auth-form-submit.spec.ts`

## Issue CSV
- Path: issues/2026-03-03_18-12-00-frontend-p1-full-polish.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] 导航项改为配置驱动，移动端/桌面端共用渲染源。
- [ ] 遗留 Glossary 页面与未使用文案键清理完成，`/glossary` 兼容重定向保留。
- [ ] `Foreshadows` 在主导航可达。
- [ ] 进度条 ARIA 语义统一到 `ProgressBar`。
- [ ] reduced-motion 提供全局 fallback，并补齐组件级开关。
- [ ] 世界书筛选存储键归一并改为 URL 显式传参联动。
- [ ] 登录/注册表单语义与回车提交行为稳定。
- [ ] 至少一个超大页面完成 hooks 级拆分（优先 `WorldBookPage`）。

## Risks / Blockers
- AppShell 重构涉及导航主路径，若配置错误会导致入口丢失。
- WorldBook 拆分涉及状态流，需避免筛选/分页/批量选择行为回归。
- 动效降级需避免影响必要反馈（如加载中状态）。

## Rollback / Recovery
- 按 Issue 提交粒度回滚：`git revert <commit>`。

## Checkpoints
- Commit after: MVP-401
- Commit after: MVP-402
- Commit after: MVP-403
- Commit after: MVP-404
- Commit after: MVP-405
- Commit after: MVP-406
- Commit after: MVP-407
- Commit after: MVP-408

## References
- `前端细节查漏补缺与优化.md`
- `frontend/src/components/layout/AppShell.tsx`
- `frontend/src/pages/WorldBookPage.tsx`
- `issues/README.md`
- `docs/testing-policy.md`
