---
mode: plan
task: "Full audit: UI + save + RAG rerank + background tasks"
created_at: "2026-01-31T05:41:03+08:00"
complexity: complex
---

# Plan: 全量细致审计与 Issue 拆分（UI/滚动条/写作保存/RAG embedding+rerank/世界书/标注回溯/数值表格/图谱/搜索/无感更新/测试）

## Goal
- 对照 `完整任务要求.txt` + `错误信息.txt` + `实际测试发现错误.md` + `前端完全优化问题发现.md` + 你口述现象，输出 **“现状 -> 问题 -> 根因 -> 修改方案 -> 可验证 Issue”** 的一一映射。
- 生成可执行 Issue CSV：**所有 Issue 完成 = 你提出的每个点都被落实/修复**（只修复/补齐；不删功能；必要时仅做兼容性重命名/重定向并保留旧入口）。
- 把“为什么现在测试测不出来”转化为：E2E/Contract/A11y/Style 守门（让 UI/保存/任务/索引链路回归可被自动发现）。
- 现状基线（2026-01-31）：`cd test; npm test` **110/110 通过**，但你反馈的 UI/保存/无感更新问题仍存在，说明当前测试缺少“样式守门/保存阻塞/任务可观测性”等断言（本计划将其拆成可执行 Issue）。

## 二次深入调研新增确认（代码级证据）

> 本节是对“粗糙拆分”的补强：把你点名的 UI/保存/RAG/无感更新问题落到 **可定位的代码行为**，并直接反映到本次 CSV（见 `issues/2026-01-31_05-41-03-full-audit-ui-save-rag-tasks.csv`）。

### UI（默认蓝色/默认滚动条/风格不统一）
- “默认蓝色选中态”：当前 `frontend/src/index.css` 未定义 `::selection`，浏览器回退到默认高亮色（你反馈的蓝色选中）。→ Issue：`AUDIT-009`。
- “默认滚动条”：当前未定义任何 scrollbar 样式（`::-webkit-scrollbar` / `scrollbar-color`），Drawer/Markdown/Debug `<pre>` 等滚动区域都使用浏览器默认。→ Issue：`AUDIT-010`。
- SearchPage（你点名的搜索页 UI）：
  - 搜索/跳转按钮使用 `className="btn-primary"` 但缺少 `btn` 基类，导致 padding/交互/聚焦样式不一致：`frontend/src/pages/SearchPage.tsx:185`、`:250`。→ Issue：`AUDIT-014`（并在本次 CSV 拆分为更小粒度子 Issue）。
  - 来源筛选 checkbox 未使用 `.checkbox`（其余页面基本已统一），会出现默认 accent 色：`frontend/src/pages/SearchPage.tsx:212`。→ Issue：`AUDIT-014` + `AUDIT-011`。
- 标注回溯侧栏（MemorySidebar）也存在“checkbox 未主题化”的遗漏：
  - 合并条目选择框当前仅 `className="mt-1"`，缺少 `.checkbox`，会回退默认 accent（蓝色）：`frontend/src/components/chapterAnalysis/MemorySidebar.tsx:714`。→ Issue：`AUDIT-016`（并在 CSV 中补充更细粒度修复点）。
- StructuredMemoryPage 存在表单控件 class 误用（影响 focus/hover/一致性）：
  - 多处 `<select className="input">`（应为 `.select`）：例如 `frontend/src/pages/StructuredMemoryPage.tsx:500`、`:530`、`:681`。→ 本轮将新增更细粒度 Issue（见本次 CSV 更新：`AUDIT-091`）。

### 写作保存/定稿（你点名“保存混乱/失灵/定稿草稿无效”）
- 保存函数层（根因候选 1：用户体感“点了没反应”）：
  - `frontend/src/pages/writing/useChapterEditor.ts:168` 起：`savingRef.current` 为 true 时会 **queue 保存并直接 `return false`**（不会 toast）。
  - `frontend/src/pages/WritingPage.tsx:408` 起：顶部“保存”按钮仅 `disabled={!dirty || loadingChapter}`，未绑定 `saving`，导致保存中仍可点击但无反馈。→ Issue：`AUDIT-019`（需进一步拆分：按钮禁用/状态文案/排队反馈/最终落库）。
