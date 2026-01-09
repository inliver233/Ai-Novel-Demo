# temp-process（实现过程记录）

> 目的：记录每个小步的“做了什么/改了哪些文件/如何验证/下一步做什么”，避免后期任务多了出现差错。

## 2025-12-22：Prompt System - M0（后端最小落地）

### 已读文档（按要求顺序）
- `提示词系统实现计划.md`（主设计：PromptBlock/Blueprint/Marker、M0~M4）
- `开发进度.md`（当前 demo 代码状态与既有决策）
- `更进一步实现.md`（仅用于后续接口预留，不在本阶段做上下文系统）

### 目标（M0）
- 引入 `prompt_presets` / `prompt_blocks` 两张新表，并提供最小 CRUD + preview/import/export/reorder。
- 旧项目仍保留 `prompt_templates`；自动生成迁移预设 `[Migrated] prompt_templates` 并从旧模板同步成块。
- 不改前端的情况下：`outline_generate` / `chapter_generate` 生成链路改为“从块系统渲染得到 system/user”，旧流程无感可用。

### 代码改动（M0）
- DB/模型/迁移
  - 新增：`backend/app/models/prompt_preset.py`、`backend/app/models/prompt_block.py`
  - 更新：`backend/app/models/__init__.py`
  - 新增 Alembic：`backend/alembic/versions/d8993729ae5a_add_prompt_presets_and_blocks.py`
- 服务层（迁移同步 + 渲染）
  - 新增：`backend/app/services/prompt_presets.py`
    - `ensure_migrated_prompt_preset()`：从 `prompt_templates` 同步出 4 个 legacy blocks（按 task 区分）
    - `render_preset_for_task()`：按 task 过滤 blocks → 渲染 → 合并成 system/user
- API（prompts 扩展）
  - 更新：`backend/app/api/routes/prompts.py`
    - 保留旧：`GET/PUT /projects/{project_id}/prompts`（PUT 后会同步迁移预设，保证旧 UI 编辑仍生效）
    - 新增：presets/blocks CRUD、reorder、import/export、preview
  - 新增 schema：`backend/app/schemas/prompt_presets.py`
- 生成链路切换到“块系统渲染”
  - 更新：`backend/app/api/routes/outline.py`
  - 更新：`backend/app/api/routes/chapters.py`

### 关键行为说明（兼容）
- 迁移预设名：`[Migrated] prompt_templates`
- legacy blocks（每个 task 2 块，共 4 块）：
  - `sys.legacy_system.{task}` + `user.legacy_user.{task}`
  - `triggers=["outline_generate"]` / `["chapter_generate"]`，避免任务串用
- preset 选择：优先非迁移预设；只有不存在匹配 task 的其他 preset 时才回落到迁移预设。

### 本地验证（已执行）
- DB 迁移：`backend/.venv/Scripts/python -m alembic -c backend/alembic.ini upgrade head`
- 迁移版本：`backend/.venv/Scripts/python -m alembic -c backend/alembic.ini current` → `d8993729ae5a (head)`
- 静态校验：`backend/.venv/Scripts/python -m compileall -q backend/app backend/alembic`
- DB 烟测：用脚本调用 `ensure_migrated_prompt_preset()` + `render_preset_for_task()` 成功生成 system/user（缺失变量按预期返回 missing 列表）

### 下一步（M1）
- 新增前端 Prompt Studio（可先新路由/新页面）：预设管理 + 块编辑 + 拖拽排序 + 后端预览 + token 统计入口（统计本阶段可先返回占位字段）。

## 2025-12-22：Prompt System - M1（Prompt Studio 与预览一致性）

### 目标（M1）
- 前端新增 Prompt Studio（不推翻旧 Prompts 页）：预设/块 CRUD、拖拽排序、导入导出、后端预览一致性。

### 代码改动（M1）
- 前端新增路由与页面
  - 新增：`frontend/src/pages/PromptStudioPage.tsx`（预设列表、块编辑、拖拽排序、导入导出、预览）
  - 更新：`frontend/src/App.tsx`（路由 `/projects/:projectId/prompt-studio`）
  - 更新：`frontend/src/pages/PromptsPage.tsx`（入口链接）
  - 更新：`frontend/src/components/layout/AppShell.tsx`（标题映射）
- 预览一致性：Prompt Studio 的预览统一调用后端 `POST /api/projects/{projectId}/prompt_preview`（前端不再做模板渲染）

## 2025-12-22：Prompt System - M2（宏系统 + Token 预算 + 可观测）

### 目标（M2）
- 后端统一渲染升级为 Jinja2 + 宏层；加入 token 估算、分块预算/裁剪，并把裁剪/缺失变量日志写入 generation_runs。

### 代码改动（M2）
- 渲染与宏
  - 更新：`backend/app/services/prompting.py`（Jinja2 + 宏：date/time/isodate/random/pick/注释；seed 可复现）
  - 更新：`backend/requirements.txt`（新增 `jinja2`）
- 覆写/继承点（最小实现）
  - 更新：`backend/app/services/prompt_presets.py`（同 preset 内 identifier 重复时后者覆盖前者，覆写模板可用 `{{original}}`/`{{base}}`）
- Token 预算与裁剪日志
  - 新增：`backend/app/services/prompt_budget.py`（token 估算 + 截断）
  - 更新：`backend/app/services/prompt_presets.py`（按块统计 token、按 must/important/optional 裁剪、返回 render_log）
- 生成记录可观测
  - 新增 Alembic：`backend/alembic/versions/f078e253d338_add_generation_runs_prompt_render_log_.py`
  - 更新：`backend/app/models/generation_run.py`（新增列 `prompt_render_log_json`）
  - 更新：`backend/app/services/run_store.py`、`backend/app/services/generation_service.py`（写入/透传 render_log）
  - 更新：`backend/app/api/routes/generation_runs.py`（对外返回 prompt_render_log）
- 前端预览展示 token
  - 更新：`frontend/src/types.ts`、`frontend/src/pages/PromptStudioPage.tsx`

## 2025-12-22：Prompt System - M3（规划→写作→润色，多阶段链路）

### 目标（M3）
- 新增 `plan_chapter`（标签契约）与可选 `plan_first` 注入写作；新增可选 `post_edit`（二次调用润色）。
- 流式章节生成也支持 `plan_first`，并保持 generation_runs 可追溯。

### 代码改动（M3）
- OutputContract 抽象与标签解析增强
  - 新增：`backend/app/services/output_contracts.py`（markers/json/tags 统一 parse；repair prompt 统一入口）
  - 更新：`backend/app/services/output_parsers.py`（tag 抽取改为“最后一个完整块”；新增 `parse_tag_output`）
  - 更新：`backend/app/api/routes/outline.py`、`backend/app/api/routes/chapters.py`（统一走 OutputContract.parse）
