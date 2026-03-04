---
mode: plan
task: outline longform generation robustness refactor
created_at: "2026-03-05T01:20:36+08:00"
complexity: complex
---

# Plan: 大纲长篇分段生成与流式稳定性重构

## Goal
- 全面重构大纲生成链路，使 120~500 章场景在输出、解析、补全、连续性上显著稳定。
- 将“单次超长 JSON”改为“分段生成 + 分段校验 + 分段补全 + 全局兜底”的收敛流程。
- 降低流式生成卡在 10%/中断后失败概率，保证可观测进度与可恢复性。

## Scope
- In:
  - `backend/app/api/routes/outline.py`：新增长篇分段生成引擎，改造同步/流式接口分支策略。
  - 大纲输出解析与连续性校验：增加分段专用解析与章号严格约束。
  - 长篇上下文构建：在分段请求中携带全量已生成索引 + 近期章节细节 + 总纲锚点。
  - 后端单测：新增/扩展分段模式、少章重试、高章数收敛相关测试。
  - `issues/2026-03-05_01-20-36-outline-longform-generation-robustness.csv`。
- Out:
  - 不改动章节正文生成主链路。
  - 不进行与本任务无关的 UI 大改与数据库 schema 变更。

## Assumptions / Dependencies
- 当前分支为 `test`，提交遵循“一行 Issue = 一个 commit”。
- 维持 SQLite 单 worker 和 LLM 调用短事务原则。
- 现有 Outline API 返回结构向后兼容，新增字段仅增量附加。

## Phases
1. 梳理现有大纲链路（生成、流式、解析、补全）并定义分段策略参数。
2. 实现后端分段生成引擎（批次生成、分段重试、章号连续性校验、全局补全兜底）。
3. 接入 `/outline/generate` 与 `/outline/generate-stream` 的长篇自动切换逻辑与进度事件。
4. 新增/更新单测，执行编译与目标回归验证。
5. 更新 Issue CSV 状态并提交推送。

## Tests & Verification
- `cd backend`
- `.\.venv\Scripts\python.exe -m compileall -q app alembic`
- `.\.venv\Scripts\python.exe -m unittest -v tests.test_outline_generation_guidance`
- `cd ..\frontend`
- `npm run build`

## Issue CSV
- Path: issues/2026-03-05_01-20-36-outline-longform-generation-robustness.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- manual

## Acceptance Checklist
- [ ] 目标章节数达到阈值时自动走分段模式，而非单次超长 JSON。
- [ ] 每批请求可对“少章返回”执行同批重试与缺号补全，章号连续且无重号。
- [ ] 500 章场景具备可收敛策略，不依赖一次性完整输出。
- [ ] 流式接口可持续反馈进度并输出阶段性结果快照。
- [ ] 后端相关测试通过，现有功能不回归。

## Risks / Blockers
- 分段请求次数增多，若上下文控制不当可能导致 token 成本上升。
- 不同 provider 对长上下文和 JSON 严格性差异较大，需要保留 fail-soft。

## Rollback / Recovery
- 该任务保持单 issue 单提交，可通过 `git revert <commit>` 整体回滚。

## Checkpoints
- Commit after: MVP-606

## References
- AGENTS.md
- issues/README.md
- docs/testing-policy.md
- backend/app/api/routes/outline.py
- backend/app/services/output_parsers.py
- frontend/src/pages/OutlinePage.tsx
