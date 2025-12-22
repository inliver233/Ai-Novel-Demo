# ainovel MVP 改进建议（demo vs mumu 对比学习版）

> 目标：输出"建议文档"+"落地记录"；以 `demo/` 实际代码为准。
> 依据优先级：`demo/mvp开发计划.md`（v2.3）> demo 实现现状 > mumu 可借鉴实现 > `demo/ainovel开发计划_v2.md`（仅灵感参考）。
> 最后更新：2025-12-13（全面调查版）

本文件覆盖两部分：
1) **demo（你的 MVP 实现）现有 UI/交互问题的"确切成因"与改法**（含文件+行号）。
2) **demo 在流程/引导/多人/存储等方面的欠缺**：完整学习 `mumu/MuMuAINovel` 的更成熟流程后，给出可落地到 MVP 的改进路线（同样给到改哪些文件、怎么改、参考代码/参考位置）。

---

## 0. 结论先行（状态总览）

### 已落地（2025-12-13）

- P0：侧边栏折叠/展开可用、图标居中对齐、折叠按钮图标化、写作/Prompt 图标去重、SidebarLink 禁用 underline（`demo/frontend/src/components/layout/AppShell.tsx`）
- P0：`/projects/:projectId` 增加 index redirect，避免空白页（`demo/frontend/src/App.tsx`）
- P1（3.A）：纯前端开工向导 + 完成度 + 下一步建议 + 自动模式入口（`demo/frontend/src/pages/ProjectWizardPage.tsx`、`demo/frontend/src/services/wizard.ts`、`demo/frontend/src/pages/DashboardPage.tsx`）
- Phase2 预留：前端 user_id 单点来源，theme/llmKey/sidebarCollapsed/wizard 等本地存储 key 改为 `<user_id>` 前缀（`demo/frontend/src/services/currentUser.ts`）
- 修复：大纲页"应用生成结果"后仍可"从大纲创建章节骨架"（`demo/frontend/src/pages/OutlinePage.tsx`）
- 修复：`outline_generate` 占位符注入补齐 `style_guide/constraints`；LLM 失败日志补齐 `error_code`（`demo/backend/app/api/routes/outline.py`、`demo/backend/app/api/routes/chapters.py`）
- 修复：新建项目后跳转设定页（对齐第 11 节演示脚本第 1 步）（`demo/frontend/src/pages/DashboardPage.tsx`）

### 当前代码验证（2025-12-13）

**用户报告的三个问题验证结果**：

1. **侧边栏隐藏后无法显示** - 代码逻辑正确（`AppShell.tsx:22-36` 使用 localStorage 持久化 collapsed 状态，`AppShell.tsx:91-99` 切换按钮绑定 `setCollapsed(!collapsed)`）。如仍有问题，可能是浏览器缓存或构建问题，建议清除 localStorage 后重试。

2. **按钮和选中阴影不重合** - 当前代码 `AppShell.tsx:43-46` 已使用 `justify-center px-0`（折叠时）和 `justify-start gap-3 px-3`（展开时），图标居中逻辑正确。

3. **写作和Prompt图标重复** - **已修复**：
   - 写作（第138行）：`<PenLine size={18} />`
   - Prompt & 模型（第144行）：`<Sparkles size={18} />`
   - 两个图标完全不同。

### 仍需改进（发现的新问题）

#### P0（立即修，影响基本可用性）

| 编号 | 问题 | 位置 | 根因 |
|------|------|------|------|
| 1.7 | OutlinePage 保存函数缺少依赖 | `OutlinePage.tsx:78-99` | `baseline` 未在 `useCallback` 依赖数组中 |
| 1.8 | PromptsPage 正则表达式错误 | `PromptsPage.tsx:48-54` | 双反斜杠导致无法匹配占位符 |
| 1.9 | WritingPage 字符串逃逸错误 | `WritingPage.tsx:350` | 应使用 `"\n"` 而非 `"\\n"` |

#### P1（强烈建议做）

| 编号 | 问题 | 位置 | 建议 |
|------|------|------|------|
| 2.1 | 缺少 Error Boundary | 全局 | 单组件错误会导致全应用白屏 |
| 2.2 | 大文件组件未拆分 | `WritingPage.tsx`(917行), `PromptsPage.tsx`(670行) | 提取 hooks 和子组件 |
| 2.3 | 缺少 Loading Skeleton | 各页面 | 加载时显示骨架屏 |
| 2.4 | API 错误处理不一致 | 前端各页面 | 统一错误处理策略 |

