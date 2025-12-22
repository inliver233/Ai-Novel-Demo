# ainovel MVP 最终改善文档（demo 代码体检 + 顶尖工程化整改清单）

> 适用范围：本仓库的 **`demo/`**（当前 MVP 可运行实现）。`mumu/` 仅作“可参考/可照抄”的对照学习材料，不作为主力实现与依赖。  
> 契约基线：**`demo/mvp开发计划.md` v2.4**（任何改变契约语义必须先 bump 文档版本并写变更说明）。  
> 本文目标：**先不做功能扩展**，只把现有 demo 的结构、代码质量、可维护性、可读性、模块化清晰度、工程化可靠性提升到“可与顶尖项目对标”的水准，并给出“下一位开发者可直接照单全改”的清单。

---

## 0. 阅读方式（强制）

1) 本文所有条目按严重级别分为 `P0/P1/P2`：  
   - `P0`：不改会导致 **明显 bug / 数据丢失 / 安全红线 / 无法维护 / 随时炸库或锁库 / 无法复现**。  
   - `P1`：强烈建议尽快改（可维护性/可读性/扩展性/一致性）。  
   - `P2`：优化与预留（MVP 之后也不晚，但现在改成本更低）。  
2) 文件级清单以 **当前仓库快照（2025-12-13）** 的行号为准；任何变更都会导致行号漂移：  
   - 执行整改时应以编辑器“跳转行号 + git blame/compare”为准重新校准。  
3) 目标不是“能跑”，而是：**能长期迭代、能交接、能定位问题、能扩到 Phase 2 而不推倒重来**。

---

## 1. 结论先行（现状总评）

### 1.1 已经做对了的（保留并固化为规范）

- 前后端契约基本对齐 `demo/mvp开发计划.md`：统一 `{ok,data|error,request_id}`（导出除外）、`X-Request-Id`、LLM Key 仅走 header、SQLite 单 worker 约束、生成不自动落库等。
- 后端已具备：项目/设定/角色/大纲/章节/Prompt/LLM preset/生成记录/导出 的 MVP 闭环能力。
- 前端已具备：7 页 + AppShell + 主题系统（Paper & Ink）+ 关键交互（dirty guard、Ctrl/Cmd+S、向导编排）。

### 1.2 目前最危险的坑（必须立即修到“稳”）

**Repo/工程卫生**
- ✅ 已新增根级 `.gitignore`，并从仓库移除 `demo/backend/.env`、`demo/backend/*.db`、`demo/backend/**/__pycache__` 等产物；本地可存在但必须严格禁止入库/交接。

**后端**
- ✅ 已修复：`demo/backend/app/main.py` 未知异常不再返回 `DB_ERROR`，改为 `INTERNAL_ERROR`，且异常路径日志级别为 `error` 并避免输出敏感信息。  
- ✅ 已改进：`AppError` / `VALIDATION_ERROR` 发生时，后端 JSON 日志会记录 `error_code/message/details(白名单)` 便于用 `request_id` 精确定位（仍严格避免输出明文 API Key）。  
- LLM 相关路由（`outline.py`/`chapters.py`）重复大量逻辑，且存在明显的“代码洁净度问题”（重复 import、无用 wrapper、locals hack、日志级别不当），长期会变成维护地狱。
- ✅ 已修复：数据库配置改为单一来源（统一使用 `settings.database_url`），避免环境切换时连错库。

**前端**
- ✅ 已修复：`PromptsPage.tsx` 占位符正则错误（`\s`）导致的模板预览/扫描失效问题。  
- ✅ 已修复：`npm run lint` 0 error（拆分 Confirm/Toast/ProjectsContext 的 hook 导出；修复 `apiClient` 正则与导出文件名解析）。  
- ✅ 已引入 `prettier` 并提供 `npm run format`/`format:check`，作为统一格式化入口（避免尾部空行/缩进继续污染）。
- ✅ 已改进：项目各核心页面新增统一“向导进度/下一步”Dock（`WizardNextBar` + `useWizardProgress`），按 `mvp开发计划.md` 第 11 节脚本实现连续导航（纯前端编排，不新增后端 wizard 持久化）。
- ✅ 已修复：Prompts `timeout_seconds` 口径（最大 1800/30分钟，默认 90 秒）——保存预设/测试连接均自动 clamp 到 1800；后端校验对齐，不再因超上限触发 400（VALIDATION_ERROR）。

---

## 2. 项目基调（必须写死并执行）

### 2.1 文档优先级（不可争论）

1. `demo/mvp开发计划.md`：**唯一契约/验收口径**  
2. `demo/ui设计规范.md`：UI/主题实现参考  
3. `mvp最终改善文档.md`（本文）：工程质量与重构整改清单  
4. `mvp改进建议.md`：阶段性问题记录（可能过期，需以代码为准）  
5. `demo/ainovel开发计划_v2.md`、`更进一步实现.md`：灵感参考（不能推着 MVP 扩 scope）

