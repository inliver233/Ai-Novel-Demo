# ainovel MVP（Atelier）

本仓库按 `mvp开发计划.md`（v2.4）实现 ainovel MVP：前端（React+TS+Vite+Tailwind）+ 后端（FastAPI）+ SQLite/Alembic + 多 Provider LLM 适配 + Markdown 导出。

## 本地启动（开发）

### 1) 后端（FastAPI）

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
# 可选（推荐）：使用锁定依赖（可复现）：
# python -m pip install -r requirements.lock.txt

copy .env.example .env  # Windows 可用；或手动创建
# 可选：应用启动时会自动执行 `alembic upgrade head`；如需手动迁移可执行：
# alembic upgrade head
# 注意（`APP_ENV=prod`）：若检测到 legacy SQLite 且缺少 `alembic_version`，启动时不会自动 `stamp`，并会直接失败；
# 请先备份 DB，再手动执行迁移（`alembic stamp ...` / `alembic upgrade head`）。

# SQLite 模式：必须单进程/单 worker
# 建议直接用 venv python 启动（避免误用系统 python 导致依赖错位）
# 注意：`--reload` 与多 worker 不兼容；请不要使用 `--reload --workers 10` 这类组合（不会按预期并发）。
# 如需多 worker/高并发：请使用 Docker Compose（Postgres + Redis + rq_worker）部署形态。
# Windows:
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --workers 1 --port 8000
# macOS/Linux:
./.venv/bin/python -m uvicorn app.main:app --reload --workers 1 --port 8000

# 后台任务队列（RAG/世界书/搜索/批量生成等）
# - dev/test（推荐）：TASK_QUEUE_BACKEND=inline（不依赖 Redis；进程内线程 worker；可用 INLINE_WORKER_CONCURRENCY 调整并发）
# - rq 模式（生产必须）：需要 Redis + worker
# 1) 先启动 Redis（任选其一）：
#   - Docker: docker run --name ainovel-redis -p 6379:6379 redis:7-alpine
#   - 或 WSL / 本机 Redis 服务
# 2) 启动 worker（Windows / PowerShell）：
.\.venv\Scripts\python.exe scripts\run_rq_worker.py
# 或：.\.venv\Scripts\rq.exe worker --url $env:REDIS_URL default
# 提示：如果 Redis 可用但没启动 worker，任务会一直排队；可用 `/api/health` 查看 `rq_worker_count/queue_size` 来排障。
```

### 2) 前端（Vite）

```bash
cd frontend
npm install
npm run dev
```

默认访问：
- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`（API base：`/api`）

## Docker Compose（部署/一键启动）

> 目标：给出一个“可启动、可观测、可回滚”的最小部署形态（frontend/backend/postgres/redis/worker）。

生产部署前建议先过一遍安全清单：`docs/deployment/security-checklist.md`。

### 1) 修改 Compose（可选）

默认不改也能启动；对外部署建议至少修改 `docker-compose.yml` 里的：
- `FRONTEND_PORT` / `BACKEND_PORT`（端口映射）
- `AUTH_ADMIN_USER_ID` / `AUTH_ADMIN_PASSWORD`（管理员账号密码；默认 `admin` / `ChangeMe123!`，上线前务必修改）
- （可选）LinuxDo OIDC：`LINUXDO_OIDC_CLIENT_ID` / `LINUXDO_OIDC_CLIENT_SECRET` / `LINUXDO_OIDC_REDIRECT_URI`

说明：
- Docker Compose 形态默认使用 `Postgres + Redis + rq_worker`，用于承载三位数并发的基础需求；SQLite 仅建议本地单机调试。
- Compose 的 Postgres 镜像默认包含 `pgvector` 扩展（用于 `vector_chunks` 向量索引表）。如果你改用外部/自建 Postgres：
  - 推荐安装并允许 `CREATE EXTENSION vector`；
  - 或将 `VECTOR_BACKEND=chroma`（继续使用 `/data/chroma`），系统会自动降级跳过 pgvector 表。
