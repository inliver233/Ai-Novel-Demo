# ainovel · 长期记忆系统调研/规划 ToDo（2026-01-08）

> 说明：这是“任务的任务清单”。每完成一项就勾掉，并在 `demo/temp-process.md` 追加过程记录与结论链接。

## A. 先建立事实基线（不改代码）

- [x] 盘点仓库结构：`demo/` 与 `Amily/` 的关键目录、入口文件、运行方式（见 `demo/temp-process.md` 2026-01-08）
- [x] 盘点 demo 的数据库：当前表结构/字段、关键数据流（项目/大纲/章节/生成记录/提示词）
- [x] 盘点 demo 的提示词系统：Preset/Block/渲染/预算/链路（outline/plan/generate/post_edit/analyze/rewrite）
- [x] 盘点 demo 的“现有记忆/上下文”：world_setting/style_guide/constraints/characters/outline + smart_context 的生成逻辑
- [x] 盘点 demo 的用户与权限：`users/projects.owner_user_id` 的现状、前端 `local-user` 的用法、后端鉴权是否存在

## B. 深入理解 demo（为后续重构做准备）

- [x] 梳理后端模块图：routes → services → models → db；列出记忆系统未来的插入点（生成前/生成后/异步任务）（见 `demo/长期记忆系统完整实现规划.md` 1.3/6/9）
- [x] 梳理前端模块图：页面/状态管理/API client；列出记忆系统未来的 UI 承载位置（角色/世界书/关系图谱/检索调试）（见 `demo/长期记忆系统完整实现规划.md` 10/附录A）
- [x] 梳理批量生成与队列：RQ/Redis、任务表、生成记录；评估是否适合作为“记忆抽取/向量化”异步管线（见 `demo/长期记忆系统完整实现规划.md` 6.2.2）
- [x] 梳理导出与可观测：generation_runs、prompt_render_log_json、导出 markdown；规划记忆相关的审计与回溯（见 `demo/长期记忆系统完整实现规划.md` 8.2/6.5）

## C. 深入学习 Amily（迁移学习，不纠结酒馆形态）

- [x] 阅读 `Amily/ST-Amily2-Chat-Optimisation/功能解析.md` 并做结构化索引（模块 → 目的 → 数据结构 → 入口）（摘要见 `demo/temp-process.md`）
- [x] 角色卡/世界书：Amily 的表格化/条目化管理方式；提炼可迁移的数据模型与 UI 交互
- [x] 记忆系统：短期/长期/摘要/注入策略；提炼“何时写入/何时检索/如何注入 prompt”
- [x] 向量化与检索：向量库/分块/召回/重排/去重；提炼适合“小说剧情”的 RAG 策略
- [x] 文本优化：生成前/生成后处理、文风控制/去 AI 味；提炼可落地的链路与提示词接口
- [x] 关系图谱：实体/关系抽取、可视化、与记忆检索联动；提炼图数据结构与更新策略

## D. 设计 ainovel 长文记忆系统（目标架构 + 阶段路线）

- [x] 明确术语与目标：章节/场景/事件/实体/关系/时间线/设定/事实/伏笔/线索/风格（见 `demo/长期记忆系统完整实现规划.md` 2）
- [x] 设计数据模型：结构化条目 + 原文证据 + embedding + 版本/来源 + 置信度 + 冲突处理（见 `demo/长期记忆系统完整实现规划.md` 5/6）
- [x] 设计写入管线：生成后抽取（事件/人物状态/关系变化/设定变更）+ 人工编辑入口 + 批处理（见 `demo/长期记忆系统完整实现规划.md` 6）
- [x] 设计检索管线：章节生成时按“任务 → 需要的信息类型”做召回；支持调试与可观测（见 `demo/长期记忆系统完整实现规划.md` 7/8）
- [x] 设计注入策略：PromptBlock 级别的“可插拔记忆块”（人物/世界/时间线/关系/近期剧情/关键伏笔）（见 `demo/长期记忆系统完整实现规划.md` 8）
- [x] 设计一致性机制：冲突检测、时间线校验、角色状态守恒、引用证据定位（见 `demo/长期记忆系统完整实现规划.md` 6.4/14）
- [x] 设计多人系统演进：认证/授权/多租户/项目协作；SQLite → Postgres 的迁移策略与兼容期（见 `demo/长期记忆系统完整实现规划.md` 11）
- [x] 设计部署形态：docker compose（web+api+db+redis+worker）；配置与密钥管理（见 `demo/长期记忆系统完整实现规划.md` 11/12）

## E. 输出最终纲领文档

- [x] 产出 `demo/长期记忆系统完整实现规划.md`（总+细：阶段拆分、接口/表/提示词/伪代码/迁移/测试/规范）
- [x] 文档自检：与现有 `ui设计规范.md`、`mvp开发计划.md`、`提示词系统实现计划.md` 对齐；避免与现状冲突（已在文档 0.1 节说明对齐关系）

## F. 深入学习 mumu（新增：用于把“可迁移实现”写进规划）

- [x] 盘点 `mumu/MuMuAINovel` 顶层结构与运行方式（README/compose/entrypoint）
- [x] 复核鉴权/会话：Cookie 注入 `request.state.user_id` + refresh/过期策略（为 demo Phase 3 提供落点）
- [x] 复核 PlotAnalysis + StoryMemory + annotations 闭环（表结构、抽取规则、标注兜底与 UI）
- [x] 复核 Chroma 向量库：PersistentClient、collection 命名哈希、组合检索 build_context_for_generation（为 demo Phase 4A 提供落点）
- [x] 复核写作风格资产：writing_styles + project_default_styles + 前端 WritingStyles 交互（为 demo Phase 7 提供落点）
- [ ] 进一步：梳理 mumu 的导入导出对“记忆/风格资产迁移”的启发（import_export / include_writing_styles 等）

## G. 文档终版自检与可开工拆分（保留为后续工作）

- [ ] 全文一致性扫描：Phase 编号、路由形态、表名/字段名在“正文/附录/ToDo”三处保持一致
- [ ] 拆分 Issue 模板：按 Phase 输出最小可交付子任务（DoD + 风险 + 降级 + 验证点）