### 2.2 “顶尖项目”质量门槛（DoD）

以下条目必须作为“每次改动的完成定义（Definition of Done）”：

- 前端：`npm run lint` 必须为 0 error（允许临时 warning，但需有明确计划消灭）。  
- 前端：`npm run build` 必须通过（当前已通过，但需要保持）。  
- 后端：`python -m compileall -q demo/backend/app demo/backend/alembic` 必须通过（当前已通过，但需要保持）。  
- 闭环手工验收：按 `demo/mvp开发计划.md` 第 11 节演示脚本从 UI 端到端跑通（LLM 需真实 Key）。  
- 安全红线：任何日志/错误/页面 Debug 信息 **不得输出明文 API Key**（包括 query string、header dump、异常堆栈中的敏感片段）。

### 2.3 统一工程规范（建议一次性落地）

> 本节只规定“工程化基线”，不涉及新增业务功能。

**仓库**
- 建议新增根级 `README.md`（或补充现有）明确：`demo/` 是主项目；`mumu/` 是参考；如何启动、如何验证、如何跑 lint/build/compile。
- 建议新增根级 `.gitignore`（即使暂时不用 git，也要按 git 工程标准管理目录卫生），覆盖：`.venv/ node_modules/ dist/ *.db __pycache__/ *.pyc` 等。

**后端（Python）**
- 建议引入 `ruff`（lint+format）与 `mypy`（逐步类型化），并在 CI/本地 pre-commit 中强制执行。  
- 建议引入 `pytest` 做最小 API 冒烟（health、projects CRUD、bulk_create replace、导出返回 markdown/错误格式）。

**前端（React/TS）**
- 建议引入 `prettier` 并与 eslint 集成（解决缩进/尾部空行/引号风格混乱），统一为一次性格式化（pre-commit 或 `npm run format`）。  
- 约定：页面只做“组合”，复杂逻辑下沉到 `hooks/`、`services/`、`components/`（写作页/Prompts 页必须拆）。

---

## 3. 与 mumu 对照：可直接借鉴/照抄的工程化点（精选）

> 仅列“对 demo 的工程质量最有价值”的点；不要求按 mumu 的业务复杂度上齐。

### 3.1 LLM 客户端池与超时拆分（性能与稳定性）

- 参考：`mumu/MuMuAINovel/backend/app/services/ai_service.py`  
  - 其做法：按 `(provider, base_url, api_key hash)` 复用 `httpx.AsyncClient`，统一 timeout/limits，避免每次请求新建 client。  
  - demo 当前：`demo/backend/app/llm/client.py` 每次 `with httpx.Client(...) as client:` 新建连接，后续并发或频繁调用会更慢且更难控。

### 3.2 Request ID 的日志上下文注入

- 参考：`mumu/MuMuAINovel/backend/app/middleware/request_id.py`  
  - 其做法：通过 logging.Filter 把 `request_id` 注入所有日志记录。  
  - demo 当前：使用 `contextvars`（也是正确路线），但需要进一步把“所有日志都带 request_id”变成硬规范，并保证错误日志级别正确。

### 3.3 SSE 工具链（Phase 2 预留）

- 参考：`mumu/MuMuAINovel/backend/app/utils/sse_response.py`  
  - demo 的 `更进一步实现.md` 已明确 SSE 是 Phase 2 的 P0；现在只需把 demo 的 LLM 层/路由层抽象好，避免未来接 SSE 时大拆。

---

## 4. 全局整改清单（按优先级）

### 4.1 P0（必须立刻做，先让工程“可控”）

- [x] 让 `demo/frontend` 的 `npm run lint` 变成 0 error（见第 5.2 节对应项）。  
- [x] 修复 `PromptsPage.tsx` 占位符正则（模板预览/占位符扫描恢复）。  
- [x] 后端修正“兜底异常码”与日志级别（避免误导排错）。  
- [x] 统一配置读取来源（`DATABASE_URL` 只允许从 `settings` 读取，避免双源）。  
- [x] 建立“构建产物不进仓库”的硬规则（新增根 `.gitignore`，并清理 `.env/*.db/__pycache__` 等产物）。

### 4.2 P1（强烈建议）

- [x] 后端：抽取 `outline_generate` 与 `chapter_generate` 的共享逻辑到 `services/`（已落地 `generation_service.py`，统一 LLM 调用/日志/生成记录写入）。  
- [x] 前端：拆分 `WritingPage.tsx`、`PromptsPage.tsx`（已拆出 `components/writing/*`、`components/prompts/*`，显著降低改动风险）。  
- [x] 前端：统一数据加载模式（新增 `src/hooks/useProjectData.ts`，并在 Settings/Characters/Outline/Writing/Wizard 等页复用），无需 `eslint-disable react-hooks/exhaustive-deps`。  

### 4.3 P2（优化/预留）