- 规划任务与注入
  - 新增：`POST /api/chapters/{chapterId}/plan`（`backend/app/api/routes/chapters.py`）
  - 更新：`backend/app/services/prompt_presets.py`（默认预设 `Default plan_chapter v1`）
  - 更新：`backend/app/schemas/chapter_generate.py`（新增 `plan_first`）
  - 更新：`backend/app/api/routes/chapters.py`（非流式/流式 `plan_first`：先规划→注入 `<PLAN>`→再写作）
- 润色任务（post_edit）
  - 更新：`backend/app/services/prompt_presets.py`（默认预设 `Default post_edit v1`）
  - 更新：`backend/app/schemas/chapter_generate.py`（新增 `post_edit`）
  - 更新：`backend/app/api/routes/chapters.py`（非流式/流式可选 `post_edit` 二次调用）
  - 更新：`frontend/src/pages/PromptStudioPage.tsx`（预览任务列表加入 `post_edit`，预览变量加入 `raw_content`）
- 多厂商 messages 统一（Prompt System 核心能力补齐）
  - 新增：`backend/app/llm/messages.py`（ChatMessage + merge/coalesce/flatten）
  - 更新：`backend/app/llm/client.py`（`call_llm_messages`/`call_llm_stream_messages`：messages→各 provider payload）
  - 更新：`backend/app/services/prompt_presets.py`（渲染返回 `messages[]`；支持 absolute 注入位）
  - 更新：`backend/app/services/generation_service.py`（支持 `prompt_messages`，调用 messages 版本 LLM）
  - 更新：`backend/app/api/routes/outline.py`、`backend/app/api/routes/chapters.py`（发送 messages；流式也用 messages）

### 本地验证（本轮已执行）
- 后端静态校验：`backend/.venv/Scripts/python -m compileall -q backend/app backend/alembic`
- 前端：`cd frontend && npm run lint`、`cd frontend && npm run build`

## 2025-12-22：默认推荐写作预设（参考酒馆预设）

### 背景
- Prompt Studio 功能较多，用户需要一个“可直接用 + 可学习改写”的默认强预设。
- 参考 `demo/参考酒馆的预设/` 中 SillyTavern 的 prompt preset JSON 结构（prompts[]：role/marker/enabled/injection_* /forbid_overrides）。

### 目标
- 新增两套“推荐默认预设”（先覆盖最核心的两条任务线）：
  - `默认·大纲生成 v3（推荐）`
  - `默认·章节生成 v3（推荐）`
- 兼容策略：
  - **老项目**：不自动接管（新预设默认 `active_for=[]`），仍由 `[Migrated] prompt_templates` 保证旧 Prompts 页“无感可用”。
  - **新项目**：创建项目时自动启用推荐预设（`active_for` 自动包含对应任务）。
- Prompt Studio 顶部增加“这是什么/怎么用”说明，并提供“一键启用推荐预设（大纲/章节）”。

### 代码改动
- 默认推荐预设种子（后端）
  - 更新：`backend/app/services/prompt_presets.py`
    - `ensure_default_outline_preset(..., activate=...)`
    - `ensure_default_chapter_preset(..., activate=...)`
- 预设列表确保可见（后端）
  - 更新：`backend/app/api/routes/prompts.py`（`GET /projects/{projectId}/prompt_presets` 里 ensure 推荐预设）
- 新建项目默认启用（后端）
  - 更新：`backend/app/api/routes/projects.py`（`POST /projects` 后 seed + activate 推荐预设）
- Prompt Studio 引导与快捷启用（前端）
  - 更新：`frontend/src/pages/PromptStudioPage.tsx`
    - 顶部说明：Preset/Block/active_for 的含义与迁移预设用途
    - 按钮：一键启用推荐预设（调用 `PUT /api/prompt_presets/{id}` 设置 active_for）

### 本地验证（建议执行）
- 后端静态校验：`backend/.venv/Scripts/python -m compileall -q backend/app backend/alembic`
- 前端构建：`cd frontend && npm run build`

## 2025-12-23：Prompt System - 全面 Review/Debug（基线阶段）

### 建立事实基线（无代码改动）
- `git status --porcelain=v1`：工作区干净
- 当前 HEAD：`c2918ba`（重构提示词系统，新增推荐默认提示词）
- 涉及核心改动文件（来自 `git log -1 --name-only`）
  - 后端：`backend/app/services/prompt_presets.py`、`backend/app/services/prompting.py`、`backend/app/services/prompt_budget.py`、`backend/app/services/output_contracts.py`、`backend/app/services/output_parsers.py`、`backend/app/llm/client.py`、`backend/app/llm/messages.py`
  - 路由：`backend/app/api/routes/prompts.py`、`backend/app/api/routes/outline.py`、`backend/app/api/routes/chapters.py`、`backend/app/api/routes/projects.py`、`backend/app/api/routes/generation_runs.py`
  - 模型/迁移：`backend/app/models/prompt_preset.py`、`backend/app/models/prompt_block.py`、`backend/app/models/generation_run.py`、`backend/alembic/versions/*prompt_*`
  - 前端：`frontend/src/pages/PromptStudioPage.tsx`、`frontend/src/pages/PromptsPage.tsx`、`frontend/src/types.ts`、`frontend/src/App.tsx`、`frontend/src/components/layout/AppShell.tsx`

### 下一步
- ✅ 已执行最小静态验证：
  - 后端：`backend/.venv/Scripts/python -m compileall -q backend/app backend/alembic`
  - 前端：`cd frontend && npm run lint`、`cd frontend && npm run build`（chunk > 500kb warning，非阻塞）
- ✅ 已核对 DB 迁移/Schema：
  - `cd backend && ./.venv/Scripts/python -m alembic -c alembic.ini current` → `f078e253d338 (head)`
  - SQLite 表/列检查：`prompt_presets/prompt_blocks` 存在；`generation_runs.prompt_render_log_json` 存在
- 下一步：开始逐文件 Review + 小步修复（优先生成链路与 prompt 渲染/预算）。

### 小步修复 1：宏注释（{{// ...}}）未被移除
- 问题：`backend/app/services/prompting.py` 的 `_MACRO_TOKEN_RE` 不匹配 `//`，导致注释宏不会被移除
- 修复：放宽 token 匹配，支持 `//...` 分支
- 改动文件：`backend/app/services/prompting.py`
- 验证：`backend/.venv/Scripts/python -m compileall -q backend/app backend/alembic`

### 小步修复 2：marker_key 值为 None 时渲染成 "None"
- 问题：`backend/app/services/prompt_presets.py` 对 `marker_key` 直接 `str(values[key])`，当值为 `None` 会污染 prompt
- 修复：`None` 视为 `""`；仅 key 缺失时计入 missing
- 改动文件：`backend/app/services/prompt_presets.py`
- 验证：`backend/.venv/Scripts/python -m compileall -q backend/app backend/alembic`

