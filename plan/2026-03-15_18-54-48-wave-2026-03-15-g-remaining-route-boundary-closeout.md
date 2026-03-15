---
mode: plan
task: Wave 2026-03-15 G remaining route boundary closeout
created_at: "2026-03-15T18:54:55+08:00"
complexity: complex
---

# Plan: Wave 2026-03-15 G remaining route boundary closeout

## Goal
- 以 compatibility-first 方式把 `backend/app/api/routes/chapter_analysis.py` 中 chapter analyze / rewrite / auto memory update 的 LLM orchestration 下沉到 application service，同时保持 `/chapters/{chapter_id}/analyze`、`/rewrite`、`/analysis/apply`、`/annotations` 合同不变。
- 把 `backend/app/api/routes/llm.py` 的 `/api/llm/test` key/base_url/retry/backoff/error-details/LLM 调用编排下沉到 application service，保持 Prompts 页“测试连接”主路径完全兼容。
- 仅在本批触达范围内继续缩小 `chapter_generation_app_service.py`、`outline_generation_app_service.py` 等热点文件的 file-line-count warning 面，并补齐本批新增 service/contract/tests/docs/regression 闭环。

## Scope
- In:
  - `chapter_analysis.py` 中 analyze / rewrite / auto memory update orchestration 下沉到 feature-local application service / model。
  - `llm.py` 中 `/llm/test` orchestration 下沉到 application service / model，route 仅保留请求接入、最小校验、service 调用与响应映射。
  - 仅拆本批直接触达的大文件热点：优先 `backend/app/services/chapter_generation_app_service.py`、`backend/app/services/outline_generation_app_service.py`，必要时增加 feature-local helper/model/service 文件，但不改现有 API/SSE 合同。
  - 补 backend unittest、定向 API/UI Playwright、全量 backend/frontend/test 回归与 Wave G 文档/issue 状态闭环。
- Out:
  - `T11` 全量主链路重写、`T12` 知识子域统一、`T13` 任务系统工业化、`T14+` 基础设施/部署/观测/CI/压测升级。
  - 改后端 API/SSE contract、status code、error code、generation run 类型，或改前端 URL/search params/ARIA/按钮文案合同。
  - 为了消除 warning 去改 `scripts/guards/no_direct_llm_call_in_api.py` / `file_line_count_guard.py` 规则。

## Assumptions / Dependencies
- 当前分支保持 `test`；工作树中的未跟踪用户文件不纳入提交；`3.13调查详细全面报告所有问题.md` 与 `5.4大调查详细记录.md` 现有本地修改必须保留并在此基础上追加。
- 允许新增 feature-local application service / helper / model / tests，但必须复用现有 `generation_service.py`、`output_contracts.py`、`plot_analysis_service.py`、`memory_update_service.py`、`llm_retry.py` 的兼容合同。
- 每个 issue 继续执行 `Issue CSV 一行 = 一个 commit`，同一 commit 同步提交代码与当前 CSV 状态，且 commit 后 push 到 `origin/test`。

## Phases
1. 生成并校验 Wave G plan/issues，完成必读 route/service/test/doc 审查，锁定最小兼容切口。
2. 交付 `MVP-678`：提取 chapter analyze / rewrite / auto memory update orchestration 到 chapter analysis application service，route 仅保留鉴权、headers/params 接入、service 调用、响应转换与最薄错误边界。
3. 交付 `MVP-679`：提取 `/api/llm/test` orchestration 到 llm test application service，保持 request body/header、retry/details、preview 与前端测试连接语义不变。
4. 交付 `MVP-680`：继续拆分 `chapter_generation_app_service.py`、`outline_generation_app_service.py` 的 feature-local helper/service/model，显著缩小本批触达的 file-line 热点 warning 面。
5. 交付 `MVP-681`：补本批新增单测/contract coverage，完成 backend/frontend/Playwright 回归，更新主文档/辅文档与 Wave G CSV 状态并推送。