- 后端：LLM client 已改为可复用 client（线程本地 client + 连接池）；SSE/流式输出预留接口仍留待 Phase2。  
- 前端：按路由维度做 code-splitting（解决 `vite build` chunk > 500kb warning）。  

---

## 5. 文件级问题清单（逐文件、逐行）

> 说明：此处列的是“必须修改/建议修改”的点；若文件未列出问题并不等于完美，只代表未发现显著技术债。  
> 行号基于当前快照（2025-12-13），后续变更需重新校准。

### 5.0 仓库根目录 / 文档 / 配置（非业务代码，但决定可维护性）

#### 5.0.1 `demo/.gitignore`

- `P0`（已完成）：忽略规则方向正确；已新增根级 `.gitignore` 并上提关键规则（避免未来新增目录漏掉）。  
  - 已补齐 SQLite WAL/SHM 产物忽略（如 `*.db-wal/*.db-shm`、`*.sqlite*-wal/*.sqlite*-shm`），避免误入库/误打包。  
  - `mumu/` 仍建议保持“参考代码”定位，避免误打包/误发布（P1）。  

#### 5.0.2 `demo/backend/.env` / `demo/backend/.env.example`

- `P0`（已完成）：已移除 `demo/backend/.env`，仅保留 `demo/backend/.env.example` 作为模板（避免误提交真实 Key）。  
- `P1`（已完成）：已补充注释说明：SQLite 单 worker 约束、`CORS_ORIGINS` 逗号分隔规则等（对齐 `demo/mvp开发计划.md` 第 7/14 节）。  

#### 5.0.3 `demo/backend/*.db`（如 `ainovel.db`、`smoke_test.db`）

- `P0`（已完成）：已从仓库移除 `demo/backend/*.db`（运行产物），并由 `.gitignore` 统一禁止入库；按 `alembic upgrade head` 生成数据库。  

#### 5.0.4 `demo/backend/.venv`、`demo/frontend/node_modules`、`demo/frontend/dist`、`demo/**/__pycache__`、`demo/**/*.pyc`

- `P0`（已完成）：已新增根级 `.gitignore` 并清理 `demo/backend` 下的 `__pycache__` 等产物；其余本地环境/构建产物也必须严格禁止入库（参见 DoD：可复现/可交接）。  

#### 5.0.5 `demo/README.md`

- `P1`（已完成）：已补充“工程卫生/不要提交产物”声明，并把“验证命令”（lint/build/compileall/演示脚本）写成固定清单。  

#### 5.0.6 `demo/对话交接.md` / `demo/开发进度.md` / `mvp改进建议.md` / `更进一步实现.md`

- `P1`：这些文档很好用，但存在“随代码漂移”风险。建议：  
  - 任何“指出具体文件行号的问题”在代码修复后立即更新；  
  - `mvp改进建议.md` 更适合做“历史记录”，本文档（`mvp最终改善文档.md`）才是长期有效的整改清单与基调。  

### 5.1 后端（`demo/backend`）

#### 5.1.1 `demo/backend/app/main.py`

- `P0`（已完成）：异常路径日志级别已修正为 `"error"`，并补齐 `exception_type` 等字段。  
- `P0`（已完成）：兜底异常错误码不再复用 `DB_ERROR`，改为 `INTERNAL_ERROR`。  
- `P1`（已完成）：已移除 import-time side effects：不再在 import 时 `load_dotenv()`/`configure_logging()`，改为 FastAPI lifespan 启动时配置日志并初始化本地用户（`.env` 由 pydantic-settings 加载）。  
- `P1`（已完成）：已从 `@app.on_event("startup")` 迁移到 lifespan（兼容 FastAPI 新推荐方式）。

#### 5.1.2 `demo/backend/app/db/session.py`

- `P0`（已完成）：数据库配置已统一为单一来源（使用 `settings.database_url`）。  
- `P1`（已完成）：已在配置层增加 `settings.is_sqlite()` 并在 session 中使用（SQLite pragmas 判断单点化），避免后续支持 PostgreSQL 时逻辑分散。

#### 5.1.3 `demo/backend/app/core/logging.py` / `demo/backend/app/db/utils.py`

- `P1`（已完成）：时间函数已合并为单一来源（`log_event` 统一使用 `utc_now_iso()`），避免未来时间格式不一致。  
- `P1`（已完成）：`log_event` 的 `level` 已收敛为 `LogLevel = Literal["debug","info","warning","error"]`，避免随意传值。  
- `P0`（已完成）：已禁用 `httpx/httpcore` 的 request 日志（避免 Gemini 的 `?key=...` 出现在日志中，符合安全红线）。  

#### 5.1.4 `demo/backend/app/api/routes/outline.py`

- `P0`（已完成）：已清理重复/未使用 import（保持文件 import 洁净）。  
- `P1`（已完成）：已删除无意义 wrapper（仅转发函数）。  
- `P1`（已完成）：错误日志已统一为 `error` 级别（见 `generation_service.py`）。  
- `P1`（已完成）：已移除 locals hack（变量初始化与错误路径处理统一）。  
- `P1`（已完成）：已抽取共享生成链路到 `services/generation_service.py`（统一 LLM 调用/日志/写入 generation_runs）。  