#### P2（MVP 预留/Phase 2）

| 编号 | 问题 | 位置 | 说明 |
|------|------|------|------|
| 3.1 | 后端未持久化 wizard_status | 数据库 | 参考 mumu 实现 |
| 3.2 | 缺少 SSE 流式输出 | 后端 LLM 调用 | 参考 mumu wizard_stream |
| 3.3 | 缺少真实用户认证 | 后端 | 按 MVP 计划 Phase 2 实施 |

---

## 1. demo UI/交互问题（逐条：复现→根因→怎么改→验证）

### 1.1 侧边栏收起后"无法再展开/像消失"（已修复）

**当前状态**：代码逻辑正确，问题可能来自旧构建缓存。

**代码验证**：
```typescript
// demo/frontend/src/components/layout/AppShell.tsx:22-36
function useSidebarCollapsed(): [boolean, (v: boolean) => void] {
  const storageKey = sidebarCollapsedStorageKey(getCurrentUserId());
  const [collapsed, setCollapsed] = useState<boolean>(() =>
    localStorage.getItem(storageKey) === "1"
  );
  return [
    collapsed,
    (v) => {
      setCollapsed(v);
      localStorage.setItem(storageKey, v ? "1" : "0");
    },
  ];
}
```

**验证清单**：
- ✅ 收起后：顶部"展开"按钮始终可见且可点
- ✅ 展开后：宽度回到 260px
- ✅ 刷新页面：状态从 localStorage 正确恢复

---

### 1.2 侧边栏按钮与选中"阴影/高亮"不重合（已修复）

**当前状态**：代码已使用正确的布局类。

**代码验证**：
```typescript
// demo/frontend/src/components/layout/AppShell.tsx:41-46
clsx(
  "flex w-full items-center rounded-atelier py-2 text-sm no-underline hover:no-underline",
  props.collapsed ? "justify-center px-0" : "justify-start gap-3 px-3",
  isActive ? "bg-canvas text-ink" : "text-subtext hover:bg-canvas hover:text-ink",
)
```

---

### 1.3 "写作"和"Prompt & 模型"图标重复（已修复）

**当前状态**：两个图标已区分。

**代码验证**：
```typescript
// demo/frontend/src/components/layout/AppShell.tsx:138
icon={<PenLine size={18} />}  // 写作

// demo/frontend/src/components/layout/AppShell.tsx:144
icon={<Sparkles size={18} />}  // Prompt & 模型
```

**完整图标映射表**（`AppShell.tsx`）：

| 行号 | 标签 | 图标 |
|------|------|------|
| 108 | Dashboard | `LayoutDashboard` |
| 114 | 向导 | `ListChecks` |
| 120 | 设定 | `Settings` |
| 126 | 角色卡 | `Users` |
| 132 | 大纲 | `BookOpenText` |
| 138 | 写作 | `PenLine` |
| 144 | Prompt & 模型 | `Sparkles` |
| 150 | 导出 | `FileDown` |

---

### 1.4 全局链接 hover 下划线（已修复）

**当前状态**：SidebarLink 已添加 `no-underline hover:no-underline`。

---

### 1.5 顶部折叠按钮图标（已修复）

**当前状态**：使用 `PanelLeftOpen` / `PanelLeftClose` 图标。

**代码位置**：`AppShell.tsx:75-99`

---

### 1.6 访问 `/projects/:projectId` 空白页（已修复）

**当前状态**：已添加 index redirect。

**代码验证**：
```typescript
// demo/frontend/src/App.tsx:28
{ index: true, element: <Navigate to="writing" replace /> },
```

---

### 1.7 OutlinePage 保存函数依赖缺失（新发现）

**问题描述**：`save` 函数使用了 `baseline` 但未在依赖数组中声明。

**代码位置**：`demo/frontend/src/pages/OutlinePage.tsx:78-99`

```typescript
const save = useCallback(
  async (nextContent?: string) => {
    if (!projectId) return;
    if (nextContent === undefined && !dirty) return;
    // ... 使用 baseline 计算 dirty
  },
  [content, dirty, projectId, toast],  // ❌ 缺少 baseline
);
```

