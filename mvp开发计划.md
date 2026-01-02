# ainovel MVP开发计划（最终审查版 v2.4：可直接开工）

> 目标：把 `ainovel开发计划_v2.md`（愿景版）收敛为 **能在毕业设计周期内稳定交付** 的 MVP（最小可用产品）。  
> 技术栈约束：**前端 React + TypeScript**、**后端 Python（FastAPI）**、**开发数据库默认 SQLite（但从一开始保持 PostgreSQL 兼容）**。  
> 文档目标：让开发者只看本文件就能回答——**有多少页面、怎么跳转、每个按钮做什么、前后端交互哪些数据、LLM接入支持哪些厂商、错误/日志怎么处理、UI主题如何落地**。

## 变更说明 / 最后审查结论（v2.4）

本次修订目标：补齐“开工即踩坑”的边界条件，保证路由/API/DB/LLM/错误/部署预案**一致且可落地**。

v2.4 契约级变更（必须先读；影响前后端与文案）：
- **LLM 配置贵重信息落库**：API Key / Base URL / Model 等必须持久化到后端数据库（建议以 `llm_profiles` 为配置库，项目通过 `llm_profile_id` 绑定）。前端刷新/重开项目无需重新配置。
- **安全边界不变但更严格**：后端响应/日志/导出/前端 toast/控制台严禁回显明文 Key；API 只允许返回 `has_api_key` / `masked_api_key` 等安全表示；定位问题仅用 `request_id`。
- **兼容策略**：仍允许请求头 `X-LLM-API-Key` 作为**单次请求 override**（用于调试/旧客户端），但前端默认不再依赖 localStorage/header 传 Key。

v2.3 补充/修正（历史，保留用于对照）：
- 明确 `bulk_create` 的覆盖策略（`replace=true`）与冲突返回
- 明确 `chapters/{chapterId}/generate` 的 `replace/append` 输出语义与“生成不自动落库”
- 明确 `/api/llm/test` 的 header/body provider 一致性校验
- 修正“防重复提交”后端建议状态码表述
- 补齐 `/api/health` 响应示例的 `request_id`

关键决定（必须遵守）：
- **数据库路径**：MVP 默认 SQLite（单机单用户）；从 Day 1 起用 Alembic 管理迁移并按 PostgreSQL 兼容方式建模；SQLite 模式下后端仅允许 **单进程/单 worker**；满足任一条件即切 PostgreSQL：启用注册登录、需要 Docker 生产部署、需要开多 worker、或需要并发写入/多人同时用。
- **数据隔离预留**：MVP 固定 `current_user_id=local-user`；所有业务表通过 `project_id -> projects.owner_user_id` 间接隔离；对不带 `projectId` 的资源路由（`/api/chapters/{chapterId}`、`/api/characters/{characterId}`）也必须做归属校验，不通过返回 404（避免 Phase 2 大返工）。
- **LLM Secrets 安全（v2.4）**：API Key / Base URL 等贵重信息必须持久化到后端数据库（建议集中在 `llm_profiles`）；后端响应与日志严禁回显明文 Key（仅允许 `has_api_key` / `masked_api_key`）；前端仅在“更新/清除 Key”时提交明文 Key，常规生成/测试连接默认不再从 localStorage/header 传 Key；为兼容旧客户端仍允许 `X-LLM-API-Key` 作为单次请求 override。
- **LLM 兼容策略**：UI 按 provider 显示字段；后端 adapter 对“不支持参数”默认忽略并记录 `dropped_params`，但对 `provider/model/api_key` 缺失、以及（`openai_compatible` 的）`base_url` 缺失直接报错并提示可操作的修复方式。
- **可解释性**：`generation_runs` 定义为 MVP 必做项（答辩可解释性）；`RunHistoryDrawer` 为 MVP 必做简版；`DebugDrawer` 为 P1 可选（做了加分，不做不影响闭环）。
- **统一响应**：除“导出下载”外，所有接口使用 `ok/data/error/request_id`；所有响应头必须带 `X-Request-Id` 并在 CORS 中 expose。

---

## 0. MVP前提与边界（务必写进论文/答辩口径）

### 0.1 运行假设（MVP阶段）
- 单机运行、单用户使用（不做注册登录/RBAC）。
- 默认使用 SQLite；MVP 不考虑高并发（SQLite 模式下后端必须单进程/单 worker）。
- 生成不做 SSE 流式（一次请求返回完整结果）；UI 用“生成中”状态与渐显动效模拟“墨水渗入”。
- 不做向量RAG、事件/时间线/伏笔抽取等“一致性工程”，只做**可控上下文拼接**（设定 + 角色卡 + 大纲 + 上一章摘要/正文）。
- 任何涉及 LLM 的接口都必须避免“长事务”：在发起上游请求前结束数据库事务，生成结果返回后再开启新事务落库（避免 SQLite `database is locked`）。

### 0.2 MVP必须跑通的闭环
建项目 → 写设定 → 建角色 → 配置LLM → 生成大纲 → 一键生成第1章草稿 → 编辑保存 → 预览阅读 → 导出整本 Markdown。

### 0.3 面向“未来多用户 + 生产Docker”的预留原则（现在就要避免的坑）
- **接口不变**：尽量保持当前 REST 路由不变，未来只是在后端加 `Authorization` 校验与数据过滤。
- **数据可隔离**：从一开始就让 `projects` 等核心数据具备“归属用户”的能力（见第6节的预留字段/表），避免将来大规模重构。
- **可迁移**：即使 MVP 用 SQLite，也必须使用 Alembic 管理迁移，方便迁移到 PostgreSQL。
- **Header 可用**：生产环境会有 CORS/反代，必须提前规划：
  - 允许自定义请求头：`X-LLM-Provider`、`X-LLM-API-Key`
  - 暴露响应头：`X-Request-Id`（前端能读到 request_id）
- **避免 SQLite 多进程坑**：MVP 阶段后端只跑单 worker；任何“多用户/生产 Docker/多 worker”里程碑之前，先切 PostgreSQL 再水平扩展（第14节）。

---

## 1. 对参考计划（v2.0）的逻辑评估（为何要收敛）

`ainovel开发计划_v2.md` 把“写作产品”与“生产级平台工程”绑定交付（RAG/队列/监控/RBAC/幂等等），对毕业设计典型风险是：
- 关键路径被平台化任务挤占（很容易“做了很多工程，但写不出一章”）。
- 依赖组件过多（Redis/Worker/监控/pgvector），调试与部署成本陡增。

因此 MVP 策略：
- **先交付写作主链路**：项目/设定/角色/大纲/章节/导出 + Prompt/参数可控 + 多厂商LLM接入。
- **一致性先做到“可解释、可控”**：用“上下文注入开关 + Prompt预览 + 生成记录”替代RAG与结构化记忆。
- **工程化有但不过度**：统一错误格式、request_id、结构化日志、基础重试；不做监控栈。

---

## 2. 技术栈（以“最新稳定版”为准）

> 原则：不锁死具体小版本号，但从创建项目那天起，使用当时的最新稳定版，并在 `package.json/pyproject.toml` 锁定。

### 2.1 前端（UI/交互以 `ui设计规范.md` 为参考）
- React（建议使用当时最新稳定版，当前建议：React 19）
- TypeScript（5.x 最新稳定）
- Vite（最新稳定）
- Tailwind CSS（最新稳定，暗色模式使用 `class`）
- shadcn/ui + Radix UI（作为基础组件底座，便于“去默认化”）
- Lucide React（图标）
- Framer Motion（页面转场/侧边栏折叠/生成动效）
- 编辑器（MVP二选一）：
  - A：Markdown 编辑器（推荐，快）：`@uiw/react-md-editor` 或 `react-markdown` + `textarea`
  - B：Tiptap（后续增强，MVP不强制）
- 状态管理：Zustand（轻量；也可用 TanStack Query + 本地 store）
- 数据请求：fetch/axios 均可（建议封装 `apiClient`，统一错误处理与 request_id 展示）

### 2.2 后端
- Python 3.12+（或你本机可用的最新稳定）
- FastAPI（最新稳定）
- Pydantic v2
- SQLAlchemy 2.x（MVP 默认 SQLite；按 PostgreSQL 兼容方式建模）
- Alembic（迁移必须：从 Day 1 开始用，避免未来切 PostgreSQL 返工）
- PostgreSQL driver（Phase 2/生产必需）：psycopg（psycopg3）
- httpx（LLM调用；统一超时/重试/错误映射）
- 日志：structlog（JSON结构化日志，MVP只落到控制台/文件）

### 2.3 目录结构建议（保证“页面-组件-接口”对齐）

前端（React）建议：
```text
src/
  app/                 # 路由、AppShell、全局providers
    router.tsx
    AppShell.tsx
  pages/               # 7个路由页（与第4节一致）
    DashboardPage.tsx
    SettingsPage.tsx
    CharactersPage.tsx
    OutlinePage.tsx
    WritingPage.tsx
    PromptsPage.tsx
    ExportPage.tsx
  components/
    ui/                # shadcn/ui 基础组件（Button/Input/Dialog/Drawer等）
    atelier/           # 业务组件（ProjectCard/ChapterEditor/AIPanel等）
  stores/              # Zustand stores（project、chapter、ui等）
  services/
    apiClient.ts       # 统一请求、错误解析、request_id提取
    llmKeyStore.ts     # （可选）本地临时 override（兼容 v2.3）；v2.4 默认使用后端 llm_profiles 持久化 Key
  styles/
    globals.css        # Tailwind + CSS variables（纸张/墨水主题）
```