- 后端层（根因候选 2：保存请求被“无感更新”阻塞）：
  - `backend/app/api/routes/chapters.py`：章节更新保存后会 schedule `vector_rebuild/search_rebuild`（以及 status=done 的 bundle）。
  - `backend/app/services/task_queue.py`：`TASK_QUEUE_BACKEND=inline` 时会 **同步执行** `search_rebuild/worldbook_auto_update/graph_auto_update/table_ai_update` 等 project_task，导致保存延迟上升，前端进入 saving 状态后用户反复点击更像“失灵”。→ Issue：`AUDIT-006`（inline 队列执行策略重审，改为 in-process 后台 worker 并保持 SQLite 单 worker 约束）。
- 定稿/草稿（根因候选 2：用户体感“切了也不管用”）：写作页在 `status=done` 时编辑任一字段会自动回退为 `drafting` 并 toast 警告：`frontend/src/pages/WritingPage.tsx:419` 起。若用户先切 done 再继续编辑，状态会被自动回退。→ Issue：`AUDIT-020`（需要明确 UX：定稿锁定/编辑定稿的“复制为草稿”路径/文案）。

### RAG rerank（你点名“rerank 不可配/不可测/没用大模型”）
- “模型配置页缺 rerank 模型配置”：PromptsPage（模型配置页）仅提供 rerank enabled/method/top_k；rerank provider/base_url/model/api_key/timeout/alpha 在 SettingsPage 才有，入口割裂且不符合你要求的“模型配置页一次配齐”。→ Issue：`AUDIT-025`（需要拆分 UI/字段/校验/掩码/迁移说明）。
- “external rerank 可能永远不生效”：后端 vector 路由对 rerank 配置读取 **只取 enabled/method/top_k**：`backend/app/api/routes/vector.py:_vector_rerank_config`；但 `backend/app/services/vector_rag_service.py` 实际支持 `external_rerank_api`（`backend/app/services/rerank_service.py`）。→ Issue：`AUDIT-026`（补齐 provider/base_url/model/api_key/timeout/alpha，并确保不泄露密钥）。
- “embedding/rerank 无法测试”：目前缺少 embedding/rerank 的 dry-run 测试端点与 UI；E2E mock 也缺 `/rerank`。→ Issues：`AUDIT-027`~`AUDIT-031`（需拆分接口/前端按钮/Mock/E2E 断言）。

## Audit Matrix（需求点 -> 当前实现 -> 已确认缺口 -> Issue 覆盖策略）

> 目的：避免“凭感觉拆 Issue”。每条都落到代码与可验证行为；Issue CSV 会按本矩阵展开。

### 1) 世界书 AI 注入/自动更新（完整任务要求：第一大点）
- 当前实现：
  - 后端存在 `worldbook_auto_update` ProjectTask + 解析/落库逻辑：`backend/app/services/worldbook_auto_update_service.py`。
  - 章节定稿会触发任务编排：`backend/app/services/project_task_service.py:263`（包含 worldbook_auto_update）。
  - 前端存在“预览触发/手工触发/任务中心”相关入口：`frontend/src/pages/WorldBookPage.tsx`、`frontend/src/pages/TaskCenterPage.tsx`。
  - E2E 已覆盖“自动更新 fail-soft”基础行为：`test/specs/ui/worldbook-auto-update-failsoft.spec.ts`。
- 已确认缺口：
  - 任务失败错误信息为空（`错误信息.txt`），导致“无感更新失败但不可定位”。
  - dev 默认队列为 `rq`（无 Redis/worker 时会失败）；inline 下又存在“部分任务不执行/或阻塞请求”的矛盾。
  - auto_update 的 **existing worldbook 上下文只提供 titles**（未提供已存在条目内容/关键词等），对“避免多/漏/重复/更新不准”不利（需引入更充分的候选条目上下文与更强的去重/合并策略，并用回归测试固化）。
- Issue 覆盖策略：
  - 先修可观测性与队列默认行为（让失败可见、可重试、dev 默认能跑）。
  - 再做 worldbook prompt 与 apply 策略增强 + 回归测试（E2E + 后端 contract/单测）。