## Tests & Verification
- Chapter analysis/rewrite application service -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_chapter_analysis*_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_plot_analysis_apply.py" -v` | `cd test && npx playwright test specs/api/chapter-analysis.contract.spec.ts specs/api/chapter-analyze-auto-memory-update.contract.spec.ts specs/ui/chapter-analysis-apply.spec.ts specs/ui/chapter-analysis-rewrite.spec.ts specs/ui/memory-update.spec.ts`
- LLM test application service -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_llm*_*.py" -v` | `cd test && npx playwright test specs/ui/prompts-test-connection.spec.ts`
- Hotspot shrink / touched generation flows -> `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_chapter_generation*_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_outline*_*.py" -v` | `cd test && npx playwright test specs/api/plan-chapter.contract.spec.ts specs/api/chapter-generate-precheck.contract.spec.ts specs/api/chapter-generate-stream-prereq.contract.spec.ts specs/api/generation-runs.contract.spec.ts specs/api/generation-runs-prompt-inspector.contract.spec.ts specs/api/prompt-preview.contract.spec.ts specs/api/outline-missing-preset.contract.spec.ts specs/api/memory-preview.contract.spec.ts specs/api/memory-retrieve.contract.spec.ts specs/ui/chapter-stream.spec.ts specs/ui/chapter-stream-cancel.spec.ts specs/ui/chapter-stream-unsupported-provider.spec.ts specs/ui/chapter-fallback.spec.ts specs/ui/outline-stream.spec.ts specs/ui/outline-fallback.spec.ts specs/ui/prompt-inspector.spec.ts specs/ui/batch-generation.spec.ts specs/ui/batch-generation-runtime-sync.spec.ts specs/ui/taskcenter-projecttasks.spec.ts specs/ui/taskcenter-projecttasks-sse.spec.ts`
- Batch closeout regression -> `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic` | `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` | `cd backend && .\.venv\Scripts\python.exe scripts\run_quality_gate.py` | `cd frontend && npm run lint` | `cd frontend && npm test` | `cd frontend && npm run build` | `cd test && npx playwright test specs/api/chapter-analysis.contract.spec.ts specs/api/chapter-analyze-auto-memory-update.contract.spec.ts specs/api/plan-chapter.contract.spec.ts specs/api/chapter-generate-precheck.contract.spec.ts specs/api/chapter-generate-stream-prereq.contract.spec.ts specs/api/generation-runs.contract.spec.ts specs/api/generation-runs-prompt-inspector.contract.spec.ts specs/api/prompt-preview.contract.spec.ts specs/api/outline-missing-preset.contract.spec.ts specs/api/memory-preview.contract.spec.ts specs/api/memory-retrieve.contract.spec.ts specs/ui/chapter-analysis-apply.spec.ts specs/ui/chapter-analysis-rewrite.spec.ts specs/ui/chapter-stream.spec.ts specs/ui/chapter-stream-cancel.spec.ts specs/ui/chapter-stream-unsupported-provider.spec.ts specs/ui/chapter-fallback.spec.ts specs/ui/outline-stream.spec.ts specs/ui/outline-fallback.spec.ts specs/ui/memory-update.spec.ts specs/ui/prompt-inspector.spec.ts specs/ui/prompts-test-connection.spec.ts specs/ui/batch-generation.spec.ts specs/ui/batch-generation-runtime-sync.spec.ts specs/ui/taskcenter-projecttasks.spec.ts specs/ui/taskcenter-projecttasks-sse.spec.ts` | `cd test && npm test`
- Issue contract validation -> `python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-03-15_18-54-48-wave-2026-03-15-g-remaining-route-boundary-closeout.csv`

## Issue CSV
- Path: issues/2026-03-15_18-54-48-wave-2026-03-15-g-remaining-route-boundary-closeout.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none：本批以本地代码审查、backend unittest、frontend lint/vitest/build 与 Playwright 黑盒回归为主，不依赖额外 MCP。

## Acceptance Checklist
- [ ] `chapter_analysis.py` / `llm.py` route 职责明显变薄，direct LLM orchestration 真正下沉到 application service。
- [ ] `no-direct-llm-call-in-api` 不再对 `backend/app/api/routes/chapter_analysis.py`、`backend/app/api/routes/llm.py` 报 legacy allowlist warning。
- [ ] `/chapters/{chapter_id}/analyze`、`/rewrite`、`/analysis/apply`、`/annotations` 与 `/api/llm/test` 的 request/response/status/error/details/generation-run 语义保持兼容。
- [ ] 本批触达的 file-line-count warning 面明显缩小；若仍有残留，文档如实写明原因与边界。
- [ ] 后端 `compileall` / `unittest` / `quality_gate`，前端 `lint` / `vitest` / `build`，指定 Playwright 与最终 `cd test && npm test` 均真实通过。
- [ ] Wave G plan/issues/doc 如实记录已做、未做与不属于本批范围的事项，并满足每个 issue 一次 commit + push 的粒度。

## Risks / Blockers
- chapter analysis 的 auto memory update 具备 fail-soft / parse_error / run-id 细节，若 service 化时误改跳过条件或错误映射，会直接回退 UI 与 contract。
- `/llm/test` 的 retry/backoff/log details 与前端测试连接主路径强耦合，若 service 化时改动 header/body 校验或 details 结构，会导致现有 unittest / UI 黑盒失败。
- `outline_generation_app_service.py` / `chapter_generation_app_service.py` 的体积较大，拆分必须保持 feature-local 边界并复用现有 tests，否则容易引入 prompt/render/run-id 行为漂移。

## Rollback / Recovery
- 若某条 application service 下沉导致 contract 回退，按 issue 粒度回滚对应 commit，仅撤销该 issue 新增 service/测试/CSV 状态。
- 若回归暴露本批触达链路阻断 bug，仅做最小兼容修复并补测试；超出批次边界的缺陷只记录在文档与 CSV，不借机扩 scope。

## Checkpoints
- Commit after: MVP-678 chapter analysis application service boundary closeout.
- Commit after: MVP-679 llm test application service boundary closeout.
- Commit after: MVP-680 touched generation/outline hotspot shrink.
- Commit after: MVP-681 docs + regression closure.

## References
- AGENTS.md
- issues/README.md
- docs/testing-policy.md
- .codex/skills/plan/SKILL.md
- .codex/skills/testing/SKILL.md
- plan/2026-03-15_14-55-24-wave-2026-03-15-f-backend-route-boundary-closeout.md
- issues/2026-03-15_14-55-24-wave-2026-03-15-f-backend-route-boundary-closeout.csv
- 5.4大调查详细记录.md
- 3.13调查详细全面报告所有问题.md
- backend/app/api/routes/chapter_analysis.py
- backend/app/api/routes/llm.py
- backend/app/api/routes/chapters.py
- backend/app/api/routes/outline.py
- backend/app/api/routes/memory.py
- backend/app/services/chapter_generation_app_service.py
- backend/app/services/chapter_generation_stream_service.py
- backend/app/services/outline_generation_app_service.py
- backend/app/services/memory_auto_update_app_service.py
- backend/app/services/generation_service.py
- backend/app/services/output_contracts.py