后端（FastAPI）建议：
```text
app/
  main.py              # FastAPI入口 + middleware(request_id/logging)
  api/                 # 路由层（projects/chapters/llm/export）
  schemas/             # Pydantic 入参/出参
  db/                  # engine/session/migrations(Alembic必须)
  models/              # SQLAlchemy models
  services/            # 业务服务（outline/chapter generation）
  llm/                 # provider适配器（openai/anthropic/gemini）
  core/                # config、errors、logging、template rendering
```

### 2.4 本地开发约定（端口/环境变量/SQLite限制）

端口约定（建议）：
- 前端（Vite）：`http://localhost:5173`
- 后端（FastAPI）：`http://localhost:8000`，API base path 固定为 `/api`

后端环境变量（建议提前统一命名，便于 Phase 2/Docker）：
- `APP_ENV=dev|prod`
- `DATABASE_URL=sqlite:///./ainovel.db`（MVP 默认；切 PostgreSQL 时只改这一项）
- `CORS_ORIGINS=http://localhost:5173`（开发跨域时；同域/反代时可为空）
- `LOG_LEVEL=INFO`

可选（想“一步到位”对齐生产的人）：
- 从开发第一天就使用 PostgreSQL（Docker 或本地安装），直接将 `DATABASE_URL` 配为 `postgresql+psycopg://...`；优势是避免后续迁移与并发锁库问题，代价是开发环境多一个依赖。

SQLite 模式强约束（必须写进 README/部署口径）：
- 仅单进程/单 worker（例如 `uvicorn ... --workers 1`），否则容易 `database is locked`
- 实现时建议开启 WAL + busy_timeout，并避免跨 LLM 调用持有数据库事务（见 0.1）

---

## 3. UI/UX 设计落地（Atelier：Paper & Ink）

> 本节把 `ui设计规范.md` 的关键规范内化到 MVP 计划里，确保“不是CRUD后台”，而是“数字化书房”。

### 3.1 主题与配色（必须做：亮/暗切换）

Light（默认）：
- Canvas：`#FBF9F6`（暖米白纸张）
- Surface：`#F2EFE9`（侧边栏/卡片底）
- Ink：`#2C2926`（主文字）
- Subtext：`#6E6A66`
- Border：`#E6E2DC`
- Accent（主色）：`#BC5D43`（陶土红）
- Success（辅助）：`#3F6359`

Dark：
- Canvas：`#1A1918`
- Surface：`#242321`
- Ink：`#E8E6E3`
- Accent：`#D97757`

主题开关：
- Sidebar 顶部放一个 `ThemeToggle`（Sun/Moon 图标），切换 `<html>` 的 `class="dark"`（light=无 dark，dark=有 dark）。
- MVP 默认 `<html data-theme="paper-ink">`；主题存储与初始化规则见第 3.8 节。

### 3.2 字体（必须做）
- UI 字体（导航/菜单）：Inter 或 Geist Sans
- 内容字体（大纲/正文）：Merriweather 或 Source Serif 4（正文 17px、行高 1.75）
- Prompt/代码：JetBrains Mono 或 Fira Code

### 3.3 布局（必须做：App Shell）
- 全局双栏：Sidebar（260px，可折叠到 56px）+ Main Content
- Main Content 内部建议 `max-w-4xl` 居中，四周 padding ≥ 32px（“纸张在桌上”）

### 3.4 组件风格（必须做：去默认化）
- Button：Primary（陶土色）/ Ghost（纸张上轻按钮）
- Input/Textarea：下划线式或极简块（拒绝蓝色ring）
- Card：极细边框 + 微弱阴影 + 圆角 12px

### 3.5 动效（MVP至少做到“顺滑”）
- 页面切换：Fade Up（opacity 0→1，y 10→0，0.4s）
- Sidebar 折叠：layout 动画平滑挤压
- 生成效果（非SSE）：响应回来后对新增文本块做淡入（模拟“墨水渗入”）

### 3.6 Tailwind + CSS Variables 落地

详见第 3.8 节“主题系统架构”，必须按分层结构编写。

### 3.7 全局组件清单（MVP必须出现）
- Layout：`AppShell`、`Sidebar`、`SidebarCollapseButton`、`ProjectSwitcher`
- Feedback：`Toast`（成功/失败统一）、`ConfirmDialog`
- Editor：`MarkdownEditor`（大纲/正文复用）、`PromptEditor`（monospace）
- AI：`AIPanel`、`GeneratingIndicator`
- Explainability：`RunHistoryDrawer`（MVP必做简版：最近生成记录）
- Debug（P1可选）：`DebugDrawer`（展示最后一次API错误/request_id；严禁展示明文 API Key）

### 3.8 主题系统架构（多风格切换预留）

MVP 默认主题：`paper-ink`（Paper & Ink 书房风格）

**设计原则：风格与亮暗模式正交**
- `data-theme="paper-ink"` — 风格主题（可扩展多种）
- `class="dark"` — 亮暗模式（light/dark）
- 组合示例：`<html data-theme="paper-ink" class="dark">` = paper-ink 风格的暗色模式

**CSS Variables 必须分两层（MVP 必须按此结构写）**：

```css
/* 第一层：语义变量（组件只消费这一层） */
:root {
  --color-canvas: var(--theme-canvas);
  --color-surface: var(--theme-surface);
  --color-ink: var(--theme-ink);
  --color-accent: var(--theme-accent);
  --color-border: var(--theme-border);
  --color-subtext: var(--theme-subtext);
  --color-success: var(--theme-success);

  --font-ui: var(--theme-font-ui);
  --font-content: var(--theme-font-content);
  --font-mono: var(--theme-font-mono);

  --radius-base: var(--theme-radius);
}

/* 第二层：主题定义（paper-ink 亮色） */
[data-theme="paper-ink"] {
  --theme-canvas: #FBF9F6;
  --theme-surface: #F2EFE9;
  --theme-ink: #2C2926;
  --theme-subtext: #6E6A66;
  --theme-border: #E6E2DC;
  --theme-accent: #BC5D43;
  --theme-success: #3F6359;
  --theme-font-ui: 'Inter', 'Geist Sans', sans-serif;
  --theme-font-content: 'Merriweather', 'Source Serif 4', serif;
  --theme-font-mono: 'JetBrains Mono', 'Fira Code', monospace;
  --theme-radius: 12px;
}

/* paper-ink 暗色 */
[data-theme="paper-ink"].dark {
  --theme-canvas: #1A1918;
  --theme-surface: #242321;
  --theme-ink: #E8E6E3;
  --theme-subtext: #B9B6B2;
  --theme-border: #2E2C29;
  --theme-accent: #D97757;
  --theme-success: #5E8A7C;
}

/* 未来扩展示例：cyberpunk 风格（MVP 不实现，仅展示架构） */
/*
[data-theme="cyberpunk"] {
  --theme-canvas: #0D0D0D;
  --theme-surface: #1A1A2E;
  --theme-ink: #EAEAEA;
  --theme-accent: #00F0FF;
  --theme-border: #2A2A4A;
  --theme-font-ui: 'Orbitron', sans-serif;
  --theme-font-content: 'Roboto Mono', monospace;
  --theme-radius: 4px;
}
*/
```

Tailwind 配置封装（`tailwind.config.js`）：
```js
module.exports = {
  theme: {
    extend: {
      colors: {
        canvas: "var(--color-canvas)",
        surface: "var(--color-surface)",
        ink: "var(--color-ink)",
        subtext: "var(--color-subtext)",
        accent: "var(--color-accent)",
        success: "var(--color-success)",
        border: "var(--color-border)",
      },
      fontFamily: {
        ui: "var(--font-ui)",
        content: "var(--font-content)",
        mono: "var(--font-mono)",
      },
      borderRadius: {
        DEFAULT: "var(--radius-base)",
      },
    },
  },
};
```

组件开发规范（必须遵守）：
```tsx
// ✅ 正确：使用语义变量
<div className="bg-canvas text-ink border-border">
<button className="bg-accent text-white">

// ❌ 错误：硬编码颜色值
<div className="bg-[#FBF9F6] text-[#2C2926]">
```

主题切换存储：
- localStorage key: `ainovel::theme::<user_id>`
- 值格式: `{ "themeId": "paper-ink", "mode": "dark" }`
- 初始化时读取并应用到 `<html>` 元素

MVP 阶段只实现 paper-ink 一套风格 + light/dark 两种模式，但必须按上述分层结构编写 CSS，确保未来可无痛扩展新风格。

---

## 4. 页面与路由（MVP最终页面数：9）

> 采用“App Shell + 路由页”的结构，保证跳转清晰、浏览器前进后退可用。

### 4.1 路由表（9页）

