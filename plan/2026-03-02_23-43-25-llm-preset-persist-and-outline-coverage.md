# Plan: llm preset persist + outline coverage hardening

## Goal
- 修复 Prompts 页高级参数（`max_tokens`/`timeout_seconds`）保存后被回退默认值的问题。
- 强化大纲长篇生成稳定性：当模型输出章节不足时，服务端按目标章数进行可追踪兜底补齐，避免骨架明显缺章。

## Scope
- In:
  - `frontend/src/pages/PromptsPage.tsx`
  - `frontend/src/components/prompts/LlmPresetPanel.tsx`
  - `backend/app/api/routes/llm_profiles.py`
  - `backend/app/api/routes/projects.py`
  - `backend/app/api/routes/llm_preset.py`
  - `backend/app/llm/capabilities.py`
  - `backend/app/api/routes/outline.py`
  - 相关 backend tests
- Out:
  - 修改数据库 schema / Alembic
  - 重构 Prompt Studio 大体系
  - 新增多次分批调用 LLM 的大纲生成工作流

## Assumptions / Dependencies
- 保持现有 API 响应结构兼容。
- 章节补齐兜底只在已解析出部分章节时生效；完全无法解析 JSON 时仍按现有 parse_error 路径处理。

## Phases
1. 明确问题路径与触发条件（参数回退 + 章节不足）。
2. 实施修复（参数持久化 + 默认值提升 + 章节覆盖兜底）。
3. 增加测试并执行验证。
4. 按 Issue CSV 一行一提交完成提交与推送。

## Tests & Verification
- `cd backend; .\.venv\Scripts\python.exe -m compileall -q app alembic`
- `cd backend; .\.venv\Scripts\python.exe -m unittest tests.test_outline_generation_guidance tests.test_llm_profile_sync_preset_defaults tests.test_prompt_preset_resources -v`
- `cd frontend; npm run build`

## Issue CSV
- Path: issues/2026-03-02_23-43-25-llm-preset-persist-and-outline-coverage.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] 更新配置不再隐式回退已保存的 `max_tokens/timeout_seconds`
- [ ] 默认 `max_tokens/timeout_seconds` 调整为更适合长篇的值
- [ ] 目标章节数为 50/100/200 时，模型即使弱输出也会被服务端补齐为完整章号覆盖
- [ ] 关键测试通过

## Risks / Blockers
- 某些网关对超高 `max_tokens` 参数容忍度低，仍可能在上游触发降级/重试。
- 自动补齐章节属于 fail-soft 兜底，后半段章节的语义细节可能较粗。

## Rollback / Recovery
- 回滚本次改动文件后执行后端单测与前端构建，恢复旧行为。

## Checkpoints
- Commit after: MVP-431
- Commit after: MVP-432

## References
- `backend/app/api/routes/llm_profiles.py`
- `backend/app/api/routes/projects.py`
- `backend/app/api/routes/outline.py`
- `frontend/src/pages/PromptsPage.tsx`