### 小步修复 3：全局预算裁剪时的 trim 优先级顺序错误
- 问题：`backend/app/services/prompt_presets.py` 在“仍超预算 → trim”阶段会优先裁剪 `important/must`，反而把 `optional` 留到最后
- 修复：trim 排序改为按 `drop_first → optional → important → must`（低优先级先裁剪）
- 改动文件：`backend/app/services/prompt_presets.py`
- 验证：`backend/.venv/Scripts/python -m compileall -q backend/app backend/alembic`

### 小步修复 4：渲染未带 provider，导致默认预算总是 24000
- 问题：`render_preset_for_task(... provider=...)` 在真实生成/预览调用处未传入 provider，`prompt_budget_tokens` 默认永远按 24000 估算，Anthropic/Gemini 下裁剪不一致
- 修复：在 prompt preview 与 outline/chapter/plan/post_edit 的渲染调用处传入项目 `LLMPreset.provider`（计划/润色二次渲染用 `llm_call.provider`）
- 改动文件：
  - `backend/app/api/routes/prompts.py`
  - `backend/app/api/routes/outline.py`
  - `backend/app/api/routes/chapters.py`
- 验证：`backend/.venv/Scripts/python -m compileall -q backend/app backend/alembic`

### 小步修复 5：Jinja2 渲染异常被吞掉且不可观测
- 问题：`backend/app/services/prompting.py` 在 Jinja2 parse/render 异常时直接回退为原模板，外部无法知道哪个块出错
- 修复：`render_template()` 额外返回 `render_error`；`render_preset_for_task()` 将错误写入 `render_log.blocks[].render_error` 并在 reason 中标记 `template_error`
- 改动文件：
  - `backend/app/services/prompting.py`
  - `backend/app/services/prompt_presets.py`
- 验证：`backend/.venv/Scripts/python -m compileall -q backend/app backend/alembic`

---

### 小步修复 6：preset.updated_at 不随 block 变更更新 + 迁移预设允许创建块
- 问题：
  - block CRUD/reorder 不会更新 `prompt_presets.updated_at`，导致“最近更新优先”与列表排序不准确
  - `POST /prompt_presets/{id}/blocks` 未禁止对迁移预设创建块（与 update/delete/reorder 的限制不一致）
- 修复：
  - block create/update/delete/reorder 时 `preset.updated_at = utc_now_iso()`
  - create block 同样禁止对 `"[Migrated] prompt_templates"` 操作
- 改动文件：`backend/app/api/routes/prompts.py`
- 验证：`backend/.venv/Scripts/python -m compileall -q backend/app backend/alembic`

### 小步修复 7：render_error 信息过长风险
- 问题：Jinja2 异常消息可能很长/含换行，写入 `prompt_render_log_json` 可能导致记录膨胀
- 修复：`backend/app/services/prompting.py` 将异常消息做单行化并截断到 200 字符
- 改动文件：`backend/app/services/prompting.py`
- 验证：`backend/.venv/Scripts/python -m compileall -q backend/app backend/alembic`

### 小步修复 8：PromptBlockUpdate 无法清空可空字段
- 问题：`PUT /prompt_blocks/{id}` 通过 `if body.xxx is not None` 判断更新，导致 `template/marker_key/injection_depth/triggers` 无法设置为 `null`（只能靠空字符串/空数组绕过）
- 修复：对可空字段改用 `body.model_fields_set` 判断是否传入，从而允许显式清空
- 改动文件：`backend/app/api/routes/prompts.py`
- 验证：`backend/.venv/Scripts/python -m compileall -q backend/app backend/alembic`

### 小步修复 9：Prompt Studio 拖拽排序在“从前拖到后”场景插入位置错误
- 问题：`frontend/src/pages/PromptStudioPage.tsx` 拖拽 reorder 时先删除再按旧 `toIdx` 插入，导致 fromIdx < toIdx 时偏移 1
- 修复：插入位置使用 `insertIdx = fromIdx < toIdx ? toIdx - 1 : toIdx`
- 改动文件：`frontend/src/pages/PromptStudioPage.tsx`
- 验证：`cd frontend && npm run lint`、`cd frontend && npm run build`

### 小步修复 10：Prompt Preview 缺少 project/story/user 结构，导致预览与真实渲染不一致
- 问题：`frontend/src/pages/PromptStudioPage.tsx` 的 `guessPreviewValues()` 只提供扁平 key，使用 `project.xxx/story.xxx/user.xxx` 的模板在预览中会误报缺失/渲染为空
- 修复：预览 values 补齐 `project/story/user` 命名空间（同时保留现有扁平 key），并提供示例 `plan/raw_content/requirements`
- 改动文件：`frontend/src/pages/PromptStudioPage.tsx`
- 验证：`cd frontend && npm run lint`、`cd frontend && npm run build`

### 小步修复 11：Prompt Studio 导出预设 revoke 时机过早
- 问题：`frontend/src/pages/PromptStudioPage.tsx` 导出后立即 `URL.revokeObjectURL`，部分浏览器可能导致下载失败/空文件
- 修复：对齐 `ExportPage`，使用 `setTimeout(..., 1000)` 延后 revoke
- 改动文件：`frontend/src/pages/PromptStudioPage.tsx`
- 验证：`cd frontend && npm run lint`、`cd frontend && npm run build`

### 小步修复 12：Prompt Studio 预览 characters 文本换行符错误
- 问题：`frontend/src/pages/PromptStudioPage.tsx` 的 `formatCharacters()` 用 `\"\\\\n\"` 拼接，预览里会出现字面量 `\\n` 而非换行
- 修复：改为 `\"\\n\"`，与后端 `format_characters()` 行为一致
- 改动文件：`frontend/src/pages/PromptStudioPage.tsx`
- 验证：`cd frontend && npm run lint`、`cd frontend && npm run build`

### 小步修复 13：Prompt Studio 预览缺少裁剪/错误细节（render_log 不可见）
- 问题：后端 `POST /prompt_preview` 已返回 `render_log`（含 dropped/trimmed/template_error 等），但前端丢弃不展示，排错困难
- 修复：Prompt Studio 预览保存并展示 `render_log`（折叠面板）+ 顶部提示 template 渲染错误列表
- 改动文件：`frontend/src/pages/PromptStudioPage.tsx`
- 验证：`cd frontend && npm run lint`、`cd frontend && npm run build`

### 回归验证（本轮结束前）
- 后端：`backend/.venv/Scripts/python -m compileall -q backend/app backend/alembic`
- 前端：`cd frontend && npm run lint`、`cd frontend && npm run build`
- DB：`cd backend && ./.venv/Scripts/python -m alembic -c alembic.ini current` → `f078e253d338 (head)`

---

## 2026-01-08：ainovel 长期记忆系统（调研 → 规划 → 纲领文档）

> 目标：不改代码，只做“完整调查 + 迁移学习 + 设计规划 + 输出纲领文档”。过程清单见：`demo/todolist.md`。

