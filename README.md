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
# Windows:
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --workers 1 --port 8000
# macOS/Linux:
./.venv/bin/python -m uvicorn app.main:app --reload --workers 1 --port 8000

# 批量生成（P1-04）：任务队列 worker（RQ + Redis）
# 1) 先启动 Redis（任选其一）：
#   - Docker: docker run --name ainovel-redis -p 6379:6379 redis:7-alpine
#   - 或 WSL / 本机 Redis 服务
# 2) 启动 worker（Windows / PowerShell）：
.\.venv\Scripts\python.exe scripts\run_rq_worker.py
# 或：.\.venv\Scripts\rq.exe worker --url $env:REDIS_URL default
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

## LLM 流式输出与请求格式

- 后端 SSE 流式输出已覆盖：`openai/openai_compatible/openai_responses/openai_responses_compatible/anthropic/gemini`
- OpenAI Chat Completions：可在「模型配置」的 `extra（JSON）` 中传 `response_format` / `reasoning_effort` / `max_completion_tokens` 等（不需要的参数会自动丢弃/降级）
- OpenAI Responses API：选择 provider `openai_responses`（或 `openai_responses_compatible`），结构化输出可通过 `extra.text` / `extra.text_format` 配置
- Claude（Anthropic）思考预算：可在 `extra.thinking` 配置；如需 Beta 特性可在 `extra.anthropic_beta` 传 header 值
- Gemini 思考预算：可在 `extra.thinkingConfig` 配置（透传到 `generationConfig.thinkingConfig`）

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

## 环境变量（后端）

见 `backend/.env.example`：
- `DATABASE_URL`：默认 `sqlite:///./ainovel.db`（SQLite 相对路径会按 `backend/` 目录解析，避免因工作目录不同导致读错库）
- `CORS_ORIGINS`：默认 `http://localhost:5173`
- `LOG_LEVEL`：默认 `INFO`
- `APP_ENV`：`dev|prod`
- `SECRET_ENCRYPTION_KEY`：prod 必填（用于可迁移的 `enc:` 加密）。升级旧数据库时可先运行 `backend/scripts/migrate_llm_profile_secrets.py` 迁移历史 API Key。

## SQLite 约束（MVP 口径）

- SQLite 模式仅支持 **单 worker**（例如 `uvicorn ... --workers 1`）
- 任何 LLM 调用不得持有长事务：调用上游前结束事务，返回后再开启事务落库
