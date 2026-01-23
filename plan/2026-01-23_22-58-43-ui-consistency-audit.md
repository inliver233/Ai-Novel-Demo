---
mode: plan
task: UI consistency audit
created_at: "2026-01-23T23:19:40+08:00"
complexity: complex
---

# Plan: UI consistency audit（全站 UI 一致性审计）

## Goal
- 背景与目标：当前前端已建立基于 Tailwind + CSS 变量的主题与组件基线，但在部分页面/控件上仍存在“绕过基线（token / base class）”的写法，导致同类控件在不同页面的颜色、focus、disabled、圆角/间距等表现不一致，增加认知负担与回归成本。
- 本批次交付物：仅生成可执行合同（本 plan + 对应 issues CSV），不做任何 UI 修复实现。
- 预期收益：
  - 视觉与交互一致性提升（hover/active/focus/disabled/selected 统一）
  - 可维护性提升（减少重复 class 组合，降低遗漏 focus ring/disabled 的概率）
  - 回归更可控（结合 Playwright 既有用例 + 必要时扩充 visual snapshots）

## Scope
- In:
  - 覆盖前端全路由 UI：`frontend/src/App.tsx` 中所有页面与其关键子面板
  - 一致性维度：颜色/token、交互状态（hover/active/focus/disabled/selected）、基础组件（Button/Input/Textarea/Select/Checkbox/Badge/Toast/Panel/Drawer/Modal）、字体与间距（以现有 class/变量为准）
  - 调查方式：静态扫描 + 运行态核查（可重复、可回放），并将发现拆分为“一行 issue = 一次 commit”的可执行条目
- Out:
  - 本批次不改任何业务/样式实现代码（只落盘 plan + issues CSV 并做 meta commit）
  - 不引入新设计体系/大规模重构；后续执行阶段也遵循 KISS/YAGNI，只在 issue 边界内修复

### 统一 UI 规范基线（以当前项目为准）
> 基线来源：`frontend/tailwind.config.js`、`frontend/src/index.css` 中已存在的 token 与组件 class。

#### 颜色 / 语义 token
- `canvas` -> `bg-canvas` / `text-canvas`（一般用于页面底）
- `surface` / `surface-hover` -> `bg-surface` / `bg-surface-hover`（卡片/面板底）
- `ink` -> `text-ink`（主文字）
- `subtext` -> `text-subtext`（辅助文字）
- `border` -> `border-border`
- `accent` -> `bg-accent` / `text-accent`（强调/主 CTA）
- `success` -> `bg-success` / `text-success`（成功提示）

#### 交互状态（现有基线）
- Focus：统一使用 `.ui-focus-ring`（`ring-accent` + `ring-offset-canvas`）
- Transition：`.ui-transition` / `.ui-transition-fast`
- Press：`.ui-pressable`（active scale）

#### 组件基线（现有 class 体系）
- Button：`.btn` + `.btn-primary` / `.btn-secondary` / `.btn-ghost` / `.btn-danger` / `.btn-icon`
- Form：`.input` / `.textarea` / `.select` / `.checkbox`
- Container：`.panel` / `.panel-interactive` / `.surface` / `.surface-interactive`
- Skeleton：`.skeleton`

#### 字体/字号/行高/圆角/动效（现有变量）
- 字体：`font-ui` / `font-content` / `font-mono`（见 `frontend/tailwind.config.js`、`frontend/src/index.css`）
- 排版类：`.atelier-content`、`.atelier-mono`
- 圆角：`rounded-atelier`（`--radius-base`）
- 动效：`--motion-duration-*`、`--motion-ease-standard`（prefers-reduced-motion 已处理）

## Assumptions / Dependencies
- 本地具备 Node.js（>=18）且 `frontend/node_modules`、`test/node_modules` 已安装（本仓库当前已存在）。
- UI 验收优先使用 Playwright 黑盒用例（`test/specs/ui/*.spec.ts`）；必要时补充 visual snapshots（`test/specs/ui/visual.spec.ts`）。
- 主题基线为 `data-theme="paper-ink"` + `.dark`（见 `frontend/src/index.css`），审计需同时关注 light/dark。

## Phases
1. 建立清单与证据规范（静态扫描 + 路由覆盖表）
2. 组件基线优先修复（checkbox/input/select/badge/toast/button variants）
3. 分页面推进（Dashboard/Writing/Outline/WorldBook/PromptStudio/Settings/高级调试页等，每页 1~3 个 issue）
4. 测试保障与截图回归（补充/更新 visual spec；批次末 run-all）
5. 回归通过后 meta commit（仅更新 CSV 的 Regression_Status）

## 调查方法（必须可重复）
### 静态扫描（rg）
- 查绕过 token 的 hardcode 色：
  - `rg -n "text-(red|green|yellow|orange|amber|emerald|teal|cyan|sky|indigo|purple|pink|rose)-|bg-(red|green|yellow|orange|amber|emerald|teal|cyan|sky|indigo|purple|pink|rose)-|border-(red|green|yellow|orange|amber|emerald|teal|cyan|sky|indigo|purple|pink|rose)-|ring-(red|green|yellow|orange|amber|emerald|teal|cyan|sky|indigo|purple|pink|rose)-" frontend/src`