### 2) 标注回溯页（完整任务要求：第二大点）
- 当前实现：
  - 页面与侧栏：`frontend/src/pages/ChapterAnalysisPage.tsx` + `frontend/src/components/chapterAnalysis/MemorySidebar.tsx`。
  - 后端提供标注 API：`backend/app/api/routes/chapter_analysis.py`（`/chapters/{chapter_id}/annotations`）。
  - “剧情记忆（StoryMemory）”后端已有 CRUD：`backend/app/api/routes/story_memory.py`；E2E 覆盖：`test/specs/ui/chapter-analysis-story-memory-crud.spec.ts`。
- 已确认缺口（来自你的反馈 + 审计报告）：
  - 页面存在横向溢出/布局不适配；侧栏下方空白过多；需要更优布局（以“常规浏览器宽度无横向滚动”为硬验收）。
  - 标注高亮颜色存在 hard-coded（违背 token 化方向）：`frontend/src/components/chapterAnalysis/AnnotatedText.tsx`。
  - checkbox/selection/scrollbar 等未完全主题化（体感“默认蓝色/默认滚动条”）。
- Issue 覆盖策略：
  - 用 E2E 增加“无横向滚动/布局不溢出”守门（scrollWidth<=clientWidth）。
  - 分拆布局/交互/可编辑性优化（每个 commit 小步落地），并统一 request_id 可复制等排障路径。

### 3) “结构化记忆/表格”系统（完整任务要求：第三大点）
- 当前实现（关键澄清，避免误拆 Issue）：
  - **图谱底座（StructuredMemory）**：entities/relations/events/foreshadows/evidence，对应 `frontend/src/pages/StructuredMemoryPage.tsx` 与 `backend/app/models/structured_memory.py`。
  - **数值表格系统（NumericTables）**：project_tables / project_table_rows + `table_ai_update`，对应：
    - `frontend/src/pages/NumericTablesPage.tsx`
    - `frontend/src/components/writing/TablesPanel.tsx`
    - `backend/app/models/project_table.py`
    - `backend/app/services/table_ai_update_service.py`
- 已确认缺口：
  - 需求强调的“数值化记录（钱/时间/战力等）”需要成为主线能力：UI/IA 仍需更明确的区分与引导。
  - “章节定稿自动触发 table_ai_update”目前缺失，需要设计：哪些表默认自动更新、如何避免任务风暴、如何失败可回滚。
- Issue 覆盖策略：
  - 先做 IA/命名与入口清晰化（减少误解）。
  - 再补齐“自动更新：按表开关 + fail-soft + 变更集 apply/rollback”闭环，并加 E2E/contract。

### 4) 向量 RAG（完整任务要求：第四大点）
- 当前实现：
  - Embedding 项目覆盖配置：PromptsPage：`frontend/src/pages/PromptsPage.tsx`（E2E：`test/specs/ui/prompts-rag-config.spec.ts`）。
  - Rerank 提供方/模型/API key 项目覆盖配置：SettingsPage：`frontend/src/pages/SettingsPage.tsx`（E2E：`test/specs/ui/settings-rerank-config.spec.ts`）。
  - RAG 管理与 query/debug：`frontend/src/pages/RagPage.tsx`。
  - 后端支持 external rerank API：`backend/app/services/rerank_service.py`（`/rerank`）。
- 已确认缺口（功能性 P0）：
  - `vector/query` 传入的 rerank config 口径过窄，导致 external rerank 不可能生效：
    - `backend/app/api/routes/vector.py:56`（仅 enabled/method/top_k）
    - `backend/app/services/memory_retrieval_service.py:75`（完整：provider/base_url/model/api_key/timeout/hybrid_alpha）
  - embedding / rerank 缺少“测试连接/测试效果”的端点与 UI（当前只有 `/api/llm/test`）。
  - mock-llm 缺少 `/v1/rerank`，导致 E2E/本地无法验证 external rerank。
- Issue 覆盖策略：
  - 先统一后端 config 口径 + 增加 embedding/rerank dry-run 测试端点 + mock 支持。
  - 再做 UI 入口整合（避免 embedding 在 Prompts、rerank provider 在 Settings、query 在 Rag 的碎片化）。

### 5) 图谱（完整任务要求：第五大点，必须联网调研）
- 当前实现：
  - 有 GraphPage + 图谱底座表（entities/relations/evidence）+ `graph_auto_update` ProjectTask：`backend/app/services/graph_auto_update_service.py`。
  - E2E 覆盖图谱页面与角色关系编辑：`test/specs/ui/graph-page.spec.ts`、`test/specs/ui/graph-character-relations-editor.spec.ts`。