### 本阶段产物（截至目前）
- `demo/todolist.md`：任务拆解与勾选清单（待补充 mumu 相关条目）
- `demo/长期记忆系统完整实现规划.md`：v0.1 草案（待基于 mumu + 互联网调研升级为可执行初版）

### 工作方法（避免迷失）
- 先建立事实基线：用 `rg`/目录结构/DB schema 把“当前是什么样”写清楚
- 再做对照学习：用 Amily / mumu 的 `功能解析.md` 做索引，按“模块→可迁移点→在 ainovel 的落点”映射
- 最后写规划：以“数据模型/管线/接口/UI/提示词/部署/迁移/测试”组织成可执行路线图

### v0.1 规划文档 Review：问题清单（本轮重写依据）
- 仍偏“结构正确但不够落地”：许多段落以“建议/示意”结束，缺少**明确决策**（默认选型/参数/失败策略/最小可交付范围）。
- 缺少 mumu 的对照吸收：目前主要引用 Amily 的方法论，但还没有把 mumu 的**真实表结构/鉴权/worker/部署**映射到 ainovel 的落点。
- demo 现状对齐需要再验证：文档里提到的部分文件/字段/链路（如某些 service/route 名、generation_runs 字段扩展）需要逐一以代码为准，避免“文档先行但落不到现 repo”。
- API 章节偏“清单化”：需要补齐每个关键 endpoint 的 request/response（含分页/过滤/排序）、错误码、权限策略、幂等与并发控制（ETag/If-Match 或 version 字段）。
- 数据模型仍缺“可操作的约束”：核心表缺少 unique/索引/软删/版本策略的明确规定（尤其是 entities 的别名归一、关系去重、事件幂等键、evidence 指针格式）。
- memory_update 契约虽给 JSON 示例，但缺少“安全执行器闭环”：需要把 Amily 表格系统的**白名单执行/校验/回滚/审计**迁移为 ainovel 的结构化写入机制，并写清楚事务边界。
- RAG/向量部分还停留在“dense topK + 可选 rerank”层：需要补齐 chunking、hybrid 检索、rerank、去重/超级排序的参数与评估方式，并明确 SQLite 降级路径与 PG/pgvector 的迁移里程碑。
- UI 规划缺少与现 UI 的耦合点说明：需要明确写作页（`AiGenerateDrawer` 等）要加哪些开关/预览/调试入口、状态流如何走、与 generation_runs 的回溯如何串起来。
- 质量与可观测仍不足：需要定义 memory_retrieval_log / memory_update_log 的结构、采样/保留策略、导出与回放路径，以及“可验证”的 DoD（含最小评测集/一致性指标）。

### Demo 现状（事实基线摘要，2026-01-08）
- 技术栈：前端 `React+TS+Vite+Tailwind`；后端 `FastAPI+SQLAlchemy+Alembic`；SQLite 默认；批量任务 `RQ+Redis`
- 数据库（`demo/backend/ainovel.db`）表：`users/projects/project_settings/characters/outlines/chapters/prompt_presets/prompt_blocks/generation_runs/batch_generation_* / llm_profiles/llm_presets`
- 当前“记忆/上下文”主要来源：
  - `project_settings`：`world_setting/style_guide/constraints`
  - `characters`：自由文本（profile/notes），注入时由 `format_characters()` 格式化
  - `outlines.content_md`
  - `chapters.summary/content_md`：用于“上一章注入（none/summary/content/tail）”与 `smart_context`
  - `smart_context`（`backend/app/services/chapter_context_service.py`）：最近 20 章摘要 + 最近 2 章正文节选 + 按 stride 的“故事骨架”摘要
- Prompt System：`prompt_presets/prompt_blocks` + 资源种子 `backend/app/resources/prompt_presets/*`；渲染 `render_preset_for_task()` 支持预算裁剪、覆写、absolute/relative 注入、宏（date/time/isodate/random/pick/注释）
- 生成链路：`plan_first`（`<plan>`）→ `chapter_generate`（markers `<<<CONTENT>>>/<<<SUMMARY>>>`）→ 可选 `post_edit`（`<rewrite>`）→ 另有 `chapter_analyze`（严格 JSON）与 `chapter_rewrite`（`<rewrite>`）
- 可观测：`generation_runs` 记录 prompt_system/user、output_text、error_json、`prompt_render_log_json`
- 用户/权限：后端 `get_current_user_id()` 固定 `local-user`；启动时 `app.main._ensure_local_user()` 插入本地用户；所有资源通过 `require_owned_*` 做 owner 校验（未来可接入真实鉴权）

### Demo 复核补充（关键实现细节，供本轮规划落地对齐）
- `render_values` 结构：既有扁平 key（`world_setting/outline/...`），也有 `project/story/user` 命名空间；后续记忆建议直接挂到 `memory.*`（可复用同样的点号路径解析）。
- `plan_first` 注入方式：`inject_plan_into_render_values()` 会把 `<PLAN>...</PLAN>` 追加到 `instruction`，并设置 `story_plan` + `story.plan`；意味着记忆检索如果要“看计划”应读取 `story.plan` 而非重新解析 prompt。
- `prompt_render_log_json` 结构：`render_preset_for_task()` 返回 `render_log={task,preset_id,prompt_budget_tokens,prompt_tokens_estimate,missing,blocks[]}`；`blocks[]` 含每块的 `tokens_before/tokens_after/trimmed/dropped/reason/render_error`，可直接复用做 Memory 注入可观测。
- generation_runs 写入模式：`write_generation_run()` 用独立短 session 落库（避免长事务绑死）；后续 memory_update / embed 也可复用该模式写审计或产物。
- 任务队列现状：`TaskQueue` 目前只封装 `enqueue_batch_generation_task()`；RQ 侧使用 `job_id=task_id` + `meta.kind=batch_generation`，适合扩展为通用 `enqueue(kind, payload)` 并复用“任务表 + item 表”形态。
- 章节状态：`chapters.status` 是自由字符串（默认 `planned`，导出用 `done` 过滤）；若要把“定稿/选稿 → 写入记忆”挂钩，需要先约定状态集合或引入 `chapter_versions/selected_version_id`。
- 观测缺口：`plan_first/post_edit` 会各自产生 generation_run，但 `POST /chapters/{id}/generate` 返回只包含章节步的 `generation_run_id`；规划里若依赖“全链路回放”，需要补齐返回与 UI 展示策略（后续实现阶段再改代码）。

### Amily（可迁移能力摘要，来自 `Amily/ST-Amily2-Chat-Optimisation`）
- 表格系统（结构化记忆底座）：`core/table-system/*`
  - 用 LLM 输出受限指令 `<Amily2Edit><!-- insertRow/updateRow/deleteRow(...) --></Amily2Edit>`，由 `core/table-system/executor.js` 做白名单解析与安全执行
  - 表格注入：`core/table-system/injector.js` 支持 position/depth/role 注入；并可“优化模式”把填表与正文优化串联
