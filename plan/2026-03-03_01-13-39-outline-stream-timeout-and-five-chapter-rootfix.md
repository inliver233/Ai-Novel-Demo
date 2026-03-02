---
mode: plan
task: outline stream timeout and chapter-5 rootfix
created_at: "2026-03-03T01:14:56+08:00"
complexity: complex
---

# Plan: outline stream timeout + chapter-5 truncation rootfix

## Goal
- 修复大章节目标（50/100/200）下 JSON `chapters` 常在第 5 章截断后的补全过程失稳问题。
- 修复流式生成在 94% 补全阶段长时间无事件导致前端 `SSE_STREAM_ERROR` 的问题。
- 修复流式异常场景下“取消生成”按钮显隐与进度状态不一致造成的卡死体验。

## Scope
- In:
  - `backend/app/api/routes/outline.py`
  - `frontend/src/pages/OutlinePage.tsx`
  - `backend/tests/test_outline_generation_guidance.py`
  - `issues/2026-03-03_01-13-39-outline-stream-timeout-and-five-chapter-rootfix.csv`
  - `plan/2026-03-03_01-13-39-outline-stream-timeout-and-five-chapter-rootfix.md`
- Out:
  - DB schema / Alembic 迁移
  - 与本问题无关的 Prompt Studio 重构

## Assumptions / Dependencies
- 模型在长输出下可能持续“少量产出”（例如每次只补 3~6 章），服务端需要允许多轮增量推进。
- SSE 链路（浏览器/反代）对“长时间无事件”敏感，需要在补全阶段持续发心跳或进度事件。

## Phases
1. 复核并加固缺失章节补全调度：分批、增量、可持续推进（不再依赖固定小轮次）。
2. 为补全阶段增加流式心跳/进度输出，避免 94% 阶段连接空闲断开。
3. 修复前端异常态（progress/error/cancel）状态机，避免“按钮消失+界面卡住”。
4. 增补单测并执行后端编译与测试。

## Tests & Verification
- `cd backend; .\.venv\Scripts\python.exe -m compileall -q app alembic`
- `cd backend; .\.venv\Scripts\python.exe -m unittest tests.test_outline_generation_guidance tests.test_prompt_preset_resources tests.test_llm_profile_sync_preset_defaults -v`

## Issue CSV
- Path: issues/2026-03-03_01-13-39-outline-stream-timeout-and-five-chapter-rootfix.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [x] 大章节目标下补全逻辑可持续推进，不会因固定小轮次提前放弃
- [x] 流式补全阶段持续产生 SSE 心跳/进度，避免 94% 长时间静默导致断流
- [x] 流式失败后前端状态明确，不出现“取消生成按钮消失但界面卡死”
- [x] 相关编译与测试通过

## Risks / Blockers
- 极弱模型可能仍无法在限定轮次内完成全部章节，需保留明确 coverage/warnings 诊断。

## Rollback / Recovery
- 回滚本次改动文件并恢复前一版补全策略；保留运行日志用于二次定位。

## Checkpoints
- Commit after: MVP-434

## References
- `backend/app/api/routes/outline.py`
- `frontend/src/pages/OutlinePage.tsx`
- `backend/tests/test_outline_generation_guidance.py`
