# Plan: outline long chapters generation fix

## Goal
- 修复“设置长篇章节数（如 200）但大纲解析常停在约 20 章”的问题，确保长篇目标下章节骨架可用。

## Scope
- In:
  - `outline_generate` 提示词契约与渲染变量
  - 大纲生成路由的章节数提取与长篇策略
  - 大纲页章节数提示文案
  - 相关后端单测
- Out:
  - 新增独立多轮章节规划工作流
  - 变更章节 CRUD/批量创建接口契约

## Assumptions / Dependencies
- 模型最终输出仍受上游模型能力与令牌限制影响，但系统需优先保证章节数量覆盖。
- 保持现有 API 返回结构兼容。

## Phases
1. 定位根因：确认是否存在 20 章硬编码与提示词约束冲突。
2. 实施修复：增加章节数优先策略、动态 beats 粒度、长篇自适应 max_tokens。
3. 回归验证：后端编译+单测、前端构建。

## Tests & Verification
- 后端语法与导入有效 -> `cd backend; .\.venv\Scripts\python.exe -m compileall -q app alembic`
- 长篇规则与模板渲染有效 -> `cd backend; .\.venv\Scripts\python.exe -m unittest tests.test_outline_generation_guidance tests.test_prompt_preset_resources -v`
- 前端类型与构建不回归 -> `cd frontend; npm run build`

## Issue CSV
- Path: issues/2026-03-02_23-25-04-outline-200-chapters-fix.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- `none`（本次使用本地代码与测试命令）

## Acceptance Checklist
- [x] 大纲生成提示词支持长篇章数优先策略
- [x] 后端在高章节目标下提供可观测的输出预算提升
- [x] 前端文案不再暗示 8-20 章上限
- [x] 新增测试覆盖核心长篇规则并通过

## Risks / Blockers
- 兼容网关模型（`openai_compatible`）能力未知，超大章数仍可能受上游限制。

## Rollback / Recovery
- 回滚本次修改文件并恢复旧提示词模板；重新运行后端单测与前端构建确认恢复。

## Checkpoints
- Commit after: MVP-430

## References
- `backend/app/api/routes/outline.py`
- `backend/app/resources/prompt_presets/outline_generate_v3/templates/sys.outline.contract.json.md`
- `frontend/src/pages/OutlinePage.tsx`
