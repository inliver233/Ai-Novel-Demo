---
mode: plan
task: "Prompt 模板页列表项文本溢出修复"
created_at: "2026-01-25T18:38:11+08:00"
complexity: simple
---

# Plan: Prompt 模板页列表项文本溢出修复

## Goal
- 修复 `/projects/<id>/prompt-templates` 左侧模板列表项中，模板名称/任务名文本溢出容器导致“跑出框”的 UI 问题。

## Scope
- In:
  - 修复 `PromptTemplatesPage` 左侧列表项布局：flex 下正确生效的截断（`min-w-0` + `truncate`），并限制右侧 task 标签宽度。
  - 增加 Playwright 用例防止回归（检查按钮无横向 overflow）。
- Out:
  - 不改动内置 prompt 资源内容（`backend/app/resources/prompt_presets/*`）。
  - 不改动后端接口与数据结构。

## Assumptions / Dependencies
- Tailwind 的 `truncate` 在 flex item 上需要配合 `min-w-0` 才能允许收缩并显示省略号。

## Phases
1. 创建 Issue CSV（并校验）。
2. 修复前端列表项布局。
3. 新增 E2E 用例并跑最小回归。
4. 更新 CSV 状态并提交推送。

## Tests & Verification
- Frontend：`cd frontend; npm run lint && npm test`
- E2E：`cd test; $env:E2E_BACKEND_URL='http://127.0.0.1:18000'; $env:E2E_FRONTEND_URL='http://127.0.0.1:15173'; $env:E2E_MOCK_PORT='14010'; npx playwright test specs/ui/prompt-templates.spec.ts`
- Note：`npm run build` 当前被既有 TS2353 阻断（`frontend/src/pages/GlossaryPage.tsx:193`），本次不在修复范围内。

## Issue CSV
- Path: issues/2026-01-25_18-38-11-prompt-templates-overflow-fix.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] 左侧列表项不出现横向溢出；长标题/任务名以省略号截断。
- [ ] 新增 E2E 用例可稳定检测横向 overflow。

## Risks / Blockers
- 不同浏览器/字体渲染差异导致边界值波动；断言需留 1px 容差。

## Rollback / Recovery
- `git revert <commit>`。

## References
- frontend/src/pages/PromptTemplatesPage.tsx
- test/specs/ui/prompt-templates.spec.ts