#### 5.1.5 `demo/backend/app/api/routes/chapters.py`

- `P1`（已完成）：错误日志已统一为 `error` 级别（见 `generation_service.py`）。  
- `P1`（已完成）：已移除 locals hack。  
- `P1`（已完成）：生成链路已与 `outline.py` 抽共享 service（`generation_service.py`）。  
- `P2`：`ChapterGenerateContext.previous_chapter`（schema）为 `str|None`，但代码仅识别 `"summary"|"content"`；建议改为 Literal 并在请求层校验（避免脏值悄悄走“无注入”分支）。  

#### 5.1.6 `demo/backend/app/services/prompt_store.py`

- `P1`（已完成）：`ensure_prompt_templates` 已补齐 `db: Session` 类型注解，并在 docstring 中明确其会 `commit()`（事务边界清晰）。  

#### 5.1.7 `demo/backend/app/services/run_store.py`

- `P1`（已完成）：generation_runs 写入已封装为独立短事务（`with SessionLocal() as db:` + commit/rollback），并补齐“为何独立 session”的说明。  
- `P2`：后续若切 PostgreSQL/多 worker，应评估该模式与连接池/事务一致性。

#### 5.1.8 `demo/backend/app/llm/client.py`

- `P1`（已完成）：LLM 调用已改为可复用 client（线程本地 client + 连接池），并分离 connect/read/write/pool 超时。  
- `P1`（已完成）：`normalize_base_url` 已抽到 `app/llm/utils.py` 统一复用（`llm_preset.py` 与 `llm/client.py`）。  
- `P1`（已完成）：上游错误在 dev 环境的 `details` 中补充 `upstream_error`（已做 key 脱敏 + 截断），便于排查渠道侧报错。  
- `P0`（已完成）：`openai_compatible` 的参数白名单更保守（减少渠道侧 400），并避免发送空 `stop=[]`。  
- `P0`（已完成）：`openai_compatible` 若遇到上游 400/422，会按固定序列做“兼容性降级重试”（drop `stop/top_p/temperature`、clamp `max_tokens`、必要时合并 `system→user`），并在错误 `details.compat_adjustments` 中记录采取的动作（便于定位网关差异）。  
- `P0`（已完成）：OpenAI-like 响应解析更兼容：支持 `choices[0].message.content` 之外的常见返回（如 `choices[0].text`、Responses-like `output[].content[].text`），避免解析 KeyError 变成 500。  
- `P0`（已完成）：Key 脱敏规则增强：`sk-` token 支持包含 `_`/`-` 的网关 key（避免只脱敏前缀导致明文泄露）。  
- `P0`（已完成）：补齐脱敏兜底：对 `Bearer <token>` 与 `X-LLM-API-Key` 形式也做脱敏（避免上游错误体意外回显敏感信息）。  
- `P2`：为 SSE/流式输出预留：当前 `call_llm` 是一次性返回，未来接 SSE 会改动大，建议提前抽象 provider adapter 接口。

#### 5.1.9 `demo/backend/app/core/config.py`

- `P1`（已完成）：`app_env`/`log_level` 已收敛为受控类型并做 normalize+校验（避免拼错静默异常）。  
- `P1`（已完成）：配置保持单一来源（`db/session.py` 仅使用 `settings.database_url`）。  

#### 5.1.10 `demo/backend/app/core/errors.py`

- `P1`：错误码已具备基本结构，但需要在项目层面建立“错误码表”（对齐 `demo/mvp开发计划.md` 第 10.4）：  
  - 兜底错误码不得复用业务/DB 错误（见 `app/main.py`）。  

#### 5.1.11 `demo/backend/app/core/request_id.py`

- `P1`：`ContextVar` 方案是正确的；建议补齐规范：  
  - 任何 `log_event` 必须确保最终日志包含 `request_id`（当前依赖 `get_request_id()` 注入，后续新增 logger 时不要绕开）。  

#### 5.1.12 `demo/backend/app/api/deps.py`

- `P1`：L15 `LOCAL_USER_ID="local-user"` 属于 MVP 约束，应在一个“单点配置/常量模块”集中定义（避免前后端散落常量不一致）。  
- `P1`：`require_owned_*` 每次通过二次查询校验归属：MVP 可接受，但后续建议统一为 repository 层（或 join 查询）以减少重复与潜在 N+1。  

#### 5.1.13 `demo/backend/app/api/router.py`

- `P2`：建议为每个 router 增加 `prefix`（按资源分组）与 `response_model`，并把 tags 统一为面向用户的分组名（当前 tags 可用，但建议规范化命名）。  

#### 5.1.14 其它路由文件（`demo/backend/app/api/routes/*.py`）