| # | 路由 | 页面名 | 说明 |
|---|------|--------|------|
| 1 | `/` | Dashboard | 项目概览/新建/删除/进入 |
| 2 | `/projects/:projectId/wizard` | 开工向导 | 完成度/下一步/跳过/自动模式 |
| 3 | `/projects/:projectId/settings` | 设定 | 项目信息 + 世界观/风格/约束 |
| 4 | `/projects/:projectId/characters` | 角色卡 | 角色列表 + 编辑抽屉 |
| 5 | `/projects/:projectId/prompts` | Prompt & 模型 | 模板编辑 + 参数 + 多厂商配置 + profiles/测试连接 |
| 6 | `/projects/:projectId/outline` | 大纲 | Markdown编辑 + AI生成 + 一键生成章节骨架 |
| 7 | `/projects/:projectId/writing` | 写作 | 章节列表 + 编辑器 + AI生成面板 |
| 8 | `/projects/:projectId/preview` | 预览 | 阅读器（章节列表 + Markdown 渲染）+ 编辑跳转 |
| 9 | `/projects/:projectId/export` | 导出 | 导出Markdown + 选项 |

### 4.2 全局 App Shell（所有页面共享）

Sidebar 区块（从上到下）：
1. 顶部：应用名 `ainovel Atelier` + `ThemeToggle` +（可选）Debug 开关
2. 项目切换：ProjectSwitcher（下拉/列表）
3. 当前项目导航：
   - 向导 / 设定 / 角色卡 / Prompt&模型 / 大纲 / 写作 / 预览 / 导出
4. 底部（可选）：版本号/帮助链接

Main Content：
- 顶部固定页标题（衬线体）+ 面包屑（可选）
- 页面主体（`max-w-screen-xl` 居中；移动端自适应留白）

### 4.3 弹窗/抽屉清单（非路由，但属于“界面规模”）
| 组件 | 触发入口 | 用途 |
|---|---|---|
| `CreateProjectModal` | Dashboard 的 `+` 卡片 | 创建项目 |
| `ConfirmDialog` | 删除项目/角色/章节 | 二次确认 |
| `CharacterDrawer` | 角色卡页“新增/点击卡片” | 编辑人物档案 |
| `GenerateOutlineModal` | 大纲页“AI生成大纲” | 生成参数（章节数/要求/注入开关） |
| `CreateChapterModal` | 写作页“新增章节” | 章号/标题/要点 |
| `RunHistoryDrawer` | 写作页“生成记录”按钮 | 查看最近生成记录（MVP必做简版） |
| `DebugDrawer` | Sidebar 顶部 Debug 开关（可选） | 调试：最后一次API错误/request_id（不展示敏感 header） |

---

## 5. 页面详设（到“按钮级别”的交互与API）

> 规则：每个页面都写清：组件、按钮、按钮触发的 API、成功/失败反馈、数据刷新策略。

### 5.0 全局交互规则（所有页面遵守）

1. **表单 dirty 状态跟踪**：任何编辑操作后标记 `dirty=true`，保存成功后重置为 `false`
2. **离开确认**：当 `dirty=true` 时，以下操作前弹出 `ConfirmDialog`：
   - 路由跳转（包括侧边栏切换项目/页面）
   - 浏览器刷新/关闭（`beforeunload` 事件）
   - 写作页切换章节
3. **快捷键**：`Ctrl/Cmd + S` 触发当前页面的“保存”按钮
4. **保存反馈**：保存成功后 toast “已保存”，保存失败 toast 显示错误 + request_id

### 5.1 Dashboard（`/`）

**主要组件**
- `ProjectGrid`
  - `ProjectCard`（点击进入项目）
  - `NewProjectCard`（虚线边框 + “+”）

**按钮/交互清单**
1. `NewProjectCard` 点击
   - 动作：打开 `CreateProjectModal`
2. `CreateProjectModal` → `创建`按钮
   - API：`POST /api/projects`
   - 成功：toast“创建成功” → 跳转 `/projects/:projectId/settings`
   - 失败：toast（显示 `error.message` + `request_id`）
3. `ProjectCard` 点击卡片主体
   - 动作：跳转 `/projects/:projectId/writing`（或保存的 last_tab）
4. `ProjectCard` 右上角 `⋯` → `删除项目`
   - 动作：打开 `ConfirmDialog`
   - 确认后 API：`DELETE /api/projects/{projectId}`
   - 成功：从网格移除 + toast
   - 失败：toast

**页面加载数据**
- `GET /api/projects`

---

### 5.2 设定（`/projects/:projectId/settings`）

**主要组件**
- `ProjectHeader`（项目名、类型、logline）
- `SettingEditor`（世界观/风格/约束三个大文本区）

**按钮/交互清单**
1. 页面进入
   - API：`GET /api/projects/{projectId}` + `GET /api/projects/{projectId}/settings`
2. `保存`按钮（右上角或页底）
   - 触发条件：表单 dirty
   - API：
     - `PUT /api/projects/{projectId}`（name/genre/logline）
     - `PUT /api/projects/{projectId}/settings`（world_setting/style_guide/constraints）
   - 成功：toast“已保存”
   - 失败：toast + 保留编辑内容
3. `重置为上次保存`（可选）
   - 动作：回滚到最后一次 GET 的值

---

### 5.3 角色卡（`/projects/:projectId/characters`）

**主要组件**
- `CharacterList`（卡片列表）
- `CharacterDrawer`（编辑抽屉：更像“人物档案”）

**按钮/交互清单**
1. `新增角色`（Primary）
   - 动作：打开 `CharacterDrawer`（空表单）
2. `CharacterCard` 点击
   - 动作：打开 `CharacterDrawer`（带数据）
3. `CharacterDrawer` → `保存`
   - 新建：`POST /api/projects/{projectId}/characters`
   - 编辑：`PUT /api/characters/{characterId}`
   - 成功：关闭抽屉 → 刷新列表（或本地更新）→ toast
4. `CharacterCard` → `删除`
   - 确认后：`DELETE /api/characters/{characterId}`
   - 成功：列表移除 + toast

**页面加载数据**
- `GET /api/projects/{projectId}/characters`

---

### 5.4 大纲（`/projects/:projectId/outline`）

**主要组件**
- `OutlineEditor`（Markdown编辑器：正文使用衬线体）
- `GenerateOutlineModal`（生成参数）
- `OutlineParsePanel`（可选：把大纲结构化成章节列表，并一键创建章节）

**按钮/交互清单**
1. 页面进入
   - API：`GET /api/projects/{projectId}/outline`
2. `保存大纲`
   - API：`PUT /api/projects/{projectId}/outline`
3. `AI生成大纲`（Primary）
   - 动作：打开 `GenerateOutlineModal`
4. `GenerateOutlineModal` → `生成`
   - API：`POST /api/projects/{projectId}/outline/generate`
   - Header：`X-LLM-Provider` + `X-LLM-API-Key`
   - 成功：
     - 展示“生成结果预览”，不立刻覆盖原文（先弹出“应用/取消”）
     - toast“生成完成”
   - 失败：toast（显示 `code/message/request_id`）
5. `应用生成结果`（Primary）
   - 动作：覆盖当前编辑器内容 + 立即保存（调用 `PUT /api/projects/{projectId}/outline`）；失败时保留编辑器内容并提示 request_id
6. `取消生成结果`（Ghost）
   - 动作：关闭预览，不改动现有大纲内容
7. **`从大纲创建章节骨架`（Primary，MVP 闭环关键入口）**
   - **位置**：大纲页顶部工具栏，与“AI生成大纲”按钮同一行
   - **启用条件**：仅当最近一次大纲生成返回的 `data.chapters.length > 0` 时启用
   - **禁用时**：按钮置灰 + hover tooltip：“请先生成包含章节结构的大纲”
   - **点击动作**：
     - 弹出确认框：“将根据大纲创建 {n} 个章节，是否继续？”
     - 确认后调用 `POST /api/projects/{projectId}/chapters/bulk_create`
     - 成功：toast “已创建 {n} 个章节” → 跳转写作页并选中第 1 章
     - 若项目已有章节：提示“检测到已有章节，是否覆盖？”；确认覆盖则调用 `POST /api/projects/{projectId}/chapters/bulk_create?replace=true`（危险：会清空该项目现有章节正文/摘要），取消则不执行

---

### 5.5 写作（`/projects/:projectId/writing`）——MVP核心

**推荐布局（对齐 Atelier 书房隐喻）**
- 左：`ChapterList`（宽 200~240px）
- 中：`ChapterEditor`（A4纸质感卡片，max-w-3xl/4xl）
- 右：`AIPanel`（可折叠 300px；MVP可先做成 Drawer）

**页面加载数据**
- `GET /api/projects/{projectId}/chapters`（列表）
- 点击具体章节：`GET /api/chapters/{chapterId}`

**按钮/交互清单**
1. `新增章节`
   - 动作：打开 `CreateChapterModal`（章号、标题、本章要点）
   - API：`POST /api/projects/{projectId}/chapters`
   - 成功：列表新增并选中该章
2. `章节列表项` 点击
   - 动作：选中章节 → 加载详情 → 编辑器展示
3. `保存章节`（Primary）
   - API：`PUT /api/chapters/{chapterId}`
   - 成功：toast“已保存”
4. `生成记录`（Ghost / Icon）
   - 动作：打开 `RunHistoryDrawer`
   - API：`GET /api/projects/{projectId}/generation_runs?limit=5`
   - 查看详情（可选）：`GET /api/generation_runs/{runId}`