**建议改法**：
```typescript
[content, dirty, projectId, toast, baseline],  // ✅ 添加 baseline
```

---

### 1.8 PromptsPage 正则表达式错误（新发现）

**问题描述**：双反斜杠导致无法正确匹配 `{{placeholder}}` 格式。

**代码位置**：`demo/frontend/src/pages/PromptsPage.tsx:48-54`

```typescript
function findPlaceholders(text: string): string[] {
  const re = /{{\\s*([a-zA-Z0-9_]+)\\s*}}/g;  // ❌ 双反斜杠
  // ...
}
```

**建议改法**：
```typescript
const re = /\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g;  // ✅ 正确的正则
```

---

### 1.9 WritingPage 字符串逃逸错误（新发现）

**问题描述**：使用 `"\\n"` 会插入字面的反斜杠+n，而非换行符。

**代码位置**：`demo/frontend/src/pages/WritingPage.tsx:350`

```typescript
const charactersText = characters
  .map((c) => `- ${c.name}${c.role ? `（${c.role}）` : ""}`)
  .join("\\n");  // ❌ 字面字符串
```

**建议改法**：
```typescript
.join("\n");  // ✅ 换行符
```

---

### 1.10 DashboardPage 日期排序类型不安全（新发现）

**问题描述**：假设 `created_at` 是 ISO 字符串但未验证。

**代码位置**：`demo/frontend/src/pages/DashboardPage.tsx:27`

```typescript
const sorted = useMemo(
  () => [...projects].sort((a, b) => b.created_at.localeCompare(a.created_at)),
  [projects]
);
```

**建议改法**：
```typescript
const sorted = useMemo(
  () => [...projects].sort((a, b) =>
    new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  ),
  [projects]
);
```

---

### 1.11 ExportPage 资源释放时机问题（新发现）

**问题描述**：点击后立即撤销 URL 可能导致下载失败。

**代码位置**：`demo/frontend/src/pages/ExportPage.tsx:62`

```typescript
const a = document.createElement("a");
a.href = objectUrl;
a.download = filename || "ainovel.md";
document.body.appendChild(a);
a.click();
a.remove();
URL.revokeObjectURL(objectUrl);  // ❌ 可能过早
```

**建议改法**：
```typescript
a.click();
setTimeout(() => {
  a.remove();
  URL.revokeObjectURL(objectUrl);
}, 100);  // ✅ 延迟释放
```

---

## 2. 流程问题：demo vs mumu 的关键差距（聚焦 MVP 级别）

### 2.1 demo 现有闭环（已具备，但缺"串联层"）

demo 已实现的能力（按 `demo/对话交接.md` 与代码现状）：
- 项目 CRUD（Dashboard）
- 设定、角色、大纲、写作、Prompt&模型、导出（7 页）
- LLM preset（项目级）+ Prompt 模板预览与测试连接
- 大纲生成、章节生成、导出 Markdown、生成记录
- **开工向导页面**（`ProjectWizardPage.tsx`，342行）
- **一键开工功能**（自动生成大纲 + 创建章节）

**已具备的流程编排**：
- 7步向导（llm → settings → characters → outline → chapters → writing → export）
- 完成度计算（`wizard.ts:83-154`）
- 步骤跳过机制（localStorage 持久化）
- 自动模式入口（一键开工按钮）

**仍缺的不是"功能点"，而是"后端持久化与流式体验"**：
- wizard_status 未持久化到数据库（只在前端 localStorage）
- 生成过程无流式反馈（SSE）
- 断线后无法从后端恢复进度

### 2.2 mumu 的"丝滑流程"拆解（可借鉴的 MVP 子集）

mumu 的关键优势（只提你现在最需要学的部分）：

#### 1) 项目向导与可恢复
- 项目列表进入项目时会判断是否未完成向导，未完成则跳转继续生成：
  - 参考：`mumu/MuMuAINovel/frontend/src/pages/ProjectList.tsx:121-127`
- 向导页从 URL 参数 `project_id` 恢复生成：
  - 参考：`mumu/MuMuAINovel/frontend/src/pages/ProjectWizardNew.tsx:35-44`
- 前端把进度写入 localStorage（断线/刷新后可恢复）：
  - 参考：`mumu/MuMuAINovel/frontend/src/components/AIProjectGenerator.tsx:68-90`
