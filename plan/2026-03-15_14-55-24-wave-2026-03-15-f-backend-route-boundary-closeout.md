---
mode: plan
task: Wave 2026-03-15 F backend route boundary closeout
created_at: "2026-03-15T14:55:24+08:00"
complexity: complex
---

# Plan: Wave 2026-03-15 F backend route boundary closeout

## Goal
- 以 compatibility-first 方式把 `chapters.py` 的 chapter plan / generate-precheck / generate / generate-stream，`outline.py` 的 generate / generate-stream / segmented / repair / fill，以及 `memory.py` 的 auto-propose LLM orchestration 下沉到 application service。
- 缩小 `no-direct-llm-call-in-api` 在本批触达链路上的 legacy allowlist 面积，同时保持 API/SSE/status code/error code/response fields/generation run 语义不回退。
- 补齐本批新增 application service 的 unittest/contract coverage，最终完成后端、前端、定向 Playwright 与全量 Playwright 的真实回归，并如实更新 issue/doc。

## Scope
- In:
  - `backend/app/api/routes/chapters.py` 中章节计划、预检、非流式生成、流式生成相关 orchestration 下沉。
  - `backend/app/api/routes/outline.py` 中 outline 生成、stream、segmented、repair、fill、aggregate run orchestration 下沉。
  - `backend/app/api/routes/memory.py` 中 auto-propose memory update 的 LLM orchestration 下沉，并统一本批触达范围内 fail-soft / validation / `generation_run_id` / `llm_generation_run_id` 细节口径。
  - 对应 backend unittest、API/UI contract spec、Wave F 文档与 issue CSV 闭环。
- Out:
  - `T11` 全量后端主链路重写、无关 CRUD route 大改、route/response/SSE contract 改版。
  - `T12`/`T13`/`T14+` 的知识子域重构、任务工业化、部署/观测/CI/压测升级。
  - 前端新一轮页面重构、URL/search params/ARIA/按钮合同改动。

## Assumptions / Dependencies
- 当前分支保持在 `test`，工作树中的未跟踪用户文件不纳入提交；`5.4大调查详细记录.md` 的现有本地修改必须保留。
- 允许新增 feature-local backend application service / model / parser / tests，但必须复用现有 `generation_pipeline.py`、`generation_service.py`、`run_store.py`、`output_contracts.py` 的兼容合同。
- 每个 issue 仍严格执行 `Issue CSV 一行 = 一个 commit`，同一 commit 同步更新代码和当前 CSV 状态，并在 commit 后 push 到 `origin/test`。

## Phases
1. 生成并校验 Wave F plan/issues，完成 guard、文档、route/service/test 边界审查，锁定最小兼容切口。
2. 交付 `MVP-674`：提取章节计划/预检/生成/流式 application service，route 仅保留鉴权、header/params 接入、service 调用、响应/SSE 映射与最薄错误边界。
3. 交付 `MVP-675`：提取 outline generate/generate-stream/segmented/repair/fill application service，保持 segmented progress、aggregate run、fallback/raw preview/result payload 合同不变。
4. 交付 `MVP-676`：提取 memory auto-propose application service，统一本批触达范围内 parse/contract fail-soft、validation details、`generation_run_id` / `llm_generation_run_id` 透传细节，并补相应单测/contract test。
5. 交付 `MVP-677`：如实更新 `3.13调查详细全面报告所有问题.md`、`5.4大调查详细记录.md`、Wave F CSV，并完成 backend/frontend/Playwright 全回归。

