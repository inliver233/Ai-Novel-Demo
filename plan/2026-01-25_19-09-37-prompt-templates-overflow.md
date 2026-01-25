---
mode: plan
task: "[P0][frontend][prompt-templates] 修复系统默认模板列表文本溢出"
created_at: "2026-01-25T19:11:14+08:00"
complexity: simple
---

# Plan: [P0][frontend][prompt-templates] 修复系统默认模板列表文本溢出

## Goal
- /prompt-templates 左侧「系统默认模板」列表项中：模板名与任务名始终不超出按钮边框；长文本显示省略号；不出现横向 overflow。

## Scope
- In: `frontend/src/pages/PromptTemplatesPage.tsx` 左侧列表项布局（必要时补充 Tailwind class）。
- In (validation unblock): 若 `npm run build` 因既有 TypeScript 类型错误失败，允许做最小化修复以完成验证闭环（例如 `frontend/src/pages/GlossaryPage.tsx`）。
- Out: 后端接口、资源数据结构、页面其它区域样式。

## Assumptions / Dependencies
- 本地可启动：frontend `5173` + backend `8000`，并用 dev fallback 进入应用。
- 目标页面：`/projects/d02e7756-e9bc-470b-b364-12f31e857bb5/prompt-templates`。

## Phases
1. 用 chrome-devtools 复现并截图/快照取证（before）。
2. 修复列表项 flex 布局溢出：补齐 `min-w-0`/`overflow-hidden` 等，确保 `truncate` 生效。
3. 用 chrome-devtools 再次截图/脚本检查（after）。
4. 运行前端与 Playwright 指定用例，更新 Issue CSV 状态。
5. commit（1 Issue = 1 commit）并 push 到 `origin/test`。

## Tests & Verification
- UI 证据：chrome-devtools 截图 + `evaluate_script` 检查 `scrollWidth <= clientWidth + 1`。
- 自动化：
  - `cd frontend; npm run lint && npm test && npm run build`
  - `cd test; npx playwright test specs/ui/prompt-templates.spec.ts`

## Issue CSV
- Path: issues/2026-01-25_19-09-37-prompt-templates-overflow.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- `chrome-devtools:take_screenshot`：before/after 取证
- `chrome-devtools:take_snapshot`：定位按钮/文本节点
- `chrome-devtools:evaluate_script`：检查 overflow 指标

## Acceptance Checklist
- [ ] /prompt-templates 左侧「系统默认模板」每个按钮内文本不溢出、长文本省略号截断。
- [ ] 产出 before/after 截图各至少 1 张。
- [ ] `evaluate_script` 指标确认无横向溢出。
- [ ] `npm run lint && npm test && npm run build` 通过。
- [ ] `npx playwright test specs/ui/prompt-templates.spec.ts` 通过。
- [ ] 1 commit 同时包含代码变更 + Issue CSV 状态更新，并 push 到 `origin/test`。

## Risks / Blockers
- 端口 5173/8000 被占用导致 Playwright 启动失败（必要时改端口并记录到 CSV Notes）。

## Rollback / Recovery
- `git revert <commit>` 回滚单次提交。

## Checkpoints
- Commit after: Issue MVP-PT-UI-002 完成并验证通过。

## References
- `frontend/src/pages/PromptTemplatesPage.tsx`
- `frontend/src/pages/GlossaryPage.tsx`
- `test/specs/ui/prompt-templates.spec.ts`
