# Plan: outline real completion retry (no fake padding)

## Goal
- 修复长篇大纲“章节不足时被假补齐”的问题，避免输出看似完整但实为占位文本。
- 在章节不足时自动发起真实补全（向 LLM 请求缺失章号），尽量补齐到目标章数。

## Scope
- In:
  - `backend/app/api/routes/outline.py`
  - `backend/app/resources/prompt_presets/outline_generate_v3/templates/sys.outline.contract.json.md`
  - `backend/tests/test_outline_generation_guidance.py`
  - `issues/2026-03-03_00-36-47-outline-real-completion-retry.csv`
  - `plan/2026-03-03_00-36-47-outline-real-completion-retry.md`
- Out:
  - DB schema / Alembic 变更
  - 前端大范围交互重构

## Assumptions / Dependencies
- 维持现有 API 结构兼容；可新增 warnings/coverage 诊断字段。
- 若多次补全仍失败，返回“真实不完整状态”而非系统占位章节。

## Phases
1. 重构章节覆盖逻辑：去掉默认占位补齐，保留覆盖诊断信息。
2. 增加缺失章节真实补全流程（自动重试 + 合并缺失章号）。
3. 强化提示约束与自动 max_tokens 策略。
4. 增加并运行后端测试，完成提交与回归核验。

## Tests & Verification
- `cd backend; .\.venv\Scripts\python.exe -m compileall -q app alembic`
- `cd backend; .\.venv\Scripts\python.exe -m unittest tests.test_outline_generation_guidance tests.test_prompt_preset_resources -v`
- `cd backend; .\.venv\Scripts\python.exe -m unittest tests.test_llm_profile_sync_preset_defaults -v`

## Issue CSV
- Path: issues/2026-03-03_00-36-47-outline-real-completion-retry.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] 不再返回“自动补齐占位章节”
- [ ] 当目标章节数存在且初次输出不足时，服务端自动向模型补全缺失章号
- [ ] `chapter_coverage` 明确记录缺失与补全过程结果
- [ ] 关键单测与编译通过

## Risks / Blockers
- 弱模型在二次补全时仍可能不遵循章号约束，需通过重试与严格过滤提高成功率。

## Rollback / Recovery
- 回滚本次改动文件，恢复旧逻辑后重新运行相关单测。

## Checkpoints
- Commit after: MVP-433

## References
- `backend/app/api/routes/outline.py`
- `backend/tests/test_outline_generation_guidance.py`
