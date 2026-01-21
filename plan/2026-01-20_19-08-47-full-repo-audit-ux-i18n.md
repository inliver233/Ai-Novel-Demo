---
mode: plan
task: Full repo audit (UX & i18n)
created_at: "2026-01-20T19:08:47+08:00"
complexity: complex
---

# Plan: full-repo-audit-ux-i18n（全仓库 UX/i18n 审计与改进）

## Goal
- 以可核对的审计矩阵为基线，统一术语/文案/信息架构（IA）与高级调试入口，逐步消除英文裸露与命名漂移。
- 在不引入大规模重构的前提下，让 `frontend` 的 `npm run lint` 与 `test/` 的 Playwright E2E 保持通过。

## Scope
- In:
  - 文档产物：`docs/ux/*`（术语表、调试页规范、IA、UI↔API 映射、审计矩阵）
  - 前端：导航/标题/UI_COPY 收口、humanize 统一、a11y label、侧边栏 IA 重构、关键页面 UX 优化
  - 测试：必要的 E2E 用例适配（导航、写作抽屉、关键流程）
- Out:
  - 不做无关业务逻辑重构；后端仅在 UI/文案/契约需要时做最小修补
  - 不引入新的远程依赖，不做真实 LLM 调用（沿用 Mock LLM）

## Assumptions / Dependencies
- 执行合同以 `issues/2026-01-20_19-08-47-full-repo-audit-ux-i18n.csv` 为准，逐条 Issue 一次交付并保持可回滚。
- UI 文案优先收口到 `frontend/src/lib/uiCopy.ts`（或模块化 `*Copy.ts`），避免散落。
- 严格遵守安全红线：不输出明文 key，仅允许 `has_api_key/masked_api_key`。

## Phases
1. Phase 0（P0：基线与可审计性）
   - docs 基线：DOC-001/002/IA-001/MAP-001/DOC-003
   - 前端 lint/format/i18n/a11y/IA：LINT-*/FORMAT-*/I18N-*/IA-*/A11Y-*
2. Phase 1（P1：页面 UX 优化）
   - UX-* 系列按页面逐个收敛与 E2E 校验
3. Phase 2（P2：维护性/性能/后端契约补齐）
   - MAINT-*/PERF-* 与必要的后端 API 审计/边界测试

## Tests & Verification
- 每条 Issue：按 CSV `Test_Method` 执行（命令或可复现 manual 步骤）。
- 阶段回归建议：
  - Phase 0 结束：`cd frontend; npm run lint` + `pwsh test/run-all.ps1`
  - 最终完成：`pwsh test/run-all.ps1`（通过后再批量标记 `Regression_Status = DONE`）

## Issue CSV
- Path: issues/2026-01-20_19-08-47-full-repo-audit-ux-i18n.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- 默认不依赖 MCP：`Tools` 字段优先填 `none`/`manual`。
- 如需 UI 探查，可选 `chrome-devtools:take_snapshot`/`take_screenshot`（并在对应 Issue 的 `Tools` 记录）。

## Acceptance Checklist
- [ ] issues CSV 通过校验脚本：`python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-01-20_19-08-47-full-repo-audit-ux-i18n.csv`
- [ ] 所有 Issue 的 `Dev_Status`/`Review1_Status` 最终为 `DONE`
- [ ] 完成批量回归后，`Regression_Status` 最终为 `DONE`
- [ ] 前端 `npm run lint` 与必要 E2E/contract 用例通过

## Risks / Blockers
- IA/文案调整可能影响 E2E 选择器：优先使用 role/label，并补齐稳定 aria-label（A11Y-001）。
- 文案集中化可能导致 key 迁移遗漏：用审计矩阵 + UI↔API map 双保险。

## Rollback / Recovery
- 每条 Issue 一次 commit：可通过 `git revert <sha>` 回滚单点改动。
- UI_COPY/humanize 修改保持向后兼容（保留旧 key/alias，或提供迁移映射）。

## Checkpoints
- Commit after: 每条 Issue 行（严格一行一提交）
- Phase 0/最终：跑 `pwsh test/run-all.ps1` 做回归闸门

## References
- issues/2026-01-20_19-08-47-full-repo-audit-ux-i18n.csv
- docs/ux/ui-api-map.md
- docs/ux/navigation-ia-v1.md
- ui设计规范.md
- README.md