- 查表单控件是否使用基线 class：
  - checkbox/radio：`rg -n 'type="checkbox"|type="radio"' frontend/src`
  - select：`rg -n '<select' frontend/src`
  - textarea：`rg -n '<textarea' frontend/src`
  - focus ring：`rg -n 'ui-focus-ring|focus-visible:ring|ring-offset' frontend/src`
- 查“疑似未定义的 utility class”：
  - `rg -n '\\bbtn-[a-z0-9_-]+' frontend/src`

### 运行态核查（建议）
- 快速回归（黑盒）：
  - `cd test; npm test -- specs/ui/navigation.spec.ts`
  - `cd test; npm test -- specs/ui/rag-page.spec.ts`
  - `cd test; npm test -- specs/ui/graph-page.spec.ts`
  - `cd test; npm test -- specs/ui/task-center.spec.ts`
  - `cd test; npm test -- specs/ui/structured-memory.spec.ts`
- 需要肉眼对齐样式时：
  - `cd test; npm run test:headed`（或 `npm run test:ui`）
  - 必要时扩展 `test/specs/ui/visual.spec.ts` 并用 `--update-snapshots` 锁定一致性

### 证据记录规范（写入 CSV Notes）
- 每个问题至少记录：
  - repro：路由/操作路径（例如 `/projects/<id>/rag -> Advanced -> ...`）
  - expected：对应基线（token/class）
  - evidence：`file:line`（必要时补 screenshot/trace 路径：`test/.artifacts/**/trace.zip`）
  - suspected_files：优先收敛到具体文件/组件

## 页面范围（至少覆盖）
- Dashboard：首页（含“高级/调试”入口区域）
- Writing / Outline / WorldBook / Prompts / PromptStudio / Styles / Preview / Export / Settings / NotFound
- 高级调试页：Rag / Graph / Fractal / StructuredMemory / TaskCenter

## Issue 拆分原则
- 一行 issue = 一次 commit：只解决 1 类一致性问题（或单页内同一组件族）。
- 优先级建议：
  - P0：明显破坏一致性/影响可用性（如 checkbox 默认样式、缺失 focus ring）
  - P1：高频页面或全局组件不一致（btn-danger、btn-sm、badge tone）
  - P2：低频/高级页或样式系统性优化（token 化 success/warn/error、toast 统一）
  - P3：清理/文档/可选优化（移除未使用模板样式等）

## Definition of Done（DoD）
- 单 issue DoD：
  - 边界内修改完成（不做无关重构）
  - `Test_Method` 可执行（或 manual checklist 可复现）
  - 对应 `test/specs/ui/*.spec.ts`（或最小子集）通过
- 批次 DoD：
  - `pwsh test/run-all.ps1` 回归通过后，统一把 CSV 的 `Regression_Status` 批量置 `DONE` 并做 meta commit（未来执行阶段）

## Tests & Verification
- 每条 issue：优先跑最相关的 Playwright spec（例如 rag/graph/admin-users/task-center 等）；必要时补 manual checklist。
- UI 结构/布局变更：可能需要更新 `test/specs/ui/visual.spec.ts-snapshots/`，并在单独 issue 中处理。

## Issue CSV
- Path: issues/2026-01-23_22-58-43-ui-consistency-audit.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- 本批次（合同生成）：`manual`（静态扫描 + 产出文件）
- 未来执行：优先 `manual` + Playwright CLI；如需浏览器辅助，可选 `chrome-devtools`（以 `docs/mcp-tools.md` 为准）

## Acceptance Checklist
- [ ] 已完成静态扫描与证据归档，Issue 拆分为可执行条目
- [ ] 已生成 plan 与 issues CSV（timestamp/slug 一致）
- [ ] CSV 校验脚本通过：`python .codex/skills/plan/scripts/validate_issues_csv.py issues/<...>.csv`
- [ ] 仅提交 plan + issues CSV 两个文件，并 push 到 `test` 分支（meta commit）

## Risks / Blockers
- 部分“危险/警告/信息”色彩当前未 token 化：需要在不引入大范围设计变更的前提下，选择“维持 Tailwind 色盘”还是“补充 token”。
- UI 视觉回归截图会带来变动量：需分离为独立 issue，避免和业务/样式修复混在同一 commit。
- 高级/调试页控件密集：容易遗漏 focus/disabled/selected 状态，需按组件族推进。

## Rollback / Recovery
- 每条 issue 一次 commit：可通过 `git revert <sha>` 回滚单点变更。
- 若截图回归更新导致不稳定：优先缩小截图范围、mask 动态区域、或拆分用例。

## Checkpoints
- Commit after: 本批次仅 1 个 meta commit（plan + issues CSV）。
- 未来执行：每条 issue 完成后 commit+push；批次末回归通过后再做“Regression_Status meta commit”。

## References
- `AGENTS.md`
- `issues/README.md`
- `docs/testing-policy.md`
- `test/README.md`
- `test/ADDING_TESTS.md`
- `frontend/tailwind.config.js`
- `frontend/src/index.css`
- `frontend/src/App.tsx`