- `P1`：通用整改（适用于 `projects/settings/characters/prompts/llm_preset/llm/generation_runs/export/health`）：  
  - 为每个 endpoint 补 `response_model`（可复用 `app/schemas/common.py` 的 `OkResponse/ErrorResponse`，或删除该文件避免“看起来要用但实际不用”的误导）。  
  - 所有 `return ok_payload(...)` 结构已统一，但建议统一返回类型声明（避免 `-> dict` 到处散落）。  
- `P1`：逐文件清单（未单独点名的，默认按“通用整改”处理）：  
  - `demo/backend/app/api/routes/health.py`：建议补 `response_model` 并作为 CI 的最小健康检查基准。  
  - `demo/backend/app/api/routes/projects.py`：建议补 `response_model`；`created_at` 若继续用字符串排序需保证格式永远是 ISO（或后端改 DateTime）。  
  - `demo/backend/app/api/routes/settings.py`：GET/PUT 的 upsert 逻辑可抽 helper（与 outline 的“单例资源”模式一致）。  
  - `demo/backend/app/api/routes/characters.py`：CRUD 已清晰；建议补 `response_model` 与一致的错误码注释。  
  - `demo/backend/app/api/routes/prompts.py`：默认模板 seed 逻辑可，但建议补 `response_model` 并统一“缺省模板版本策略”（未来模板变更如何迁移）。  
  - `demo/backend/app/api/routes/llm.py`：provider 的 base_url 默认值与 `llm_preset.py`/`llm/client.py` 有重复，建议统一来源。  
  - `demo/backend/app/api/routes/export.py`：见下方 `_as_bool` 改造建议；同时建议把导出文件名策略写成单测（中文文件名）。  
  - `demo/backend/app/api/routes/generation_runs.py`：见下方 JSON 解析去重建议；并建议增加分页/游标（P2）。  
  - `demo/backend/app/api/routes/outline.py` / `demo/backend/app/api/routes/chapters.py`：已在 5.1.4/5.1.5 单独列出。  
- `P1`：`demo/backend/app/api/routes/llm_preset.py`：  
  - L16-L23 `_normalize_base_url` 与 `app/llm/client.py` 重复（已完成：抽到 `app/llm/utils.py` 统一）。  
  - L59 `# type: ignore[arg-type]` 暴露类型不一致，应从 schema 层/模型层解决，而不是 ignore。  
- `P2`：`demo/backend/app/api/routes/export.py`：  
  - L20-L24 `_as_bool` 用字符串解析 bool：建议直接用 FastAPI 的 `bool` query 参数（由框架解析），减少自定义逻辑与边界 bug。  
- `P2`：`demo/backend/app/api/routes/generation_runs.py`：  
  - JSON 解析逻辑在 list/get 中重复，建议抽 `_parse_json_field()` 工具函数统一容错策略。  

#### 5.1.15 模型层（`demo/backend/app/models/*.py`）

- `P1`：`created_at/updated_at` 使用 `String` 存 ISO 时间：可行但不够“顶尖工程化”。建议改为 `DateTime(timezone=True)` + `func.now()`（并保持 SQLite/PostgreSQL 兼容）。  
- `P0`（v2.4 契约级变更）：API Key/Base URL 等贵重信息需落库（推荐 `llm_profiles` 作为配置库），且**响应/日志不得回显明文 Key**（仅 `has_api_key/masked_api_key`）。  
- `P1`：逐文件清单（建议至少逐个确认字段/索引/约束是否与 `demo/mvp开发计划.md` 第 6 节一致）：  
  - `demo/backend/app/models/user.py`：包含 `password_hash` 但 MVP 不启用登录；需明确 Phase 2 启用策略或移除避免误导。  
  - `demo/backend/app/models/project.py`：时间字段/索引策略见上；可补 `updated_at` 自动更新一致性测试。  
  - `demo/backend/app/models/project_settings.py`：单例表设计 OK；建议补 `updated_at`（P2，若需要审计/同步）。  
  - `demo/backend/app/models/character.py`：仅有 `updated_at` 无 `created_at`；是否需要请明确（MVP 可不加，但需一致性）。  
  - `demo/backend/app/models/outline.py`：同上。  
  - `demo/backend/app/models/chapter.py`：`status` 为字符串；建议与 schema 的 Literal 保持一致，并在 DB 层考虑 CHECK（SQLite 可选）。  
  - `demo/backend/app/models/prompt_template.py`：`type` 建议收敛为受控枚举（outline_generate/chapter_generate）。  
  - `demo/backend/app/models/llm_preset.py`：字段较多但不存 Key（v2.4：Key 存 `llm_profiles`，preset 只存 provider/base_url/model/参数）。  
  - `demo/backend/app/models/generation_run.py`：`params_json/error_json` 为 Text；后续若切 PostgreSQL 可迁移 JSONB（P2）。  
  - `demo/backend/app/models/__init__.py`：当前仅导出集合 OK；建议保持 import side effects 可控（只用于 Alembic 元数据发现）。  

