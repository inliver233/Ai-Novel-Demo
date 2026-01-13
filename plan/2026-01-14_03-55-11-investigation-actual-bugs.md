---
mode: plan
task: 实测问题调查归因与修复准备
created_at: "2026-01-14T04:05:22+08:00"
complexity: complex
---

# Plan: 实测问题调查归因 + 修复准备材料（不实现修复）

## Goal
- 产出可执行的修复准备基线：`plan/*.md` + `issues/*.csv` +（可选）将新证据补充到 `实际测试发现错误.md`。
- 对 `实际测试发现错误.md` 中问题逐条给出：复现结论（`confirmed | partial | not_reproduced | needs_confirmation`）、证据摘要、疑似根因候选点（file:line）、验证路径、修复顺序与回归建议。
- 本次严格不做任何“修复实现”（不改业务/测试/配置逻辑）。仅做调查、拆分 Issue、生成文档。

## Scope
- In:
  - 允许新增/修改：`plan/...md`、`issues/...csv`、`实际测试发现错误.md`（仅限调查记录补充）。
  - 允许：启动前后端、运行 Playwright 复核、只读代码定位（`rg`/打开源码）。
- Out:
  - 禁止：`frontend/src/**`、`backend/app/**`、`test/**` 的任何实现修改。
  - 禁止：DB schema/Alembic 迁移实现、无关重构。

## Assumptions / Dependencies
- 环境：Windows + PowerShell；前端 `http://127.0.0.1:5173`；后端 `http://127.0.0.1:8000`（API base `/api`）。
- 后端默认启动在当前仓库状态会失败（P0，见 `实际测试发现错误.md:27`）；为进入 UI 复核，本次仅使用**进程级环境变量**临时覆盖 `AUTH_ADMIN_PASSWORD` 为长度 ≥ 8（不落盘、不提交）。
- 复核以 Playwright（更接近真实点击）为主；`chrome-devtools` 工具点击可能存在“点击伪影”，相关条目统一标注 `needs_confirmation`。
- 安全：任何文档/输出不记录明文密钥/令牌/密码；如涉及 Key 仅允许 `has_api_key/masked_api_key`；密码仅记录长度/是否满足约束。

## Phases
1. 复现与证据补齐（已完成）：按已知问题清单 + 横向扩展，用 Playwright + 只读定位补齐证据与结论，并写入 `实际测试发现错误.md` 的“调查补充”。（见 `实际测试发现错误.md:165`）
2. 归因与拆分 Issue（本次交付）：把问题聚类成“启动/路由+blocker/Drawer遮罩/a11y/交互伪影”，拆成未来可独立交付的 Issue（1 行=1 commit）。
3. 修复实现与回归（未来工作）：按优先级逐条实现、测试、review、回归并关闭 Issue。

## 调查结论摘要（按优先级）

### P0
- `confirmed`：后端按 README 启动在 lifespan 退出（`AUTH_ADMIN_PASSWORD` 长度 < 8 导致 `ensure_admin_user()` 抛错；`/docs` 不可达）。见 `实际测试发现错误.md:27`。

### P1
- `confirmed`：React Router 控制台警告 `A router only supports one blocker at a time` 可复现（跨页面残留多个 `useBlocker`）。见 `实际测试发现错误.md:184`。
- `partial`：世界书「预览触发」并非全链路失效：Drawer 关闭时 `POST .../preview_trigger -> 200`；Drawer 打开时 4s 内无 request/response（疑似被遮罩/布局覆盖导致点击未命中预览按钮）。见 `实际测试发现错误.md:43`、`实际测试发现错误.md:165`。
- `needs_confirmation`：侧边栏“URL 变但主体未更新需刷新”（原记录：`实际测试发现错误.md:90`）。Playwright 下未稳定复现；但 blocker warning 的存在会放大导航不稳定体感，建议先按 blocker 方向排查/修复后再复核该症状。

### P2
- `confirmed`：Settings 页存在 5 个表单字段缺少 `id/name`（Vector RAG 3 个 + 邀请成员 2 个）。见 `实际测试发现错误.md:64`、补充 `实际测试发现错误.md:165`。
- `needs_confirmation`：世界书编辑 Drawer 不支持 `Esc` 关闭（只能点击「关闭」或点遮罩）。见补充 `实际测试发现错误.md:192`。
- `needs_confirmation`：记录中的“保存按钮点击无效/模型配置保存为新配置无效/Memory Update 无提示/关闭无效/向导补齐设定误判”等，在 Playwright 下均 `not_reproduced`（见补充 `实际测试发现错误.md:165`），建议用真实鼠标二次复核并给出最终结论。

## 覆盖矩阵（页面 × 动作 × 结果）

