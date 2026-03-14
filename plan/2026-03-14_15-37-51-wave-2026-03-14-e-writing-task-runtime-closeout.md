---
mode: plan
task: Wave 2026-03-14 E writing task runtime closeout
created_at: "2026-03-14T15:37:51+08:00"
complexity: complex
---

# Plan: Wave 2026-03-14 E writing task runtime closeout

## Goal
- 收口 `Writing` 批量生成与 `TaskCenter` 共用的 project task runtime/query/invalidation 边界，消除当前重复散落的 SSE、轮询 fallback、runtime/detail 刷新职责。
- 将 `AiGenerateDrawer` 从单文件混合职责拆成 feature-local shell / model / section / copy 边界，同时保持默认模式、高级模式、save-before-generate、compare/revert、prompt override、memory/context 与 stream/fallback 合同不回退。
- 在本批触达范围内统一 helper text、warning、disabled reason、fail-soft、dropped params 与 recommendation 口径，并只修明显的语义 token 泄漏。
- 以真实 issue、文档和全量回归闭环，保持仓库继续满足“可直接推送生产端”的标准。

## Scope
- In:
  - `frontend/src/pages/writing/useBatchGeneration.ts`、`frontend/src/pages/taskCenter/useTaskCenterPageState.ts` 及其新增的 feature-local runtime/query 共享资源模块。
  - `frontend/src/components/writing/AiGenerateDrawer.tsx` 及新增的 `aiGenerateDrawer/` feature-local 模块。
  - 本批触达的 copy/token 收口：`AiGenerateDrawer`、`BatchGenerationModal`、`GenerationHistoryDrawer`、`TaskCenter` runtime/detail 面板及必要的 copy/model 文件。
  - 对应 vitest、Issue CSV、调查文档与要求的后端/前端/Playwright 回归。
- Out:
  - `T09` 全站统一数据层或新的全局 store 工程。
  - `T07` 写作高级模式产品级全面重构或 `useChapterGeneration` 主合同重写。
  - 路由、`chapterId` / `applyRunId`、ARIA、按钮文案、search params、后端 SSE/API contract 改动。
  - 大纲结构化编辑、后端主链路重构、部署/CI/可观测性、多主题工程。

## Assumptions / Dependencies
- 当前分支保持在 `test`，且工作区中已有的未跟踪用户文件不纳入本批提交。
- `5.4大调查详细记录.md` 已存在本地修改，最终文档收口必须基于现有内容追加 Wave E 事实，不覆盖已有本地块。
- `useProjectTaskEvents`、`chapterStore` 与现有 Playwright 黑盒覆盖是本批的兼容护栏；允许新增最小共享资源层，但不能扩成全站重写。
- 每个 issue 仍按 `Issue CSV 一行 = 一个 commit` 执行，并在同一 commit 更新当前 CSV 状态后 push 到 `origin/test`。

## Phases
1. 生成 Wave E 计划与 Issue CSV，完成 runtime / drawer / copy / 黑盒合同审查，锁定最小兼容边界。
2. 交付 `MVP-670`：抽出 project task runtime/query/invalidation 共享边界，消除 Writing 与 TaskCenter 的重复刷新、SSE、polling fallback、动作后失效逻辑。
3. 交付 `MVP-671`：拆分 `AiGenerateDrawer` 的 shell/default/advanced/copy-model 边界，保留生成主合同、按钮、ARIA 与 compare/revert 行为。
4. 交付 `MVP-672`：统一本批触达 copy / warning / disabled reason / fail-soft / recommendation 与语义 token，并补充 vitest。
5. 交付 `MVP-673`：更新调查文档与 CSV，完成后端、前端、定向 Playwright 和最终 `cd test && npm test` 全量回归。

## Tests & Verification
- Runtime/resource 边界验证 -> `cd frontend && npm test -- --run src/services/projectTaskStore.test.ts src/pages/taskCenter/taskCenterModels.test.ts src/pages/writing/*.test.ts` | `cd test && npx playwright test specs/ui/batch-generation.spec.ts specs/ui/batch-generation-runtime-sync.spec.ts specs/ui/task-center.spec.ts specs/ui/taskcenter-projecttasks.spec.ts specs/ui/taskcenter-projecttasks-sse.spec.ts`
- AiGenerateDrawer/写作合同验证 -> `cd frontend && npm test -- --run src/components/writing/aiGenerateDrawer/*.test.ts src/pages/writing/*.test.ts` | `cd test && npx playwright test specs/ui/chapter-stream.spec.ts specs/ui/chapter-stream-cancel.spec.ts specs/ui/chapter-stream-unsupported-provider.spec.ts specs/ui/chapter-fallback.spec.ts specs/ui/chapter-create-conflict.spec.ts specs/ui/chapter-scale-navigation.spec.ts specs/ui/writing-unsaved-confirm.spec.ts specs/ui/writing-save-status.spec.ts specs/ui/writing-done-status.spec.ts specs/ui/writing-generate-validation-error.spec.ts specs/ui/writing-auto-updates-after-generate.spec.ts specs/ui/writing-advanced-generate-reliability.spec.ts specs/ui/content-optimize-flow.spec.ts specs/ui/context-preview-sync.spec.ts specs/ui/memory-context-preview.spec.ts specs/ui/prompt-inspector.spec.ts specs/ui/tables-panel.spec.ts specs/ui/tables-injection.spec.ts specs/ui/memory-update.spec.ts specs/ui/chapter-analysis-apply.spec.ts specs/ui/chapter-analysis-rewrite.spec.ts specs/ui/foreshadow-drawer.spec.ts`
- Cross-page regression -> `cd test && npx playwright test specs/ui/navigation.spec.ts specs/ui/a11y-form-fields.spec.ts specs/ui/visual.spec.ts specs/ui/chapter-reader.spec.ts specs/ui/preview-navigation.spec.ts specs/ui/search-page.spec.ts specs/ui/xss-markdown.spec.ts`
- Batch closeout regression -> `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe scripts\run_quality_gate.py` | `cd frontend && npm run lint` | `cd frontend && npm test` | `cd frontend && npm run build` | `cd test && npm test`
- Issue contract validation -> `python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-03-14_15-37-51-wave-2026-03-14-e-writing-task-runtime-closeout.csv`

