---
mode: plan
task: LLM 502 proxy/stream hotfix
created_at: "2026-02-27T05:01:39+08:00"
complexity: medium
---

# Plan: [P0][backend] 修复 LLM 502 + 流式回退/重试

## Goal
- 解决后端到上游的连接不稳定/不可达导致的 `502`（LLM_UPSTREAM_ERROR），在需要代理/系统代理时可显式启用。
- 章节流式生成在上游不支持 SSE 或返回空流时，自动回退到非流式并以 SSE 分片稳定输出。
- 保持默认行为向后兼容；后端测试集通过。

## Scope
- In:
  - 后端 `httpx` client：支持 `trust_env`（读取系统 `HTTP(S)_PROXY`）与显式代理。
  - `/api/llm/test`：对可重试 LLM 错误做轻量重试，并在错误 details 中记录 attempts。
  - `/chapters/{id}/generate-stream`：仅在未产出任何 chunk 时重试；空流自动回退非流式并分片输出。
- Out:
  - 引入 Celery/Redis 等外部队列
  - 数据库从 SQLite 迁移到 Postgres
  - 大规模重构/变更前端协议

## Assumptions / Dependencies
- 部分环境通过系统代理才能访问上游；后端当前可能因为 `trust_env=False` 而忽略代理导致 502。
- 部分 OpenAI-compatible 网关不支持 SSE（或返回非 SSE），会导致“未收到流式分片”。
- 仍遵守仓库约束：SQLite 单 worker、LLM 调用不持有长事务。

## Phases
1. 复现与定位：确认 502/空流的触发路径与可配置点。
2. 实现修复：代理/重试/空流回退；补充最小可观测性（attempts）。
3. 验证回归：backend compileall + unittest；手动验证说明写入 Notes/README。

## Tests & Verification
- 语法/单测：`cd backend; .\\.venv\\Scripts\\python.exe -m compileall -q app alembic` -> 无输出即通过
- 后端测试：`cd backend; .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- 手动（需要本地代理/Key）：设置 `LLM_HTTP_TRUST_ENV=true` 或 `LLM_HTTP_PROXY=http://127.0.0.1:PORT` 后，前端“模型测试”返回 pong；章节生成不再出现“未收到流式分片”。

## Issue CSV
- Path: issues/2026-02-27_04-58-27-llm-502-proxy-stream-fallback.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none（全部走本地实现与命令行验证）

## Acceptance Checklist
- [ ] 默认不启用代理（向后兼容）；启用 `LLM_HTTP_TRUST_ENV/LLM_HTTP_PROXY` 后后端可连上上游。
- [ ] `/api/llm/test` 遇到可重试错误会重试，并在错误 details 中包含 attempts。
- [ ] 章节流式：当 stream 无任何 chunk 时自动回退非流式，并仍以 SSE chunk 形式返回文本。
- [ ] 后端 `compileall` + `unittest` 通过。

## Risks / Blockers
- 代理配置错误会导致连接继续失败；通过 attempts/details + 显式 env 命名降低排障成本。
- 流式回退会改变前端收到 chunk 的粒度（仅在空流场景触发）。

## Rollback / Recovery
- 回滚对应 commits；或临时不设置 `LLM_HTTP_TRUST_ENV/LLM_HTTP_PROXY`（保持旧行为）。

## Checkpoints
- Commit after: 每条 Issue 完成并验证后立即提交并 push（严格一 Issue 一 commit）。

## References
- backend/app/llm/http_client.py
- backend/app/api/routes/llm.py
- backend/app/api/routes/chapters.py
- backend/app/llm/client.py