- 后端在 Project 上持久化 `wizard_status / wizard_step`：
  - 参考：`mumu/MuMuAINovel/backend/app/models/project.py:21-22`

#### 2) 生成过程可视化（SSE 流式进度）
- 后端用 SSE 防超时，把"进度/片段/结果"分事件发送：
  - 参考：`mumu/MuMuAINovel/backend/app/api/wizard_stream.py`（进度事件 + wizard_step 更新点 `:215-246`、`:1049-1050`）
- 前端用 `ssePost` 消费流式响应：
  - 参考：`mumu/MuMuAINovel/frontend/src/utils/sseClient.ts`

#### 3) "先把 API Key 配好再开始生成"
- mumu 的 Settings 支持保存 key、测试连接、拉模型列表：
  - 前端：`mumu/MuMuAINovel/frontend/src/pages/Settings.tsx`
  - 后端：`mumu/MuMuAINovel/backend/app/api/settings.py:37-60`、`:/test`（`settings.py:309`）

#### 4) 多人登录与会话管理
- 前端路由保护与会话续期：
  - `mumu/MuMuAINovel/frontend/src/components/ProtectedRoute.tsx`
  - `mumu/MuMuAINovel/frontend/src/utils/sessionManager.ts`
- 后端 Cookie 注入 user_id：
  - `mumu/MuMuAINovel/backend/app/middleware/auth_middleware.py`

**客观提醒（mumu 的代价/你不一定要照搬的点）**
- mumu 的实现复杂度高：SSE + 大文件组件（`AIProjectGenerator.tsx` 900+ 行）+ 多路功能；照搬会让 demo 维护成本飙升。
- demo MVP 的正确策略是：先"补串联层"，再按需引入 SSE/向导持久化/登录。

---

## 3. 面向 demo 的"流程升级方案"（按 MVP 可控复杂度分层）

> 下面给三层方案：你可以从 **A 层（纯前端编排）**开始，几乎不动后端就能获得"丝滑流程"；再视需要升级到 B/C。

### 3.A 方案（已基本落地）：纯前端"开工向导 + 完成度"编排

**当前状态**：已实现。

**已有文件**：
- `demo/frontend/src/pages/ProjectWizardPage.tsx`（342行）
- `demo/frontend/src/services/wizard.ts`（162行）

**已实现功能**：
- 7步向导清单
- 完成度百分比计算
- 步骤跳过/撤销跳过
- 一键开工（自动生成大纲 + 创建章节）
- 继续按钮跳转到下一步

**可进一步优化**：
- Dashboard 项目卡片展示完成度徽章
- 未完成向导项目的特殊标记

---

### 3.B 方案（中等改动）：后端持久化 `wizard_status/wizard_step`

**为什么要做**
- 纯前端判定会受"用户删数据/换浏览器/多用户"影响
- 持久化后 Dashboard 能稳定展示"继续向导"
- 为 Phase 2 多用户做准备

**建议改动（后端）**

1) 给 `Project` 增字段（参考 mumu）
   - demo 位置：`demo/backend/app/models/project.py:10-19`
   - 参考：`mumu/MuMuAINovel/backend/app/models/project.py:21-22`
   - 字段建议：
     ```python
     wizard_status: Mapped[str] = mapped_column(String(20), default="incomplete")  # incomplete|completed
     wizard_step: Mapped[int] = mapped_column(Integer, default=0)  # 0..7
     ```

2) Alembic 增量迁移
   - 在 `demo/backend/alembic/versions/` 新增 migration

3) projects API 返回这两个字段
   - 修改 `demo/backend/app/schemas/projects.py`

**建议改动（前端）**
- Dashboard 点击项目：
  - 若 `wizard_status === "incomplete"` → `/projects/:id/wizard`
  - 否则 → `/projects/:id/writing`
- 参考：`mumu/MuMuAINovel/frontend/src/pages/ProjectList.tsx:121-127`

---

### 3.C 方案（进阶）：引入 SSE/流式进度

**什么时候值得做**
- 当你出现"生成接口经常超时、用户不知道卡在哪、想支持断线续跑"的需求时

**可借鉴的关键实现点（不要全抄，挑你需要的）**
- 后端 SSE 事件协议（progress/chunk/result/error/done）：`mumu/MuMuAINovel/frontend/src/utils/sseClient.ts:1-170`
- wizard_stream 里"生成→解析→更新 wizard_step→发送 done"的结构：`mumu/MuMuAINovel/backend/app/api/wizard_stream.py`（关注 `wizard_step` 更新行：`:215-246`、`:327`、`:1050`）

