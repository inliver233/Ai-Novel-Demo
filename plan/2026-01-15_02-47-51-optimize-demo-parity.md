---
mode: plan
task: Optimize demo parity (demo vs Amily vs MuMu)
created_at: "2026-01-15T03:18:55+08:00"
complexity: complex
---

# Plan: optimize-demo-parity（demo 对照 Amily 与 MuMu）

## Goal
- 将仓库根目录 `学习两个项目的可以优化的地方.md` 中的所有“可学习/可优化点”拆解为可按顺序落地的 Issue CSV，并补充基于 demo 代码核对发现的真实入口与缺口。
- 目标状态：当本 CSV 全部完成后，demo 在 **query 预处理、RAG rerank、Vector 多 chunk、语义相关历史、伏笔闭环、WorldBook 编辑体验、Prompt 资产管理与编排、上下文压缩、可观测性、数据生命周期、多 embedding、多 KB、Fractal LLM 摘要** 等方面与 Amily/MuMu 没有关键能力差距。
- 保持 demo 的安全红线与 fail-soft 设计不回退（缺 embedding 不影响写作、密钥不明文输出、日志脱敏）。

## Scope
- In:
  - demo 后端（FastAPI + SQLite + Alembic）
  - demo 前端（React + TypeScript + Vite）
  - demo 测试（test/ Playwright blackbox + API contract）
  - 本次产物：plan + issues CSV + 覆盖矩阵
- Out:
  - 不修改 Amily/ 与 mumu/ 的实现（仅参考路径与概念）
  - 不引入真实 LLM 调用到 E2E（沿用现有 Mock LLM 约束）

## Assumptions / Dependencies
- 执行期必须遵守 `demo/AGENTS.md`：
  - 所有代码变更与提交在 `test` 分支
  - 一行 Issue = 一个 commit，并同 commit 更新 CSV 状态
- 新能力默认 **关闭** 或 **可选启用**，确保向后兼容与可回滚。
- 网络依赖（embedding、external rerank 等）必须 fail-soft：不可用时返回稳定 shape + disabled_reason，不阻塞写作生成。
- 安全：任何导出/日志/回放均不得泄露明文密钥，仅允许 `has_api_key` / `masked_api_key`。

## Phases
1. Phase 0（P0：低风险/立竿见影，先把“可控/可观测/一致性”补齐）
   - Query 预处理基础设施：`OPTI-001`～`OPTI-006`
   - Context Preview ≈ 实际注入：`OPTI-007`～`OPTI-009`
   - Rerank 开关与 UI 可观测：`OPTI-010`～`OPTI-012`
   - Prompt budget 动态联动：`OPTI-015`
   - deterministic fractal 信息源增强：`OPTI-016`
   - 可观测性面板 + debug bundle：`OPTI-017`～`OPTI-019`
   - 标注 overlap 回归保障：`OPTI-020`
2. Phase 1（P1：中等改动/收益很高，补齐核心“可用体验”）
   - Rerank provider + super-sort：`OPTI-013`～`OPTI-014`
   - VectorRAG 多 chunk：`OPTI-021`～`OPTI-023`
   - StoryMemory 向量化 + semantic_history + 伏笔闭环：`OPTI-024`～`OPTI-029`
   - WorldBook 批量/导入导出/匹配增强：`OPTI-030`～`OPTI-036`
   - Structured Memory 表格化 + 任务中心：`OPTI-037`～`OPTI-042`
   - GraphContext 输出稳定性：`OPTI-043`
   - ContextOptimizer + 统一预算：`OPTI-044`～`OPTI-047`
   - Prompt 资产管理 + 条件编排：`OPTI-048`～`OPTI-052`
   - 数据生命周期（dirty/purge/迁移）：`OPTI-053`～`OPTI-057`
3. Phase 2（P2：架构升级，补齐“可扩展”与“跨环境可落地”）
   - Embedding provider 插件化与本地 ST：`OPTI-058`～`OPTI-062`
   - 多知识库管理与并行检索合并：`OPTI-063`～`OPTI-067`
   - Fractal LLM 版分层摘要：`OPTI-068`～`OPTI-070`
   - 概念迁移文档：`OPTI-071`