- 已确认缺口：
  - `错误信息.txt` 表明 graph_auto_update 任务失败且 message 为空（可观测性/队列优先）。
  - 需形成“小说人物关系抽取”数据模型/证据溯源/编辑 UX 的明确设计文档（本轮已做初步联网调研，后续固化为 repo 文档并落地）。
  - `graph_auto_update` 当前对 MemoryUpdate ops 的 `target_table` 白名单仅允许 `entities/relations/evidence`：`backend/app/services/graph_auto_update_service.py:282`，未允许 `events`。而人物关系在叙事中常是 n-ary（带时间/地点/事件语境）——更适合用“事件节点/证据”建模并回放。→ 本轮将新增更细粒度 Issue（见本次 CSV 更新：`AUDIT-092`）。

### 6) 术语表/高级调试重构为强力搜索引擎（完整任务要求：第六大点）
- 当前实现：
  - 有全局搜索：`frontend/src/pages/SearchPage.tsx` + 后端索引：`backend/app/services/search_index_service.py`。
  - 仍存在 GlossaryPage（术语映射）且 IA 存在“search/glossary 双入口同名/重复能力”的混乱：`frontend/src/lib/routes.ts` + `frontend/src/lib/uiCopy.ts`。
- 已确认缺口：
  - search_index 覆盖源不足（缺数值表格/图谱等更多来源）。
  - SearchPage 存在明显样式与一致性缺陷（按钮 class、checkbox、selection、滚动条等）。
- Issue 覆盖策略：
  - 先合并 IA（一个入口：搜索引擎；术语映射作为子能力）。
  - 再扩展索引覆盖与模糊搜索/排序策略，并补 E2E。

## Scope
- In:
  - Frontend（React/Tailwind）：
    - 全站一致性收敛（按钮/输入/选中态/checkbox/selection/scrollbar/动效 token）。
    - 页面布局溢出与 scroll trap 修复（尤其是标注回溯/写作/阅读）。
    - 写作保存/定稿体验：避免“按钮看似可点但无反馈”与“自动回退草稿造成误解”。
    - RAG 配置入口整合与测试入口补齐（embedding/rerank）。
    - A11y 基线：表单 id/name、键盘可达性等。
  - Backend（FastAPI/SQLite/Alembic）：
    - 任务系统：ProjectTask/MemoryTask 的失败信息可见（不为空）、队列状态可观测、失败可重试；dev 默认不依赖 Redis 也能跑（单 worker）。
    - RAG：embedding/rerank 配置口径统一；external rerank 真正生效；提供 embedding/rerank dry-run 测试端点；mock-llm 补齐 `/v1/rerank`。
    - 世界书：auto_update 输入覆盖与去重策略增强；失败不阻断主流程；与写作注入联动可验证。
    - 图谱：graph_auto_update 可跑、可回滚；按调研结果增强 schema/提示词/编辑入口。
    - 数值表格：table_ai_update 可自动触发（按表开关）+ 变更集 apply/rollback + 回归测试。
    - 搜索：索引覆盖面扩展与模糊搜索质量；跳转路径完善。
  - Test（Playwright + contract + a11y/style guard）：
    - 端口冲突处理
    - UI class 断言（避免 btn 基类遗漏）
    - 无横向滚动守门
    - request_id 可复制
    - external rerank 生效验证
- Out:
  - 不做无关重构；不改变业务语义（除非 Issue 中明确列出并同步 E2E/contract）。
  - 不引入重型外部依赖（例如 Neo4j）；不做“测试专用逻辑”。

## Assumptions / Dependencies
- 以当前仓库实现与既有测试用例为事实基线：`test/specs/**` 已覆盖部分关键链路（Search/Prompts RAG/Settings rerank key masking/Writing unsaved confirm 等），但**仍缺少**“视觉/样式守门”“保存/定稿状态回归”“external rerank 生效验证”等（对应本次新增 Issue）。
- 当前前端已有 Atelier tokens 与基础 class（`btn/input/select/textarea` 等），但缺少全局 `::selection/scrollbar`，且部分页面未统一使用 base class（例如 SearchPage）。
- 队列：dev 默认 `task_queue_backend=rq` 与“普通用户不想装 Redis/worker”的预期冲突；必须提供“默认能跑”的 dev fallback，同时避免 inline 同步执行导致保存/写作卡顿。
- SQLite：单 worker；任何 LLM/外部调用不得持有长事务（遵守 README）。

