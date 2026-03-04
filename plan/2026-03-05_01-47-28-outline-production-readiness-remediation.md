---
mode: plan
task: outline production readiness full review and remediation
created_at: "2026-03-05T01:47:28+08:00"
complexity: complex
---

# Plan: 大纲系统生产就绪全面排查与修复闭环

## Goal
- 对大纲生成相关前后端链路做生产前级别全面排查，修复阻塞与高风险问题，确保自动化测试全绿。
- 覆盖稳定性、可维护性、可观测性、兼容性与回归完整性。

## Scope
- In:
  - 修复黑盒阻塞项（DB schema baseline 与当前 schema 不一致）。
  - 加固长篇分段大纲生成：消除分段提示词冲突、控制上下文增长、补充聚合级 run 可观测性。
  - 补齐长篇分段模式的测试覆盖并执行全量回归（backend/frontend/test）。
  - `issues/2026-03-05_01-47-28-outline-production-readiness-remediation.csv`
- Out:
  - 不做与大纲/测试闭环无关的功能改造。

## Assumptions / Dependencies
- 当前工作分支为 `test`；按“一行 Issue = 一个 commit”执行。
- 以现有 mock-llm + Playwright 测试体系作为黑盒验收基准。

## Phases
1. 修复 E2E 阻塞：更新 DB schema baseline，恢复黑盒 schema 合同通过。
2. 修复大纲分段核心风险：提示词冲突、上下文预算、聚合 run 可观测性。
3. 增强测试：新增/扩展分段模式测试并执行 backend/frontend/e2e 全量回归。
4. 汇总结果与风险清单，确保可发布。

## Tests & Verification
- `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic`
- `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v`
- `cd frontend && npm run lint && npm test && npm run build`
- `cd test && npm test`

## Issue CSV
- Path: issues/2026-03-05_01-47-28-outline-production-readiness-remediation.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- manual

## Acceptance Checklist
- [ ] Playwright 全套通过（含 db schema 合同）。
- [ ] 长篇分段模式无提示词冲突，且上下文不会无界增长。
- [ ] 分段模式写入聚合级 generation run，便于排障与审计。
- [ ] 后端/前端/黑盒全量测试通过。

## Risks / Blockers
- 全量 E2E 时间较长；若外部环境波动可能引入偶发失败。
- 分段策略改动需严格保持向后兼容。

## Rollback / Recovery
- 按 Issue 粒度回滚对应 commit（`git revert <commit>`）。

## Checkpoints
- Commit after: MVP-607 / MVP-608 / MVP-609

## References
- backend/app/api/routes/outline.py
- backend/tests/test_outline_generation_guidance.py
- test/contracts/db_schema.json
- test/specs/db/db-schema.spec.ts
