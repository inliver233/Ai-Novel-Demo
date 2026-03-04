---
mode: plan
task: llm modular api config overhaul
created_at: "2026-03-04T20:44:37+08:00"
complexity: complex
---

# Plan: 模型配置系统模块化重构（主模型 + 任务子模块）

## Goal
- 将当前“单一主模型”配置重构为“主模型 + 可扩展任务模块覆盖”，实现不同业务环节可绑定不同模型配置，未配置任务默认回退主模型。
- 升级 Prompts 页为模块化卡片布局，提升多模块场景下的可读性与可调节性。
- 补充模型列表拉取（下拉可选 + 手输）与推理类高级参数配置，确保请求兼容并具备失败降级。

## Scope
- In:
  - 后端 LLM 配置数据结构与解析流程（任务级覆盖）
  - LLM 配置相关 API（读取、保存、模型列表）
  - 前端 Prompts/模型配置页面 UI 与交互重构
  - 关键调用链（章节生成/分析/大纲/记忆更新/自动更新任务）接入任务级模型选择
  - 相关单测/契约测试补充与回归
  - `issues/2026-03-04_20-44-37-llm-modular-api-config-overhaul.csv`
- Out:
  - 与 LLM 配置无关的页面重构
  - 非必要的数据层大重构

## Assumptions / Dependencies
- 分支保持 `test`，并按 Issue CSV 执行“代码 + CSV 状态”同 commit。
- 现有 `llm_preset` 与 `llm_profile` 需保持兼容，历史项目可无感升级。
- 网络文档研究仅采用官方/一手文档与可靠开源实现参考。

## Phases
1. 调研并固化任务模块清单、参数映射与兼容策略。
2. 实现后端任务级 LLM 覆盖模型（含迁移、schema、routes、resolver）。
3. 接入所有主要 LLM 调用链，保证“任务覆盖 > 主模型默认”。
4. 重构 Prompts 页为模块化卡片并加入模型列表下拉/手输与高级推理参数。
5. 补测试并执行最小可靠回归，修复问题后提交。

## Tests & Verification
- 后端语法/单测：
  - `cd backend`
  - `.\.venv\Scripts\python.exe -m compileall -q app alembic`
  - `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- 前端构建与类型验证：
  - `cd frontend`
  - `npm run build`
- 针对性前端/契约回归（按改动增量执行）：
  - `cd frontend && npm test`
  - `cd test && npm test -- --grep "prompts|settings|prompt"`（若环境可用）

## Issue CSV
- Path: issues/2026-03-04_20-44-37-llm-modular-api-config-overhaul.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- context7:query-docs（参数契约核对）
- chrome-devtools:*（必要时做页面交互快检）
- manual

## Acceptance Checklist
- [ ] 新增任务级模型模块配置，支持按功能选择模型配置，未配置时回退主模型。
- [ ] 模型配置页支持新增/删除模块并清晰展示模块状态与来源。
- [ ] 支持模型列表拉取（下拉 + 手输），并在失败时安全降级到手动输入。
- [ ] 高级参数支持常见推理相关设置并按 provider 安全映射，避免请求格式错误。
- [ ] 主要 LLM 调用路径全部接入任务级配置解析。
- [ ] 相关测试通过，且核心流程无明显回归。

## Risks / Blockers
- 任务级覆盖接入面较广，存在漏接入某些后台任务的风险。
- 不同 provider 参数差异大，若映射不严谨可能触发 400/422。
- UI 状态复杂度上升，需防止保存状态与脏检查失真。

## Rollback / Recovery
- 若出现回归，按 issue 对应 commit 进行 `git revert <commit>`。
- 数据结构变更通过 Alembic 回滚脚本恢复。

## Checkpoints
- Commit after: MVP-601

## References
- AGENTS.md
- issues/README.md
- docs/testing-policy.md
- docs/mcp-tools.md
- backend/app/api/routes/llm_preset.py
- backend/app/services/generation_service.py
- frontend/src/pages/PromptsPage.tsx
- frontend/src/components/prompts/LlmPresetPanel.tsx
