---
mode: plan
task: UI 排版修复 + RAG 配置归拢 + Sidebar 图标去重 -> Issue CSV + Plan
created_at: "2026-01-28T18:47:32+08:00"
complexity: complex
---

# Plan: UI 排版修复 + RAG 配置归拢 + Sidebar 图标去重

## Goal
- Dashboard 项目卡片从“书本大卡”回归常规尺寸（仍保持两列）。
- `/projects/:projectId/reader` 阅读页正文不再被挤成窄竖条。
- 右下角 Toast（提示）在长文案/长 request_id 情况下不溢出边框。
- RAG（Embedding/Rerank）相关 key/url/model/provider 配置迁移到「模型配置」页，并保留清晰入口与兼容。
- 侧边栏所有入口图标语义化且不重复。

## Scope
- In:
  - Frontend：Dashboard、Reader、Toast、Prompts/Settings（RAG 配置迁移）、Sidebar icons。
  - E2E：按需新增/调整 Playwright 用例；末尾集中更新 visual snapshots。
  - 本批次仅生成 plan + issues CSV（不在本批次实现）。
- Out:
  - 不做无关重构/信息架构重排；不减少既有功能（只能修复/增强）。
  - 不做 DB schema 变更（如执行时发现缺口，再另立 issue）。

## Assumptions / Dependencies
- 当前分支为 `test`（已确认）。
- RAG 配置目前由项目 Settings 承载（`/api/projects/:id/settings`），迁移以“入口与页面归拢”为主，不改后端字段语义。
- 图标库为 `lucide-react`，优先在现有图标集中选择不重复且语义明确的图标。

## Phases
1. UI 布局问题收敛：Dashboard 卡片尺寸、Reader 宽度、Toast 溢出。
2. 配置归拢：Prompts 增加 RAG 配置区；RAG/Settings 的入口指向 Prompts 并保留状态/排障信息。
3. 视觉与回归：侧边栏图标去重；更新 visual snapshots；跑 `pwsh test/run-all.ps1`。

## Tests & Verification
- Dashboard 卡片 -> `cd test; npm test -- specs/ui/project-create.spec.ts`（必要时补充 visual）。
- Reader 正文宽度 -> `cd test; npm test -- specs/ui/chapter-reader.spec.ts`（必要时补“正文宽度阈值”断言）。
- Toast 不溢出 -> 新增/扩展 E2E 用例或手工 checklist（在各 issue 的 Test_Method 中定义）。
- RAG 配置迁移 -> `cd test; npm test -- specs/ui/prompts-test-connection.spec.ts` + 新增 `prompts-rag-config.spec.ts`。
- Sidebar icons -> `cd test; npm test -- specs/ui/navigation.spec.ts`。
- Visual 快照 -> `cd test; npx playwright test specs/ui/visual.spec.ts --update-snapshots` + `cd test; npm test -- specs/ui/visual.spec.ts`。
- 全量回归 -> `pwsh test/run-all.ps1`。

## Issue CSV
- Path: issues/2026-01-28_18-47-32-ui-layout-rag-icons.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- 主要：Playwright CLI（`test/`）
- 可选：`chrome-devtools:take_snapshot`（需要手工核对布局时使用）

## Acceptance Checklist
- [ ] Dashboard 项目卡片不再是“书本大卡”，两列布局符合预期。
- [ ] 阅读页正文宽度恢复正常，不再是窄竖条。
- [ ] Toast 长文本/长 request_id 不溢出提示框。
- [ ] RAG Embedding/Rerank 配置可在「模型配置」页完成，且从 RAG/Settings 有明确入口。
- [ ] Sidebar 图标无重复且语义合理。
- [ ] `pwsh test/run-all.ps1` 可作为最终回归通过标准。

## Risks / Blockers
- 视觉快照会随布局/图标变化而更新，需要在末尾集中更新，避免反复 churn。
- Reader 从 paper→tool（或容器策略调整）可能影响“纸面感”，需要同时保证正文行长合理。
- RAG 配置入口若重复/不清晰会造成用户困惑：建议 Prompts 为主入口；Settings 保留状态 + 跳转。

## Rollback / Recovery
- 严格按“一条 issue = 一次 commit”执行：可通过 `git revert <sha>` 单点回滚。

## Checkpoints
- Commit after: 每条 issue 完成后（含 CSV 状态更新）立即 commit+push；批次末做 Regression_Status meta commit。

## References
- `frontend/src/pages/DashboardPage.tsx:173`
- `frontend/src/pages/DashboardPage.tsx:184`
- `frontend/src/pages/DashboardPage.tsx:330`
- `frontend/src/lib/routes.ts:22`
- `frontend/src/components/layout/AppShell.tsx:886`
- `frontend/src/pages/ChapterReaderPage.tsx:546`
- `frontend/src/components/ui/ToastProvider.tsx:75`
- `frontend/src/components/ui/RequestIdBadge.tsx:12`
- `frontend/src/pages/SettingsPage.tsx:885`
- `frontend/src/pages/PromptsPage.tsx:61`
- `frontend/src/pages/rag/RagHeaderPanel.tsx:75`
- `frontend/src/components/layout/AppShell.tsx:374`
- `test/specs/ui/visual.spec.ts:1`
- `test/run-all.ps1:1`
- `AGENTS.md:1`
- `issues/README.md:1`
- `docs/testing-policy.md:1`

