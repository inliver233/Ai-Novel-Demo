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