#### 5.1.16 Schema 层（`demo/backend/app/schemas/*.py`）

- `P1`（已完成）：`LLMProvider` 已单点定义为 `app/schemas/llm.py` 并复用。  
- `P2`：`chapter_generate.py` 的 `previous_chapter: str | None` 建议改为 `Literal["none","summary","content"]`（与前端表单严格对齐）。  
- `P1`：逐文件清单（建议逐个确认约束：Field 的 min/max、Literal 的取值、与前端 types.ts 对齐）：  
  - `demo/backend/app/schemas/base.py`：`from_attributes=True` OK；建议统一所有 out schema 都继承它（减少不一致）。  
  - `demo/backend/app/schemas/common.py`：目前未被用作 `response_model`；要么全面启用，要么删除避免误导。  
  - `demo/backend/app/schemas/projects.py`：约束 OK。  
  - `demo/backend/app/schemas/settings.py`：目前未继承 ORMModel；虽不影响，但建议一致化。  
  - `demo/backend/app/schemas/characters.py`：约束 OK。  
  - `demo/backend/app/schemas/outline.py`：约束 OK。  
  - `demo/backend/app/schemas/chapters.py`：`ChapterStatus` 已是 Literal；建议与 DB `status` 字段强一致。  
  - `demo/backend/app/schemas/chapter_generate.py`：见上 `previous_chapter`；同时建议对 `instruction` 做更清晰的长度/空白策略。  
  - `demo/backend/app/schemas/outline_generate.py`：`requirements: dict` 过于宽泛；建议逐步结构化（P2）。  
  - `demo/backend/app/schemas/prompts.py`：`type: str` 建议收敛为受控枚举（outline_generate/chapter_generate）。  
  - `demo/backend/app/schemas/llm_preset.py` / `demo/backend/app/schemas/llm_test.py`：provider 类型已单点定义并复用（见 `app/schemas/llm.py`）。  
  - `demo/backend/app/schemas/generation_runs.py`：字段 OK；建议把 `type` 收敛为受控枚举（outline/chapter/test 等）。  

#### 5.1.17 Alembic（`demo/backend/alembic/*`）

- `P1`：`alembic/env.py` 通过 `sys.path.append` 导入应用：可用但建议最小化副作用（例如用项目包安装或明确入口），并确保不会在导入时触发应用初始化副作用。  
- `P0`（已完成）：已清理 `alembic/__pycache__` 等产物，并由 `.gitignore` 统一禁止入库。  

#### 5.1.18 `demo/backend/requirements.txt`

- `P1`：建议区分 `requirements.txt` 与 `requirements-dev.txt`（或迁移 `pyproject.toml`），把 `ruff/pytest/mypy` 等 dev 工具纳入并固定版本区间，保证团队一致性与可复现。  

### 5.2 前端（`demo/frontend`）

#### 5.2.1 `demo/frontend/src/pages/PromptsPage.tsx`

- `P0`（已完成）：占位符正则已修复为 `/{{\s*([a-zA-Z0-9_]+)\s*}}/g`（模板预览/占位符扫描恢复）。  
- `P1`（已完成）：已拆分为 `components/prompts/*`（`LlmPresetPanel`/`PromptTemplatesPanel` 等），显著降低单文件改动风险。

#### 5.2.2 `demo/frontend/src/services/apiClient.ts`

- `P0`（已完成）：已修复 `no-useless-escape`，并支持解析 `Content-Disposition` 的 `filename*=`（UTF-8）与 `filename=`。  
- `P1`（已完成）：网络错误已统一包装：`fetch` 异常会转成 `ApiError(code="NETWORK_ERROR", ...)`，页面可统一 toast。  

#### 5.2.3 `demo/frontend/src/components/ui/ConfirmProvider.tsx`

- `P0`（已完成）：已将 `useConfirm` 拆分到独立模块（避免 Provider + hook 同文件触发 Fast Refresh 规则）。  
- `P1`（已完成）：尾部空行/格式问题已清理（保持文件整洁，便于 diff/审查）。

#### 5.2.4 `demo/frontend/src/components/ui/ToastProvider.tsx`

- `P0`（已完成）：同上（`useToast` 已拆分到独立模块）。  
- `P1`（已完成）：尾部空行/格式问题已清理（同上）。  

#### 5.2.5 `demo/frontend/src/contexts/ProjectsContext.tsx`

- `P0`（已完成）：同上（`useProjects` 已拆分到独立模块）。  

#### 5.2.6 `demo/frontend/src/pages/ExportPage.tsx`

- `P0`（已完成）：已延迟 `URL.revokeObjectURL(objectUrl)`，避免偶发下载失败。  
- `P1`（已完成）：缩进/格式已统一（避免未来审查/合并痛苦）。  

#### 5.2.7 `demo/frontend/src/pages/DashboardPage.tsx`