## Phases
1. Phase 0：事实与守门（先让“错了能看见”）
   - 任务失败 message 不为空（AppError/TaskCenter/日志）。
   - 队列状态可观测（health/status）+ 前端可提示“为何无感更新不运行”。
   - E2E 端口冲突可恢复（自动选端口/可配置端口）。
2. Phase 1：队列与无感更新“默认能跑”（dev 不依赖 Redis）
   - inline 队列改为“单线程后台 worker（in-process）”：避免阻塞保存/写作，同时让 vector_rebuild/memory_task 等也能跑。
   - 章节定稿触发的任务编排补齐（worldbook/graph/search/vector/table/…），并确保幂等/可重试。
3. Phase 2：UI 全局一致性（Paper & Ink / Atelier）
   - 全局 `::selection`、scrollbar、checkbox/radio accent、focus-visible ring 统一。
   - 统一语义色（warning/danger/info），替换 hard-coded amber/red/sky。
   - A4 纸面宽度策略：按 route layout 收敛（写作/阅读/预览/大纲等）。
4. Phase 3：写作体验（保存/定稿/自动更新反馈）
   - 保存按钮与 saving 状态：可见/可解释/不会“看似可点但无反馈”。
   - 定稿（done）与编辑策略：防“自动回退草稿”造成误解；提供明确交互（锁定/解锁/复制为草稿）。
   - 定稿后自动任务：可见（TaskCenter/Toast）、失败可重试，不阻塞编辑。
5. Phase 4：RAG（embedding+rerank 真正可用 + 可测试）
   - 统一 rerank config 口径（vector/query 与写作注入一致，支持 external rerank API）。
   - 增加 embedding/rerank dry-run 测试端点与 UI；mock-llm 补 `/v1/rerank`；E2E 锁定。
6. Phase 5：世界书自动更新质量与可控性
   - 提升 prompt 输入与去重策略；保证不捏造/不漏；失败不影响主流程；与写作注入联动可验证。
7. Phase 6：数值表格系统（数值化记录主线 + 自动更新）
   - IA 清晰化（与图谱底座区分）；按表开关自动更新；变更集 apply/rollback；检索注入与搜索索引覆盖。
8. Phase 7：图谱系统调研 + 落地
   - 输出 repo 内设计文档（数据模型/抽取策略/证据溯源/编辑 UX）；落地到 SQLite property graph（必要时引入 event 视角但不引入重型外部 DB）。
9. Phase 8：搜索引擎（替代/重构术语表）
   - 统一入口（Search）；术语映射作为子能力；索引覆盖更多 source（表格/图谱/更多）+ 模糊搜索/排序；跳转完善。
10. Phase 9：测试体系增强与回归闸门
   - 为 UI/无感更新/RAG external rerank/保存等补齐 E2E/contract/a11y/style guard；形成稳定回归集。

