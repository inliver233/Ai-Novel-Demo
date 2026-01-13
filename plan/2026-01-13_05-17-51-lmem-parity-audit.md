---
mode: plan
task: LMEM parity audit
created_at: "2026-01-13T05:20:28+08:00"
complexity: complex
---

# Plan: LMEM parity audit（对照《长期记忆系统完整实现规划.md》）

## Goal
- 产出一份可执行的 Issue CSV，覆盖 test 分支相对《长期记忆系统完整实现规划.md》的“缺口/占位/未集成/设计偏差”，用于后续逐条修复并保持回归可通过。
- 明确哪些模块“已有页面/接口/表”但尚未真正融入写作生成链路与提示词引擎（prompt presets + render_values 注入）。

## Scope
- In:
  - 对照文档：`长期记忆系统完整实现规划.md`（重点：§5 MemoryContextPack / §7~§12 模块注入 / §13 多用户与生产化）。
  - 基于当前 `test` 分支 HEAD 的真实代码状态，盘点：未实现 / 仅占位 / 未接入生成 / 与规划偏差。
  - 产出：本 plan + matching Issue CSV（本批次不做业务实现）。
- Out:
  - 本批次不改业务逻辑、不做重构、不提交功能修复（仅生成计划与 Issue 列表）。
  - 不对 `dev` 分支做任何提交/变更。

## Assumptions / Dependencies
- 基线测试已通过：`pwsh test/run-all.ps1` → PASS（本机 2026-01-13 执行）。
- 后续实现涉及生成 prompt 变化，默认必须保持“关闭记忆注入时行为不变”，并提供快速降级/回滚路径。

## Phases
1. P0：把“记忆注入”从占位接入生成链路（request schema → render_values.memory → prompt preset blocks → generation_runs 观测）。
2. P1：补齐 MemoryContextPack 各 section 的真实实现与 UI/契约测试（story_memory/structured/graph/vector_rag/fractal）。
3. P1：补齐 Memory Update 的“自动 propose（LLM 契约）+ 人在环 review + 防草稿污染（章节定稿策略）”。
4. P1：补齐多用户协作最小闭环（用户创建/管理 + project_memberships 管理入口）。
5. P2：补齐向量检索配置（embedding/rerank）与可观测/（可选）异步 memory_tasks/worker 编排，并完善文档。

## Tests & Verification
- 基线：`pwsh test/run-all.ps1`（已跑）。
- 单 Issue：以 CSV 的 `Test_Method` 为准（优先最小可靠：backend unit / frontend unit / Playwright contract/ui）。

## Issue CSV
- Path: issues/2026-01-13_05-17-51-lmem-parity-audit.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- 本批次：`none`（仅审计与产出计划/CSV）。
- 后续实现：以本地命令 + Playwright 为主；MCP 工具按 `docs/mcp-tools.md` 且单轮≤2。

## Acceptance Checklist
- [ ] 生成 `plan/2026-01-13_05-17-51-lmem-parity-audit.md` 与 matching `issues/2026-01-13_05-17-51-lmem-parity-audit.csv`。
- [ ] CSV 通过 `python .codex/skills/plan/scripts/validate_issues_csv.py <issues.csv>`。
- [ ] Issue 覆盖规划文档中的关键缺口（特别是“未接入生成链路/提示词引擎”），并注明依赖与验收方式。

## Risks / Blockers
- 记忆注入接入后会改变 prompt，从而影响生成效果：必须默认关闭/可配置，且需要可观测（generation_runs + logs）支持回放定位。
- 向量检索与（未来）rerank 涉及密钥与成本：需要安全存储与脱敏日志，并明确 dev/prod 配置策略。

## Rollback / Recovery
- 每条 Issue 独立 commit：出现问题可按 Issue 回滚单 commit。
- DB schema 变更类 Issue：必须同步更新 `test/contracts/db_schema.json` 并回归。

## Checkpoints
- Commit after: 每完成一个 Phase（P0/P1/P2）跑一次 `pwsh test/run-all.ps1` 并更新 Regression_Status（可另起 meta commit）。

## References
- `长期记忆系统完整实现规划.md`
- `backend/app/services/memory_retrieval_service.py:14`
- `backend/app/api/routes/chapters.py:818`
- `backend/app/schemas/chapter_generate.py:35`
- `frontend/src/pages/writing/useChapterGeneration.ts:40`
- `backend/app/resources/prompt_presets/chapter_generate_v3/preset.json`