- `SECRET_ENCRYPTION_KEY` 可留空：容器启动时会自动生成并持久化到 `app_data` 卷（不会输出明文）。

（推荐）也可使用 env-file 覆盖变量：

```bash
cp .env.docker.example .env.docker
# 然后编辑 .env.docker（不要提交到 git）
docker compose --env-file .env.docker up -d --build
```

注意（Postgres 密码包含特殊字符时）：
- `DATABASE_URL` 里的密码必须做 URL 编码（例如 `@` 需要写成 `%40`），否则会导致连接串解析错误。
- 最简单的做法：给 `POSTGRES_PASSWORD` 选一个只包含字母/数字的密码；或按下方方式编码。

```bash
python3 - <<'PY'
import urllib.parse
pwd = "YourPostgresPasswordHere"
print(urllib.parse.quote(pwd, safe=""))
PY
```

### 2) 启动

```bash
docker compose up -d --build
```

访问：
- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`（也可通过前端同域代理：`/api`）

### 3) 日志与排障（含 request_id）

```bash
docker compose logs -f backend
docker compose logs -f rq_worker
```

后端日志为 JSON 行，包含 `request_id`，可用于前后端/网关联动定位。

### 4) 回滚/重置策略（明确）

- 回滚代码：切回旧 commit 后执行 `docker compose up --build -d`（默认保留 `postgres_data` 卷，不丢数据）。
- 重置数据：`docker compose down -v`（会删除 `postgres_data`/`app_data` 卷，**不可恢复**）。
- 数据卷：
  - Postgres：`postgres_data`
  - 应用数据（向量库 + 服务端密钥）：`app_data`（挂载到 `/data`；包含 `/data/chroma` 与 `/data/secrets`）

### 5) Ubuntu 云服务器（从 git clone 到可访问）

以下步骤适用于“只想尽快跑起来”的部署方式（HTTP + 端口访问）。如果你要用 LinuxDo OIDC，建议配 HTTPS（见下方）。

1) 安装 Docker + Compose（Ubuntu）

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
```

2) 拉代码并切到 `test` 分支（部署用）

```bash
git clone <YOUR_REPO_URL>.git
cd Ai-Novel-Demo
git checkout test
```

3) 创建部署用 env 文件并修改关键项

```bash
cp .env.docker.example .env.docker
nano .env.docker
```

至少建议修改（不要把真实值提交到 git）：
- `AUTH_ADMIN_USER_ID` / `AUTH_ADMIN_PASSWORD`：管理员账号密码（只在“首次初始化空 DB”时写入；改了 env 不会自动重置旧密码，想重置可用全新部署时 `docker compose down -v`）。
- `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `DATABASE_URL`：数据库配置（`POSTGRES_DB` 是库名，不是密码）。
- （可选）`FRONTEND_PORT` / `BACKEND_PORT`：外网访问端口（默认 `5173/8000`）。
- （可选）LinuxDo：`LINUXDO_OIDC_CLIENT_ID` / `LINUXDO_OIDC_CLIENT_SECRET` / `LINUXDO_OIDC_REDIRECT_URI`。

4) 启动

```bash
docker compose --env-file .env.docker up -d --build
docker compose ps
docker compose logs -f backend
```

5) UFW 放行端口（示例：保留 SSH + 开前端端口）

```bash
sudo ufw allow OpenSSH
sudo ufw allow 5173/tcp
# 如需直连后端（可选）：sudo ufw allow 8000/tcp
sudo ufw enable
sudo ufw status
```

6) LinuxDo OIDC（可选）

- 回调地址（redirect uri）推荐填写：`https://<你的域名>/api/auth/oidc/linuxdo/callback`
- 如果你暂时没有 HTTPS，可先不启用 LinuxDo（前端按钮仍会显示；未配置时点击会给出提示）。

7) 迁移失败如何恢复（新部署）