## Tests & Verification
- Backend：
  - `cd backend`
  - `.\.venv\Scripts\python.exe -m compileall -q app alembic`
  - `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- Frontend：
  - `cd frontend`
  - `npm run lint`
  - `npm test`
  - `npm run build`
- E2E：
  - 说明：E2E 依赖后端/前端/Mock LLM 的端口；若端口被占用会导致全套失败。本批次会通过 `AUDIT-054` 把端口选择变为“可配置/可自动避让”。
  - `pwsh test/run-all.ps1`
  - 本轮已跑通：`cd test; npm test`（110 passed）

## Issue CSV
- Path: issues/2026-01-31_05-41-03-full-audit-ui-save-rag-tasks.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- `web.run`：图谱/检索建模调研（按 `AUDIT-045` 执行并固化到 repo 文档）。
- `chrome-devtools:*`：复核 UI 溢出/点击命中/遮罩层级（WorldBook 预览触发等）。
- `context7:*`：查阅 Playwright/React/库文档（按需）。
 - 备注：本轮已做一次初步联网检索（property graph vs RDF、n-ary relation/event 建模、GraphRAG 抽取范式等），结论将在 `AUDIT-045` 以“可复用的决策记录”形式固化。

## Acceptance Checklist
- [ ] 任务失败信息不再为空；TaskCenter 能看到可复制的 error_type/code/message（不泄露密钥）。
- [ ] dev 默认无需 Redis/worker 也能跑“章节定稿触发的无感更新”；且不会阻塞保存/写作交互。
- [ ] 全站无“默认蓝色选中态/默认原生控件样式”；`::selection` 与 scrollbars/checkbox/radio 符合 Atelier 风格。
- [ ] 写作页保存/定稿/草稿状态切换可靠且可解释；“保存按钮看似可点但无反馈”的情况消失。
- [ ] 世界书 AI 自动更新可跑、可回滚、失败可见且不阻塞；与写作注入联动可验证。
- [ ] 标注回溯页无横向滚动；侧栏布局不留大块空白；剧情记忆 CRUD 与 worldbook 数据边界清晰。
- [ ] 数值表格聚焦“数值化记录”：可编辑 + AI 自动更新（按表开关）+ apply/rollback。
- [ ] RAG：embedding+rerank 都能配置与测试；external rerank 真正生效（vector/query 与写作注入一致），并由 E2E 锁定。
- [ ] 搜索引擎覆盖更多数据源并支持模糊搜索；Glossary/Search IA 不再混乱。
- [ ] E2E 端口占用不再导致全套失败；新增 a11y/style guard 能捕获本轮关键回归。

## Risks / Blockers
- UI 风格/布局改动跨面广：必须按页面/组件分批提交，每批都配套 E2E/visual/style guard，避免“修一处坏十处”。
- 队列：既要 dev 默认可用，又要 prod 可靠；inline 后台 worker 需要确保单线程/可停止/不吞异常。
- RAG rerank：链路涉及 Settings/Prompts/RagPage + `vector/query` + 写作注入；需 contract/E2E 锁定“确实走 external rerank”。
- IA：Glossary/Search、StructuredMemory/Graph/NumericTables 名称与入口调整必须保留兼容路径（路由重定向）并补回归。

## Rollback / Recovery
- 一 Issue 一提交，可 `git revert` 精准回滚。
- DB 变更用 Alembic 管控；如涉及 schema 更新，同步更新 `test/contracts/db_schema.json`。

## Checkpoints
- 每完成一个“主题包”（例如：队列可用性 / UI 基础 / RAG external rerank / 写作保存）跑一次：`pwsh test/run-all.ps1`。

## References
- `完整任务要求.txt`
- `错误信息.txt`
- `ui设计规范.md`
- `前端完全优化问题发现.md`
- `实际测试发现错误.md`
- `frontend/src/index.css`（缺少 `::selection`/scrollbar 等全局样式）
- `frontend/src/pages/SearchPage.tsx:185`（按钮 class 未包含 `btn` 基类）
- `frontend/src/pages/SearchPage.tsx:212`（来源 checkbox 未使用 `.checkbox`）
- `frontend/src/pages/WritingPage.tsx:368`（bg-white 与主题不一致）
- `frontend/src/pages/writing/useChapterEditor.ts:168`（savingRef+queue return false -> 体感“保存失灵”风险）
- `frontend/src/components/chapterAnalysis/MemorySidebar.tsx:714`（merge checkbox 未使用 `.checkbox`）
- `frontend/src/pages/StructuredMemoryPage.tsx:500`（`<select className=\"input\">` 误用）
- `backend/app/services/task_queue.py:16`（inline 同步执行 project_task -> 保存/写作卡顿 & 部分任务不执行）
- `backend/app/core/errors.py:8`（AppError str() 为空 -> TaskCenter error_message 为空）
- `backend/app/api/routes/vector.py:56`（rerank config 口径过窄 -> external rerank 不生效）
- `backend/app/services/memory_retrieval_service.py:75`（rerank config 完整口径）
- `backend/app/services/rerank_service.py`（external rerank API `/rerank` 已实现但 UI/路由未打通）
- `backend/app/services/project_task_service.py:263`（chapter_done 任务编排）
- `backend/app/services/worldbook_auto_update_service.py:462`（优先使用 chapter.summary 导致漏信息风险）
- `backend/app/services/graph_auto_update_service.py:282`（graph_auto_update 不允许 events -> 建模能力受限）
- `backend/app/services/search_index_service.py`（搜索索引覆盖范围）
- `test/specs/ui/*`（现有 E2E 覆盖基线：visual smoke 未覆盖 Search/ChapterAnalysis 等）