- 世界书系统（WorldBook）：`core/lore.js` + `WorldEditor/*`
  - 蓝灯（constant）常驻注入；绿灯（关键词）触发注入；支持递归触发（把已触发条目的内容加入下一轮检索）
- 长程总结（国史馆/流水总帐）：`core/historiographer.js`
  - 自动/手动分段总结 → 写回世界书；金印进度（“前X楼总结已完成”）用于增量与自动隐藏联动；支持归档/回滚
- 向量 RAG（翰林院）：`core/rag-processor.js` + `core/rag-settings.js`
  - 分来源分块（novel/chat/lorebook/manual），写入向量库；检索后按来源注入；支持 rerank + “超级排序”(`core/super-sorter.js`)
  - Query 预处理：标签抽取/排除规则；还能识别显式索引（M123）增强检索
- 分形记忆（多层摘要）：`core/fractal-memory.js`
  - scene → arc → saga 的滚动压缩，并注入 prompt；还能同步到表格（形成结构化可视）
- 关系图谱：`core/relationship-graph/*`
  - 图谱数据主要从“角色/关系”表格推导同步；检索时用实体名匹配 query 并输出 `<GraphContext>` 注入
- 文本优化（生成后处理/去AI味/一致性修复）：`core/summarizer.js` + `core/events.js`
  - 可配置的 prompt 组合顺序（PresetSettings）；可注入世界书/历史/表格；对目标标签块进行替换式重写，并可与填表联动
- “超级记忆”（表格→世界书索引/详情同步）：`core/super-memory/*`
  - 表格更新事件队列化合并 → 写入世界书索引（smart-indexer）与详情；并把状态快照存入消息 metadata 以便恢复

### Amily 复核补充（可迁移的“具体做法”，用于反哺 ainovel 规划）
- 表格系统安全执行器（`core/table-system/executor.js`）
  - 白名单：仅允许 `insertRow/updateRow/deleteRow`；其他函数名直接拒绝执行（防注入）。
  - 参数解析：手写 parser 处理引号/嵌套 `{}`/`[]`，并对 JSON 错误做多轮修复（补数字 key 引号、单引号转双引号、宽松 key 匹配）。
  - 语义容错：`updateRow` 行越界自动降级为 `insertRow`；`deleteRow` 采用 `rowStatuses=pending-deletion` 的“延迟删除”两阶段策略（降低误删不可逆风险）。
- 表格注入与删除提交（`core/table-system/injector.js`）
  - 注入前先 `commitPendingDeletions()` 并把状态写回聊天消息（确保删除在下一次发送前落地，避免悬挂状态）。
  - 注入文案随 filling_mode 切换（main/secondary/optimized），最终用 `setExtensionPrompt(key, content, position, depth, ..., role)` 做位置/深度/角色可配置注入。
- 世界书绿灯递归触发（`core/lore.js#getPlotOptimizedWorldbookContent`）
  - `blueLightEntries=constant` 常驻；`pendingGreenLights=!constant` 关键词触发。
  - 递归：`searchText = chatHistory + triggeredContent(!prevent_recursion)`；命中规则：`exclude_recursion` 只在 chatHistory 匹配，否则在 searchText 匹配；直到不再新增条目。
  - 输出：为每条目附“触发关键词说明”，并按 `worldbookCharLimit` 截断。
- RAG 分块（`core/rag-processor.js#splitIntoChunks`）
  - 按来源分块：novel/chat_history/lorebook/manual；统一用 `chunkSize/overlap` 滑窗；novel 额外用正则识别“卷/章”做结构化 metadata（volume/chapter/section/globalIndex）。
  - 每块用 `<标签> + [来源前缀] + chunkText` 包裹，后续可用于注入展示与超级排序。
- RAG 检索预处理 + rerank + 超级排序（`core/rag-processor.js#rearrangeChat/#rerankResults` + `core/super-sorter.js`）
  - 预处理：可从最近 N 条消息中按标签抽取块、应用排除规则；识别显式索引 `M\\d+` 并增强 query。
  - rerank：可选外部 rerank API；最终分数 `semantic = rerank_score*alpha + dense_score*(1-alpha)`，再乘以来源/时序权重（世界书/手动更高、聊天按楼层近因增强）。
  - 超级排序：按来源类型决定“叙事阅读顺序”（聊天按 floor/part，小说按卷/章/节，手动按 timestamp，世界书按 sourceName）；若 key 不可得则回退 final_score。
- 关系图谱注入（`core/relationship-graph/executor.js`）
  - 轻量实体匹配：queryText substring 命中 node.label；取 1-hop 邻居；输出 `<GraphContext>`（含命中原因、节点 info、边方向）。
  - 图谱数据主要从表格推导同步（`core/relationship-graph/manager.js`，虽混淆但可见“角色表/关系表”映射规则）。
- 分形记忆（`core/fractal-memory.js`）
  - 阈值压缩：每 5 条消息提炼 1 条 scene；scene 满 5 压缩成 arc；arc 满 5 重写 saga（100–200 字）。
  - 同步到表格并注入 prompt（`HANLINYUAN_FRACTAL_MEMORY`），形成“可视 + 可检索”的双通道资产。

### MuMuAINovel（可迁移能力摘要，来自 `mumu/MuMuAINovel`）
- 多用户与鉴权（`backend/app/middleware/auth_middleware.py` + `backend/app/api/auth.py`）
  - Cookie 会话：`user_id`（HttpOnly）+ `session_expire_at`（前端可读）并注入 `request.state.user_id/user/is_admin`。
  - 登录方式：LinuxDO OAuth2 + 本地账号（`.env` 管理员账号可自动创建/初始化密码）。
- 生产化数据库与部署（`docker-compose.yml` + `Dockerfile` + `backend/app/database.py`）
  - 默认 Postgres（`postgresql+asyncpg`）+ 连接池参数；仓库同时维护 `alembic/postgres` 与 `alembic/sqlite` 两套迁移。
  - Compose 启动：`postgres` + 单体 `mumuainovel` 服务；注意向量库目录 `data/chroma_db` 默认未挂载 volume（需要在生产补齐持久化策略/可重建策略）。
- 长期记忆（向量 + 剧情分析）（`backend/app/models/memory.py` + `backend/app/services/memory_service.py` + `backend/app/services/plot_analyzer.py`）
  - 结构：`StoryMemory`（多类型记忆 + importance + tags + 章节时间线 + 文本位置 + 伏笔状态）+ `PlotAnalysis`（章节结构化分析：hooks/foreshadows/plot_points/character_states/评分等）。
  - 向量：ChromaDB PersistentClient（collection=hash(user_id,project_id) 规避命名限制）+ SentenceTransformer 多语言模型（支持离线模型目录，失败降级备用模型）。
  - 检索策略：`build_context_for_generation()` 同时取 recent(近3章)、semantic search(大纲 query)、unresolved foreshadows、角色相关、重要情节点，并格式化为可注入文本段落。
  - 写入策略：`extract_memories_from_analysis()` 会把分析结果转成“可落库 + 可向量化”的标准结构，并记录 `text_position/text_length` 供前端做标注高亮。
