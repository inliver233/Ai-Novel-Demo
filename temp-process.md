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