- 观察到后端/worker 反复重启、日志提示迁移失败时：通常是“首次初始化中断”导致。
- 如果是新部署且允许清空数据，最快的恢复方式：

```bash
docker compose down -v
docker compose --env-file .env.docker up -d --build
```

## LLM 流式输出与请求格式

- 后端 SSE 流式输出已覆盖：`openai/openai_compatible/openai_responses/openai_responses_compatible/anthropic/gemini`
- OpenAI Chat Completions：可在「模型配置」的 `extra（JSON）` 中传 `response_format` / `reasoning_effort` / `max_completion_tokens` 等（不需要的参数会自动丢弃/降级）
- OpenAI Responses API：选择 provider `openai_responses`（或 `openai_responses_compatible`），结构化输出可通过 `extra.text` / `extra.text_format` 配置
- Claude（Anthropic）思考预算：可在 `extra.thinking` 配置；如需 Beta 特性可在 `extra.anthropic_beta` 传 header 值
- Gemini 思考预算：可在 `extra.thinkingConfig` 配置（透传到 `generationConfig.thinkingConfig`）
- 如访问上游需要代理：默认后端 `httpx` 不读取系统代理环境变量（避免意外走代理）；可设置 `LLM_HTTP_TRUST_ENV=true` 启用 `HTTP_PROXY/HTTPS_PROXY`，或设置 `LLM_HTTP_PROXY=http://127.0.0.1:PORT` 显式指定代理。

## 长期记忆（LMEM）/记忆注入（memory injection）

- 预览：写作页的 Context Preview 会调用 `/api/projects/{project_id}/memory/retrieve` 返回 MemoryContextPack（worldbook/story_memory/structured/vector_rag/graph_context/fractal）。
- 开关：生成章节时会把 `memory_injection_enabled` 随请求发送到后端；后端会在生成前将 pack 注入到 `render_values.memory`。
- Prompt 注入：推荐使用内置章节预设 `chapter_generate_v4`（包含 `sys.memory.*` blocks，marker_key=`memory.<section>.text_md`）；旧的 `chapter_generate_v3` 不包含 memory blocks。
- 回放/定位：`generation_runs.params_json` 会记录 `memory_injection_enabled` 与 `memory_retrieval_log_json`。
- 向量检索：Embedding/Rerank 配置可通过「项目设置」写入 DB（API Key 加密，仅返回 `has_api_key/masked_api_key`），或通过后端 env fallback（见 `backend/.env.example`）；配置与自检步骤见 `docs/rag-embedding-rerank.md`。

## 工程卫生（必须）

- **不要提交运行/构建产物**：例如 `backend/.env`、`backend/*.db`、`frontend/dist`、`frontend/node_modules`、`demo/**/__pycache__` 等（已由根 `.gitignore` 统一忽略）。
- **安全红线**：任何日志/错误/调试信息不得输出明文 API Key（响应/导出/控制台也不允许；仅允许 `has_api_key/masked_api_key`）。
- **后端命令一律使用 venv python**：Windows 用 `backend\\.venv\\Scripts\\python.exe`（不要用系统 python，避免出现“装了依赖但 uvicorn 缺包/版本错位”的坑）。
- **Prompt 模板安全**：Prompt Studio 的模板渲染使用“安全子集”（不执行 Jinja2）。仅支持：
  - 变量：`{{var}}` / `{{a.b}}`（仅 dict/list 路径；拒绝 `__xxx__` 等危险段）
  - 条件：`{% if ... %}{% else %}{% endif %}`（表达式仅允许 `and/or/not/in/==/!=` + 字符串字面量 + 变量路径）
  - 宏：`{{date}}/{{time}}/{{isodate}}/{{random::...}}/{{pick::...}}/{{// comment}}`
  - 默认内置模板资源：`backend/app/resources/prompt_presets/*`（每个目录：`preset.json` + `templates/*.md`；`backend/app/services/prompt_presets.py` 只做加载/ensure/渲染，不再内嵌超大模板常量）
  - 升级策略：新增默认模板版本时，新建一个资源目录（例如 `chapter_generate_v4`）并更新默认 preset 名称；默认不会覆盖用户在 Prompt Studio 的自定义修改

