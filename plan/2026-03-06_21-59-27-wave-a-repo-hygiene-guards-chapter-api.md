---
mode: plan
task: wave a repo hygiene guards and chapter api
created_at: "2026-03-06T21:59:27.3553408+08:00"
complexity: complex
---

# Plan: Wave A 仓库卫生、工程门禁与章节 API 地基

## Goal
- 在不破坏现有功能、保持生产可部署的前提下，完成 Wave A 的 `T01 + T02 + T04`：收口仓库卫生、建立后端质量门禁、落地章节轻量列表/详情合同并完成兼容迁移。

## Scope
- In:
  - 停止跟踪 `backend/.env`，收口 `.gitignore` 与本地产物约定。
  - 建立 `scripts/guards/` 基础框架，并落地 secrets / db artifacts / backend print / API 直调 LLM / file line count guards。
  - 为 backend 建立可执行质量入口（`ruff` + guards）。
  - 新增章节 meta 列表合同与 cursor 第一版，保留旧列表接口兼容窗口。
  - 将 Preview / Reader / Writing / Wizard / Foreshadows 的章节列表读取切到轻量 meta 接口，正文继续按需走 detail。
  - 补后端契约测试、黑盒 API 契约测试、相关前端 / Playwright 回归，并按 issue 提交推送。
- Out:
  - 不做章节虚拟滚动、完整前端数据层重构或全量缓存体系（留给 `T05/T06`）。
  - 不做任务系统、SSE、Runtime 工业化改造（留给后续波次）。
  - 不做无关业务重构。

## Assumptions / Dependencies
- 当前分支为 `test`，可直接按仓库规则提交并推送到 `origin/test`。
- `backend/.venv`、`frontend/node_modules`、`test/node_modules` 已存在，可在本机继续运行验证命令。
- 旧的 `GET /api/projects/{project_id}/chapters` 需要保留兼容窗口，因此新合同采用 additive 策略。
- `backend/app/api/routes/chapters.py` 当前是高热点文件，T04 只做合同加法与必要辅助抽取，不做大爆炸拆分。

## Phases
1. 生成 plan / issue CSV，并完成 T01 的仓库卫生收口。
2. 建立 guards 框架、后端质量入口与第一批可执行门禁。
3. 设计并实现章节 meta/detail 合同，补齐后端契约测试与黑盒 API 测试。
4. 迁移关键前端读路径到轻量列表 + 按需详情，并完成 Wave A 回归、review、commit、push。

## Tests & Verification
- T01: `git ls-files backend/.env` + `git check-ignore -v backend/.env backend/ainovel.db backend/.tmp_verify_p0.db-wal test/.artifacts tmp_outline_view.png`
- T02: `cd backend && .\.venv\Scripts\python.exe -m compileall -q app alembic tests scripts ..\scripts\guards`
- T02: `cd backend && .\.venv\Scripts\python.exe -m ruff check app tests scripts ..\scripts\guards`
- T02: `cd backend && .\.venv\Scripts\python.exe ..\scripts\guardsun.py`
- T04: `cd backend && .\.venv\Scripts\python.exe -m unittest tests.test_chapters_meta_contract tests.test_rbac_project_memberships -v`
- T04: `cd test && npx playwright test specs/api/chapters-meta.contract.spec.ts`
- Frontend migration: `cd frontend && npm run lint && npm test && npm run build`
- UI/E2E regression: `cd test && npx playwright test specs/ui/chapter-reader.spec.ts specs/ui/xss-markdown.spec.ts specs/ui/writing-save-status.spec.ts`
- Final regression: `cd backend && .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v` + `cd test && npx playwright test specs/api/api-smoke.spec.ts specs/ui/chapter-reader.spec.ts specs/ui/xss-markdown.spec.ts specs/ui/writing-save-status.spec.ts`

## Issue CSV
- Path: `issues/2026-03-06_21-59-27-wave-a-repo-hygiene-guards-chapter-api.csv`
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- none

## Acceptance Checklist
- [ ] `backend/.env` 不再被 Git 跟踪，仓库卫生规则与实际产物一致。
- [ ] `scripts/guards/` 可执行且至少 5 个 guard 可跑，默认策略不会把现有仓库完全卡死。
- [ ] backend 存在正式质量入口，开发者可一键运行 `ruff + guards`。
- [ ] 新章节 `meta/detail` 合同可用，meta 列表默认不传 `content_md/summary/plan`。
- [ ] Preview / Reader / Writing 等关键读路径不再依赖全量章节正文列表。
- [ ] 旧接口仍可工作，Wave A 完成后可继续生产部署并承接 `T05/T06`。

## Risks / Blockers
- `no-direct-llm-call-in-api` 与 `file-line-count-guard` 可能命中现有热点文件；需以 allowlist / warning mode 先审计、后收紧。
- Preview / Reader 从“列表即正文”改为“列表 + detail”后，如果状态管理不稳，容易出现切章闪烁或 stale response，需要用请求序列守卫兜底。
- 推送到 `origin/test` 依赖本机 git/SSH 状态正常；若远端拒绝需记录真实阻塞原因。

## Rollback / Recovery
- 每个 issue 独立 commit，可通过 `git revert <commit>` 回滚单条 issue。
- 章节 API 改造采用 additive 策略，若前端迁移出问题，可先回退前端 commit，保留新后端合同不影响旧路径。

## Checkpoints
- Commit after: `MVP-623`, `MVP-624`, `MVP-625`, `MVP-626`, `MVP-627`

## References
- `AGENTS.md`
- `5.4大调查详细记录.md:1116`
- `5.4大调查详细记录.md:1166`
- `5.4大调查详细记录.md:1266`
- `5.4大调查详细记录.md:1842`
- `5.4大调查详细记录.md:1889`
- `backend/app/api/routes/chapters.py:478`
- `frontend/src/pages/PreviewPage.tsx:46`
- `frontend/src/pages/ChapterReaderPage.tsx:128`
- `frontend/src/pages/writing/useChapterEditor.ts:95`