5. `AIPanel` → `生成草稿（替换）`（Primary）
   - 若编辑器有未保存修改（dirty）：先弹窗确认
     - `保存并生成`：先 `PUT /api/chapters/{chapterId}` 再调用生成接口（推荐，避免“生成基于旧内容”）
     - `直接生成（基于上次保存）`：不保存，直接生成
     - `取消`
   - API：`POST /api/chapters/{chapterId}/generate`
   - Body（关键）：`mode="replace"` + 上下文开关 + 用户指令
   - 成功：
     - 将返回 `content_md` 写入正文编辑器
     - 自动把状态设为 `drafting`（并提示“别忘了保存”）
   - 失败：toast（带 `code/message/request_id`），且**不得覆盖**当前编辑器内容
6. `AIPanel` → `生成草稿（追加）`（Ghost）
   - API 同上，但 `mode="append"`（把新内容追加到文末）
   - 失败：同上（不得改动现有正文）
7. `AIPanel` → `继续写（可选，P1）`
   - 等价于 append + 自动注入“当前正文末尾片段”
8. `删除章节`（危险按钮放二级菜单）
   - API：`DELETE /api/chapters/{chapterId}`
   - 成功：从列表移除，选中相邻章节或空状态

**写作页必须有的状态提示**
- 未选择章节：右侧显示“请选择或新建章节”
- 生成中：按钮禁用 + `GeneratingIndicator`（纸张上“墨迹”loading）
- 未保存提示：离开页面/切换章节时弹出“是否保存？”

**防重复提交策略（必须做）**
- 前端：点击“生成”后立即 `setLoading(true)` 并禁用按钮，直到响应返回或超时
- 按钮文案变化：`生成草稿` → `生成中...`（带 loading 图标）
- 后端（Phase 2 可选）：对同一 chapter_id 在短窗口（例如 30s）内的重复请求返回 `409 CONFLICT`（提示“正在生成，请稍后重试”）

---

### 5.6 Prompt & 模型（`/projects/:projectId/prompts`）

**主要组件**
- `ProviderSelector`（OpenAI/OpenAI兼容/Claude/Gemini）
- `LLMConfigForm`（base_url/model/参数）
- `ApiKeyInput`（保存到后端配置库；只展示掩码；支持“更新/清除 Key”，不可回显完整 Key）
- `PromptTemplateEditor`（两个模板：大纲/章节；代码字体）
- `PromptPreview`（渲染占位符后的最终prompt预览）

**按钮/交互清单**
1. 页面进入
   - API：`GET /api/projects/{projectId}/llm_preset` + `GET /api/projects/{projectId}/prompts`
2. `保存LLM配置`
   - API：`PUT /api/projects/{projectId}/llm_preset`
3. `保存Prompt模板`
   - API：`PUT /api/projects/{projectId}/prompts`
4. `恢复默认模板`
   - 动作：本地替换为默认 → 需点击保存才落库
5. `测试连接`（Primary）
   - API：`POST /api/llm/test`
   - Header：`X-LLM-Provider`（建议）
   - Key 来源：默认使用当前项目绑定的后端配置（`llm_profile_id`）中已保存的 Key；如需临时 override，可附带 `X-LLM-API-Key`（不落库，仅本次请求）
   - Body：使用**当前表单值**（provider/base_url/model/timeout/参数）；推荐先保存配置/Key 再测试，保证刷新后一致
   - 成功：toast“连接成功（延迟 xxms）”
   - 失败：toast（带 request_id）

   **测试连接失败细化提示（必须实现）**

   | 后端错误码 | 前端 toast 提示 |
   |---|---|
   | `LLM_KEY_MISSING` | “请先填写 API Key” |
   | `LLM_AUTH_ERROR` | “API Key 无效或已过期，请检查后重试” |
   | `LLM_TIMEOUT` | “连接超时，请检查网络或 base_url 是否正确” |
   | `LLM_BAD_REQUEST` | “请求参数有误，可能是模型名称拼写错误” |
   | `LLM_UPSTREAM_ERROR` | “服务暂时不可用，请稍后重试（{status_code}）” |
6. `清除 API Key`（Ghost）
   - 动作：清除当前项目绑定配置的后端 Key（不回显原值），并提示“已清除”

**本页必须解决的问题**
- 用户一眼知道：当前用哪个厂商、哪个模型、参数是多少、模板长什么样、下一次生成会带什么上下文。

---

### 5.7 导出（`/projects/:projectId/export`）

**主要组件**
- `ExportOptions`（checkbox：包含设定/角色/大纲/仅导出done章节）
- `ExportPreview`（可选：只显示大纲与目录）

**按钮/交互清单**
1. `导出Markdown`（Primary）
   - API：`GET /api/projects/{projectId}/export/markdown?include_settings=1&include_characters=1&include_outline=1&chapters=all`
   - 成功：浏览器下载 `project-name.md`
   - 失败：toast（带 `code/message/request_id`）
2. `复制到剪贴板`（可选）
   - 动作：把导出内容复制到 clipboard（前端生成或调用接口返回文本）

---

### 5.8 预览（`/projects/:projectId/preview`）

**主要组件**
- `ChapterList`（PC 左侧可折叠；移动端抽屉）
- `ChapterReader`（Markdown 渲染；使用 Paper & Ink 语义样式）
- `EditButton`（跳转写作页并定位到该章）

**按钮/交互清单**
1. 页面进入
   - API：复用章节列表接口（`GET /api/projects/{projectId}/chapters`）
2. 切换章节
   - 动作：只切换展示章节内容（不写库）
3. 隐藏/显示章节列表
   - PC：折叠侧栏；移动端：抽屉开关（不影响阅读区）
4. `编辑`
   - 跳转：`/projects/{projectId}/writing?chapterId=<id>`（进入写作页并定位章节）
5. `下一步`
   - 使用 `WizardNextBar`：当“全部章节写完”后，下一步应进入预览；预览后下一步进入导出

**约束**
- 预览页尽量只读：不在此处编辑正文（编辑仍在写作页）
- 向导“写完”判定建议使用 `chapters.status=done`（本仓库现行口径）

---

### 5.9 开工向导（`/projects/:projectId/wizard`）

**主要组件**
- `ProgressSummary`（完成度百分比 + 下一步）
- `StepList`（步骤清单：打开/跳过/撤销跳过）
- `AutoMode`（一键：生成大纲 → 保存 → 创建章节骨架 → 跳转写作页）

**按钮/交互清单**
1. 页面进入
   - 动作：批量加载当前项目关键数据（settings/characters/prompts/preset/outline/chapters + profiles），计算完成度与下一步
2. `打开`
   - 动作：跳转到该步骤对应页面
3. `跳过` / `撤销跳过`
   - 动作：仅本地标记（MVP 口径），不写入后端
4. `一键开工`
   - 动作：复用大纲页与 bulk_create 的接口完成“生成→保存→建章”，成功后跳转写作页

**约束**
- 向导进度的“完成度%”应以真实数据为准：大纲/章节权重更高；写作需“全部章节 done”才 100%

## 6. 数据模型（SQLite 默认，兼容 PostgreSQL）与前端数据结构（TypeScript）

### 6.1 数据表（MVP最小集合 + 必要索引）

> 注：MVP 默认 SQLite（TEXT/INTEGER/REAL），但从 Day 1 起必须以“可迁移到 PostgreSQL”为约束来设计：
> - `id` 推荐 UUID string（PG 可无缝换成 UUID 类型）
> - 时间统一存 **UTC 的 ISO 8601/RFC3339 字符串**（PG 映射到 `timestamptz`）
> - JSON/数组字段在 SQLite 里以 TEXT 存 JSON 字符串（PG 可映射到 JSONB/ARRAY；MVP 不做 JSON 查询）

0) `users`（建议现在就建表：为未来多用户做铺垫；MVP可仅有一条 `local-user`）
- `id` TEXT PK（建议：`local-user` 作为MVP默认用户）
- `email` TEXT UNIQUE（MVP可空；未来注册登录用）
- `password_hash` TEXT（MVP可空；未来登录用）
- `display_name` TEXT
- `created_at` TEXT
- `updated_at` TEXT

1) `projects`
- `id` TEXT PK
- `owner_user_id` TEXT NOT NULL INDEX（MVP固定写入 `local-user`；多用户时用于数据隔离）
- `name` TEXT NOT NULL
- `genre` TEXT
- `logline` TEXT
- `created_at` TEXT
- `updated_at` TEXT

2) `project_settings`
- `project_id` TEXT PK FK(projects.id)
- `world_setting` TEXT
- `style_guide` TEXT
- `constraints` TEXT

3) `characters`
- `id` TEXT PK
- `project_id` TEXT INDEX
- `name` TEXT NOT NULL
- `role` TEXT
- `profile` TEXT
- `notes` TEXT
- `updated_at` TEXT

4) `outline`
- `project_id` TEXT PK
- `content_md` TEXT
- `updated_at` TEXT

5) `chapters`
- `id` TEXT PK
- `project_id` TEXT INDEX
- `number` INTEGER NOT NULL
- `title` TEXT
- `plan` TEXT
- `content_md` TEXT
- `summary` TEXT（可空；建议与正文同一次生成返回）
- `status` TEXT NOT NULL DEFAULT 'planned'
- `updated_at` TEXT
- UNIQUE(`project_id`,`number`)