## UI/UX 规范（必须）

- 统一设计语言见 `ui设计规范.md`（含颜色/排版/组件/动效 Token）。
- 新增页面/组件时，要求所有可交互元素具备 `Hover/Focus/Active/Disabled` 状态，并遵循统一的 `Cubic Bezier + 150/250/350ms` 动效窗口。
- UI 文案新增规则：新增文案优先收口到 `frontend/src/lib/uiCopy.ts`（或按模块拆分的 `*Copy.ts`），避免散落在组件内导致混杂语言与回归困难。

## 验证清单（DoD）

前端：

```bash
cd frontend
npm run lint
npm test
npm run build
```

后端：

```bash
cd backend
.\.venv\Scripts\python.exe -m compileall -q app alembic
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

手工闭环：

- 按 `mvp开发计划.md` 第 11 节演示脚本跑通（LLM 步骤需要真实 Key）

## E2E 默认账号 & dev_fallback（DEV only）

- Playwright E2E（`pwsh test/run-all.ps1`）会以 `AUTH_ADMIN_USER_ID=admin` / `AUTH_ADMIN_PASSWORD=admin-pass` 启动后端并用于 UI 测试登录。
- 仓库自带 `backend/.env` 默认也使用 `AUTH_ADMIN_PASSWORD=admin-pass`（长度 ≥ 8），按本文档启动后端即可直接登录。
- 如在 `backend/.env` 配置 `AUTH_ADMIN_PASSWORD`，需至少 8 位；开发环境下若配置过短会跳过 admin bootstrap 并输出 warning（避免启动失败）。
- 前端 E2E 会设置 `VITE_DEV_FALLBACK_ENABLED=true` 以覆盖 dev_fallback 路径；生产环境务必保持禁用并确保 `APP_ENV=prod`（避免鉴权绕过风险）。

## 仓库卫生与本地配置

- 本地配置文件只保留 `*.example` 进版本库；实际运行时请复制 `backend/.env.example -> backend/.env`、`frontend/.env.example -> frontend/.env`、`.env.docker.example -> .env.docker`，并保持这些本地文件不提交到 Git。
- 允许本地生成但禁止提交的运行/测试产物包括：`*.db`、`*.db-wal`、`*.db-shm`、`tmp_*`、`.tmp_*`、`test/.artifacts/`、`test/.tmp/`、临时截图、`*.log` / `*.err.log` / `*.out.log` 等调试日志。
- 如本地已有被误跟踪的配置文件，使用 `git rm --cached <path>` 停止跟踪即可；例如本仓库应确保 `backend/.env` 仅作为本地文件存在。
- 安全红线不变：任何日志、报错、导出与调试输出都不得包含明文 secrets；接口与日志面只允许 `has_api_key` / `masked_api_key`。

### 仓库 guard（Wave A）

- 查看当前 guard：`cd backend && .\.venv\Scripts\python.exe ..\scripts\guards\run.py --list`
- 运行仓库卫生 guard：`cd backend && .\.venv\Scripts\python.exe ..\scripts\guards\run.py no-secrets-in-repo db-artifacts-guard`
- 说明：guard 会检查 Git 已跟踪文件 + 未忽略的新文件，优先在提交前挡住敏感文件、数据库产物、测试产物和临时截图/日志。

### backend 质量入口（Wave A）

- 安装 dev 检查依赖：`cd backend && .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`
- 一键运行 backend 基线：`cd backend && .\.venv\Scripts\python.exe scripts\run_quality_gate.py`
- 当前基线包含：`compileall`、`ruff check`、`scripts/guards/run.py`
- 当前 guard 集合：`no-secrets-in-repo`、`db-artifacts-guard`、`deployment-security-guard`、`backend-no-print-guard`、`no-direct-llm-call-in-api`、`file-line-count-guard`、`prompt-preset-integrity-guard`
- 项目级分层门禁：`python scripts/run_gate.py --layer smoke|contract|critical|full`
- 项目级回归 runner：`python scripts/run_regression.py --profile prepush|release|full`
- 矩阵/重跑说明：见 `docs/testing-matrix.md` 与 `docs/testing-gates.md`
- 说明：`file-line-count-guard` 与 `no-direct-llm-call-in-api` 当前采用 audit-first 策略，先以 warning 暴露历史热点，避免第一版直接把老仓库卡死。

## 环境变量（后端）

见 `backend/.env.example`：
- `DATABASE_URL`：默认 `sqlite:///./ainovel.db`（SQLite 相对路径会按 `backend/` 目录解析，避免因工作目录不同导致读错库）
- `CORS_ORIGINS`：默认 `http://localhost:5173`
- `LOG_LEVEL`：默认 `INFO`
- `APP_ENV`：`dev|test|prod`
- `AUTH_DEV_FALLBACK_USER_ID`：仅 `APP_ENV=dev` 生效（dev 免登录本地用户）。生产环境务必 `APP_ENV=prod`，并建议将该值置空/不设置；若生产误以 `APP_ENV=dev` 启动会造成鉴权绕过（high）。
- `SECRET_ENCRYPTION_KEY`：prod 必填（用于可迁移的 `enc:` 加密）。升级旧数据库时可先运行 `backend/scripts/migrate_llm_profile_secrets.py` 迁移历史 API Key。