**落到 demo 的最小切入点**
- 先只给"章节生成"加 stream（替代一次性返回），前端写作页即可做到更丝滑的 Ghostwriter 效果
- 再考虑把 outline_generate 做成 stream

---

## 4. 多人/登录/存储（只做 MVP 级别学习与预留，不强行一次性上满）

### 4.1 demo 当前"local-user"链路（客观评价）

这是 `demo/mvp开发计划.md` 明确允许的 MVP 方案（Phase 2 才登录），demo 也做了必要预留：
- 后端固定 user_id：`demo/backend/app/api/deps.py:15-23`
- 后端启动时创建本地用户，保证外键完整：`demo/backend/app/main.py:101-110`
- 前端所有本地存储 key 都带 user_id 前缀（未来可切到真实用户）：
  - 主题：`demo/frontend/index.html:11-20`、`demo/frontend/src/services/theme.ts:8-9`
  - LLM Key：`demo/frontend/src/services/llmKeyStore.ts:3-7`
  - 侧边栏折叠：`demo/frontend/src/components/layout/AppShell.tsx:22-24`
  - 向导进度：`demo/frontend/src/services/wizard.ts:35-45`

### 4.2 Phase 2 最小登录方案（按 `demo/mvp开发计划.md` 第 14 章）

**建议你"照着计划做"，不要被 mumu 的复杂度带偏**
- 计划已经给出最小接口集：`POST /api/auth/register|login|logout` + `GET /api/auth/me`（见 `demo/mvp开发计划.md` 14.1）
- demo 的数据隔离基础已经在模型层具备（`projects.owner_user_id`）并且 deps 里有 `require_owned_*` 封装（`demo/backend/app/api/deps.py:26-54`）

**你可以从 mumu 借鉴什么（而不是照抄）**
- 中间件把 user_id 注入到 request.state，业务代码就不用每个接口重复解析 cookie/header：
  - `mumu/MuMuAINovel/backend/app/middleware/auth_middleware.py:14-46`
- 前端路由保护 + 会话续期体验：
  - `mumu/MuMuAINovel/frontend/src/components/ProtectedRoute.tsx`
  - `mumu/MuMuAINovel/frontend/src/utils/sessionManager.ts`

### 4.3 API Key 管理升级路径（MVP → 生产）

**MVP（v2.4 契约）**
- Key/URL 等贵重信息落库到后端数据库（推荐：`llm_profiles` 配置库），前端不再依赖 localStorage 作为唯一来源；响应只回 `has_api_key/masked_api_key`。
- `demo/frontend/src/services/llmKeyStore.ts` 可保留为“临时 override”（兼容旧规则/调试），但不应作为默认路径。

**生产/多人阶段（建议二选一）**
1) 不落库：每次生成临时输入 Key（或只保存在内存，刷新即失）
2) 后端加密存储：参考 mumu "settings 保存 key" 思路，但必须加密：
   - mumu 后端 settings：`mumu/MuMuAINovel/backend/app/api/settings.py:44-84`
   - mumu 前端 settings：`mumu/MuMuAINovel/frontend/src/pages/Settings.tsx`
   - **注意**：mumu 当前是明文存储 `api_key`（安全问题），生产环境必须加密

### 4.4 mumu 多用户实现详解（可学习要点）

基于深入分析，mumu 的多用户系统包含：

**认证方式**：
- LinuxDO OAuth2 登录（`auth.py:307-326`）
- 本地账户登录（`auth.py:81-191`）

**Session 管理**：
- Cookie-based，httponly（`auth.py:162-185`）
- 2小时有效期，支持刷新（`auth.py:329-391`）

**数据隔离**：
- 所有表都有 `user_id` 字段
- API 查询强制 `WHERE user_id = current_user_id`
- 中间件自动注入 user_id 到 `request.state`

**可借鉴点**：
```python
# mumu/MuMuAINovel/backend/app/middleware/auth_middleware.py:14-46
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        user_id = request.cookies.get("user_id")
        if user_id:
            user = await user_manager.get_user(user_id)
            if user and user.trust_level != -1:  # 非禁用用户
                request.state.user_id = user_id
                request.state.user = user
                request.state.is_admin = user.is_admin
        # ...
```

