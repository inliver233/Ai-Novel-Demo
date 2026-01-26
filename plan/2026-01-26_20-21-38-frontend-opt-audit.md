---
mode: plan
task: 前端完全优化问题发现 -> Issue CSV + Plan
created_at: "2026-01-26T20:28:23+08:00"
complexity: complex
---

# Plan: 前端完全优化问题发现（全量转 Issue 合同）

## Goal
- 把 `前端完全优化问题发现.md` 的**每一个问题点**做一次代码侧核对（文件存在/关键证据可检索），并拆分为可执行的 Issue CSV（1 行 = 1 commit）。
- 本批次仅生成计划与执行合同：新增 `plan/*` 与 `issues/*` 文件，不做任何前端实现修改。

## Scope
- In:
  - 覆盖：`前端完全优化问题发现.md` 全文（系统性 2.* + 路由 3.* + 全局组件 4.*）。
  - 输出：一个 plan + 一个 issues CSV（timestamp/slug 严格一致）。
  - Issue 颗粒度：以报告的 [P0/P1/P2] 条目为最小单元，外加 2.* 系统性问题的 11 个“基础设施/规范”issue。
- Out:
  - 不在本批次做任何业务/样式/结构代码改动。
  - 不做无关重构；后续执行也必须遵循 KISS/YAGNI 与“一行 issue = 一次 commit”。

## Assumptions / Dependencies
- 已在 `test` 分支（当前为 `test`）。
- 前端测试与 E2E 依赖可用：`frontend`/`test` 的 `npm` 脚本可执行。
- 报告中引用的 `docs/ux/audit-report-2026-01-26.md` **当前不存在**（需要后续执行时补齐或修正引用）。

## Phases
1. 静态核对与证据收集：确认报告引用的 `frontend/src/**` 文件均存在，关键证据可用 `rg` 检索。
2. 生成“系统性问题”基础设施 issue（2.1~2.11）：容器宽度/输入变体/focus 策略/request_id/copyText/状态模板/滚动策略/语义色/WizardNextBar safe area/A11y/性能。
3. 生成“按路由/组件”的 issue（3.* 与 4.*）：按报告顺序落盘，确保 100 个 [P0/P1/P2] 点全部覆盖。
4. 校验 CSV 格式：`python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-01-26_20-21-38-frontend-opt-audit.csv`。

## Tests & Verification
- 本批次（仅生成合同）校验：
  - CSV schema 校验：`python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-01-26_20-21-38-frontend-opt-audit.csv`
- 后续执行阶段（写进每条 issue 的 Test_Method）：
  - Frontend：`cd frontend; npm run lint | cd frontend; npm run build`
  - E2E：`cd test; npm test -- specs/ui/<对应页面>.spec.ts`（若无对应 spec，则 manual checklist）

## Issue CSV
- Path: issues/2026-01-26_20-21-38-frontend-opt-audit.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- 本批次：`manual`（静态核对 + 生成文件）。
- 后续执行：优先 Playwright CLI + manual；必要时再用 `chrome-devtools:*`（见 `docs/mcp-tools.md`）。

## Acceptance Checklist
- [ ] 已核对 `前端完全优化问题发现.md` 引用的前端文件全部存在（无缺失）。
- [ ] 已生成 plan 与 issues CSV（timestamp/slug 一致）。
- [ ] Issues CSV 已通过校验脚本。
- [ ] CSV 覆盖报告所有问题点：2.*（11 条）+ [P0/P1/P2]（100 条）。

## Risks / Blockers
- UI 变更点多且分散：后续执行阶段需要谨慎控制回归范围，避免引入功能退化（只能修复/增强，不能少功能）。
- 部分问题属于“设计/文案一致性”而非纯逻辑：需要结合 `ui设计规范.md` 与 `docs/ux/*` 做取舍，但不得改变既有 Paper & Ink / Atelier 方向。
- 缺失引用文档：`docs/ux/audit-report-2026-01-26.md` 目前不存在，可能导致后续高级调试页统一工作缺少参考。

## Rollback / Recovery
- 后续执行严格按“一行 issue = 一次 commit”，可通过 `git revert <sha>` 回滚单点。

## Checkpoints
- Commit after: 每条 issue 完成后（含 CSV 状态更新）立即 commit+push；批次末再做 Regression_Status 的 meta commit。

## References
- `前端完全优化问题发现.md`
- `AGENTS.md`
- `issues/README.md`
- `docs/testing-policy.md`
- `docs/ux/glossary.md`
- `docs/ux/navigation-ia-v1.md`
- `docs/ux/advanced-debug-page-guidelines.md`
- `ui设计规范.md`

