---
mode: plan
task: 2026Q1 UX/i18n 深度审计与产品化改进
created_at: "2026-01-23T05:03:06+08:00"
complexity: complex
---

# Plan: 2026Q1 UX/i18n 深度审计与产品化改进（ainovel）

## Goal
- 让项目面向“中文创作用户”可用：核心工作流（建项目 → 设定 → 大纲 → 写作 → 预览/导出）路径清晰、文案友好、信息层级合理。
- 将“高级调试/内部术语/英文裸露”收口到可隐藏/可折叠区域，并提供解释/示例，避免页面堆叠导致“功能看不懂、用不上”。
- 工程质量守门：前端 `npm run lint` 通过；后端单测通过；E2E（Playwright）全绿且尽量消除 worldbook 相关 flaky。

## Scope
- In:
  - 全局：侧边栏 IA/命名、页面标题、按钮/表单文案汉化（保留必要专有名词如 prompt、embedding、rerank、API、JSON 等）
  - 前端：`frontend/src/pages/*` 全量页面 + `frontend/src/components/writing/*` 写作抽屉/模态的交互与信息架构重排
  - 测试：修复/加固 Playwright 易碎点（当前集中在 worldbook 大列表/批量流程），必要时补稳定等待与 helper
  - 文档：同步 `docs/ux/*` 与现状（避免 IA/审计矩阵/实现漂移）
- Out:
  - 不做无关重构；不引入“与本审计无关”的新业务功能
  - 不做真实 LLM 调用（沿用 mock/本地验证策略）；不改变既有后端鉴权模型

## Assumptions / Dependencies
- 以 `issues/2026-01-23_05-03-06-2026q1-ux-cn-productization-audit.csv` 为执行合同：一行 Issue = 一次 commit（实现阶段遵循 `AGENTS.md`）。
- UI 文案优先收口到 `frontend/src/lib/uiCopy.ts`（或按模块拆分 `*Copy.ts`），避免散落导致中英混杂与回归困难。
- 当前基线（本次审计实测）：
  - `cd backend; .\\.venv\\Scripts\\python.exe -m unittest ...` 通过
  - `cd frontend; npm test` 与 `npm run build` 通过
  - `cd frontend; npm run lint` 失败：`AiGenerateDrawer.tsx` / `PromptStudioPresetListPanel.tsx` 存在 `react-hooks/set-state-in-effect` error
  - `cd test; npm test` 存在 worldbook UI 用例偶发失败（观察到 large list pagination 断言时序问题）

## Phases
1. Phase 0（P0：质量门槛与可执行性）
   - 修复前端 lint errors/warnings，恢复 `npm run lint` 作为基础守门
   - 稳定 E2E：worldbook 相关 flaky 先止血（必要时引入等待 helper 与重复运行验证）
   - 修复测试脚本输出编码（UTF-8），避免中文日志/trace 输出乱码影响排障
   - 同步 docs/ux：IA 与 audit-matrix 与实际实现一致
2. Phase 1（P1：信息架构与中文化规则落地）
   - 统一侧边栏/标题/分组口径：区分“创作工作台”与“高级调试”
   - 建立“术语 → UI 文案 → 解释/示例”的一致链路（必要时在 UI 内提供入口/tooltip）
3. Phase 2（P1：核心页面产品化）
   - Dashboard / Wizard：明确下一步与入口（减少“去哪写/从哪开始”）
   - Settings：分区 + 解释 + 逐步披露（把高级项折叠、把必填项前置）
   - Outline / Writing：减少堆叠、明确主操作、提高上下文联动可理解性
   - WorldBook / Characters / Preview / Export：统一列表-编辑-预览的交互范式与中文文案
4. Phase 3（P2：高级调试页可用性改造）
   - Rag / Graph / Fractal / StructuredMemory / TaskCenter：统一 DebugPageShell 风格、增加“何时用/怎么看/风险提示”，并把原始 JSON 收进折叠区
5. Phase 4（P2：回归与收尾）
   - 汇总检查：全局中英文一致性、a11y label 稳定性、关键流程 E2E 覆盖与回归闸门

## Tests & Verification
- Frontend：
  - `cd frontend; npm run lint`
  - `cd frontend; npm test`
  - `cd frontend; npm run build`
- Backend：
  - `cd backend; .\\.venv\\Scripts\\python.exe -m compileall -q app alembic`
  - `cd backend; .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- E2E / Blackbox：
  - `cd test; npm test`
  - 对 worldbook 易碎用例：建议在修复后执行 `--repeat-each 5` 验证稳定性（见对应 Issue 的 `Test_Method`）

## Issue CSV
- Path: issues/2026-01-23_05-03-06-2026q1-ux-cn-productization-audit.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- 默认：`Tools = none`（以命令与代码审查为主）。
- 需要 UI 结构快照时：可选 `chrome-devtools:take_snapshot` / `chrome-devtools:take_screenshot`（并在 Issue 的 `Tools` 记录）。

## Acceptance Checklist
- [ ] issues CSV 通过校验：`python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-01-23_05-03-06-2026q1-ux-cn-productization-audit.csv`
- [ ] P0 完成后：`cd frontend; npm run lint` 通过；`cd test; npm test` 全绿且 worldbook 用例可重复运行
- [ ] 所有页面/抽屉：主要交互入口有明确中文说明；高级字段默认折叠；错误态/空态可理解
- [ ] 所有 Issue：`Dev_Status`/`Review1_Status`/最终 `Regression_Status` 为 `DONE`

## Risks / Blockers
- UX/文案调整容易破坏 E2E 选择器：优先使用 `getByRole/getByLabel` + 稳定 `aria-label`，避免依赖可变文案。
- worldbook 列表类页面在高负载下存在时序抖动：需要在测试与 UI 上共同“显式等待加载完成”。
- 高级调试页信息过多：必须坚持“默认收起 + 逐步披露 + 明确用途”，否则改动后仍难用。

## Rollback / Recovery
- 每条 Issue 一次 commit：可 `git revert <sha>` 回滚单点变更。
- UI_COPY 改动优先向后兼容（必要时保留旧 key alias），避免大范围回归。

## Checkpoints
- Commit after: 每条 Issue 行（严格一行一提交）
- P0 完成后：跑一轮 `cd test; npm test` 作为阶段闸门
- 全部完成后：`.\test\run-all.ps1` 作为最终回归闸门

## References
- README.md
- docs/ux/glossary.md
- docs/ux/navigation-ia-v1.md
- docs/ux/audit-matrix.md
- frontend/src/components/writing/AiGenerateDrawer.tsx
- frontend/src/pages/promptStudio/PromptStudioPresetListPanel.tsx
- test/specs/ui/worldbook-large-list-pagination.spec.ts