6) `prompt_templates`
- `id` TEXT PK
- `project_id` TEXT INDEX
- `type` TEXT NOT NULL（`outline_generate` / `chapter_generate`）
- `system_template` TEXT
- `user_template` TEXT
- `updated_at` TEXT
- UNIQUE(`project_id`,`type`)

7) `llm_presets`（MVP 不存 API Key；Phase 2 预留字段）
- `project_id` TEXT PK
- `provider` TEXT NOT NULL（`openai`/`openai_compatible`/`anthropic`/`gemini`）
- `base_url` TEXT
- `model` TEXT NOT NULL
- `temperature` REAL
- `top_p` REAL
- `max_tokens` INTEGER
- `presence_penalty` REAL
- `frequency_penalty` REAL
- `top_k` INTEGER（给 Claude/Gemini 用，可空）
- `stop_json` TEXT（JSON数组字符串，可空）
- `timeout_seconds` INTEGER
- `extra_json` TEXT（JSON：厂商特有配置，如 Gemini safetySettings）
- `encrypted_api_key` TEXT（MVP 阶段可空，不读写；Phase 2 启用：服务端加密存储）
- `key_updated_at` TEXT（MVP 阶段可空，不读写；Key 更新时间）

8) `generation_runs`（MVP必做简版：用于答辩可解释性）
- `id` TEXT PK
- `project_id` TEXT INDEX
- `actor_user_id` TEXT（MVP可写 `local-user`；多用户时记录操作者）
- `chapter_id` TEXT NULL（大纲生成为空，章节生成填）
- `type` TEXT（`outline`/`chapter`）
- `provider` TEXT
- `model` TEXT
- `request_id` TEXT（后端生成，与日志相关联）
- `prompt_system` TEXT
- `prompt_user` TEXT
- `params_json` TEXT
- `output_text` TEXT
- `error_json` TEXT（失败时写）
- `created_at` TEXT

`output_text` 存储策略：
- MVP 阶段：直接存储全文（SQLite 单用户无压力）
- Phase 2 考虑（可选）：
  - 仅存储前 500 字 + "...（已截断，完整内容见章节）"
  - 或存储到对象存储，表里只存 URL

### 6.2 前端 TypeScript 类型（关键字段）

```ts
export type LLMProvider = "openai" | "openai_compatible" | "anthropic" | "gemini";

export interface Project {
  id: string;
  owner_user_id?: string;
  name: string;
  genre?: string;
  logline?: string;
}

export interface User {
  id: string;
  email?: string;
  display_name?: string;
}

export interface ProjectSettings {
  project_id: string;
  world_setting: string;
  style_guide: string;
  constraints: string;
}

export interface Character {
  id: string;
  project_id: string;
  name: string;
  role?: string;
  profile?: string;
  notes?: string;
}

export type ChapterStatus = "planned" | "drafting" | "done";

export interface Chapter {
  id: string;
  project_id: string;
  number: number;
  title: string;
  plan: string;
  content_md: string;
  summary?: string;
  status: ChapterStatus;
}
```

---

## 7. API 设计（前后端交互契约：含错误与日志）

### 7.1 通用约定
- Base path：`/api`
- Content-Type：`application/json; charset=utf-8`
- 每次响应都带：
  - Header：`X-Request-Id: <uuid>`
  - JSON：`request_id`

**成功响应格式**
```json
{ "ok": true, "data": { }, "request_id": "..." }
```

**失败响应格式**
```json
{
  "ok": false,
  "error": { "code": "LLM_AUTH_ERROR", "message": "API Key 无效", "details": {} },
  "request_id": "..."
}
```

> 约定：除导出下载（第 7.8 节）外，其余接口均返回 `application/json` 且遵循上述统一响应格式。

**Project 单例资源约定（避免新项目首次打开就 404）**
- `project_settings` / `outline` / `llm_preset` / `prompt_templates` 视为 project 的“单例资源集合”
- 对这些资源：
  - `GET`：若不存在，返回空值/内置默认值（可同时自动创建占位行），**不返回 404**
  - `PUT`：采用 upsert（不存在则创建，存在则更新）

**LLM Secrets 管理（v2.4）**
- LLM 连接信息（`provider/base_url/model/api_key`）必须持久化到后端数据库（建议：`llm_profiles` 作为可复用配置库；项目通过 `projects.llm_profile_id` 绑定当前配置）。
- **API Key 提交边界**：前端仅在“创建/更新/清除 Key”时向后端提交明文 Key；常规“测试连接/生成大纲/生成章节”请求默认不再携带明文 Key。
- **响应边界**：后端响应不得返回明文 Key，仅允许 `has_api_key` / `masked_api_key` 等安全表示。
- **Key 解析优先级（兼容 v2.3）**：
  1) 若请求头包含 `X-LLM-API-Key`，视为**单次请求 override**（仅本次请求生效；后端不落库）
  2) 否则从当前项目绑定的 `llm_profile` 读取 Key
  3) 若仍缺失，返回 401 `LLM_KEY_MISSING` 并提示去 Prompts 页保存 Key
- **Provider 一致性**：对 project 范围的生成接口，若带 `X-LLM-Provider`，必须与该项目保存的 `llm_preset.provider` 一致；不一致返回 400 并提示“先保存/切换当前项目的 provider”。

**鉴权预留（MVP关闭；未来多用户开启）**
- 未来启用登录后，统一使用：`Authorization: Bearer <access_token>`
- 为了不重构业务代码，建议后端从一开始就有一个概念：`current_user_id`
  - MVP：固定返回 `local-user`
  - 多用户：从 JWT 解析得到真实用户
- 启用多用户后所有 `GET /api/projects` 等接口默认只返回当前用户可访问的数据（至少按 `projects.owner_user_id` 过滤）。

**CORS / 反向代理注意事项（为 Docker/生产预留）**
- 如果前后端分域部署，需要在后端开启 CORS，并确保：
  - `Access-Control-Allow-Headers` 包含：`Content-Type, Authorization, X-LLM-Provider, X-LLM-API-Key`
  - `Access-Control-Expose-Headers` 包含：`X-Request-Id`（否则前端读不到 request_id）
- 如果生产使用 Nginx/网关，确保不会丢弃自定义 Header（尤其是 `X-Request-Id`）。
- **网关/反代日志脱敏**：
  - access_log 不记录 `Authorization`、`X-LLM-API-Key` 请求头
  - 不记录 URL query 中的 `key=...`（Gemini API 使用 query 传 key）
  - Nginx 示例：可在 log_format 中排除敏感字段，或使用 `proxy_set_header X-LLM-API-Key "";` 仅在转发层透传但不记录
- 生产安全提醒：`CORS_ORIGINS` 必须配置为明确域名（不要图省事用 `*`）；网关 access log 不应记录敏感 header/完整 URL（避免泄露 Key）。

### 7.2 项目
- `GET /api/projects`
- `POST /api/projects`
- `GET /api/projects/{projectId}`
- `PUT /api/projects/{projectId}`
- `DELETE /api/projects/{projectId}`

`POST /api/projects` request
```json
{ "name": "我的小说", "genre": "都市", "logline": "一句话梗概" }
```

### 7.3 设定
- `GET /api/projects/{projectId}/settings`
- `PUT /api/projects/{projectId}/settings`

### 7.4 角色卡
- `GET /api/projects/{projectId}/characters`
- `POST /api/projects/{projectId}/characters`
- `PUT /api/characters/{characterId}`
- `DELETE /api/characters/{characterId}`

### 7.5 大纲
- `GET /api/projects/{projectId}/outline`
- `PUT /api/projects/{projectId}/outline`

**生成大纲**
- `POST /api/projects/{projectId}/outline/generate`

request（MVP建议让模型输出 JSON，便于“从大纲建章节”）
```json
{
  "requirements": {
    "chapter_count": 12,
    "tone": "偏现实，克制但有爆点",
    "pacing": "前3章强钩子，中段升级，结尾反转"
  },
  "context": { "include_world_setting": true, "include_characters": true }
}
```

response（解析成功）
```json
{
  "ok": true,
  "data": {
    "outline_md": "# 大纲\\n...",
    "chapters": [
      { "number": 1, "title": "第一章", "beats": ["要点1", "要点2"] }
    ],
    "raw_output": "..."
  },
  "request_id": "..."
}
```

response（解析失败也不阻塞：`chapters` 为空）
```json
{
  "ok": true,
  "data": {
    "outline_md": "...",
    "chapters": [],
    "raw_output": "...",
    "parse_error": { "code": "OUTLINE_PARSE_ERROR", "message": "无法从模型输出解析章节结构" }
  },
  "request_id": "..."
}
```

### 7.6 章节
- `GET /api/projects/{projectId}/chapters`
- `POST /api/projects/{projectId}/chapters`
- `POST /api/projects/{projectId}/chapters/bulk_create`
- `GET /api/chapters/{chapterId}`
- `PUT /api/chapters/{chapterId}`
- `DELETE /api/chapters/{chapterId}`
- `POST /api/chapters/{chapterId}/generate`

**创建章节**
- `POST /api/projects/{projectId}/chapters`
```json
{ "number": 1, "title": "第一章", "plan": "本章要点…", "status": "planned" }
```

