# 图谱建模（小说人物关系）最佳实践与本仓库映射

> 目标：让“人物/组织/地点/物品等实体 + 关系 + 证据 +（可选）事件”既能被 LLM 自动抽取，又能被作者在 UI 中可编辑、可回放、可回滚，并保持 SQLite 落地成本可控。

本仓库已在 `docs/graph-decision.md` 记录了 v1 决策（采用属性图风格 + evidence + changeset）。本文补齐“小说场景的建模最佳实践 + UI 交互建议 + 与当前实现的映射”，用于后续 `graph_auto_update` 的 prompt/contract 收敛与 GraphPage 体验迭代。

## 1. 推荐主模型：属性图（Property Graph / LPG）

属性图的基本概念：

- **节点（Node）**：实体（人物、地点、组织、物品、事件…）
- **关系（Relationship）**：有向边，表示实体之间的关系
- **属性（Properties）**：节点/关系都可以携带 key-value

该模型对“关系带属性/证据/时间范围”的表达更直接，也更适合做 UI 编辑（比 RDF 三元组更低心智负担）。参考：

- Neo4j：Graph DB Concepts / Property Graph（node/relationship/properties）：https://neo4j.com/docs/getting-started/appendix/graphdb-concepts/
- Neo4j：Relationship direction（关系方向性）：https://neo4j.com/docs/getting-started/appendix/graphdb-concepts/#relationship-direction
- W3C：N-ary relations（当关系本身需要更多参与者/属性时的建模提示）：https://www.w3.org/TR/swbp-n-aryRelations/

## 2. 实体（Nodes）：类型、同一性与别名

### 2.1 实体类型（建议）

在小说写作场景，建议把实体类型控制在少量可解释的集合中（避免“过细 taxonomy”导致抽取与编辑困难）：

- `character`：人物
- `organization`：组织/势力
- `location`：地点
- `item`：重要物品（可选；也可先用 generic）
- `event`：事件（可选；见 4）
- `generic`：其他一切（占位，后续可细分）

### 2.2 同一性（Identity）策略

核心目标：避免同一人物被抽取出多个节点（“张三/三哥/阿三”分裂），同时避免过度合并导致误判。

建议策略：

1) **强约束：ID 稳定**  
   LLM 自动抽取时应优先复用既有实体的 `entity_id`，新增实体使用后端提供的 `new_entity_id_pool`（或等价机制），禁止模型自造 ID。

2) **名称（name）用于展示，而非唯一键**  
   UI 允许用户修改显示名；唯一性用 `type + normalized_name`（或 `id`）实现。

3) **别名/同名歧义**  
   通过 `attributes_json` 存储 `aliases`（数组）与 `disambiguation_note`（文本），并在 UI 提供“合并/拆分/标注同名不同人”的操作。

## 3. 关系（Edges）：方向、类型、属性与证据

### 3.1 方向性（Direction）约定

关系在存储层建议全部使用**有向边**，并在 relation_type 上做语义方向约定（UI 可按 `is_symmetric`/类型集合选择无向展示）。

例：

- `parent_of`: parent → child
- `member_of`: character → organization
- `located_in`: entity → location
- `owes_to`: debtor → creditor

Neo4j 的建议是：方向用于表达语义与查询便利，是否“在 UI 中画成无向”是展示层决策（参考上文 Neo4j 文档）。

### 3.2 关系类型（relation_type）命名建议

建议：

- `snake_case`，尽量使用动词短语或明确语义（`friend_of`、`rival_of`、`works_for`）
- 避免把自然语言整句塞进 `relation_type`（那是 `description_md` 的工作）
- 允许扩展，但尽量收敛在一个“推荐集合”，否则 UI 会变成不可控的标签堆

### 3.3 关系属性（attributes）建议（写作友好）

关系属性建议分两层：

- **结构化属性**：用于排序/筛选/算法（放入 `attributes_json`）
- **解释性文本**：用于给作者看的补充说明（放入 `description_md`）

常用结构化属性 key（建议）：