| 页面/模块 | 动作 | 期望 | 复核结论 |
|---|---|---|---|
| Backend | README 启动 | 服务监听 8000，`/docs` 可达 | FAIL（P0 confirmed） |
| Login | 登录 admin | 进入 Dashboard | OK |
| Dashboard | 新建项目 | 跳转到 `/settings` | OK |
| Settings | 点击保存 | `PUT /api/projects/<id>/settings -> 200` | OK（not_reproduced“按钮点不动”） |
| Outline | 保存大纲 | `PUT /api/projects/<id>/outline -> 200` | OK（not_reproduced“按钮点不动”） |
| Prompts | 保存为新配置 | `POST /api/llm_profiles -> 200` | OK（not_reproduced“无请求”） |
| Worldbook | 预览（Drawer 关闭） | `POST .../preview_trigger -> 200` | OK |
| Worldbook | 预览（Drawer 打开） | 同上 | FAIL/无响应（P1 partial） |
| Writing | 保存章节 | `PUT /api/chapters/<id> -> 200` | OK（not_reproduced“按钮点不动”） |
| Writing | Memory Update gating/关闭 | 非 done toast；done 打开 Drawer；点击关闭可收起 | OK（not_reproduced“无提示/关闭无效”） |
| Export | 导出 Markdown | 触发下载；`/export* -> 200` | OK |
| Router | 跨页 dirty 离开 | 无 `only supports one blocker` warning | FAIL（P1 confirmed） |

## 同类问题族谱（共因假设）与定位点

### 族谱 A：启动链路 / 配置默认值（P0）
- 症状：后端 lifespan 失败退出，前端/测试全阻塞。
- 候选根因：`backend/.env` 默认 `AUTH_ADMIN_PASSWORD` 过短，触发 `hash_password` 校验抛错；lifespan 未兜底导致进程退出。
- 只读定位：`backend/app/main.py:81`、`backend/app/services/auth_service.py:12`。
- 如何验证修复：README 启动命令开箱即用；`/docs` 200；E2E `test/` 可启动后端。

### 族谱 B：Worldbook 预览触发 + Drawer 遮罩/层级（P1）
- 症状：Drawer 打开时“预览”点击无请求、可能误触编辑区字段，造成 dirty。
- 候选根因：布局在 `lg:grid-cols-2` 下预览区位于右侧；Drawer 从右侧覆盖预览区导致命中/交互异常（遮罩与 panel 的 hit-test 关系需要明确）。
- 只读定位：`frontend/src/pages/WorldbookPage.tsx:268`（两列布局）、`frontend/src/pages/WorldbookPage.tsx:310`（预览面板）、`frontend/src/pages/WorldbookPage.tsx:435`（编辑 Drawer）、`frontend/src/services/worldbookApi.ts:86`（接口）。
- 如何验证修复：Drawer 打开时预览要么可用（可触发 `preview_trigger`），要么明确禁用并提示；不得误改编辑区字段。

### 族谱 C：路由/离开提示（useBlocker）与页面缓存（PersistentOutlet）（P1）
- 症状：控制台 warning `A router only supports one blocker at a time`；可能引发导航不稳定/误判为“URL 变但页面没变”。
- 候选根因：`PersistentOutlet` 缓存导致“离开页面未卸载”；多个页面同时 dirty 时，多个 `useUnsavedChangesGuard` 同时注册 `useBlocker`，触发 warning（且 blocker 行为可能不确定）。
- 只读定位：`frontend/src/components/layout/AppShell.tsx:103`（PersistentOutlet）、`frontend/src/hooks/useUnsavedChangesGuard.tsx:6`（useBlocker）、受影响页面：`SettingsPage.tsx:218`、`OutlinePage.tsx:137`、`PromptsPage.tsx:219`、`pages/writing/useChapterEditor.ts:88` 等。
- 如何验证修复：按 `实际测试发现错误.md:184` 的复现路径操作后，控制台不再出现该 warning；离开提示逻辑稳定且仅由“当前可见页”生效。

### 族谱 D：保存按钮/交互“点不动”（P1，needs_confirmation）
- 症状：记录中多个页面“保存按钮点不动但 Ctrl/Cmd+S 可用”。
- 当前结论：Playwright 下未复现（点击保存可产生对应 `PUT -> 200`）；更像是工具点击命中/遮罩拦截导致的伪影。
- 如何验证：用真实鼠标复核；若仍可复现，再追查是否存在 Overlay 未关闭、z-index、pointer-events 或事件监听冲突。

### 族谱 E：a11y（P2，confirmed）
- 症状：Settings 页 5 个字段缺少 `id/name`（Chrome issue count:5）。
- 只读定位：`frontend/src/pages/SettingsPage.tsx:461`（Vector RAG Base URL/Model/API Key 三个输入）、`frontend/src/pages/SettingsPage.tsx:541`（邀请 user_id / 角色 select）。
- 如何验证修复：Chrome Issues 不再提示；DOM scan `missing id/name count` 为 0；E2E 选择器稳定性提升。

## 建议修复顺序（未来实现顺序）
1. **P0** 后端启动开箱即用（否则所有 UI/E2E 阻塞）。
2. **P1** Router blocker warning（`PersistentOutlet`/`useBlocker` 同时存在）——高风险且会放大“路由异常/刷新才更新”的体感。
3. **P1** Worldbook 预览触发（Drawer 打开时不可用/误触）——核心功能链路 + 容易造成误编辑。
4. **P2** Settings a11y（id/name）——低风险、收益明确。
5. **P2** Drawer Esc 关闭一致性（如确认需要）——减少误触成本。
6. 对所有 `needs_confirmation` 条目用真实点击复核；若确认是工具伪影，应在文档中撤案/降级，避免投入修复实现。

