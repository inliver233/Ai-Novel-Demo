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

copy .env.example .env  # Windows 可用；或手动创建
# 可选：应用启动时会自动执行 `alembic upgrade head`；如需手动迁移可执行：
# alembic upgrade head

# SQLite 模式：必须单进程/单 worker
uvicorn app.main:app --reload --workers 1 --port 8000
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

## 工程卫生（必须）

- **不要提交运行/构建产物**：例如 `backend/.env`、`backend/*.db`、`frontend/dist`、`frontend/node_modules`、`demo/**/__pycache__` 等（已由根 `.gitignore` 统一忽略）。
- **安全红线**：任何日志/错误/调试信息不得输出明文 API Key（响应/导出/控制台也不允许；仅允许 `has_api_key/masked_api_key`）。

## 验证清单（DoD）

前端：

```bash
cd frontend
npm run lint
npm run build
```

后端：

```bash
python -m compileall -q backend\\app backend\\alembic
```

手工闭环：

- 按 `mvp开发计划.md` 第 11 节演示脚本跑通（LLM 步骤需要真实 Key）

## 环境变量（后端）

见 `backend/.env.example`：
- `DATABASE_URL`：默认 `sqlite:///./ainovel.db`
- `CORS_ORIGINS`：默认 `http://localhost:5173`
- `LOG_LEVEL`：默认 `INFO`
- `APP_ENV`：`dev|prod`

## SQLite 约束（MVP 口径）

- SQLite 模式仅支持 **单 worker**（例如 `uvicorn ... --workers 1`）
- 任何 LLM 调用不得持有长事务：调用上游前结束事务，返回后再开启事务落库