- `P1`：L27 `created_at.localeCompare` 依赖 created_at 的格式稳定（当前后端是 ISO string，理论可用，但仍建议改成 `Date.parse` 排序以更稳健）。  
- `P2`：L36-L71 对每个项目顺序拉取 5 个接口：项目多时会慢；可考虑后端提供“wizard 摘要”聚合接口或前端并发限速。

#### 5.2.8 `demo/frontend/src/pages/CharactersPage.tsx`

- `P1`（已完成）：已移除 `eslint-disable`，并将 `load` 用 `useCallback` 包装补齐依赖，避免“切换项目但数据未刷新”的隐性 bug。  
- `P1`：文件尾部存在空行（需格式化统一清理）。  

#### 5.2.9 `demo/frontend/src/pages/SettingsPage.tsx`

- `P1`：文件尾部存在大量空行（需格式化统一清理）。  

#### 5.2.10 `demo/frontend/src/pages/OutlinePage.tsx`

- `P1`：L77-L99 `save` 的 `useCallback` 依赖中未出现 `baseline`（虽然当前通过 `dirty` 间接表达，但容易引起维护者误判）：建议改为“在 callback 内计算 dirty”或显式纳入依赖并简化逻辑。  
- `P1`：存在缩进不一致（需 prettier）。

#### 5.2.11 `demo/frontend/src/pages/WritingPage.tsx`

- `P1`：文件过大（37KB）：必须拆分，否则后续每次改动都是高风险。建议拆分方向：  
  - `ChapterListPane`、`ChapterEditorPane`、`GenerationPanel`、`RunHistoryDrawer`、`useChapters(projectId)`、`useGeneration(...)`。  
- `P2`：做路由级 code-splitting 后可顺带解决 build chunk warning。

#### 5.2.12 `demo/frontend/src/main.tsx`

- `P2`：引号/分号风格与其余文件不一致（单引号、无分号）：应交给 prettier 统一，不要靠人工约定。

#### 5.2.13 `demo/frontend/src/App.tsx`

- `P1`：路由表与页面导入集中在一个文件：建议抽到 `src/router.tsx`（或 `src/routes.tsx`），并在 `App.tsx` 只做 Provider 组合与 `<RouterProvider />` 挂载，降低耦合。  
- `P2`：建议加全局 Error Boundary（路由级或 AppShell 级），避免运行时异常导致整页白屏且无 toast。  

#### 5.2.14 `demo/frontend/src/pages/ProjectWizardPage.tsx`

- `P1`（已完成）：已消除 `react-hooks/exhaustive-deps` warning（lint 0 warning）。  
- `P1`：文件较大（13KB）：建议拆分“步骤列表 UI / 自动模式执行器 / 数据加载 hook”。  

#### 5.2.15 `demo/frontend/src/pages/NotFoundPage.tsx`

- `P2`：建议提供返回 Dashboard 的按钮/链接（减少迷路成本），并统一文案风格与 AppShell。  

#### 5.2.16 `demo/frontend/src/components/layout/AppShell.tsx`

- `P1`（已完成）：标题已改为“路由元信息表 + resolveTitle”集中管理（避免散落判断）。  
- `P1`（已完成）：侧边栏折叠状态 key 已抽到 `services/uiState.ts`（并统一使用 `storageKeys.ts` 前缀/拼接）。  

#### 5.2.17 `demo/frontend/src/components/layout/ProjectProviderGuard.tsx`

- `P2`：当前 guard 通过 `ProjectsContext` 判断项目存在：可用，但建议在“项目不存在”时提供返回入口与更明确的下一步（例如回到 Dashboard 并触发 refresh）。  

#### 5.2.18 `demo/frontend/src/components/atelier/ThemeToggle.tsx` / `demo/frontend/src/services/theme.ts`

- `P2`：ThemeToggle 的初始值建议用 `useState(() => ...)` 代替 `useMemo(() => ..., [])`（语义更清晰）。  
- `P2`：`applyThemeState` 直接操作 DOM：可接受，但建议补充“仅浏览器运行”的显式约束说明。  

#### 5.2.19 `demo/frontend/src/components/atelier/ProjectSwitcher.tsx`

- `P2`：L11-L14 `selected` 的 `useMemo` 纯属冗余：可以直接 `value={projectId ?? ""}`，减少样板代码。  

#### 5.2.20 `demo/frontend/src/components/atelier/MarkdownEditor.tsx`

- `P1`：建议把 `tab` 状态做成可选受控（便于写作页在“生成后自动切到预览”等交互里复用）。  
- `P2`：字符统计使用 `chars` 可能误导（中文/emoji 不是用户理解的“字数”）：MVP 可不改，但需在后续明确“字数统计口径”。  

#### 5.2.21 `demo/frontend/src/hooks/useSaveHotkey.ts`

- `P2`：hook 依赖 `onSave`：调用方应保证传入稳定引用（用 `useCallback` 包装），否则会频繁 add/remove listener。可在 hook 内部用 `useRef` 固化 listener，减少抖动。  