**批量创建章节（来自大纲解析）**
- `POST /api/projects/{projectId}/chapters/bulk_create?replace=false|true`（默认 `replace=false`）
- 行为约定：
  - `replace=false`：若该项目已存在任意章节，返回 `409 CONFLICT`（前端提示“先删除章节或选择覆盖创建”）
  - `replace=true`：先删除该项目所有章节，再按本次请求创建章节骨架（危险操作，前端必须二次确认）
```json
{
  "chapters": [
    { "number": 1, "title": "第一章", "plan": "要点1；要点2" },
    { "number": 2, "title": "第二章", "plan": "..." }
  ]
}
```

**保存章节（编辑器的保存按钮）**
- `PUT /api/chapters/{chapterId}`
```json
{ "title": "第一章", "plan": "…", "content_md": "…", "summary": "…", "status": "drafting" }
```

**生成章节**
- `POST /api/chapters/{chapterId}/generate`

行为约定（避免前后端对“追加/替换”的理解不一致）：
- 本接口**不自动写入** `chapters.content_md/summary/status`（只返回生成结果 + 写入 `generation_runs`）；前端需在用户确认后调用 `PUT /api/chapters/{chapterId}` 才落库
- `mode="replace"`：`data.content_md` 为“完整替换稿”
- `mode="append"`：`data.content_md` 为“新增片段”（前端追加到现有正文末尾，避免重复拼接整章）

request
```json
{
  "mode": "replace",
  "instruction": "写出本章冲突升级，结尾留钩子。",
  "context": {
    "include_world_setting": true,
    "include_style_guide": true,
    "include_constraints": true,
    "include_outline": true,
    "character_ids": ["uuid-1", "uuid-2"],
    "previous_chapter": "summary"
  }
}
```

response（建议同一次返回正文+摘要）
```json
{
  "ok": true,
  "data": {
    "content_md": "## 第一章\\n...",
    "summary": "本章发生了……",
    "raw_output": "..."
  },
  "request_id": "..."
}
```

**summary 字段来源**：
- AI 生成章节时：后端同时返回 `content_md` 和 `summary`（Prompt 里要求模型输出）
- 用户手动写章节：summary 默认为空
- Phase 2 可选：提供“AI 生成摘要”按钮（单独调用 LLM 总结当前正文）

### 7.7 Prompt & 模型
- `GET /api/projects/{projectId}/prompts`
- `PUT /api/projects/{projectId}/prompts`
- `GET /api/projects/{projectId}/llm_preset`
- `PUT /api/projects/{projectId}/llm_preset`

**保存 LLM preset（不含 API Key）**
- `PUT /api/projects/{projectId}/llm_preset`
```json
{
  "provider": "openai_compatible",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "temperature": 0.7,
  "top_p": 1.0,
  "max_tokens": 1500,
  "presence_penalty": 0,
  "frequency_penalty": 0,
  "top_k": null,
  "stop": ["---"],
  "timeout_seconds": 90,
  "extra": {}
}
```

**保存 Prompt 模板**
- `PUT /api/projects/{projectId}/prompts`
```json
{
  "templates": [
    { "type": "outline_generate", "system_template": "...", "user_template": "..." },
    { "type": "chapter_generate", "system_template": "...", "user_template": "..." }
  ]
}
```

**测试连接**
- `POST /api/llm/test`

request
```json
{
  "provider": "openai_compatible",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "timeout_seconds": 20,
  "params": { "temperature": 0, "max_tokens": 8 }
}
```

约定：Header `X-LLM-Provider` 必须与 `body.provider` 一致；不一致返回 400（避免“Key 与 provider 串用”）。

response
```json
{ "ok": true, "data": { "latency_ms": 523 }, "request_id": "..." }
```

### 7.8 导出
- `GET /api/projects/{projectId}/export/markdown`

导出响应建议：
- `Content-Type: text/markdown; charset=utf-8`
- `Content-Disposition: attachment; filename=\"<project_name>.md\"`

异常响应约定（重要）：
- 成功时返回 Markdown 文本（非 JSON）
- 失败时返回 `application/json` 且遵循统一错误格式（前端按 `Content-Type` 分支处理，并照常展示 `request_id`）

### 7.9 生成记录（generation_runs，MVP必做简版）
- `GET /api/projects/{projectId}/generation_runs?limit=5`
- `GET /api/generation_runs/{runId}`

### 7.10 LLM Profiles（配置库 + Secrets）管理（v2.4，MVP 必做）

MVP v2.4 策略：将 LLM 连接配置作为“可复用配置库”持久化到后端数据库（推荐表：`llm_profiles`），项目通过 `projects.llm_profile_id` 绑定当前配置。

接口（推荐最小集）：
- `GET /api/llm_profiles` — 获取当前用户的配置列表（**不返回明文 Key**，仅返回 `has_api_key/masked_api_key`）
- `POST /api/llm_profiles` — 新建配置（允许携带 `api_key` 写入；响应不回显明文）
- `PUT /api/llm_profiles/{profileId}` — 更新配置（允许更新/清除 `api_key`；响应不回显明文）
- `DELETE /api/llm_profiles/{profileId}` — 删除配置（被项目引用时应自动解绑）

项目绑定：
- `PUT /api/projects/{projectId}` body：`{ "llm_profile_id": "<profileId|null>" }`

安全要求（强制）：
- 明文 Key 只允许出现在**请求入参**（保存/更新/清除），不得出现在响应/日志/错误详情/导出。
- 如实现加密存储，应仅服务端可解密；前端不可“读取并显示完整 Key”（最多展示掩码）。

### 7.11 健康检查（生产部署必需）

- `GET /api/health`

response（无需鉴权）：
```json
{ "ok": true, "data": { "status": "healthy", "version": "1.0.0" }, "request_id": "..." }
```

---

## 8. 多LLM Provider 支持（OpenAI / OpenAI兼容 / Claude / Gemini）

> 本节定义“后端怎么把统一请求翻译成各家协议”，确保开发时不会临时拍脑袋。

### 8.1 Provider 配置字段（Prompts页表单必须覆盖）

通用字段（所有 provider 共享）：
- `provider`：`openai` / `openai_compatible` / `anthropic` / `gemini`
- `model`：模型名
- `temperature`、`top_p`、`max_tokens`、`stop`、`timeout_seconds`

按 provider 显示的字段与默认值建议：
- `openai`
  - `base_url`：默认 `https://api.openai.com/v1`
  - `presence_penalty` / `frequency_penalty`（可选）
- `openai_compatible`
  - `base_url`：用户自填（占位提示：`https://your-proxy.com/v1`）
  - 约定：允许用户填写含/不含 `/v1`；后端不自动追加 `/v1`（避免误判不同厂商路径）
  - `presence_penalty` / `frequency_penalty`（可选，厂商不支持则忽略）
- `anthropic`（Claude）
  - `base_url`：默认 `https://api.anthropic.com`
  - `top_k`（可选）
  - `extra.anthropic_version`（可选；默认用后端常量）
- `gemini`
  - `base_url`：默认 `https://generativelanguage.googleapis.com`
  - `top_k`（可选）
  - `extra.safety_settings`（可选，MVP可先不暴露）

**provider 选择指引（必须在 UI 上清晰提示）**：
- `openai`：直连 api.openai.com，base_url 默认填充，用户无需修改
- `openai_compatible`：用于**非官方渠道访问 OpenAI 协议的服务**，包括：
  - Azure OpenAI（需填 Azure endpoint）
  - 国内中转站（如 api2d、openai-sb 等）
  - 本地部署（Ollama / vLLM / LocalAI / LM Studio）
  - 其他兼容 OpenAI Chat Completions 协议的服务

UI 提示文案：
- openai 下方小字：“直连 OpenAI 官方 API”
- openai_compatible 的 base_url placeholder：`https://your-proxy.com/v1`
- openai_compatible 下方小字：“使用 API 中转、本地模型或其他兼容服务时选此项”

**base_url 后端处理规则（必须统一实现）**：
1. 去掉末尾 `/`
2. 按 provider 拼接 endpoint：
   - `openai` / `openai_compatible`：`{base_url}/chat/completions`
   - `anthropic`：`{base_url}/v1/messages`
   - `gemini`：`{base_url}/v1beta/models/{model}:generateContent`
3. 不自动追加 `/v1`（避免误判：用户填 `https://api.example.com/v1` 时不会变成 `/v1/v1`）
4. 校验 URL 格式：必须以 `http://` 或 `https://` 开头，否则返回 400

字段展示与兼容策略（必须明确，避免“一堆参数不支持导致失败”）：
- 前端表单：只展示当前 provider 支持/常用的字段；不支持的字段隐藏或置灰（不要让用户“填了也白填”）
- 后端 adapter：对当前 provider 不支持的参数**默认丢弃**并在日志记录 `dropped_params`（不报错）；但以下情况必须直接报错：
  - 缺失/非法：`provider`、`model`、（`openai_compatible` 的）`base_url`
  - 缺失：可用 API Key（请求未提供 override 且当前项目绑定配置无已保存 Key；返回 401，并提示去 Prompts 页填写）