## 章节 API（Wave A）

- 兼容旧接口：`GET /api/projects/{project_id}/chapters` 仍返回完整章节对象（含 `plan` / `summary` / `content_md`），用于兼容窗口内的旧调用方。
- 新列表合同：`GET /api/projects/{project_id}/chapters/meta?limit=<n>&cursor=<last_number>` 返回轻量 `ChapterListItem`，只包含章节元数据与 `has_plan` / `has_summary` / `has_content` 标记，不再返回全文内容。
- 详情合同：`GET /api/chapters/{chapter_id}` 返回单章完整 `ChapterDetail`；Preview / Reader / Writing 等读路径应优先使用 “meta 列表 + detail 按需读取”。
- cursor 说明：`cursor` 取上一页最后一章的 `number`，服务端按 `number > cursor` 继续返回后续章节；返回值包含 `next_cursor`、`has_more`、`returned`、`total`。
- 后续迁移建议：Wave A 先迁移 Preview / Reader / Writing / Wizard / Foreshadows 的列表读路径；更完整的数据层缓存与失效策略留给 `T05/T06`。

## Chapter frontend data layer (Wave B)
- `frontend/src/services/chaptersApi.ts` remains the transport layer and should not grow page-level cache semantics.
- `frontend/src/services/chapterStore.ts` owns project-scoped chapter `meta/detail` caching, invalidation, neighbor-detail prefetch, and cross-page sharing.
- List/navigation views should read `ChapterListItem` from `/chapters/meta`; full content (`content_md`, `summary`, `plan`) should be loaded on demand via `ChapterDetail` from `/api/chapters/{chapter_id}`.
- Any mutation that changes the chapter set (`create / update / delete / bulk_create / outline switch`) should go through `chapterStore` or trigger explicit invalidation instead of syncing from the legacy full-list endpoint.
- `Writing / Preview / Reader` now use `frontend/src/components/writing/ChapterVirtualList.tsx` for windowed rendering; new directory/list features should reuse it instead of falling back to full DOM rendering.

## SQLite 约束（MVP 口径）

- SQLite 模式仅支持 **单 worker**（例如 `uvicorn ... --workers 1`）
- 任何 LLM 调用不得持有长事务：调用上游前结束事务，返回后再开启事务落库
