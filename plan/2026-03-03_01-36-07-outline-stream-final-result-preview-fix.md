---
mode: plan
task: outline stream final result preview fix
created_at: "2026-03-03T01:38:08+08:00"
complexity: medium
---

# Plan: outline stream final-result preview and save-actions fix

## Goal
- 修复流式大纲在补全阶段完成后，前端未稳定拿到最终结果导致“100%但无可保存预览”的问题。
- 修复流式 raw 预览停留在初始章节（例如 10 章）而看不到补全后最终章节的问题。

## Scope
- In:
  - `frontend/src/pages/OutlinePage.tsx`
  - `backend/app/api/routes/outline.py`
  - `issues/2026-03-03_01-36-07-outline-stream-final-result-preview-fix.csv`
  - `plan/2026-03-03_01-36-07-outline-stream-final-result-preview-fix.md`
- Out:
  - 数据库结构调整
  - 与本问题无关的页面重构

## Assumptions / Dependencies
- SSE `result` 事件在大 payload 下存在被前端解析失败的风险，需要控制 payload 体积并增加前端兜底恢复。

## Phases
1. 前端增强流式结果解析：`onResult` + `connect` 返回结果 + raw 文本解析三级兜底。
2. 前端在拿到最终结果后刷新 raw 预览为“最终 JSON”，确保可见完整章节。
3. 后端压缩流式 `result` 事件体（去除大字段），提升 result 事件到达稳定性。
4. 运行编译与测试并更新 issue 状态。

## Tests & Verification
- `cd backend; .\.venv\Scripts\python.exe -m compileall -q app alembic`
- `cd backend; .\.venv\Scripts\python.exe -m unittest tests.test_outline_generation_guidance tests.test_prompt_preset_resources tests.test_llm_profile_sync_preset_defaults -v`
- `cd frontend; npm run build`

## Issue CSV
- Path: issues/2026-03-03_01-36-07-outline-stream-final-result-preview-fix.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [x] 流式 100% 后可稳定得到预览对象并显示“覆盖/另存”操作按钮
- [x] raw 预览可看到补全后的最终 JSON，而不只停留在初始章节输出
- [x] 后端 `result` 事件 payload 精简，降低大结果解析失败风险
- [x] 相关编译与测试通过

## Risks / Blockers
- 若上游代理对 SSE 仍有额外限制，仍可能偶发断流；本次已增加前端结果恢复兜底。

## Rollback / Recovery
- 回滚本次前后端改动，恢复之前流式结果策略。

## Checkpoints
- Commit after: MVP-435

## References
- `frontend/src/pages/OutlinePage.tsx`
- `backend/app/api/routes/outline.py`
