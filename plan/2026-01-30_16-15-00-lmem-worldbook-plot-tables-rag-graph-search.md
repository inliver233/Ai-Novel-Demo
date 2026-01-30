---
mode: plan
task: lmem 世界书/记忆/表格/RAG/图谱/搜索引擎 + 自动化后台更新
created_at: "2026-01-30T16:15:00+08:00"
complexity: complex
---

# Plan: 世界书/记忆/表格/RAG/图谱/搜索引擎 + 自动化后台更新（一期）

## Goal
- 章节生成完成/定稿后：世界书条目、剧情记忆、数值表格、图谱、向量 RAG、全项目搜索索引可“静默后台自动更新”；失败不阻断写作主流程，可重试且在 Task Center 可观测。
- 明确边界并隔离：世界书（设定）/剧情记忆（情节）/图谱（实体关系证据）/数值表格（数字化状态）。
- RAG 支持 embedding 与 rerank 项目级独立配置（base_url/key/model 可不同；响应/日志不泄露 key，仅 `has_api_key/masked_api_key`）。
- “术语表（Glossary）”重构为“全项目搜索引擎”；高级调试页信息分层一致（Overview/Actions/Results/Debug）。

## Scope
- In:
  - Backend：`ProjectSettings` 扩展（rerank 独立配置、search/worldbook 自动化开关与 dirty 标记）、搜索索引表/FTS、worldbook 自动更新 API+任务、`StoryMemory` CRUD、graph/table 更新编排、Task Center 任务状态对齐与重试。
  - Frontend：ChapterAnalysis CRUD+布局优化；StructuredMemory 重新定位命名（图谱底座）；新增“数值表格（Advanced Debug）”页；新增“全局搜索”页替代 Glossary；设置页补齐 rerank 配置；Task Center 可观测性改进。
  - E2E：Playwright 覆盖关键黑盒流；DB 迁移同步 `test/contracts/db_schema.json`。
- Out:
  - 不做无关重构/大规模样式翻新。
  - 不引入重型图数据库（Neo4j 等）。
  - 不做“测试专用业务逻辑”。
  - 不改变现有接口字段/枚举，除非明确列为本批 Issue 且同步 E2E contract。

## Assumptions / Dependencies
- SQLite/FTS5 可用；搜索优先使用 FTS5 trigram（支持 substring 匹配）。若运行环境缺失 trigram tokenizer，则提供 fallback（如 LIKE/前缀查询/退化 match）并记录风险。
- 后台任务：dev 可 `TASK_QUEUE_BACKEND=inline`；prod 必须 `rq+redis`（遵守 `README.md`）。
- 复用既有 `memory_change_sets` / `memory_tasks` / RQ worker 作为“后台自动更新”主干（必要时扩展 kind/状态枚举与 UI）。
- SQLite 单 worker；任何 LLM/外部调用不得持有长事务（调用上游前结束事务；返回后再落库）。

## Phases
1. Phase 0（研究 + 规范对齐）
   - 联网调研并沉淀设计决策：小说人物关系图谱建模/编辑体验；SQLite FTS5 trigram/外部内容表与增量更新策略。
   - 统一名词/入口：StructuredMemory（图谱底座） vs 数值表格（project_tables）；Glossary → Search；完善 `UI_COPY` 与导航。
   - Task Center：后端任务状态与前端展示/统计对齐，确保“可观测+可重试”基础可靠。
2. Phase 1（数据/接口/任务编排）
   - RAG rerank 升级：`ProjectSettings` 增加 rerank `provider/base_url/model/api_key(加密)/timeout/hybrid_alpha`；Settings API/前端设置页支持；检索数量/注入数量/权重默认合理且可配置。
   - 搜索引擎：新增统一 Search API（多源聚合+高亮片段+跳转定位），并实现自动更新（dirty 标记+后台 task）。
   - 世界书 AI 注入：章节定稿后自动抽取/对比/新建/更新条目；失败降级不影响写作；提供手动“重试/重建”按钮；任务与错误可在 Task Center 看见。
   - 图谱：以 property graph（entities/relations + attributes/evidence）为核心，补齐人物关系表达与增量更新策略；支持 AI 提取→变更集→应用/回滚。
   - 数值表格：基于 project_tables 提供 Advanced Debug 页面 + AI 更新入口（TableUpdate change set）；与图谱/剧情记忆提示词与数据隔离。
   - 剧情记忆：StoryMemory 完整 CRUD（新增/编辑/删除/合并/标记完成/foreshadow resolve）+ 与回溯页面联动。