## Issue CSV
- Path: issues/2026-03-14_15-37-51-wave-2026-03-14-e-writing-task-runtime-closeout.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none：本批以本地代码审查、vitest、后端命令与 Playwright 为主，不依赖额外 MCP。

## Acceptance Checklist
- [ ] Writing 与 TaskCenter 共用的 project task runtime/query/invalidation 边界清晰，重复刷新/SSE/polling fallback/动作后失效逻辑显著减少且行为不变。
- [ ] `AiGenerateDrawer` 不再混合全部高级生成职责；shell、默认模式、高级模式、copy/model 映射边界清晰，按钮/ARIA/生成合同不回退。
- [ ] 本批触达的 helper text、warning、disabled reason、fail-soft、dropped params 与 recommendation 口径更统一，且明显的颜色/token 硬编码继续收口到现有语义 token。
- [ ] 后端 compileall / unittest / quality gate，前端 lint / vitest / build，指定 Playwright 与最终全量 Playwright 全部真实实跑通过。
- [ ] Issue CSV、`3.13调查详细全面报告所有问题.md`、`5.4大调查详细记录.md` 如实记录本批已做/未做/不属于本批范围的事项。

## Risks / Blockers
- 共享 runtime 边界如果只搬运代码而不收口状态所有权，会留下双份刷新源，继续制造 stale UI 与事件抖动问题。
- `AiGenerateDrawer` 若只拆 JSX 不拆 model/copy，会继续把 fallback、compare/revert、覆盖提示与高阶选项说明耦合在一起，评审风险不降反升。
- 现有黑盒大量依赖按钮文案、ARIA 与 query-param 合同，任何无意变更都会直接导致主链路回退。

## Rollback / Recovery
- 若共享 runtime 层引入 stale 状态或跨页联动回退，按 issue 粒度回滚对应 commit，仅撤销本批新增的 runtime resource/store 模块与 CSV 状态变更。
- 若 `AiGenerateDrawer` 拆分影响按钮/ARIA/生成行为，回滚该 issue commit，并保留其他已验证 issue 不动。

## Checkpoints
- Commit after: MVP-670 shared project task runtime/query boundary closeout.
- Commit after: MVP-671 AiGenerateDrawer local split.
- Commit after: MVP-672 touched copy/style closeout.
- Commit after: MVP-673 docs + regression closure.

## References
- AGENTS.md
- issues/README.md
- docs/testing-policy.md
- .codex/skills/plan/SKILL.md
- .codex/skills/testing/SKILL.md
- plan/2026-03-14_01-35-58-wave-2026-03-14-d-outline-writing-closeout.md
- issues/2026-03-14_01-35-58-wave-2026-03-14-d-outline-writing-closeout.csv
- 5.4大调查详细记录.md
- 3.13调查详细全面报告所有问题.md
- frontend/src/components/writing/AiGenerateDrawer.tsx
- frontend/src/pages/writing/useChapterGeneration.ts
- frontend/src/pages/writing/useBatchGeneration.ts
- frontend/src/pages/writing/useWritingPageState.ts
- frontend/src/pages/writing/useApplyGenerationRun.ts
- frontend/src/pages/taskCenter/useTaskCenterPageState.ts
- frontend/src/hooks/useProjectTaskEvents.ts
- frontend/src/services/projectTaskRuntime.ts
- frontend/src/hooks/useProjectData.ts
- frontend/src/services/chapterStore.ts
- frontend/src/lib/uiCopy.ts
- frontend/src/components/writing/BatchGenerationModal.tsx
- frontend/src/components/writing/GenerationHistoryDrawer.tsx
- frontend/src/components/writing/ContextPreviewDrawer.tsx
- frontend/src/pages/PreviewPage.tsx
- frontend/src/pages/ChapterReaderPage.tsx