## Tests & Verification
- 每条 Issue 的验证方式以 CSV 的 `Test_Method` 为准。
- Phase 级别回归建议：
  - Phase 0 结束：至少跑一次 `pwsh test/run-all.ps1`
  - Phase 1 结束：跑 `pwsh test/run-all.ps1` 并补齐必要的契约/黑盒用例
  - Phase 2 结束：跑 `pwsh test/run-all.ps1`，并在多 KB/命名迁移场景做一次“迁移前后可 query”的 smoke 验证

## Issue CSV
- Path: issues/2026-01-15_02-47-51-optimize-demo-parity.csv
- Must share the same timestamp/slug as this plan.
- 校验脚本：`python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-01-15_02-47-51-optimize-demo-parity.csv`

## Tools / MCP
- 本计划产物不依赖 MCP；执行期 `Tools` 字段按 CSV 填 `none` 或 `manual`（遵循 `docs/mcp-tools.md`）。

## Acceptance Checklist
- [ ] Issue CSV 通过校验脚本（表头/必填/枚举值）
- [ ] 覆盖矩阵无遗漏：`学习两个项目的可以优化的地方.md` 的每个 source_id 都能映射到 ≥1 个 Issue
- [ ] plan 与 issues CSV 的 timestamp/slug 完全一致
- [ ] 本次仅新增/修改计划与 issue 产物文件（无业务代码变更）

## Risks / Blockers
- Schema 变更集中：ProjectSettings、KnowledgeBase 等需要谨慎迁移与回滚策略。
- 多后端 embedding / external rerank 引入网络与依赖风险：必须 fail-soft + 脱敏。
- ContextOptimizer 与预算策略会改变 prompt 文本：必须默认关闭且提供差异可视化与回放证据。
- Chroma collection 命名迁移与多 KB 会触及历史数据：需要“先并存后迁移”的策略与明确回滚。

## Rollback / Recovery
- DB：通过 Alembic downgrade 或开关回退（默认关闭新功能）。
- 向量库：迁移时保留旧 collection 直到新 collection rebuild 成功；提供 purge 前确认与备份建议。
- Prompt 文本变更：保留 raw 与 normalized 与 optimizer 前后摘要到 run params，支持回放定位。

## Checkpoints
- 执行期严格按 `demo/AGENTS.md`：每条 `OPTI-###` 完成后提交一次，并同步更新 CSV 状态。
- 建议在 Phase 边界做一次“回归批次”并更新所有相关行的 `Regression_Status`。

## References
- Baseline doc: `../学习两个项目的可以优化的地方.md`
- Key demo entrypoints:
  - chapters generate: `backend/app/api/routes/chapters.py`
  - memory pack: `backend/app/services/memory_retrieval_service.py`
  - vector rag: `backend/app/services/vector_rag_service.py`
  - prompt presets: `backend/app/services/prompt_presets.py`
  - UI: `frontend/src/pages/RagPage.tsx` `frontend/src/pages/WorldBookPage.tsx` `frontend/src/pages/PromptStudioPage.tsx`