- 章节生成注入点（`backend/app/api/chapters.py`）
  - 生成 prompt 时合并：smart_context（骨架/相关历史/最近摘要/最近全文 + 上一章结尾强衔接说明）+ memory_context（来自 memory_service）+ 写作风格（writing_styles）。
- 可视化回溯（`frontend/src/pages/ChapterAnalysis.tsx`）
  - 章节内容支持“记忆标注高亮 + 右侧记忆侧边栏”（钩子/伏笔/情节点/角色事件统计与跳转），前后端通过 `position/length` 对齐。
- 关系图谱（`backend/app/models/relationship.py` + `backend/app/api/relationships.py` + `frontend/src/pages/Relationships.tsx`）
  - 预定义 `RelationshipType`（含反向关系名/分类/icon/intimacy_range），`CharacterRelationship` 采用有向边；支持导出图谱数据用于可视化。
- 写作风格资产（`backend/app/models/writing_style.py` + `backend/app/api/writing_styles.py`）
  - 风格以 `prompt_content` 持久化，区分系统预设（user_id=NULL）与用户自定义（user_id=xxx）；生成时可选风格并应用到 prompt。

### mumu → demo 映射表（Feature → mumu 落点 → ainovel 落点建议）

| Feature | mumu 参考实现（文件/入口） | ainovel（demo）落点建议 |
|---|---|---|
| 多用户会话 + 中间件注入 | `backend/app/middleware/auth_middleware.py`、`backend/app/api/auth.py` | 后端新增 auth 中间件/路由；把 `backend/app/api/deps.py#get_current_user_id()` 从常量改为从会话/JWT 解析；前端新增登录页/会话刷新与“未登录跳转”。 |
| 项目数据隔离 | `Project.user_id` + `verify_project_access()` | 维持 `projects.owner_user_id` 现有语义，后续引入 `project_memberships` 兼容协作；所有 memory 表按 project_id 隔离并复用 `require_owned_project`。 |
| 记忆表（多类型）+ 伏笔状态 | `backend/app/models/memory.py#StoryMemory` | 作为 Phase1/2 的“轻量统一记忆表”候选：先落 `memories`（type+content+importance+chapter_number+pos/len+tags），再逐步拆分为 entities/relations/events/foreshadows。 |
| 剧情分析 → 记忆抽取 | `backend/app/services/plot_analyzer.py` + `api/memories.py` | 把 demo 现有 `chapter_analyze` 产物升级为“PlotAnalysis + Memory extraction”双输出；采用严格 JSON 契约 + evidence(text_position/text_length)；写入走 change_set + 审计。 |
| 语义检索 + 组合上下文 | `backend/app/services/memory_service.py#build_context_for_generation` | 在 `chapter_context_service.py` 构建 `memory.*` 命名空间；检索策略可借鉴“recent + semantic + unresolved foreshadows + character_query + plot_points”的组合，并输出 MemoryContextPack。 |
| 向量库选型（Chroma + 本地模型） | `backend/app/services/memory_service.py` | Phase0/1 可用 Chroma 作为“SQLite 期向量子系统”（要明确持久化/重建策略）；Phase3+ 建议转 PG/pgvector（与生产化合并）。 |
| 记忆证据高亮 UI | `frontend/src/pages/ChapterAnalysis.tsx` + `/chapters/{id}/annotations` | 在 Writing 页/Chapter 页增加“记忆标注/侧栏”视图：按 `evidence.pointer(start,len)` 做高亮；同时提供检索调试与注入预览。 |
| 写作风格资产 | `backend/app/models/writing_style.py`、`api/writing_styles.py` | 在 demo 增加 `style_profiles`（样稿/抽取规则/负面清单）并映射到 PromptBlocks；与 `post_edit` 形成可配置链路。 |
| 关系类型 + 图谱 | `backend/app/models/relationship.py`、`api/relationships.py` | 把 Amily 的“表→图”思路与 mumu 的“RelationshipType/CharacterRelationship”结合：先固化关系类型表 + 有向边关系表，检索注入 `<GraphContext>`。 |
| 异步任务状态表 | `models/analysis_task.py` + `BackgroundTasks` | demo 已有 RQ + `batch_generation_tasks`；可复用同样表结构实现 `memory_tasks`（propose/apply/embed/rebuild）与 SSE/轮询状态接口。 |
| Docker + Postgres 生产化 | `docker-compose.yml` + `Dockerfile` | 参考 mumu 的 compose 拆分：`frontend`/`backend`/`postgres`/`redis`/`rq_worker`；并给出 SQLite→PG 迁移窗口与 DoD。 |

### 互联网调研要点（只保留“能落地到我们规划”的结论）
- pgvector（Postgres 向量检索）要点
  - 索引类型：HNSW / IVFFlat；HNSW 通常更好的 speed-recall，但更吃内存、build/写入更慢；且无训练步骤（适合“先建空表后逐步入库”）。
  - HNSW 调参：`m`、`ef_construction`（建图质量/成本）+ 查询期 `SET hnsw.ef_search=...`（召回/速度）。
  - 过滤条件“过筛导致返回不足”的问题：pgvector 新版本引入 iterative index scan 可缓解 overfiltering（规划里做“按条件不足则继续扫描”的降级策略）。
  - Hybrid：pgvector 官方建议与 Postgres FTS 组合做 hybrid search，再用 RRF 或 cross-encoder rerank 融合。
- Postgres 全文检索（FTS）要点
  - 核心操作符/函数：`to_tsvector`、`plainto_tsquery`、`@@`、`ts_rank`/`ts_rank_cd`（rank）。
- ChromaDB 过滤能力要点（用于“SQLite 期向量子系统”备选）
  - `Collection.query/get` 支持 `where`(metadata) 与 `where_document`(document)；where 语法类 Mongo，支持 `$and/$or/$in/$gte...`。
  - Chroma 目前不支持 metadata 里存 list 做复杂 tags 过滤；Cookbook 建议把每个 tag 作为 boolean 字段（`{games:true}`）来过滤。
- Rerank（第二阶段重排）要点
  - Cohere Rerank API：`query + documents[] -> results`，推荐单次不超过 1000 docs，长文会按 `max_tokens_per_doc` 截断；可用 `top_n` 控制返回数量。