#### 5.2.22 `demo/frontend/src/hooks/useUnsavedChangesGuard.tsx`

- `P1`：依赖 `ConfirmProvider` 的 confirm 方法稳定性：若后续拆分 ConfirmProvider，需要保证 `confirm` 引用稳定，否则 blocker effect 可能重复触发。  

#### 5.2.23 `demo/frontend/src/services/wizard.ts`

- `P1`（已完成）：localStorage key 前缀/拼接已集中到 `services/storageKeys.ts`（避免多个前缀/拼写差异）。  

#### 5.2.24 `demo/frontend/src/services/llmKeyStore.ts` / `demo/frontend/src/types.ts`

- `P1`（已完成）：`LLMProvider` 已单点定义在 `src/types.ts` 并复用（`llmKeyStore.ts` 仅引用类型）。  

#### 5.2.25 `demo/frontend/src/services/currentUser.ts`

- `P2`：MVP 固定 `local-user` 正确，但建议把 `AUTH_USER_ID_STORAGE_KEY` 与后端常量对齐（后续 Phase 2 登录会用到）。  

#### 5.2.26 `demo/frontend/index.html` / `demo/frontend/src/index.css` / `demo/frontend/tailwind.config.js`

- `P1`：主题系统是 demo 的亮点，建议把“变量分层规则（语义变量 vs palette 变量）”写成不可违反的规范，并在 PR review 中强制检查：组件只能消费语义变量。  

#### 5.2.27 前端工程配置（`demo/frontend/package.json` 等）

- `P0`（已完成）：已新增 `prettier`，并提供 `npm run format`/`format:check`（统一格式化入口）。  
- `P2`：`vite build` chunk warning（>500KB）：建议用路由级动态 import 拆包（Writing/Prompts 页面最优先）。  
- `P1`：逐文件清单（建议一次性把“工程规则”写死）：  
  - `demo/frontend/package.json`：新增 `format` 脚本（prettier），并把 `lint` 改成 CI 必跑；必要时加 `lint:fix`。  
  - `demo/frontend/eslint.config.js`：解决 `react-refresh/only-export-components` 规则带来的 3 个 error（拆文件或放宽规则）。  
  - `demo/frontend/vite.config.ts`：目前 proxy OK；后续 code-splitting 可在路由层做，不建议在这里堆 manualChunks（除非确有需要）。  
  - `demo/frontend/tsconfig*.json`：建议开启/保持严格模式（`strict`）并清理不必要的 any；新增路径别名（`@/`）可提升可读性（P2）。  
  - `demo/frontend/tailwind.config.js` / `demo/frontend/postcss.config.js`：保持最小配置即可；主题变量优先在 `index.css` 管理，不要把主题逻辑分散到组件。  
  - `demo/frontend/index.html`：主题初始化脚本建议保持极简，并明确“不读取/不输出任何敏感信息”。  

---

## 6. 推荐实施顺序（不扩 scope 的前提下）

1) **批次 A（P0，目标：工程基线“可控”）**  
   - 修复前端 lint errors（Confirm/Toast/ProjectsContext 拆文件或调规则；apiClient 正则；PromptsPage 占位符正则；ExportPage revoke 时机）。  
   - 后端修复兜底错误码与日志级别；统一 DATABASE_URL 读取来源。  
2) **批次 B（P1，目标：可维护）**  
   - 后端抽 service 去重（outline/chapter generate）。  
   - 前端拆大页、统一数据加载与错误处理、移除 eslint-disable。  
3) **批次 C（P2，目标：更顶尖）**  
   - 前端 code-splitting；后端 LLM client 池化与 SSE 预留；补最小测试与 CI。

---

## 7. 验证清单（每批次都要跑）

**后端**
- `python -m compileall -q demo\\backend\\app demo\\backend\\alembic`
- 启动：`uvicorn app.main:app --reload --workers 1 --port 8000`（SQLite 单 worker）
- 自测：`GET /api/health`、项目 CRUD、prompts/preset 保存、outline/chapter generate（用真 Key）、generation_runs 查询、export 下载

**前端**
- `npm run lint`
- `npm run build`
- 手工：按 `demo/mvp开发计划.md` 第 11 节演示脚本跑通闭环

**本次验收记录（2025-12-14）**
- ✅ 后端：`python -m compileall -q backend\\app backend\\alembic`
- ✅ 前端：`cd frontend && npm run lint`
- ✅ 前端：`cd frontend && npm run build`（chunk > 500kB warning 允许，属 P2）
- ✅ 清理本地产物：`backend/**/__pycache__/`、`backend/**/*.pyc`、`frontend/dist/`

**本次验收记录（2025-12-15）**
- ✅ 后端：`python -m compileall -q backend\app backend\alembic`
- ✅ 前端：`cd frontend && npm run lint`（0 error）
- ✅ 前端：`cd frontend && npm run build`（chunk > 500kB warning 允许，属 P2）
