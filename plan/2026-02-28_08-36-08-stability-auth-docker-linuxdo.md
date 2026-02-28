---
mode: plan
task: P0 Stability/Auth/Docker Compose
created_at: "2026-02-28T08:39:17+08:00"
complexity: complex
---

# Plan: P0 Stability/Auth/Docker Compose

## Goal
- 后台任务：更强健的 LLM 调用重试 + JSON 合同解析 fail-soft，减少 502/parse_error 直接导致任务失败。
- 并发与数据库：Docker Compose 默认使用 Postgres + Redis + RQ worker，支持三位数用户并发访问的基础能力（避免 SQLite 多 worker 锁）。
- 认证体验：未登录访问一律进入登录页，可跳转注册；登录/注册页支持 LinuxDo OIDC 一键登录/自动注册。
- 一键部署：git clone 后仅需改 docker-compose.yml 的端口/管理员账号密码（有默认）即可启动前后端+DB+队列；可选配置 LinuxDo OIDC。

## Scope
- In:
  - backend：表格/记忆类 AI 更新的 parse 兜底（ops 允许为空）+ 统一 LLM retry；生产环境 guardrail（禁止 SQLite 多进程/强提示）。
  - frontend：登录页/注册页 UI 增强 + LinuxDo 按钮（按 /api/auth/providers 自动显隐）+ 默认禁用 dev fallback。
  - deploy：docker-compose.yml/.env.docker.example/README.md：补齐默认值、worker 并发参数、密钥生成/持久化策略与启动说明。
- Out:
  - 邮箱白名单/验证码/找回密码等高级账号体系。
  - 多节点水平扩容（k8s/helm）、外部反向代理/TLS 终端方案。

## Assumptions / Dependencies
- 生产并发目标以 Postgres 为前提；SQLite 仅用于本地单人/单 worker。
- LinuxDo OIDC 需要用户自行申请 client_id/client_secret 并在平台配置 redirect_uri；未配置时按钮隐藏。

## Phases
1. 基线调查：确认现有任务队列/DB/认证/Compose 状态，生成 Issue CSV 并校验。
2. 后端稳定性：AI ops 解析放宽 + LLM retry 统一；必要的 prod guardrail 与可观测性。
3. 前端认证与部署：登录/注册页 + LinuxDo OIDC 按钮 + 路由守卫；完善 docker compose 一键启动与文档。

## Tests & Verification
- backend：`cd backend; .\\.venv\\Scripts\\python.exe -m compileall -q app alembic; .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- frontend：`cd frontend; npm run lint; npm test; npm run build`
- manual（docker compose）：`docker compose up -d --build` 后访问前端，完成：注册->登录->创建项目；可选 LinuxDo OIDC 登录（需真实配置）。

## Issue CSV
- Path: issues/2026-02-28_08-36-08-stability-auth-docker-linuxdo.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none（本轮以本地代码/测试命令为主；UI 验证采用 manual 步骤）

## Acceptance Checklist
- [ ] 背景任务：LLM 502/timeout 自动重试；解析失败时 fail-soft（不再“一次失败即 error”）；关键信息可在 task/run 详情定位。
- [ ] 并发：docker compose 默认 Postgres+Redis+RQ worker；文档明确三位数并发应使用该模式。
- [ ] 认证：未登录访问进入 /login；可跳转 /register；账号密码注册/登录可用。
- [ ] OIDC：登录/注册页下方提供 LinuxDo 一键登录/注册；未配置时隐藏。
- [ ] Docker Compose：克隆后改端口/管理员账号密码即可启动；README 给出最小步骤。
- [ ] 每条 Issue：实现->按 Test_Method 验证->更新 CSV 状态->单 commit->push 到 test 分支。

## Risks / Blockers
- 外部 OIDC/模型服务属于不确定依赖：无法在离线/无凭据环境里做端到端真实登录与真实模型调用；需以可配置 + 清晰 manual 验证步骤覆盖。
- 过度放宽解析可能导致“静默不更新”：需用 warnings + 任务结果可观测字段提示。

## Rollback / Recovery
- 每个 Issue 一次 commit；如出现回归：`git revert <commit>` 回滚单条 Issue。
- docker 部署异常：先 `docker compose down -v` 清理卷，再按 README 重新启动。

## Checkpoints
- Commit after: each Issue row

## References
- backend/app/services/task_queue.py
- backend/app/services/worldbook_auto_update_service.py
- backend/app/services/graph_auto_update_service.py
- frontend/src/pages/LoginPage.tsx
- frontend/src/pages/RegisterPage.tsx
- docker-compose.yml