API Key（v2.4 策略）：
- 必须落库到后端数据库（推荐：`llm_profiles` 作为配置库；项目绑定 `llm_profile_id`）。
- 常规“生成/测试连接”请求默认不再携带明文 Key；为兼容调试/旧客户端，仍允许在 Header 带 `X-LLM-API-Key` 作为单次 override。

### 8.2 统一内部请求结构（后端内部）

```json
{
  "provider": "openai_compatible",
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "messages": [
    { "role": "system", "content": "..." },
    { "role": "user", "content": "..." }
  ],
  "params": {
    "temperature": 0.7,
    "top_p": 1.0,
    "max_tokens": 1500,
    "presence_penalty": 0,
    "frequency_penalty": 0,
    "stop": ["---"]
  },
  "provider_options": {}
}
```

### 8.3 参数映射表（常见参数）

| 统一字段 | OpenAI/兼容 | Claude (Anthropic) | Gemini |
|---|---|---|---|
| temperature | `temperature` | `temperature` | `generationConfig.temperature` |
| top_p | `top_p` | `top_p`（如不支持则忽略） | `generationConfig.topP` |
| max_tokens | `max_tokens`（兼容） | `max_tokens` | `generationConfig.maxOutputTokens` |
| stop | `stop` | `stop_sequences` | `generationConfig.stopSequences` |
| presence_penalty | `presence_penalty` | 忽略 | 忽略 |
| frequency_penalty | `frequency_penalty` | 忽略 | 忽略 |
| top_k | 忽略 | `top_k` | `generationConfig.topK` |

### 8.4 上游请求示例（供实现时对照）

#### A) OpenAI / OpenAI兼容（Chat Completions）
- Endpoint：`POST {base_url}/chat/completions`
- Auth：`Authorization: Bearer <api_key>`

```json
{
  "model": "gpt-4o-mini",
  "messages": [{ "role": "system", "content": "..." }, { "role": "user", "content": "..." }],
  "temperature": 0.7,
  "top_p": 1.0,
  "max_tokens": 1500,
  "stop": ["---"]
}
```

#### B) Claude（Anthropic Messages）
- Endpoint：`POST https://api.anthropic.com/v1/messages`（base_url可配置）
- Auth header：`x-api-key: <api_key>` + `anthropic-version: 2023-06-01`（或最新）

```json
{
  "model": "claude-3-5-sonnet-latest",
  "max_tokens": 1500,
  "temperature": 0.7,
  "system": "系统提示…",
  "messages": [{ "role": "user", "content": "用户提示…" }]
}
```

#### C) Gemini（Google Generative Language API）
- Endpoint：`POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=<api_key>`

```json
{
  "systemInstruction": { "parts": [{ "text": "系统提示…" }] },
  "contents": [{ "role": "user", "parts": [{ "text": "用户提示…" }] }],
  "generationConfig": { "temperature": 0.7, "topP": 1.0, "maxOutputTokens": 1500 }
}
```

### 8.5 多厂商错误映射（必须做：统一给前端）

| 场景 | 后端错误码 | HTTP | 前端提示（示例） |
|---|---|---:|---|
| 缺少 API Key | `LLM_KEY_MISSING` | 401 | “请先在 Prompts 页填写 API Key” |
| API Key 无效 | `LLM_AUTH_ERROR` | 401 | “API Key 无效或已过期” |
| 额度/频控 | `LLM_RATE_LIMIT` | 429 | “请求过多/额度不足，请稍后重试” |
| 参数不支持 | `LLM_BAD_REQUEST` | 400 | “该模型不支持某参数，请关闭后重试” |
| 上游超时 | `LLM_TIMEOUT` | 504 | “生成超时，可降低字数或重试” |
| 上游异常 | `LLM_UPSTREAM_ERROR` | 502 | “模型服务异常，请稍后重试” |

---

## 9. Prompt系统（模板、占位符、预览、容错）

### 9.1 模板类型（2个）
- `outline_generate`：生成大纲（建议输出 JSON，字段固定：`outline_md` + `chapters[]`）
- `chapter_generate`：生成章节（建议输出 JSON，字段固定：`content_md` + `summary`）

输出契约（MVP 固定，减少解析歧义）：
- 大纲生成：`{ "outline_md": "...", "chapters": [{ "number": 1, "title": "...", "beats": ["..."] }] }`
- 章节生成：`{ "content_md": "...", "summary": "..." }`

### 9.2 占位符（MVP固定集合）
- 项目：`{{project_name}}` `{{genre}}` `{{logline}}`
- 设定：`{{world_setting}}` `{{style_guide}}` `{{constraints}}`
- 角色：`{{characters}}`（按选中角色拼接）
- 大纲：`{{outline}}`
- 章节：`{{chapter_number}}` `{{chapter_title}}` `{{chapter_plan}}`
- 生成入参：`{{requirements}}`（大纲生成需求文本）`{{instruction}}`（章节生成用户指令）
- 上下文：`{{previous_chapter}}`

### 9.3 Prompt预览（必须做）
- Prompts 页面提供 `PromptPreview`：
  - 显示渲染后的 system/user 文本
  - 高亮缺失占位符（例如 `{{outline}}` 为空时标黄）
  - 显示“注入开关”导致的内容变化（至少显示是否注入上一章/大纲/角色）

