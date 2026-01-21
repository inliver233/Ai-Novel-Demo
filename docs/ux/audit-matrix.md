# 审计覆盖矩阵（页面 / 抽屉 / 关键交互）

目的：用可核对的矩阵记录本批次审计覆盖范围，并将每个页面/抽屉绑定到 Issue ID，避免 UX/i18n/IA 改动遗漏。

来源与基线：
- 路由入口：`frontend/src/App.tsx`
- 页面与 API 映射：`docs/ux/ui-api-map.md`（MAP-001）
- IA 规范：`docs/ux/navigation-ia-v1.md`（IA-001）
- 术语/汉化：`docs/ux/glossary.md`（DOC-001）
- 高级调试页规范：`docs/ux/advanced-debug-page-guidelines.md`（DOC-002）

## 页面 / 路由覆盖（frontend/src/App.tsx）

> 说明：Issue IDs 来自 `issues/2026-01-20_19-08-47-full-repo-audit-ux-i18n.csv` 的 `Files` 反查（同一页面可能对应多个 Issue）。

| Route | Page | Issue IDs |
| --- | --- | --- |
| `/login` | `LoginPage` | I18N-001 \| UX-LOGIN-001 |
| `/` | `DashboardPage` | I18N-004 \| UX-DASH-001 |
| `/admin/users` | `AdminUsersPage` | I18N-002 \| UX-ADMIN-001 |
| `/projects/:projectId/wizard` | `ProjectWizardPage` | UX-WIZ-001 |
| `/projects/:projectId/settings` | `SettingsPage` | FORMAT-001 \| I18N-002 \| UX-SET-001 |
| `/projects/:projectId/characters` | `CharactersPage` | UX-CHAR-001 |
| `/projects/:projectId/outline` | `OutlinePage` | UX-OUT-001 |
| `/projects/:projectId/writing` | `WritingPage` | I18N-002 \| UX-WRITE-001 \| UX-WRITE-002 |
| `/projects/:projectId/tasks` | `TaskCenterPage` | FORMAT-001 \| I18N-002 \| I18N-004 \| A11Y-001 \| TASK-001 \| TASK-002 |
| `/projects/:projectId/structured-memory` | `StructuredMemoryPage` | LINT-001 \| FORMAT-001 \| SMEM-001 \| SMEM-002 \| PERF-002 |
| `/projects/:projectId/chapter-analysis` | `ChapterAnalysisPage` | UX-ANNO-001 |
| `/projects/:projectId/preview` | `PreviewPage` | I18N-002 \| UX-PREV-001 |
| `/projects/:projectId/prompts` | `PromptsPage` | UX-PROMPTS-001 |
| `/projects/:projectId/prompt-studio` | `PromptStudioPage` | FORMAT-001 \| UX-PSTUDIO-001 \| MAINT-002 |
| `/projects/:projectId/export` | `ExportPage` | UX-EXP-001 |
| `/projects/:projectId/worldbook` | `WorldBookPage` | LINT-002 \| FORMAT-001 \| UX-WB-001 \| PERF-002 |
| `/projects/:projectId/graph` | `GraphPage` | UX-ADV-001 \| GRAPH-001 \| GRAPH-002 |
| `/projects/:projectId/fractal` | `FractalPage` | FORMAT-001 \| FRACTAL-001 \| FRACTAL-002 |
| `/projects/:projectId/styles` | `StylesPage` | UX-STYLES-001 |
| `/projects/:projectId/rag` | `RagPage` | LINT-002 \| FORMAT-001 \| I18N-004 \| A11Y-001 \| RAG-001 \| RAG-002 \| RAG-003 \| MAINT-003 \| PERF-002 |
| `*` | `NotFoundPage` | I18N-001 \| UX-404-001 |

## 写作抽屉 / 模态覆盖（WritingPage）

> 说明：此处覆盖“写作页抽屉/弹窗/工具栏”等高频交互入口（组件位于 `frontend/src/components/writing/*`）。

| Component | Issue IDs |
| --- | --- |
| `AiGenerateDrawer` | FORMAT-001 \| UX-WRITE-003 |
| `ContextPreviewDrawer` | FORMAT-001 \| MAINT-001 \| UX-WRITE-006 |
| `MemoryUpdateDrawer` | LINT-002 \| UX-WRITE-007 |
| `ForeshadowDrawer` | FORMAT-001 \| UX-WRITE-008 |
| `GenerationHistoryDrawer` | FORMAT-001 \| UX-WRITE-005 |
| `BatchGenerationModal` | UX-WRITE-004 |
| `ChapterAnalysisModal` | UX-WRITE-001 \| UX-ANNO-001 |
| `ChapterListPanel` | UX-WRITE-001 |
| `CreateChapterDialog` | UX-WRITE-001 |
| `WritingToolbar` | UX-WRITE-002 |

## 全局导航 / 容器（可选核对点）

| Component | Issue IDs |
| --- | --- |
| `AppShell`（侧边栏/布局） | I18N-001 \| IA-002 \| IA-003 \| A11Y-001 \| FE-CORE-001 |
| `ProjectProviderGuard`（错误态/无权限提示） | I18N-001 \| I18N-004 \| UX-GUARD-001 |
