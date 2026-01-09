# AGENTS (ainovel)

> Purpose: 为 ainovel 仓库提供可执行的 AI 开发约束 + Issue CSV 工作流，使每次变更都可验证、可回滚、可追踪。

## Role & objective
- Role: AI 编码代理（Codex CLI）
- Objective: 按 Issue CSV 逐条交付功能/修复，并保持向后兼容与测试可通过。

## Constraints (non-negotiable)
- 分支：所有**代码变更与 git commit** 必须在 `test`（或 `test/*`）分支进行；禁止直接在 `dev` / `main` 提交。
- 粒度：**Issue CSV 一行 = 一个 commit**；同一 commit 必须同时提交「代码变更 + 当前 CSV 状态更新」。
- 范围：KISS/YAGNI；不做无关重构；只改本 Issue 边界内的内容。
- 事实：不假想测试通过/命令结果；能跑就跑；跑不了要写明原因与替代证据。
- 安全：不得泄露任何密钥/令牌/个人数据；任何日志输出必须脱敏（仅允许 `has_api_key` / `masked_api_key`）。
- SQLite：单 worker；LLM 调用不得持有长事务（见 `README.md`）。

## Tech & data
- Frontend: React + TypeScript + Vite + Tailwind
- Backend: FastAPI + SQLite + Alembic
- E2E/Blackbox: Playwright（`test/` 目录，独立于前后端实现细节）

## E2E loop (must)
E2E loop = plan -> issues -> implement -> test -> review -> commit -> regression.

## Plan & Issue CSV generation
- Plan 文件：`plan/YYYY-MM-DD_HH-mm-ss-<slug>.md`
- Issue CSV 文件：`issues/YYYY-MM-DD_HH-mm-ss-<slug>.csv`（timestamp/slug 必须与 plan 一致）
- 使用 repo 内技能：`.codex/skills/plan`（模板与校验脚本在 `.codex/skills/plan/assets`、`.codex/skills/plan/scripts`）

## Issue CSV contract
- 以 `issues/README.md` 为准：表头、必填字段、枚举值必须严格匹配（建议先用模板生成再填充）。
- 状态枚举：`TODO | DOING | DONE`
- `Test_Method`：必须写可执行命令或可复现的 manual 步骤（规则见 `docs/testing-policy.md`）。
- `Tools`：填 `manual` / `none` 或 `docs/mcp-tools.md` 中列出的 `server:tool`。

### ID / 标签约定（在不改表头前提下）
- `ID`：允许项目级前缀，例如：
  - `LMEM-###`：长期记忆系统（Long-term memory）
  - `MVP-###`：MVP/Atelier 迭代
- `Title`：建议加“可筛选标签前缀”，例如：`[P0][backend][phase:0.1] ...`
- `Notes`：建议结构化（用 `|` 分隔），例如：`priority:P0 | area:backend | phase:0.1 | owner:xxx | refs:...`

## Git workflow
开始任何实现前必须确认分支：

```bash
git branch --show-current
```

不在 `test`（或 `test/*`）时：

```bash
# 首次（从 dev 创建/重置 test）
git checkout -B test dev

# 或切换到既有 test
git checkout test
```

提交规范：
- Commit message：`[<ID>] <Title>`
- 提交前自检：`git status` / `git diff` 只包含本 Issue 的改动
- 必须 `git add`：代码改动 + 当前 CSV 文件（同一 commit）
- 用户要求：每次提交后 push 到 GitHub 的 `test` 分支（首次：`git push -u origin test`；后续：`git push`）

## Testing strategy
按变更选择**最小但可靠**的验证集；每条 Issue 必须在 CSV 里写清 `Test_Method`。

### Backend
```bash
cd backend
.\.venv\Scripts\python.exe -m compileall -q app alembic
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

### Frontend
```bash
cd frontend
npm run lint
npm test
npm run build
```

### E2E / Blackbox (`test/`)
首次安装（只需一次）：
```powershell
cd test
npm install
npm run install:browsers
```

运行全套：
```powershell
cd test
npm test
```

UI 变更后更新截图基线：
```powershell
cd test
npx playwright test --update-snapshots
```

当 Alembic 迁移或模型字段有意变更（DB schema 变更）：
```powershell
pwsh test/scripts/snapshot-db.ps1
```

### E2E 编写规则（摘要）
- UI spec 从 `test/lib/ui-test` 导入（默认外网阻断）；选择器优先 `getByRole/getByLabel` 且 `exact: true`。
- 不要改业务代码做“测试专用逻辑”；优先黑盒 API/页面流程。
- 不要真实调用 LLM：统一走 Mock LLM（见 `test/README.md`、`test/ADDING_TESTS.md`）。

## MCP tools
- 以 `docs/mcp-tools.md` 为准（当前启用：`context7`、`chrome-devtools`）。
- 单轮对话最多调用 2 个 MCP 工具；失败要降级并记录（写进 CSV 的 `Notes` 或交接输出）。

## Output style (for agent replies)
- 默认中文；简洁、结构化。
- 修改文件时给出 `path:line` 引用。
- 非平凡改动必须写：风险 + 下一步建议。