- `strength`：强度（0~1 或 0~100）
- `status`：`active | past | unknown`
- `confidence`：抽取置信度（0~1）
- `since_chapter_id / until_chapter_id / last_seen_at_chapter_id`：时间范围（用章节定位替代真实时间更贴近写作）
- `tags`：数组（例如 `secret`/`public`、`romance`/`family`）
- `is_symmetric`：是否可无向展示（或由 relation_type 推导）

### 3.4 证据（evidence）：必须有“可回放”的引用

写作场景下，“为什么你认为他们是敌对关系？”必须可解释；否则自动抽取不可用。

建议每条关系至少保留 0~N 条证据：

- 来源：章节（`source_type=chapter` + `source_id=chapter_id`）
- `quote_md`：原文片段（尽量短，避免整章）
- 关系操作（op）中引用 `evidence_ids`

## 4. 事件（Events）与 n-ary 关系：何时引入

当你需要表达“多参与者/多角色/带时间点”的复杂事实时，仅靠二元边会变得别扭：

例：“A 在第 12 章救了 B（原因/地点/后果）”

两种常见做法：

1) **事件节点（event node）**（推荐逐步演进）  
   建一个 `event` 节点，关系连接参与者与事件：`participated_in`、`rescued`、`witnessed` 等；事件节点上存时间/地点/摘要/证据。

2) **关系实例节点（reification / n-ary pattern）**  
   把“关系本身”变成一个节点承载属性，然后再连回原实体。W3C n-ary relations note 给出了这种思路：https://www.w3.org/TR/swbp-n-aryRelations/

EventKG 等事件中心知识图也强调“事件 + 时间 + 实体参与者”的建模方式，可作为参考：https://arxiv.org/abs/1804.04526

## 5. UI/编辑体验建议（GraphPage）

写作工具的关键不在“图画得多炫”，而在“能维护、能回滚、能追责”：

1) **表格/列表优先，图可视化作为辅视图**  
   大多数编辑动作（新增/改强度/改状态/加证据）在列表里更高效；图用于浏览与发现。

2) **强约束输入，弱约束展示**  
   - 新建/编辑关系：从推荐 relation_type 里选（可搜索），再允许“高级：自定义”
   - 方向性：通过 UI 引导（from/to）+ 预览文案（例如 “张三 parent_of 李四”）

3) **证据工作流**  
   每条关系应能“一键打开证据”：显示章节标题、跳转定位、quote 高亮；并允许补充/删除证据。

4) **变更集（ChangeSet）可视化**  
   自动抽取产生的 ops 应以 diff 形式展示：新增/修改/删除哪些实体与关系；支持 apply/rollback；并能在 TaskCenter 定位 run_id/request_id。

5) **合并/去重工具**  
   提供“合并实体”“合并关系（同 from/to/type）”“清理孤立节点”等维护能力，降低图长期漂移。

## 6. 与本仓库实现的映射（当前状态）

本仓库 v1 已按“属性图 + evidence + changeset”落库：

- 实体：`MemoryEntity`
- 关系：`MemoryRelation`
- 证据：`MemoryEvidence`
- 事件：`MemoryEvent`（扩展点；v1 抽取不强制写）
- 变更集：`memory_change_sets` / `memory_change_set_items`（apply/rollback）

建议后续实现遵循以下兼容性原则：

- **保持 API 兼容**：不破坏现有 entity/relation/evidence 的字段；新增能力优先放到 `attributes_json`（可选字段）。
- **保持 ID 稳定**：自动抽取不得重写既有 id；新增 id 由后端分配（pool）。
- **抽取协议 fail-closed**：继续复用 `memory_update_v1`（ops 列表），服务端校验 schema，不合规则拒绝并给出可定位错误。
- **证据优先**：关系变更尽量附带 evidence；没有证据时也要显式说明 `confidence/status`，避免“无依据断言”。

## 7. 相关研究/工具（可选参考）

- LitBank（小说领域实体/事件等标注数据集，可用于“实体同一性/事件抽取”基线参考）：https://github.com/dbamman/litbank
- BookNLP（面向书籍/小说文本的 NLP 工具链，可作为非 LLM 路线备选）：https://github.com/booknlp/booknlp