---

## 5. 代码维护性/质量（只提"对 MVP 价值最高"的改进）

### 5.1 前端：大文件组件应拆分

**现状（行数级别）**
- `demo/frontend/src/pages/PromptsPage.tsx`：约 670 行
- `demo/frontend/src/pages/WritingPage.tsx`：约 917 行
- `demo/frontend/src/pages/OutlinePage.tsx`：约 358 行
- `demo/frontend/src/pages/ProjectWizardPage.tsx`：约 342 行

**建议拆分方式（不改变业务语义）**
- 把"数据拉取 + dirty/baseline 比较 + 保存"提取为自定义 hook（例如 `usePromptsState(projectId)`）
- 把 UI 区块拆成组件：`LlmPresetForm`、`PromptTemplateEditor`、`PromptPreviewPanel`、`RunHistoryDrawer` 等

**参考 mumu 的组件拆分**：
- 组件目录：`mumu/MuMuAINovel/frontend/src/components/`
- 专门化组件：`AIProjectGenerator.tsx`、`ChapterRegenerationModal.tsx`、`SSEProgressModal.tsx` 等

### 5.2 前端：把 user_id 从"散落常量"集中管理（已完成）

**当前状态**：已实现单点来源。

**代码位置**：`demo/frontend/src/services/currentUser.ts`
```typescript
export const DEFAULT_USER_ID = "local-user";
export const AUTH_USER_ID_STORAGE_KEY = "ainovel::auth::user_id";

export function getCurrentUserId(): string {
  return localStorage.getItem(AUTH_USER_ID_STORAGE_KEY) ?? DEFAULT_USER_ID;
}
```

### 5.3 后端：固定 local-user 的实现已正确

demo 后端当前做法是正确的 MVP 口径：
- user_id 依赖注入点唯一：`demo/backend/app/api/deps.py:18-23`
- 本地用户创建也集中在 startup：`demo/backend/app/main.py:101-110`

**Phase 2 改造时仍保持"单点替换"**
- 只改 `get_current_user_id()`：从 token/cookie 解析真实用户
- 其余业务路由继续使用 `UserIdDep`，不需要全仓库搜索替换

### 5.4 状态管理对比

| 维度 | demo | mumu | 建议 |
|------|------|------|------|
| 方案 | React Context | Zustand | demo 可升级到 Zustand |
| 覆盖 | 仅 Projects | 多集合（projects, outlines, characters, chapters） | 按需扩展 |
| 缓存 | 无 | 时间戳追踪 | 可参考 mumu 的 `lastUpdated` 机制 |
| Hooks | 基础 | 完整的 Sync Hooks | 可参考 `mumu/frontend/src/store/hooks.ts` |

### 5.5 API 客户端对比

| 维度 | demo | mumu | 建议 |
|------|------|------|------|
| 实现 | 自定义 fetch 封装（104行） | axios + 拦截器（733行） | demo 方案简洁高效 |
| 错误处理 | 自定义 ApiError 类 | HTTP 状态码映射 + message.error | 可增强错误分类 |
| 模块化 | 单文件 | 24个 API 模块 | 按需拆分 |

### 5.6 缺少的关键功能

**demo 缺少而 mumu 有的**：
1. Error Boundary 组件
2. Loading Skeleton / 骨架屏
3. 单元测试覆盖
4. 操作审计日志

---

## 6. 推荐实施顺序（按收益/风险排序）

### Sprint P0（1-2小时）- 修复代码错误

1. 修复 `OutlinePage.tsx` useCallback 依赖（1.7）
2. 修复 `PromptsPage.tsx` 正则表达式（1.8）
3. 修复 `WritingPage.tsx` 字符串逃逸（1.9）
4. 修复 `DashboardPage.tsx` 日期排序（1.10）
5. 修复 `ExportPage.tsx` 资源释放（1.11）

### Sprint P1（1-2天）- 增强健壮性

1. 添加全局 Error Boundary
2. 统一错误处理策略
3. 添加 Loading Skeleton
4. 拆分大文件组件（至少提取 hooks）

### Sprint P2（视需要）- 后端增强

1. 3.B：持久化 wizard_status/wizard_step
2. 4.2：最小登录（按 `demo/mvp开发计划.md` 14.1）
3. 3.C：SSE 流式生成（可选）