### v1.0 规划文档二次 Review（本轮重写的硬修点）
- 版本口径不一致：`demo/长期记忆系统完整实现规划.md` 标题写 v1.0，但 `demo/temp-process.md`/`demo/todolist.md` 仍把它描述为 v0.1；本轮重写要统一为“v1.0 初版可执行”，并在文档头部写清“本轮新增/本轮仍缺”。
- Phase 依赖存在循环表述：表格中 Phase 3B 依赖 7（建议合并），而 Phase 7 又依赖 3B；需要改成**单向依赖**（例如把 PG/Redis/Worker/Compose 作为“基础设施 Phase”，Auth/RBAC 作为其子阶段），避免排期与实现顺序混乱。
- demo 落点需再对齐（防“文档先行但落不到 repo”）：
  - 现有 API 路由形态是否以 `/api/projects/{project_id}/...` 为主，还是以资源路由（`/api/chapters/{id}`）为主；规划中的 endpoint 命名需要按 demo 现状统一。
  - 前端现有页面与 hooks 目录结构需确认：规划里出现的 `frontend/src/pages/writing/useChapterAnalysis.ts` 等路径若不存在，应改成与现有 `WritingPage/AiGenerateDrawer` 的实际组织方式一致的落点建议。
- “建议/可选”过多，缺少默认决策：每个 Phase 需要补齐默认方案与参数（chunk_size/overlap、top_k、预算分配、阈值、rerank 触发条件、回退策略），并把“可选路线”明确标注为后置或实验。
- 记忆写入安全闭环还需要更“可实施”：
  - 输出契约（LLM JSON）需要补齐：版本号、schema 校验失败的错误面向 UI 展示、最大 ops 数/字段长度限制、拒绝策略（fail-closed）与降级（转 warnings）。
  - 执行器需要明确事务边界与幂等键：propose/apply/rollback 各自的幂等 key 与并发控制（乐观锁 version / If-Match），以及 apply 的“部分成功是否允许”（建议不允许）。
- 多用户与安全细节不足：Cookie 会话需要明确 `SameSite`/`Secure`/`HttpOnly`、CSRF 策略（double submit 或 same-site + 自定义 header）、密码哈希（bcrypt/argon2）、会话失效与登出；并写清 dev 的 `local-user` fallback 如何在 prod 禁用。
- 迁移与生产化需补齐 DoD 级别细节：SQLite→PG 迁移脚本的验证清单（行数/关键表 hash/外键完整性/回滚步骤），以及 docker compose 的数据卷/备份策略（尤其是向量库若选 Chroma）。
- 可观测/回放需要落到“字段/表/保留策略”：`memory_retrieval_log_json`/`memory_update_log_json` 放哪（generation_runs 新列/独立 artifact 表）、保留周期/采样策略、如何一键导出用于复现（含 prompt、pack、候选列表、最终注入、裁剪原因）。

### Demo 复核补充（再核验：接口形态 / 返回字段 / 资源目录）
- 章节相关 API 当前以资源路由为主：生成/分析/重写均为 `/api/chapters/{chapter_id}/...`（非 `/api/projects/{project_id}/chapters/...`）；长期记忆规划里的 endpoint 命名应跟随这一现实，避免未来实现时出现“路由全面重排”的隐性大重构。
- `plan_first` 的真实实现是“先渲染 plan_chapter → LLM → inject_plan_into_render_values → 再次渲染 chapter_generate”（见 `backend/app/api/routes/chapters.py`）；因此记忆检索若要利用计划，应读取 `render_values.story.plan`/`story_plan`（而不是从最终 prompt 逆向解析）。
- 章节生成 API 返回的 `generation_run_id` 仅对应 `run_type="chapter"`；plan/post_edit 的 generation_run_id 不在响应里返回（若未来要做全链路回放 UI，需要规划里明确“如何拿到这些 run 的关联关系/如何展示”）。
- Prompt preset 资源目录现状：`backend/app/resources/prompt_presets/` 目前存在 `chapter_generate_v3/outline_generate_v3/plan_chapter_v1/post_edit_v1/chapter_analyze_v1/chapter_rewrite_v1`；规划里如要新增 `chapter_generate_v4`，应以“新资源目录 + 一键启用推荐预设”的方式演进，避免破坏已有项目。
- 前端已存在 `frontend/src/pages/writing/useChapterAnalysis.ts`，并且调用 `/api/chapters/{id}/analyze` 与 `/api/chapters/{id}/rewrite`；后续若扩展为 PlotAnalysis/StoryMemory/标注 UI，可在此基础上增量演进，而不是重新发明页面结构。

### Amily 复核补充（代码级摘录：可迁移算法）
- 表格系统安全执行器的“闭环形态”很明确：LLM 只输出 `<Amily2Edit>...</Amily2Edit>`，executor 只解析三种指令并推演（`core/table-system/executor.js`）。
  - 指令块提取：正则 `/\<Amily2Edit\>([\\s\\S]*?)\<\\/Amily2Edit\>/`，并剥离 `<!-- -->` 注释，再按行 split（避免自由文本夹带）。
  - 白名单：`allowedFunctions={insertRow,updateRow,deleteRow}`；未在白名单的函数名直接拒绝（fail-closed）。
  - 参数解析：手写 `parseFunctionCall()` 逐字符扫描，处理引号与 `{}`/`[]` 嵌套深度，确保逗号只在“顶层”拆分参数；`parseValue()` 先尝试 JSON，再用多轮修复（数字 key 加引号、单引号转双引号、宽松 key 匹配、`tryParseObject()`）提高鲁棒性。
  - 容错与安全：`updateRow` 越界自动降级为 `insertRow`；`deleteRow` 第一次只标记 `rowStatuses[rowIndex]='pending-deletion'`（两阶段删除）。
- 世界书绿灯递归触发算法落地清晰（`core/lore.js#getPlotOptimizedWorldbookContent`）：
  - `blueLightEntries=constant` 直接加入 triggered；`pendingGreenLights=!constant` 做关键词触发。
  - 递归搜索文本：`fullSearchText = chatHistory + triggeredContent(!prevent_recursion)`；`exclude_recursion` 时仅在 `chatHistory` 搜索关键词。
  - 迭代直到本轮无新增条目；最终拼接条目并按 `worldbookCharLimit` 截断。
- RAG 的“按来源分块 + metadata + 包装标签 + 超级排序”是可直接迁移的结构（`core/rag-processor.js` + `core/super-sorter.js`）：
  - `splitIntoChunks(source)` 分派到 novel/chat_history/lorebook/manual；统一 `chunkSize/overlap` 滑窗。
  - novel 额外解析“卷/章/节”（正则识别），metadata 写入 `volume/chapter/section/globalIndex`，并用 `<标签> + [来源前缀] + chunkText` 包裹（便于注入展示与排序）。
  - `superSort()` 对不同来源给出“叙事阅读顺序”排序键：聊天按 floor/part，小说按卷/章/节，手动按 timestamp，世界书按 sourceName；缺 key 回退 `final_score`。
- 关系图谱注入足够轻量（`core/relationship-graph/executor.js`）：queryText substring 命中实体名 → 扩散 1-hop 邻居 → 输出 `<GraphContext>`，并在每个节点标注 reason 与有向边（`->`/`<-`）。
- 文本优化属于“替换式重写”范式（`core/summarizer.js`）：用 `extractContentByTag/replaceContentByTag` 只重写目标标签块；并可在同一次调用中附带 `<Amily2Edit>` 做“优化+填表”联动（对 ainovel 的 post_edit + memory_update 联动有参考价值）。