## 回归矩阵建议（未来新增/强化 E2E 点）
- Smoke：登录 -> 新建项目 -> 设定保存 -> 大纲保存 -> 写作创建章+保存 -> 导出下载。
- Worldbook：Drawer 关闭/打开两态下预览触发（至少覆盖“Drawer 打开时的禁用/提示/可用性”）。
- Router guard：跨页面 dirty 离开流程不得产生 `only supports one blocker` warning；离开确认/取消后 URL 与页面一致。
- a11y：Settings 页关键表单输入具备 `id/name`。

## Tests & Verification
- 本次调查复核命令（示例）：
  - Backend（P0 复现）：`cd backend; .\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --workers 1 --port 8000`
  - Frontend：`cd frontend; npm run dev`
  - Playwright：`cd test; npx playwright --version`
- 未来修复阶段（每条 Issue 在 CSV 填写）：
  - Backend：`cd backend; .\\.venv\\Scripts\\python.exe -m compileall -q app alembic` + `unittest discover ...`
  - Frontend：`cd frontend; npm run lint` / `npm test` / `npm run build`
  - E2E：`cd test; npm test`（或针对性 spec）

## Issue CSV
- Path: issues/2026-01-14_03-55-11-investigation-actual-bugs.csv
- Must share the same timestamp/slug as this plan.

## Tools / MCP
- `manual`：PowerShell 命令、Playwright（`test/`）。
- `chrome-devtools:*`：可选（仅用于截图/Network 面板补证；本次以 Playwright 为主）。

## Acceptance Checklist
- [ ] `plan/2026-01-14_03-55-11-investigation-actual-bugs.md` 与 `issues/2026-01-14_03-55-11-investigation-actual-bugs.csv` 已生成且匹配
- [ ] `python .codex/skills/plan/scripts/validate_issues_csv.py issues/2026-01-14_03-55-11-investigation-actual-bugs.csv` 通过
- [ ] plan 包含：结论摘要、覆盖矩阵、族谱/共因、修复顺序、回归建议、`needs_confirmation` 标注
- [ ] CSV 覆盖：已知问题 + 新发现问题（至少 Router blocker warning、Worldbook Drawer Esc）
- [ ] 除“文档入库初始化”外，所有真实问题行状态均为 `TODO`（三列均 TODO）

## Risks / Blockers
- P0：后端开箱即用失败会阻塞所有 UI/E2E。
- P1：`PersistentOutlet` 与 `useBlocker` 并存导致多个 blocker，属于高风险且难定位的问题源。
- P1：Worldbook 预览与编辑 Drawer 并存状态若不明确 UX，会继续产生误触/误编辑。
- `needs_confirmation` 条目若实际为工具伪影，应避免投入修复实现；优先复核。

## Rollback / Recovery
- 本次仅文档变更：`git revert <commit>` 或 `git reset --hard origin/test`。
- 运行产物（db/log/node_modules）不提交；如污染 tracked 文件，使用 `git checkout -- <path>` 恢复。

## Checkpoints
- Commit after: 仅 1 个提交（文档入库）：`[MVP-PLAN-001] ...`（包含 `实际测试发现错误.md` + plan + CSV）。

## References
- `实际测试发现错误.md:27`（P0 后端启动失败）
- `实际测试发现错误.md:43`（世界书预览触发）
- `实际测试发现错误.md:64`（a11y count 5）
- `实际测试发现错误.md:90`（侧边栏路由异常，needs_confirmation）
- `实际测试发现错误.md:106`（保存按钮点击无效，needs_confirmation）
- `实际测试发现错误.md:122`（保存为新配置无效，needs_confirmation）
- `实际测试发现错误.md:136`（向导补齐设定误判，needs_confirmation）
- `实际测试发现错误.md:151`（Memory Update 关闭无效，needs_confirmation）
- `实际测试发现错误.md:165`（Playwright 复核补充）
- `实际测试发现错误.md:184`（Router blocker warning）
- `实际测试发现错误.md:192`（Worldbook Drawer Esc）
- `backend/app/main.py:81`（lifespan 调用链）
- `backend/app/services/auth_service.py:12`（密码长度校验）
- `frontend/src/components/layout/AppShell.tsx:103`（PersistentOutlet）
- `frontend/src/hooks/useUnsavedChangesGuard.tsx:6`（useBlocker）
- `frontend/src/pages/WorldbookPage.tsx:310`（预览面板）
- `frontend/src/pages/WorldbookPage.tsx:435`（编辑 Drawer）
- `frontend/src/services/worldbookApi.ts:86`（preview_trigger API）
- `frontend/src/pages/SettingsPage.tsx:461`（Vector RAG 输入）
- `frontend/src/pages/SettingsPage.tsx:541`（邀请输入）
- `issues/README.md:1`（CSV contract）
- `docs/testing-policy.md:1`（Test_Method 规则）