---

## 7. 你可以直接参考的 mumu 实现点（精选）

> 只列"对 MVP 最关键、你最想要的丝滑流程"相关点。

### 7.1 流程编排

| 功能 | mumu 位置 | 说明 |
|------|----------|------|
| 未完成向导→继续向导 | `frontend/src/pages/ProjectList.tsx:121-127` | 项目列表点击分流 |
| URL参数恢复生成 | `frontend/src/pages/ProjectWizardNew.tsx:35-44` | 刷新后继续 |
| 向导进度写localStorage | `frontend/src/components/AIProjectGenerator.tsx:68-90` | 断线恢复 |
| Project持久化wizard_step | `backend/app/models/project.py:21-22` | 后端持久化 |
| 后端向导流式API | `backend/app/api/wizard_stream.py:215-246` | SSE实现 |
| SSE客户端协议 | `frontend/src/utils/sseClient.ts` | progress/chunk/result/error/done |

### 7.2 多用户认证

| 功能 | mumu 位置 | 说明 |
|------|----------|------|
| 认证中间件 | `backend/app/middleware/auth_middleware.py:14-46` | user_id 注入 |
| OAuth2 回调 | `backend/app/api/auth.py:307-326` | LinuxDO 登录 |
| 本地账户登录 | `backend/app/api/auth.py:81-191` | 密码验证 |
| 前端路由保护 | `frontend/src/components/ProtectedRoute.tsx` | 未登录重定向 |
| 会话管理 | `frontend/src/utils/sessionManager.ts` | 过期检测+刷新 |

### 7.3 状态管理

| 功能 | mumu 位置 | 说明 |
|------|----------|------|
| Zustand Store | `frontend/src/store/index.ts` | 集中状态管理 |
| Sync Hooks | `frontend/src/store/hooks.ts` | 自动API+状态同步 |
| 类型定义 | `frontend/src/types/index.ts` | 696行完整类型 |

### 7.4 代码质量

| 功能 | mumu 位置 | 说明 |
|------|----------|------|
| 日志格式化 | `backend/app/logger.py` | 彩色+中文注释 |
| 连接池优化 | `backend/app/config.py:46-62` | 支持150-200并发 |
| HTTP客户端复用 | `backend/app/services/ai_service.py:14-79` | 连接池管理 |

---

## 8. demo vs mumu 整体对比评分

| 维度 | demo | mumu | 说明 |
|------|------|------|------|
| 代码组织 | 7/10 | 9/10 | mumu 更规范完整 |
| 代码风格 | 8/10 | 8/10 | 都很规范 |
| 错误处理 | 8/10 | 8/10 | 各有特色 |
| TypeScript类型 | 7/10 | 9/10 | mumu 类型定义详尽 |
| 状态管理 | 6/10 | 9/10 | mumu Zustand 完整生态 |
| API设计 | 7/10 | 9/10 | mumu 功能更全 |
| 组件复用性 | 8/10 | 8/10 | demo 通用性强 |
| 性能优化 | 6/10 | 9/10 | mumu 系统级优化 |
| 依赖管理 | 9/10 | 8/10 | demo 更轻量 |
| 可维护性 | 7/10 | 7/10 | 都需要更多文档 |
| **综合** | **7.3/10** | **8.4/10** | mumu 整体更成熟 |

**demo 的优势**：
- 轻量级，加载快
- 代码简洁，易于理解
- MVP 定位清晰，不过度工程化

**mumu 的优势**：
- 功能完整，覆盖面广
- 多用户支持成熟
- 系统级性能优化
- SSE 流式生成体验好

---

## 9. 后续跟进事项

### 已完成

- [x] 侧边栏折叠/展开修复
- [x] 图标去重
- [x] 路由 index redirect
- [x] 开工向导页面
- [x] 一键开工功能
- [x] user_id 单点管理

### 待完成

- [ ] 修复代码错误（1.7-1.11）
- [ ] 添加 Error Boundary
- [ ] 添加 Loading Skeleton
- [ ] 拆分大文件组件
- [ ] 后端持久化 wizard_status（3.B）
- [ ] SSE 流式生成（3.C，可选）
- [ ] Phase 2 登录功能

---

*文档维护：每次代码改动后同步更新本文件的"已落地"和"待完成"清单。*