### MuMuAINovel 复核补充（代码级要点：可直接吸收的工程化落地）
- 多用户 Cookie 会话与刷新（`backend/app/api/auth.py` + `backend/app/middleware/auth_middleware.py`）
  - 登录后写 Cookie：`user_id`(HttpOnly) + `session_expire_at`(非 HttpOnly 供前端读)；默认 `samesite="lax"`；`POST /auth/refresh` 在接近过期时续期。
  - 中间件只做“从 Cookie 注入 request.state.user_id/user/is_admin”，并在用户 `trust_level==-1` 时视为未登录（禁用）。
  - 本地登录的管理员用户 `user_id` 通过 `md5(username)` 生成（`local_xxx`），并把密码写入 `user_passwords`（后续可用绑定账号登录）。
- Postgres + 迁移与容器化（`docker-compose.yml` + `Dockerfile` + `backend/scripts/entrypoint.sh`）
  - Compose 形态：`postgres` + 单体 `mumuainovel`（后端 + 前端静态），entrypoint 等待 DB → `alembic upgrade head` → `uvicorn`。
  - `backend/scripts/init_postgres.sql` 初始化扩展：`uuid-ossp` + `pg_trgm`（全文/模糊检索基础），未使用 pgvector（向量走 Chroma）。
  - Docker 多阶段：node 构建前端产物复制到 `/app/static`；Python 镜像内置 embedding 模型目录并设置 Transformers 离线环境变量。
- “长篇智能上下文”升级版 smart_context（在 `backend/app/api/chapters.py` 内实现）
  - `build_smart_chapter_context()`：骨架采样（每 50 章 1 条标题+摘要）+ 语义相关历史（用 `chapter_summary` 的向量检索 top 15）+ 最近 30 章摘要 + 最近 3 章全文。
  - 衔接强化：从 `recent_full` 中抽取“上一章结尾 ~600 字”，并追加明确指令（必须承接结尾、不要复述、从新情节点开始）。
- PlotAnalysis + StoryMemory（SQL 表）+ Chroma 向量（双存储闭环）
  - 模型：`backend/app/models/memory.py`：`plot_analysis`（hooks/foreshadows/plot_points/character_states/评分等 JSON）+ `story_memories`（type/content/importance/tags/story_timeline + chapter_position/text_length + is_foreshadow）。
  - 抽取：`backend/app/services/plot_analyzer.py#extract_memories_from_analysis`：为 hook/foreshadow/plot_point 记录 `keyword → text_position/text_length`，并强制生成 `chapter_summary` 作为后续“相关历史检索”的锚点。
  - 向量库：`backend/app/services/memory_service.py`：Chroma `PersistentClient(path="data/chroma_db")`，collection 以 `sha256(user_id)[:8] + sha256(project_id)[:8]` 组合命名；metadata 里保存 `chapter_id/chapter_number/importance/is_foreshadow/tags_json` 等。
  - 检索组合：`MemoryService.build_context_for_generation()` 同时取 recent(近3章)、semantic(大纲 query)、unresolved foreshadows、角色 query、plot_points，并格式化为可注入的分段文本（附 stats）。
- 标注回溯 UI 与后端兜底（`frontend/src/components/AnnotatedText.tsx` + `backend/app/api/chapters.py#/{chapter_id}/annotations`）
  - 前端标注支持重叠/相邻合并分片、tooltip 展示多标注；无效 position 过滤并提示。
  - 后端若 DB 中 `chapter_position==-1`，会尝试从 `PlotAnalysis` 的 keyword 在正文中重新 `find()` 定位，作为兜底（保证可视化基本可用）。
- 结构化更新的“实际示范”：分析结果驱动其它结构表更新（`backend/app/api/chapters.py` 中的 CareerUpdateService 调用）
  - 分析任务结束后会根据 `character_states` 更新角色职业进度（失败不影响分析主流程），体现“LLM 分析 → 结构化变更”的闭环可行性（对 ainovel 的 change_set / 安全执行器设计有参考价值）。

### 互联网调研补充（2026-01-08：把“最佳实践”翻译成可落地约束）
- pgvector 0.8.0：重点解决“过滤导致 overfiltering/结果不足”与 HNSW/IVFFlat 性能问题；新增 iterative index scan（可选 strict_order/relaxed_order）与 `hnsw.max_scan_tuples` 等阈值参数（后续规划里应写成“默认开关 + 回退策略 + 观测指标”）。 
- pgvector 官方建议（过滤场景）：少量离散值用 partial index；多离散值可考虑 partition；并给出“materialized CTE + 外层二次排序/距离过滤”的 SQL 写法（规划里可直接给示例，方便未来调试）。
- pg_trgm（Postgres 官方扩展）：提供 trigram 相似度与 GIN/GiST 索引，可用于“实体名/别名的模糊匹配”和“回写去重/冲突检测”的字符串侧召回；阈值可通过 `pg_trgm.similarity_threshold` 等 GUC 配置。
- RRF（Reciprocal Rank Fusion）作为 hybrid 融合的通用公式：`score = Σ 1/(rank + k)`，工程实践常用 `k≈60`；适合把 FTS rank 与 vector rank 融合为统一排序（避免 raw score 尺度不一致）。
- Cohere Rerank Best Practices：明确“doc chunking 会影响 rerank 成本与效果”“max documents 与 query/doc token 上限”“支持 structured/YAML 输入”等；规划里应把 rerank 作为可插拔模块（密钥缺失/成本过高时自动关闭），并限制候选池大小（例如 50~200）避免延迟爆炸。

### 规划文档二次自检与修订（2026-01-08）
- 发现问题：
  - `demo/长期记忆系统完整实现规划.md` 的章节编号与 Phase 映射仍有残留不一致：出现 “Phase 13” 等旧编号；附录 Phase 顺序错位（Auth 放在最后）、Structured Memory 被误写为 Phase 4；Prompt 资源的 Phase 映射与路线图不一致。
  - Phase 7（Style Profiles/去味/一致性修复）只有路线图级描述，缺“模块细则”（数据/接口/注入点/UI/降级/DoD），不够可开工。
- 修订动作：
  - 规划文档新增 **“12. 模块细则：Style Profiles + 去 AI 味 + 一致性修复（Phase 7）”**，并把多用户/可观测等章节顺延编号，避免“路线图有、细则缺”。
  - 规划文档附录按 Phase 0→7 重排，补齐 Phase 3/7 的前后端落地清单；修正 Prompt 资源映射；移除 “Phase 13” 等残留编号。
  - 修正规则表述：`smart_context` 明确保留为长期兜底（Phase 0~4 允许降级使用，Phase 4A/4B+5 稳定后再逐步降权）。
