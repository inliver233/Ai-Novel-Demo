# ainovel 全自动测试（E2E/契约/DB）

这个 `test/` 目录是一套**独立于前后端实现细节**的黑盒测试系统：自动拉起前端 + 后端 + Mock LLM，然后跑 UI 跳转/按钮/流式生成、API 返回格式、DB Schema 回归等测试，尽量做到“更新完功能 → 一键跑全套 → 有问题立刻定位”。

## 覆盖范围（当前已落地）

- **UI Smoke**：核心页面能打开、路由能跳转、关键按钮可见
- **流式生成**：
  - 大纲：`/outline/generate-stream`（前端 SSE）+ 后端对 OpenAI-compatible 流式转发 + 解析/预览/应用
  - 章节：`/chapters/{id}/generate-stream`（逐块渲染 + marker 解析）
- **Visual Regression（截图回归）**：Dashboard / Outline / Writing（空编辑态）
- **API Smoke**：`/api/health`、projects/settings/characters/export 等基础闭环
- **DB Schema 回归**：SQLite schema 与 `test/contracts/db_schema.json` 基线一致（检测迁移/字段变更）

> 注意：流式生成默认走本地 Mock（不会调用真实 LLM），不需要真实 Key。

## 前置条件（必看）

- Node.js（建议 >= 18）
- 后端：已按仓库根 README 完成初始化，确保存在 `backend/.venv`（`globalSetup` 会直接使用 `backend/.venv/.../python` 启动后端）
- 前端：已安装依赖（`globalSetup` 会在 `frontend/` 下执行 `npm run dev`）

## 一键运行

首次安装（只需一次）：

```powershell
cd test
npm install
npm run install:browsers
```

运行全套 E2E（会自动启动/关闭：Mock LLM + 后端 + 前端）：

```powershell
cd test
npm test
```

打开 Playwright 报告：

```powershell
cd test
npm run report
```

## 运行机制（你不需要手工启动服务）

Playwright `globalSetup/globalTeardown` 会做这些事：

1. 启动本地 **Mock LLM**（OpenAI-compatible）：`http://127.0.0.1:4010/v1`
2. 使用隔离 DB 启动后端（FastAPI）：`http://127.0.0.1:8000`
   - DB：`backend/.tmp_test/ainovel.e2e.db`
   - `TASK_QUEUE_BACKEND=inline`（不依赖 Redis）
3. 启动前端（Vite）：`http://127.0.0.1:5173`
4. 测试产物输出到：`test/.artifacts/`

## 默认测试账号（E2E）

Playwright `globalSetup` 会用以下默认账号启动后端并用于 UI 测试登录：

- 用户名：`admin`
- 密码：`admin-pass`

同时前端会设置 `VITE_DEV_FALLBACK_ENABLED=true`（仅 DEV；生产环境不得开启 dev_fallback）。

端口占用处理：

- `globalSetup` 会先尝试杀掉上一轮残留的 E2E 进程（读取 `test/.tmp/state.json` 的 pids），然后重试端口检查。
- Mock LLM 端口（默认 `4010`）如果被占用，会自动选择一个空闲端口并继续（控制台会提示如何用 `E2E_MOCK_PORT` 固定）。
- 后端/前端端口（默认 `8000/5173`）若仍被其它程序占用，会给出清晰的 env 覆盖提示。

如需自定义端口（例如本机已占用 8000/5173），可在运行前设置环境变量：

```powershell
$env:E2E_BACKEND_URL="http://127.0.0.1:18000"
$env:E2E_FRONTEND_URL="http://127.0.0.1:5174"
$env:E2E_MOCK_PORT="4010"
npm test
```

## 回归截图（Visual Regression）

首次或 UI 变更后，更新截图基线：

```powershell
cd test
npx playwright test --update-snapshots
```

截图基线位置：`test/specs/ui/visual.spec.ts-snapshots/`

如截图偶发不稳定（flaky），优先按以下顺序处理：

- 改为**组件/容器级**截图（避免 fullPage 高度变化/滚动抖动）
- `mask` 掉动态区域（时间戳、随机列表、动画 Loading 等）
- 必要时在测试侧注入 CSS 固定字体/禁用动画（不要改业务代码）

## DB Schema 基线（重要）

当你修改了 Alembic 迁移或模型字段（属于“有意 schema 变更”）：

```powershell
pwsh test/scripts/snapshot-db.ps1
```

它会生成/更新：`test/contracts/db_schema.json`。

## 如何定位失败（给人/AI 都够用）

失败时优先看：

- `test/.artifacts/playwright-report/`（HTML 报告）
- `test/.artifacts/test-results/**/trace.zip`（带时间轴的可视化复现）
- `test/.artifacts/backend.log` / `test/.artifacts/frontend.log` / `test/.artifacts/mock-llm.log`

建议把以下内容贴给 AI（或自己排查）：

1. 失败用例名（Playwright 输出里有）
2. 对应的 `trace.zip` 路径
3. `backend.log` 中同一时间段的报错（后端会带 `X-Request-Id`）

## 开发规则（新增测试时必须遵守）

- 不要改业务代码做测试专用逻辑；优先使用可访问性选择器：`getByRole/getByLabel/getByText`
- 选择器要尽量 **exact**：避免中文按钮名被“包含匹配”导致 strict mode 报错
- UI tests 默认开启**外网阻断**：任何非 `127.0.0.1/localhost` 的浏览器请求会直接 fail-fast（UI spec 需从 `test/lib/ui-test.ts` 导入）
- UI 测试尽量走真实页面流程；数据准备尽量走 API（黑盒）
- 不要在本地真实调用 LLM：统一走 Mock LLM（避免 Key/网络/费用/不稳定）
- 任何新功能都应补至少一个：
  - **API 契约断言**（字段/状态码/错误码），或
  - **UI 闭环用例**（按钮 → 请求 → 渲染/状态）
