# ainovel · 长期记忆系统（LMEM）Issue CSV 说明

> 更新时间：2026-01-09  
> 来源：`长期记忆系统完整实现规划.md`（Phase 0~7）

本仓库采用 **Issue CSV = 执行合同** 的方式推进开发：真实执行以 `issues/*.csv` 为准；本文用于说明 LMEM 这条主线的 CSV 如何组织、字段如何填写、以及如何按批次推进。

## 相关文档（先读）
- 执行约束（AI 工作方式）：`AGENTS.md`
- Issue CSV 字段规则（表头/必填/枚举）：`issues/README.md`
- 测试与验收策略：`docs/testing-policy.md`
- Issue 执行闭环（实现→验收→提交）：`issues_csv_execute.md`
- MCP 工具清单：`docs/mcp-tools.md`

## 约定：如何在不改表头的前提下保留 priority/phase/area/owner
Issue CSV 的表头是固定的（见 `issues/README.md`），因此 LMEM 的这些信息按以下方式编码：

- `ID`：使用 `LMEM-###`（例如 `LMEM-010`）
- `Title`：建议加可筛选标签前缀，例如：`[P0][backend][phase:0.1] MemoryContextPack + 调试接口 + 日志占位`
- `Notes`：建议结构化（用 `|` 分隔），例如：`priority:P0 | area:backend | phase:0.1 | owner:<name> | refs:<file:line;...>`

## 生成 / 校验 / 执行（标准动作）
- 校验 CSV 表头与必填：`python .codex/skills/plan/scripts/validate_issues_csv.py <issues.csv>`
- 执行（进入闭环模式）：`/prompts:issues_csv_execute <issues.csv>`

> 建议：每个批次配一份 `plan/*.md`，并在 plan 里写明对应的 `issues/*.csv` 路径（timestamp/slug 一致）。

## 批次建议（避免一次 CSV 过大）
LMEM 推荐按 phase 分批（每批 3–8 条左右），例如：
- Phase 0：后端插入点 + 前端占位 + 测试覆盖
- Phase 1：WorldBook 最小闭环
- Phase 2：分析/记忆库/annotations
- Phase 3：Smart Context（结构化 + RAG + 预算/降级）
- Phase 4/5：写作流程增强与回放/对齐
- Phase 6/7：Graph / Fractal / Style Profiles

当前批次的“真实执行 CSV 文件名”，以 `plan/*.md` 的 `Issue CSV` 段落为准（位于 `issues/` 目录）。

## 已生成（本次准备）
- Plan：`plan/2026-01-09_21-44-18-lmem-backlog.md`
- Issue CSV：`issues/2026-01-09_21-44-18-lmem-backlog.csv`