### 9.4 容错策略（必须做）
- 如果模型未按 JSON 输出：
  - 后端尝试提取 JSON（查找 ```json 块或首个 `{` 到末尾）
  - 仍失败：`content_md = raw_output`，并返回 `raw_output`
- Outline 解析失败：
  - `chapters=[]` 但 `outline_md` 仍返回，用户可以手动编辑并继续

---

## 10. 错误、日志与“可解释性”（MVP答辩关键）

### 10.1 后端日志（结构化 JSON）
每个请求至少记录：
- `request_id`、`path`、`method`、`latency_ms`、`status_code`
LLM调用额外记录：
- `provider`、`model`、`timeout_seconds`、`prompt_chars`、`output_chars`、`error_code`

敏感信息脱敏（必须做，属于安全红线）：
- 严禁记录：`Authorization`、`X-LLM-API-Key`、`Cookie/Set-Cookie`、以及 URL query 中的 `key=...`（Gemini 常见）
- 如需调试，仅允许输出 allowlist（例如 `X-Request-Id`/`Content-Type`）或输出掩码后的值（例如 `sk-***abcd`）

日志示例（结构，非固定字段）：
```json
{
  "ts": "2025-12-12T21:30:00Z",
  "level": "info",
  "request_id": "8c6c0f3a-...",
  "path": "/api/chapters/xxx/generate",
  "method": "POST",
  "status_code": 200,
  "latency_ms": 4821,
  "llm": { "provider": "openai_compatible", "model": "gpt-4o-mini", "prompt_chars": 8421, "output_chars": 12034 }
}
```

### 10.2 前端错误展示（必须做）
- 所有失败 toast 必须包含：
  - 用户可理解的中文 message
  - `request_id`（可复制）
- Prompts 页“测试连接失败”要给出更明确提示（Key无效/URL不通/模型名错误）

### 10.3 生成记录（MVP必做简版）
- 每次大纲/章节生成，把：
  - 渲染后的 system/user prompt
  - 参数（temperature等）
  - 输出（或错误）
  - request_id
  写入 `generation_runs`
- 写作页提供一个 `RunHistoryDrawer`（最少只显示最近5条：时间/类型/成功失败/查看详情）

### 10.4 错误码清单（MVP建议固定）

通用：
- `VALIDATION_ERROR`：入参校验失败（400）
- `NOT_FOUND`：资源不存在（404）
- `CONFLICT`：唯一约束冲突（例如同一项目重复章号）（409）
- `DB_ERROR`：数据库读写失败（500）
- 鉴权（Phase 2 启用）：
  - `UNAUTHORIZED`：未登录 / Token 过期 / Token 无效（401）
  - `FORBIDDEN`：已登录但无权限访问该资源（403）

Prompt/解析：
- `PROMPT_RENDER_ERROR`：占位符渲染失败（例如模板里出现未知变量且选择“严格模式”）（400）
- `OUTLINE_PARSE_ERROR`：大纲结构化解析失败（**非致命**：接口仍可 `ok=true` 返回 `outline_md`，但 `data.parse_error` 提示解析失败）

LLM：
- `LLM_CONFIG_ERROR`：LLM 配置缺失/非法（例如未保存 preset、provider 不一致、base_url 无效）（400）
- `LLM_KEY_MISSING`：缺少可用的 API Key（请求未提供 override 且当前项目绑定配置无已保存 Key）（401）
- `LLM_AUTH_ERROR`（401）
- `LLM_RATE_LIMIT`（429）
- `LLM_BAD_REQUEST`（400）
- `LLM_TIMEOUT`（504）
- `LLM_UPSTREAM_ERROR`（502）

---

## 11. 一条完整“跑通小说创作”的演示脚本（按按钮走）

1. Dashboard 点 `+` → 创建项目 → 自动跳转设定页
2. 设定页填三段文本 → 点 `保存`
3. 角色卡页点 `新增角色` ×3 → 每次点 `保存`
4. Prompts 页选择 Provider（例如 OpenAI兼容）→ 填 base_url/model → 输入 API Key（保存到后端配置库）→ 点 `测试连接`
5. 大纲页点 `AI生成大纲` → 填章节数/要求 → 点 `生成` → 点 `应用生成结果`
6. 大纲页点 `从大纲创建章节骨架` → 成功后跳转写作页并选中第1章
7. 写作页右侧点 `生成草稿（替换）` → 等待完成 → 点 `保存章节` → 将本章 `status` 设为 `done`（向导以 `done` 判定“写完”）
8. 预览页通读章节内容（章节列表可隐藏/移动端抽屉）→ 可点 `编辑` 跳回写作页定位章节
9. 导出页点 `导出Markdown` → 下载文件打开检查

---

## 12. 敏捷迭代计划（4个 Sprint，带DoD）

> 每个 Sprint 结束必须可演示（按第11节脚本逐步跑通）。

### Sprint 1：App Shell + 项目CRUD + 主题
交付：
- App Shell（Sidebar折叠、主题切换）
- Dashboard（项目列表/新建/删除/进入）
- 设定页（可保存）
DoD：
- 主题切换生效且全局一致
- 新建项目后能进入设定页并保存

### Sprint 2：角色卡 + LLM配置/测试 + Prompt编辑/预览
交付：
- 角色卡CRUD（抽屉编辑）
- Prompts 页（provider/参数/模板/预览/测试连接）
DoD：
- 支持至少 2 个 provider（先 OpenAI兼容 + Claude 或 Gemini）
- 测试连接能返回 latency_ms 或明确错误

### Sprint 3：大纲生成 + 章节骨架 + 写作页骨架
交付：
- 大纲页（生成、应用、保存）
- bulk_create 章节
- 写作页（章节列表、编辑器、保存）
DoD：
- “从大纲创建章节骨架”可用，写作页能选中第1章

### Sprint 4：章节生成 + 导出 + 生成记录 + 打磨
交付：
- 章节生成（replace/append）
- 导出Markdown
- generation_runs 记录 + 查看抽屉（至少最近5条）
DoD：
- 第11节脚本可稳定跑完
- 生成失败时有可理解提示 + request_id 可用于定位

---

## 13. MVP之后的演进路线（仅展望）

按“收益/成本比”排序：
1. SSE流式输出 + 右侧AI面板“批注卡片”交互
2. 多草稿版本（选稿/对比）
3. 自动摘要/人物出场表（仍不做RAG）
4. 世界书条目化 + 关键词注入
5. 向量记忆（pgvector/Chroma）与检索注入
6. 分支/重生、一致性评审、事件/时间线/伏笔体系
7. 多用户/权限/审计/监控/限流/生产化部署

---

## 14. Phase 2 预案：多用户注册 + Docker生产部署（为避免返工）

> 本节不要求在 MVP 当期实现，但要求 **MVP实现时按这些预留点写代码**，避免未来推倒重来。

### 14.1 多用户注册/登录（推荐最小方案）

后端新增能力（建议接口）：
- `POST /api/auth/register`：注册（email + password）
- `POST /api/auth/login`：登录（返回 access token；或设置 refresh cookie）
- `POST /api/auth/logout`
- `GET /api/auth/me`：当前用户信息

Token 策略（推荐）：
- `Authorization: Bearer <access_token>`（短时效）
- refresh token 走 `httpOnly` cookie（可选；若不做 refresh，可让用户重新登录）

密码存储（必须）：
- `password_hash` 使用强哈希（bcrypt/argon2），禁止明文。

### 14.2 数据隔离（“每个用户互不干扰”最低要求）

最低可行隔离规则：
- `projects.owner_user_id` = 当前用户 id
- 任意访问 `projectId` 的接口都必须校验项目归属（否则返回 404 或 403）
- `GET /api/projects` 只返回当前用户项目

实现要点（避免“少一个接口忘了加过滤”）：
- 在后端统一封装 `require_project(projectId, current_user_id)` 并在所有 project 路由复用
- 对不带 `projectId` 的资源路由（章节/角色）：先查资源，再通过 `resource.project_id -> projects.owner_user_id` 校验归属；不通过统一返回 404（减少信息泄露）

协作/共享（可选，后续再做）：
- 增加 `project_memberships`（`project_id`,`user_id`,`role`），替代单一 owner 模式。

### 14.3 API Key 管理（MVP方案的生产风险与升级路径）

v2.4（现行契约，必须）：
- Key / Base URL 等贵重信息必须持久化到后端数据库（推荐集中在 `llm_profiles` 配置库）
- 前端只在“更新 Key / 清除 Key”时提交明文 Key；接口响应只回 `has_api_key` / `masked_api_key`，严禁回显明文
- 常规“生成/测试连接”默认不携带明文 Key：后端从当前项目绑定的 `llm_profile_id` 读取 Key
- 兼容：仍允许请求头 `X-LLM-API-Key` 作为**单次请求 override**（仅本次请求；后端不持久化），用于调试/旧客户端

安全红线（必须遵守）：
- 后端/网关日志、错误详情、前端 toast/console/Network 展示、导出内容：任何情况下都不得输出明文 Key（必须脱敏；详见第10节）

实现建议（按环境）：
- Windows 开发环境：可使用平台密钥（如 DPAPI）进行加密后落库，避免引入额外依赖
- 生产环境：必须使用可迁移的服务端密钥（`SECRET_ENCRYPTION_KEY`，用于 `enc:` 加密）；上线前先运行迁移脚本把历史 `dpapi:`/`plain:` Key 迁移为 `enc:`（见 `backend/scripts/migrate_llm_profile_secrets.py`），并确保日志与错误体全链路脱敏

v2.3 旧方案（历史，已废弃）：前端 localStorage 保存 Key + header 透传（存在同域脚本可读、共享电脑串用、反代日志泄露等风险）

### 14.4 Docker / 生产部署（推荐架构）

推荐部署形态（最小生产可用）：
- `frontend`：构建静态资源 → Nginx 托管（同域名）
- `backend`：FastAPI（Uvicorn/Gunicorn）提供 `/api`
- `db`：PostgreSQL（生产建议必须用 PG；SQLite 不适合多用户并发）

同域 vs 分域（必须提前想清楚，否则 CORS/路径会返工）：
- **同域（推荐）**：Nginx 同时托管前端与反代 `/api`，前端请求用相对路径 `/api/...`，后端可不启用 CORS
- **分域**：前端与后端不同域名/端口，后端必须配置 `CORS_ORIGINS`，并允许/暴露自定义 header（见第7节）

关键环境变量（建议提前统一命名）：
- `APP_ENV=dev|prod`
- `DATABASE_URL=sqlite:///...`（MVP）→ `postgresql+psycopg://user:pass@db:5432/ainovel`（生产）
- `CORS_ORIGINS=`（如果前后端分域；同域可为空或不启用 CORS）
- 前端（分域时）：`VITE_API_BASE_URL=https://<your-domain>/api`（同域时建议直接用 `/api`，无需配置）
- `JWT_SECRET` / `JWT_PUBLIC_KEY`（启用登录后）
- `LOG_LEVEL=INFO`

迁移与启动（必须能自动化）：
- 容器启动时执行：`alembic upgrade head`
- 再启动应用服务（避免“表不存在”）

**docker-compose 服务编排要点（文字指引）**

服务定义与依赖顺序：
1. `db` (PostgreSQL) — 最先启动
2. `backend` (FastAPI) — 依赖 db，启动前执行迁移
3. `nginx` (前端 + 反代) — 依赖 backend

健康检查配置：
- db: `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}`
- backend: `GET /api/health` 返回 200（需实现该端点）
- nginx: 进程存活即可

数据持久化 volumes：
- `./data/postgres:/var/lib/postgresql/data` — 数据库持久化
- `./logs:/app/logs` — 后端日志（可选）

启动脚本参考（entrypoint）：
```bash
#!/bin/bash
# backend entrypoint
alembic upgrade head  # 先迁移
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

反向代理要点：
- Nginx 把 `/api` 转发到 backend
- 透传/保留 `X-Request-Id`（或由网关生成并透传），并确保自定义请求头 `X-LLM-Provider/X-LLM-API-Key` 不被剥离
- 建议同时透传 `X-Forwarded-For/X-Forwarded-Proto`，便于后端日志与将来做鉴权回调

Nginx 反代配置要点：
```nginx
# /api 转发到后端
location /api {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # 超时配置（LLM 调用可能很慢）
    proxy_connect_timeout 10s;
    proxy_read_timeout 180s;  # 至少 180s，覆盖 LLM 超时
    proxy_send_timeout 60s;
}

# 前端静态文件
location / {
    root /usr/share/nginx/html;
    index index.html;
    try_files $uri $uri/ /index.html;  # SPA 路由兜底
}
```

Header 透传注意：
- 确保 X-LLM-Provider / X-LLM-API-Key 能透传到后端（Nginx 默认透传）
- X-Request-Id 由后端生成，Nginx 不要覆盖
- access_log 不记录敏感 header（X-LLM-API-Key）

### 14.5 并发与性能（避免 SQLite 的“上线即锁库”）

在 SQLite 阶段（MVP）：
- 后端只跑 **单进程/单worker**（否则容易 `database is locked`）

上生产前（多用户 + Docker）：
- 切 PostgreSQL 后才能开多 worker
- 再考虑：限流、队列、SSE、缓存、审计与监控等平台化能力
