---
mode: plan
task: outline fill preview and quality tuning
created_at: "2026-03-03T02:09:46+08:00"
complexity: medium
---

# Plan: outline fill preview visibility and fill quality tuning

## Goal
- 修复大纲补全阶段“轮次在走但 raw JSON 预览不实时更新”的可视化问题。
- 优化补全章节质量，减少“前半段细、后半段粗”的风格断层。

## Scope
- In:
  - `backend/app/api/routes/outline.py`
  - `frontend/src/pages/OutlinePage.tsx`
  - `backend/tests/test_outline_generation_guidance.py`
  - `issues/2026-03-03_02-09-46-outline-fill-preview-and-quality-tuning.csv`
  - `plan/2026-03-03_02-09-46-outline-fill-preview-and-quality-tuning.md`
- Out:
  - 数据库结构变更
  - 与大纲补全无关的 UI 重构

## Assumptions / Dependencies
- 当前补全阶段只推送 progress 文本，不推送可解析章节快照，导致前端无法实时刷新预览。
- 补全提示词固定为 `beats 1~2`，在中等/长篇目标下会显著拉低补全章节细节密度。

## Phases
1. 在补全轮次成功应用后回传中间章节快照，前端复用现有 onResult 流程实时刷新预览 JSON。
2. 将补全提示词改为“按目标章数 + 已有章节粒度”自适应，并追加有限风格样本约束。
3. 更新单测覆盖补全进度快照字段与提示词质量规则。
4. 运行后端测试与前端构建，更新 issue 状态并提交推送。

## Tests & Verification
- `cd backend; .\.venv\Scripts\python.exe -m unittest tests.test_outline_generation_guidance -v`
- `cd frontend; npm run build`

## Issue CSV
- Path: issues/2026-03-03_02-09-46-outline-fill-preview-and-quality-tuning.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [x] 补全阶段每轮完成后，前端可看到章节 JSON 实时增长（不再只停留初始章节）
- [x] 补全章节提示词质量约束增强，后续章节细节密度不再明显塌陷
- [x] 相关单测与构建通过

## Risks / Blockers
- 中间快照过大可能增加 SSE 带宽；需保持 payload 精简且不携带 raw_output/fixed_json。

## Rollback / Recovery
- 回滚本次 outline 流式补全快照与提示词改动，恢复仅最终结果回传策略。

## Checkpoints
- Commit after: MVP-437

## References
- `backend/app/api/routes/outline.py`
- `frontend/src/pages/OutlinePage.tsx`