## Tests & Verification
- Chapter application service 边界 -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_chapter_*.py" -v` | `cd test && npx playwright test specs/api/plan-chapter.contract.spec.ts specs/api/chapter-generate-precheck.contract.spec.ts specs/api/chapter-generate-stream-prereq.contract.spec.ts specs/api/generation-runs.contract.spec.ts specs/api/generation-runs-prompt-inspector.contract.spec.ts specs/api/prompt-preview.contract.spec.ts specs/ui/chapter-stream.spec.ts specs/ui/chapter-stream-cancel.spec.ts specs/ui/chapter-stream-unsupported-provider.spec.ts specs/ui/chapter-fallback.spec.ts`
- Outline application service 边界 -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_outline_*.py" -v` | `cd test && npx playwright test specs/api/outline-missing-preset.contract.spec.ts specs/ui/outline-stream.spec.ts specs/ui/outline-fallback.spec.ts`
- Memory auto-propose / contract 细节 -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_memory*_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_output_contract_memory_update_*.py" -v` | `cd test && npx playwright test specs/api/memory-preview.contract.spec.ts specs/api/memory-retrieve.contract.spec.ts specs/api/chapter-analyze-auto-memory-update.contract.spec.ts specs/ui/memory-update.spec.ts specs/ui/chapter-analysis-apply.spec.ts specs/ui/chapter-analysis-rewrite.spec.ts`
- Batch closeout regression -> `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe scripts\run_quality_gate.py` | `cd frontend && npm run lint` | `cd frontend && npm test` | `cd frontend && npm run build` | `cd test && npx playwright test specs/api/plan-chapter.contract.spec.ts specs/api/chapter-generate-precheck.contract.spec.ts specs/api/chapter-generate-stream-prereq.contract.spec.ts specs/api/generation-runs.contract.spec.ts specs/api/generation-runs-prompt-inspector.contract.spec.ts specs/api/prompt-preview.contract.spec.ts specs/api/outline-missing-preset.contract.spec.ts specs/api/memory-preview.contract.spec.ts specs/api/memory-retrieve.contract.spec.ts specs/api/chapter-analyze-auto-memory-update.contract.spec.ts specs/ui/chapter-stream.spec.ts specs/ui/chapter-stream-cancel.spec.ts specs/ui/chapter-stream-unsupported-provider.spec.ts specs/ui/chapter-fallback.spec.ts specs/ui/outline-stream.spec.ts specs/ui/outline-fallback.spec.ts specs/ui/prompt-inspector.spec.ts specs/ui/memory-update.spec.ts specs/ui/chapter-analysis-apply.spec.ts specs/ui/chapter-analysis-rewrite.spec.ts specs/ui/batch-generation.spec.ts specs/ui/batch-generation-runtime-sync.spec.ts specs/ui/taskcenter-projecttasks.spec.ts specs/ui/taskcenter-projecttasks-sse.spec.ts` | `cd test && npm test`
- Issue contract validation -> `python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-03-15_14-55-24-wave-2026-03-15-f-backend-route-boundary-closeout.csv`

## Issue CSV
- Path: issues/2026-03-15_14-55-24-wave-2026-03-15-f-backend-route-boundary-closeout.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none：本批以本地代码审查、backend unittest、frontend build/lint/vitest 与 Playwright 黑盒回归为主，不依赖额外 MCP。

## Acceptance Checklist
- [ ] `chapters.py` / `outline.py` / `memory.py` 的 route 职责明显变薄，LLM orchestration 真正下沉到 application service，而不是只换文件位置。
- [ ] `no-direct-llm-call-in-api` 在 `chapters.py` / `outline.py` / `memory.py` 上的 legacy allowlist 实际缩小；若有残留，文档如实说明原因与边界。
- [ ] 章节计划、章节生成、章节流式 fallback、大纲生成/repair/fill/segmented、memory auto-propose、prompt inspector、generation run、warnings/parse_error/dropped_params/finish_reason、TaskCenter/auto updates 黑盒主链路不回退。
- [ ] 后端 `compileall` / `unittest` / `quality_gate`，前端 `lint` / `vitest` / `build`，指定 Playwright 与最终 `cd test && npm test` 全部真实通过。
- [ ] Wave F plan/issues/doc 如实记录已做、未做与不属于本批范围的事项，并满足每个 issue 一次 commit + push 的交付粒度。

## Risks / Blockers
- 如果只抽 helper 不收口 orchestration 所有权，route 复杂度和 allowlist warning 基本不会实质下降，评审不会接受。
- `generate-stream` 和 `outline generate-stream` 同时承担 fallback/retry/repair/SSE 映射，拆分时若误改事件顺序或 result payload，UI 黑盒会直接回退。
- memory auto-propose 的 parse/validation/run-id 细节若统一方式错误，会影响 chapter analyze auto-propose fail-soft 行为和 change set 链路。

## Rollback / Recovery
- 若某条 application service 下沉引入合同回退，按 issue 粒度回滚对应 commit，仅撤销该 issue 新增 service/测试/CSV 状态，不影响其他已验证 issue。
- 若回归暴露本批触达链路阻断 bug，仅做最小兼容修复并补测试；若超出批次边界，则记录在文档和 CSV，不借机扩 scope。

## Checkpoints
- Commit after: MVP-674 chapters application service boundary closeout.
- Commit after: MVP-675 outline application service boundary closeout.
- Commit after: MVP-676 memory auto-propose boundary and touched fail-soft detail unification.
- Commit after: MVP-677 docs + regression closure.

## References
- AGENTS.md
- issues/README.md
- docs/testing-policy.md
- .codex/skills/plan/SKILL.md
- .codex/skills/testing/SKILL.md
- plan/2026-03-14_15-37-51-wave-2026-03-14-e-writing-task-runtime-closeout.md
- issues/2026-03-14_15-37-51-wave-2026-03-14-e-writing-task-runtime-closeout.csv
- 5.4大调查详细记录.md
- 3.13调查详细全面报告所有问题.md
- backend/app/api/routes/chapters.py
- backend/app/api/routes/outline.py
- backend/app/api/routes/memory.py
- backend/app/services/generation_pipeline.py
- backend/app/services/generation_service.py
- backend/app/services/run_store.py
- backend/app/services/output_contracts.py
- backend/app/services/chapter_context_service.py
- backend/app/services/memory_update_service.py
- backend/app/services/outline_payload_normalizer.py
