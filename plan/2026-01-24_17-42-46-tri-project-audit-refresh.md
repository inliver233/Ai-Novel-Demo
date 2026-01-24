---
mode: plan
task: Tri-project audit refresh (demo vs Amily vs MuMu)
created_at: "2026-01-24T17:47:06+08:00"
complexity: complex
---

# Plan: tri-project-audit-refresh（demo × Amily × MuMu 全功能对照 → 可落地 Issue Backlog）

## Goal
- 以 demo 为主线，完整梳理：长期记忆系统、提示词系统、RAG 检索、上下文注入与管理、UI/交互、工程质量与可用性。
- 对照 Amily 与 MuMu 的优势实现，提炼“可迁移做法”（概念迁移而非代码照搬），并拆成可执行 Issue CSV。
- 为下一轮高难度任务提供统一上下文：每个缺口都有明确入口、验收与验证方法。

## Scope
- In:
  - demo：`backend/`、`frontend/`、`test/`、`docs/`
  - 产物：review（落盘）+ plan + Issue CSV（本批次不做功能实现）
  - 重点域：LMEM / Prompt / RAG / Context / UX / Quality
- Out:
  - 不修改 Amily 与 MuMu（仅做参考与对照）
  - 不在本批次进行业务改造与重构（只生成 backlog）

## Assumptions / Dependencies
- 以 demo `AGENTS.md` 为执行契约：后续实现必须在 `test` 分支、1 行 Issue = 1 commit、同 commit 更新 CSV 状态。
- 新能力默认关闭或可选启用（避免破坏现有生成与回归）。
- 安全红线不回退：密钥不进日志/响应/导出，仅允许 `has_api_key/masked_api_key`。

## Phases
1. 证据收集与能力快照（含版本/commit 定位）
2. 三方能力矩阵与“可迁移做法”提炼（含风险/护栏）
3. 转换为可执行 Issue CSV（拆分依赖、定义验收与验证）
4. 校验 CSV 表头/必填/枚举，并落盘 review 文档

## Tests & Verification
- CSV 校验：`python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-01-24_17-42-46-tri-project-audit-refresh.csv`
- 代码未变更时无需跑全量回归；若后续开始执行该 CSV，则以每条 Issue 的 `Test_Method` 为准，并在批次末跑 `pwsh test/run-all.ps1`。

## Issue CSV
- Path: `issues/2026-01-24_17-42-46-tri-project-audit-refresh.csv`
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- 本批次：`none`（只做审计与产出计划/CSV）。

## Acceptance Checklist
- [ ] 已落盘 review：`docs/reviews/REV-029.md`
- [ ] 已生成 plan 与 matching Issue CSV（timestamp/slug 一致）
- [ ] Issue CSV 通过校验脚本（表头/必填/枚举）
- [ ] Issue 覆盖：Prompt / Memory / RAG / Context / UX / Quality 六大域

## Risks / Blockers
- 跨项目迁移易“把实现方式照搬”导致退化（尤其提示词字符串模板、无测试约束）：必须坚持 demo 的 Prompt Engine 与测试闭环。
- 大能力（Prompt Inspector / 文本导入 / MCP 工具链）属于 P2 级别改造：必须拆分并先补齐观测与降级路径。

## Rollback / Recovery
- 后续执行期：每条 Issue 独立 commit，必要时逐条回滚；DB schema 变更同步 `test/contracts/db_schema.json`。

## Checkpoints
- 每完成一个域（Prompt/Memory/RAG/Context/UX/Quality）至少跑一次最小验证集；批次末跑 `pwsh test/run-all.ps1`。

## References
- `docs/reviews/REV-029.md`
- `学习优化详细区别.md`
- `长期记忆系统完整实现规划.md`
- `提示词系统实现计划.md`