3. Phase 2（UX 打磨 + 默认开启 + 回归）
   - ChapterAnalysisPage：修复横向溢出与侧栏空白；补齐 CRUD；空态/错态/加载态符合高级调试规范。
   - 图谱 UI：列表编辑优先（必要时补简易可视化）；支持证据回放（关联章节/引用片段）。
   - Search UI：替换 GlossaryPage；支持范围筛选、模糊查询、结果聚合与定位跳转；保持 E2E 选择器稳定。
   - 自动化默认开启策略：章节定稿/大纲/设定/角色卡变更触发后台更新；失败可重试；普通用户默认获得效果。
   - 全套回归：`pwsh test/run-all.ps1`；DB 合同与 UI 截图按需更新。

## Tests & Verification
- 每条 Issue 的 `Test_Method` 必须可执行（命令或可复现 checklist）。
- Backend：
  - `cd backend`
  - `.\.venv\Scripts\python.exe -m compileall -q app alembic`
  - `.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- Frontend：
  - `cd frontend`
  - `npm run lint`
  - `npm test`
  - `npm run build`
- E2E：`pwsh test/run-all.ps1`
- DB schema 变更：`pwsh test/scripts/snapshot-db.ps1`（并跑相关 E2E）

## Issue CSV
- Path: `issues/2026-01-30_16-15-00-lmem-worldbook-plot-tables-rag-graph-search.csv`
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- `context7:resolve-library-id` / `context7:query-docs`：查 React/TS/SQLite/Playwright 等文档与示例（必要时）。
- `chrome-devtools:*`：黑盒 UI 验证、定位溢出/选择器问题（必要时）。
- 联网调研：PowerShell `Invoke-WebRequest/curl`；把结论写入 References + Issue Notes。

## Acceptance Checklist
- [ ] 世界书：章节定稿后自动抽取/新建/更新条目；失败不阻断；可重试；有手动兜底。
- [ ] 标注回溯页：无横向滚动；侧栏紧凑；StoryMemory CRUD 完整并与世界书隔离。
- [ ] 结构化系统重规划：图谱底座 vs 数值表格系统命名/入口/提示词/数据模型隔离清晰。
- [ ] RAG：embedding 与 rerank 项目级独立配置；rerank 默认启用；索引随内容变化自动更新。
- [ ] 图谱：基于联网调研形成设计；支持 AI 提取+校验+更新；UI 可编辑与证据回放；可降级。
- [ ] 搜索：Glossary 重构为全项目搜索引擎（多源聚合/模糊匹配/定位跳转）。
- [ ] Task Center：可观测后台任务；失败可重试；状态字段一致；无 key 泄露。
- [ ] 全套回归通过并能收口 Regression_Status。

## Risks / Blockers
- FTS5 trigram tokenizer 的可用性与中文效果/性能权衡（需探测与 fallback）。
- RQ/Redis 在本地/CI 的可用性；需 inline fallback 保证主流程不阻断。
- DB schema 扩展带来的迁移/E2E 合同更新成本。
- 图谱可视化范围控制（先列表/编辑/筛选，避免过度投入）。

## Rollback / Recovery
- Issue 粒度：一行一提交；可 `git revert <commit>` 精准回滚。
- DB：Alembic downgrade（如提供）+ 同步回滚 `test/contracts/db_schema.json`。
- 自动化任务 fail-soft：失败仅影响对应模块；保留手动“重试/重建”；Task Center 记录 error/request_id。

## Checkpoints
- Commit after: 每条 Issue 完成即提交并 push；每个 Phase 末跑一次 `pwsh test/run-all.ps1`。

## References
- `docs/design/graph-model.md`
- `docs/design/search-engine.md`
- `docs/design/task-system.md`
- `docs/ux/ui-api-map.md`
- `docs/ux/advanced-debug-page-guidelines.md`
- `backend/app/services/worldbook_service.py:56`
- `backend/app/api/routes/chapter_analysis.py:36`
- `backend/app/services/memory_update_service.py:995`
- `backend/app/services/memory_retrieval_service.py:75`
- `backend/app/services/rerank_service.py:11`
- `https://www.sqlite.org/fts5.html`
- `https://neo4j.com/docs/getting-started/current/graphdb-concepts/`
- `https://starc.app/help/characters-relations`