## Coverage Matrix（baseline doc -> issues）
| source_id | doc_item | issues |
| --- | --- | --- |
| DOC-1.2-01 | **RAG：多知识库/多来源管理**（Amily 的“知识库列表 + 启用/禁用/移动/重命名”概念） | OPTI-063 OPTI-064 OPTI-065 OPTI-066 OPTI-067 |
| DOC-1.2-02 | **RAG：更强 rerank**（Amily：外部 rerank 服务 + 元数据加权 + super sort） | OPTI-010 OPTI-013 OPTI-014 |
| DOC-1.2-03 | **检索 query 预处理**（Amily：tag 提取 + 内容排除规则 + “索引引用增强”） | OPTI-001 OPTI-002 OPTI-003 OPTI-006 |
| DOC-1.2-04 | **“相关历史”召回**（MuMu：用 chapter_summary 做语义检索，召回最相关章节而非仅最近） | OPTI-024 OPTI-025 |
| DOC-1.2-05 | **上下文压缩/合并**（Amily：Context Optimizer 把分散档案块合并成表） | OPTI-044 |
| DOC-1.2-06 | **Embedding 多后端**（Amily：openai/azure/google/custom/local_proxy；MuMu：本地 sentence-transformers） | OPTI-058 OPTI-059 OPTI-060 OPTI-062 |
| DOC-1.2-07 | **标注 UI 的重叠/聚合处理**（MuMu 的 AnnotatedText 思路） | OPTI-020 |
| DOC-2.1-01 | **P0：引入 query 预处理层（可选启用）** | OPTI-001 OPTI-002 OPTI-003 OPTI-004 |
| DOC-2.1-02 | demo 落点建议：在 `demo/backend/app/api/routes/chapters.py:550` 里组装 `memory_query_text` 之后、调用 `retrieve_memory_context_pack` 之前加一层 `normalize_memory_query_text()`（新函数建议放 `demo/backend/app/services/memory_retrieval_service.py`，或拟新增 `demo/backend/app/services/memory_query_service.py`）。 | OPTI-001 OPTI-004 |
| DOC-2.1-03 | **P1：把“相关历史”做成 pack 的一个可选 section**（语义检索/召回） | OPTI-025 OPTI-028 OPTI-029 |
| DOC-2.1-04 | **P1：Context Preview 的“模块级开关/查询文本/预算”可做成一键同步到写作生成** | OPTI-007 OPTI-008 OPTI-009 |
| DOC-2.2-01 | **P0：WorldBook 页面补齐“批量操作/复制/搜索/排序”** | OPTI-030 OPTI-031 OPTI-032 OPTI-036 |
| DOC-2.2-02 | **P1：引入“条目分组/标签/导入导出整本世界书”** | OPTI-033 OPTI-034 OPTI-036 |
| DOC-2.2-03 | **P1：关键词匹配增强（拼音/别名/正则白名单）** | OPTI-035 OPTI-036 |
| DOC-2.3-01 | **P0：标注渲染增强（重叠/紧邻/聚合 Tooltip）** | OPTI-020 |
| DOC-2.3-02 | **P1：StoryMemory 检索升级为“语义检索 + 类型过滤”** | OPTI-025 |
| DOC-2.3-03 | **P1：Foreshadow 闭环能力补齐（未回收伏笔列表）** | OPTI-026 OPTI-027 OPTI-028 OPTI-029 |
| DOC-2.4-01 | **P0：Structured Memory 的“表格化编辑体验”** | OPTI-040 OPTI-041 OPTI-042 |
| DOC-2.4-02 | **P1：ChangeSet 可观测性再加强** | OPTI-037 OPTI-038 OPTI-039 OPTI-041 |
| DOC-2.5-01 | **P0：把 GraphContext 的 query 预处理与 RAG 对齐** | OPTI-001 OPTI-002 OPTI-005 |
| DOC-2.5-02 | **P1：GraphContext 的“输出排序/稳定性”** | OPTI-043 |
| DOC-2.6-01 | **P1：FractalMemory 升级为“LLM 版可选”** | OPTI-068 OPTI-069 |
| DOC-2.6-02 | 失败降级：仍保留当前 deterministic `demo/backend/app/services/fractal_memory_service.py` | OPTI-068 OPTI-070 |
| DOC-2.6-03 | **P0：现有 deterministic fractal 的“更强信息源”** | OPTI-016 |
| DOC-2.7-01 | **P0：把 rerank 从“可用”变成“可控 + 可观测”** | OPTI-010 OPTI-011 OPTI-012 OPTI-013 OPTI-014 |
| DOC-2.7-02 | **P1：允许“同一来源多 chunk”并用排序/预算控制** | OPTI-021 OPTI-022 OPTI-023 |
| DOC-2.7-03 | **P1：多知识库（collection）概念** | OPTI-063 OPTI-064 OPTI-065 OPTI-066 OPTI-067 |
| DOC-2.7-04 | **P1：把 StoryMemory 向量化，做“语义相关历史/伏笔检索”** | OPTI-024 |
| DOC-2.7-05 | 新增 `story_memory_vector_service`（可复用现有 Chroma/pgvector；与 `demo/backend/app/services/vector_rag_service.py` 共用 embedding 配置） | OPTI-024 |
| DOC-2.7-06 | **P2：Embedding provider 插件化（多后端 + 本地模型）** | OPTI-058 OPTI-060 OPTI-061 |
| DOC-2.7-07 | 把 `_embed_texts` 从 `demo/backend/app/services/vector_rag_service.py` 抽象到独立模块（例如拟新增 `demo/backend/app/services/embedding_service.py`） | OPTI-059 |
| DOC-2.8-01 | **P0：把“PromptPreset/PromptBlock”补齐“模板资产管理”能力** | OPTI-048 OPTI-049 OPTI-052 |
| DOC-2.8-02 | **P1：预算与模型上下文窗口联动** | OPTI-015 |
| DOC-2.8-03 | **P1：引入“条件块编排 UI”** | OPTI-050 OPTI-052 |
| DOC-2.9-01 | **P0：增加 Context Optimizer（服务端）** | OPTI-044 OPTI-045 OPTI-047 |
| DOC-2.9-02 | **P1：把“smart_context”与“memory pack”做统一预算** | OPTI-046 OPTI-047 |
| DOC-2.10-01 | **P0：把“预览≈实际注入”的 debug bundle 做成一键导出** | OPTI-018 OPTI-019 |
| DOC-2.10-02 | **P0：RagPage/ContextPreviewDrawer 补齐可观测字段展示** | OPTI-009 OPTI-012 OPTI-017 |
| DOC-2.10-03 | **P1：ChangeSet/MemoryTask 的可观测性统一到“任务中心”** | OPTI-037 OPTI-038 OPTI-039 OPTI-042 |
| DOC-2.11-01 | **P0：对“需要 rebuild”的资源打脏标记，并在 UI 显示/提醒** | OPTI-053 OPTI-054 OPTI-057 |
| DOC-2.11-02 | **P1：补齐“删除/清理”链路（向量库/派生缓存）** | OPTI-055 OPTI-057 |
| DOC-2.11-03 | **P1：未来做多租户/多知识库时，采用哈希命名避免限制与冲突** | OPTI-056 OPTI-057 |
| DOC-2.8-OPT-CACHE | **（未用/可优化）PromptBlock.cache_json**：模型与资源加载都已支持（`demo/backend/app/models/prompt_block.py:29`、`demo/backend/app/services/prompt_preset_resources.py:243`），但 `render_preset_for_task` 当前未消费 cache 语义 → 未来可用于“静态块/昂贵块”缓存或“按 marker_key 复用”。 | OPTI-051 OPTI-052 |
| DOC-3-P0-01 | RAG/Graph/Memory 的 **query 预处理**：tag 提取 + 排除规则 + 可选“索引引用增强” | OPTI-001 OPTI-002 OPTI-003 OPTI-004 OPTI-005 OPTI-006 |
| DOC-3-P0-02 | **Rerank 开关 + 可观测 UI**：把 demo 已有 rerank_obs 用起来 | OPTI-010 OPTI-011 OPTI-012 |
| DOC-3-P0-03 | **标注 UI 重叠处理**（可视化质量提升明显） | OPTI-020 |
| DOC-3-P0-04 | Prompt budget 与 model context window **联动** | OPTI-015 |
| DOC-3-P0-05 | Context Preview 与实际注入 **一致性修复**（预览支持带 query_text + modules） | OPTI-007 OPTI-008 OPTI-009 |
| DOC-3-P1-01 | StoryMemory **向量化** + “相关历史/未回收伏笔”检索（把 plot_analysis 的产物真正用起来） | OPTI-024 OPTI-026 |
| DOC-3-P1-02 | VectorRAG **支持同一 source 多 chunk**，并引入排序策略（chapter_number/chunk_index） | OPTI-021 OPTI-022 |
| DOC-3-P1-03 | WorldBook 页面 **批量操作/复制/导入导出** | OPTI-030 OPTI-031 OPTI-033 |
| DOC-3-P1-04 | Prompt Studio 增加“整套模板资产导入导出/分类视图” | OPTI-048 OPTI-049 |
| DOC-3-P2-01 | Embedding provider 插件化（openai/azure/google/custom + 本地 sentence-transformers） | OPTI-058 |
| DOC-3-P2-02 | 多知识库（KB）管理：拆分索引、分权重、可启停、可迁移 | OPTI-063 OPTI-065 |
| DOC-3-P2-03 | FractalMemory LLM 化（分层摘要更可控），并与 post_edit/style_profile 联动 | OPTI-068 OPTI-069 |
| DOC-4-01 | Amily 是 **SillyTavern 前端扩展**：很多能力依赖 ST 的事件总线/世界书 API/向量 API（`/api/vector/*`）。demo 迁移时要“概念迁移”，不是代码直接拷贝。 | OPTI-071 |
| DOC-4-02 | MuMu 的向量记忆依赖 **本地 SentenceTransformer 模型**：如果 demo 要引入本地 embedding，需要考虑： | OPTI-058 OPTI-061 |
| DOC-4-03 | demo 已经做了大量安全/降级设计（安全模板子集、密钥加密、缺 embedding 不影响写作）。迁移增强功能时务必保持这些“红线”不回退。 | OPTI-018 OPTI-058 OPTI-060 OPTI-062 |
