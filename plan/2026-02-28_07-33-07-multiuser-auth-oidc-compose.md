---
mode: plan
task: Multi-user auth + LinuxDo OIDC + compose
created_at: "2026-02-28T07:33:07+08:00"
complexity: complex
---

# Plan: 多用户注册登录 + LinuxDo OIDC + Compose 一键部署 + 并发/任务稳定性

## Goal
- Git clone 后可通过 docker compose 启动完整系统（frontend/backend/postgres/redis/worker），支持：
  - 未登录访问自动跳转登录页，可跳转注册页
  - 本地账号密码注册/登录
  - LinuxDo Connect OIDC 快捷登录（首次自动注册）
  - 后台任务/并发：可通过 env/compose 配置 web worker、DB pool、RQ worker 扩展，减少失败与排队

## Scope
- In:
  - Backend：
    - AI ops JSON 合同 fail-soft（ops 缺失/为空视为 no-op + warning，不应直接失败）
    - Web 并发参数化（uvicorn workers）、DB 连接池参数化（SQLAlchemy pool）、RQ worker 并发/扩展说明
    - 新增本地注册 `/api/auth/local/register`
    - 新增 LinuxDo OIDC（start/callback）+ 外部账号映射表（alembic 迁移）
    - 允许通过 `AUTH_COOKIE_SECURE` 控制 cookie secure（便于 HTTP 冒烟；公网建议 HTTPS + secure）
  - Frontend：
    - 新增 `/register` 页面
    - Login/Register 互链 + 未登录默认进入 `/login`
    - 登录/注册页新增 LinuxDo 快捷登录入口（根据后端 providers 可用性展示）
  - Deployment：
    - 完善 docker compose quickstart（默认安全、可通过 env 调并发）
    - 更新 `.env.docker.example` 与 `README.md`（部署与多 worker 指南）
- Out:
  - 邮箱白名单/验证/接码
  - 账号绑定/解绑 UI、多 OIDC Provider
  - 反向代理/TLS 终止（仅文档建议）
  - 完整压测基准（仅提供并发 knobs 与冒烟步骤）

## Assumptions / Dependencies
- 生产形态使用 Postgres + Redis + rq_worker（SQLite 仅本地单 worker）。
- LinuxDo OIDC 需要部署者提供 `LINUXDO_OIDC_CLIENT_ID/CLIENT_SECRET`（未配置时按钮隐藏/不可用）。
- 公网部署建议 HTTPS；若仅 HTTP，需要显式设置 `AUTH_COOKIE_SECURE=0`（有风险）。

## Phases
1. 修复后台任务“ops 空/缺失”导致的失败（schema/服务对齐，no-op 视为成功）。
2. 增加并发/数据库可配置项（uvicorn workers、SQLAlchemy pool、RQ worker 扩展）。
3. 实现本地注册 + 前端注册页/路由/互链。
4. 接入 LinuxDo OIDC（后端 + 迁移 + 前端按钮）。
5. Compose quickstart 完善 + 回归验证。

## Tests & Verification
- Backend：`cd backend; .\.venv\Scripts\python.exe -m compileall -q app alembic` + `cd backend; .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- Frontend：`cd frontend; npm run lint` + `cd frontend; npm test` + `cd frontend; npm run build`
- Compose：`docker compose config`（静态校验）+ 手工冒烟：注册 -> 登录 -> 创建项目（OIDC 可选）。

## Issue CSV
- Path: issues/2026-02-28_07-33-07-multiuser-auth-oidc-compose.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] 未登录访问受保护页面会重定向到 `/login`，登录页可跳转 `/register`。
- [ ] `/register` 可创建本地账号并自动登录。
- [ ] LinuxDo OIDC 登录：首次自动注册并登录；已注册用户直接登录。
- [ ] docker compose quickstart：只需配置必要 env 即可启动；并发参数可通过 env 调整。
- [ ] 后台任务遇到 ops 缺失/为空时不会直接报 parse_error（以 no-op/warning 收敛）。
- [ ] 回归：backend unittest + frontend lint/test/build 通过。

## Risks / Blockers
- OIDC 需要真实 client/redirect_uri 才能端到端联调；在缺少凭据时只能做单测+代码审查。
- 公网部署若无 TLS 且 `AUTH_COOKIE_SECURE=0` 会降低会话安全。
- “三位数并发”取决于宿主资源/DB `max_connections`/worker 数量；本改动提供 knobs，不承诺单机极限。

## Rollback / Recovery
- 回滚单个 commit 后重新 `docker compose up --build`（默认保留数据卷）。
- OIDC 迁移可通过 alembic downgrade 回滚到前一 revision（需确认无数据依赖）。

## Checkpoints
- Commit after: 每个 Issue CSV 行（1 行=1 commit）+ 最后一次回归将所有 Regression_Status 标记 DONE。

## References
- backend/app/services/project_task_service.py:909
- backend/app/db/session.py:1
- backend/scripts/entrypoint.sh:1
- frontend/src/pages/LoginPage.tsx:1
- docker-compose.yml:1
