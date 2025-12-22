# 临时过程记录（必填）

> 仓库：`E:\毕设小说项目\项目\demo`  
> 契约基线：`mvp开发计划.md` v2.4（除非明确修改契约语义，否则不 bump）  
> 绝对约束（本轮）：禁用任何 MCP；API Key 不得明文回显；SQLite 单 worker；LLM 调用不持有 DB 长事务；统一响应 `{ok,data|error,request_id}` + `X-Request-Id`（CORS expose）；生成不自动落库；保留 `backend/ainovel.db.bak.20251218173544`。

---

## 0) TODO Checklist（必须清零）

### 文档与基线
- [x] 已按顺序阅读：`对话交接.md` → `开发进度.md` → `mvp开发计划.md` → `mvp最终改善文档.md` → `ui设计规范.md`
- [x] 已核对 `git status`/`git diff`，梳理 WIP 与风险点

### 代码修复与质量
- [x] 后端：统一响应契约 `{ok,data|error,request_id}`（导出除外）+ `X-Request-Id`（CORS expose）
- [x] 后端：Secrets 不泄露（日志/错误详情/响应/导出/前端 toast/console 全链路无明文 key）
- [x] 后端：SQLite 单 worker 约束可见且不易误用（文档/启动提示/可选 runtime guard）
- [x] 后端：LLM 调用不持有 DB 长事务（先读库→关闭 session→请求上游→新 session 落库）
- [x] 后端：错误码映射与 `request_id` 可追踪（失败 JSON 可定位）
- [x] 前端：Prompts profiles（CRUD/绑定/保存 key/清除 key/测试连接）全链路 OK，且不依赖 localStorage/header 传 key
- [x] 前端：完成度口径（全部章节 `status=done` 才 100%）在 Dashboard 与 WizardNextBar 一致
- [x] 前端：Writing 流式生成可隐藏面板不中断；隐藏浮层可展开/取消；toast 携带 `request_id`
- [x] 前端：Preview 页（列表/抽屉/渲染/编辑跳转/下一步到 Export）可用且响应式不破
- [x] 全局：遵循 Paper & Ink（避免破坏主题系统的硬编码；尽量消费语义变量/现有组件）

### 验收与 DoD
- [ ] 手工闭环（按 `mvp开发计划.md` 第 11 节）跑通并记录关键 `request_id`（不使用 MCP）
- [ ] 三端响应式回归（390x844 / 768x1024 / 1440x900）关键路径通过（Console 0 error；Network 无未处理 4xx/5xx）
- [x] DoD：`python -m compileall -q backend\\app backend\\alembic` 通过
- [x] DoD：`cd frontend && npm run lint && npm run build` 通过

---

## 1) 发现的问题清单（现象 / 根因 / 修复 / 验证）

> 逐条追加；每条必须写清楚“如何验证”。

### P0 / P1（本轮必须修）
1) **LLM Test 仍可能持有 DB 事务**
   - 现象：`POST /api/llm/test` 在读取项目/配置后直接调用上游，SQLite 下可能导致长事务/锁库风险（不符合 v2.4 约束）。
   - 根因：路由使用请求级 session（`DbDep`）读取后未显式结束事务/关闭 session。
   - 修复：读取所需字段后 `commit/close`（或使用独立 SessionLocal 读完即关）再调用上游；确保无长事务。
   - 验证：对 `/api/llm/test` 发起慢请求时，其他写入接口不应被 `database is locked` 影响；代码 review 确认“读库→关→上游→（如需）再开库”。
   - 状态：✅ 已修复（`backend/app/api/routes/llm.py` 改为独立 `SessionLocal()` 读完即 `close()`，再调用上游）

2) **更新 llm_profile 后项目 preset 可能不同步**
   - 现象：更新 profile 的 `provider/base_url/model` 后，项目生成仍按旧 preset 参数走，产生“UI 显示/生成实际不一致”。
   - 根因：绑定 profile 时后端会同步 `llm_preset`，但 profile 更新路径未同步所有引用该 profile 的项目 preset。
   - 修复：后端在更新 profile 时同步更新所有绑定该 profile 的项目 `llm_presets.provider/base_url/model`（并补齐缺失 preset）。
   - 验证：更新 profile 后无需重新绑定，生成与测试连接走新配置；回归 Prompts 页刷新后字段一致。
   - 状态：✅ 已修复（`backend/app/api/routes/llm_profiles.py` 新增 `_sync_bound_project_presets`）

3) **前端遗留 `llmKeyStore`（localStorage 明文 Key）**
   - 现象：存在 `frontend/src/services/llmKeyStore.ts`（写入 localStorage），与 v2.4“前端默认不保存 key”冲突，且存在误用风险。
   - 根因：历史方案遗留文件，当前已无引用但仍存在。
   - 修复：删除该文件（或降级为仅保留 storageKey 计算且不读写 Key）。
   - 验证：全局搜索无引用；`npm run lint`/`npm run build` 通过。
   - 状态：✅ 已修复（已删除 `frontend/src/services/llmKeyStore.ts`，并通过 lint/build）

4) **写作页 AI 面板按钮命名/顺序不符合直觉**
   - 现象：按钮为“保存章节 / 保存并开始下一章生成 / 生成草稿（追加） / 生成草稿（替换）”，理解成本偏高。
   - 修复：改为“生成（替换） / 保存并继续 / 追加生成 / 保存”，并同步提示文案。
   - 验证：写作页右侧 AI 面板按钮显示与语义一致。
   - 状态：✅ 已修复（`frontend/src/components/writing/AiGenerateDrawer.tsx`）

5) **写作未完成时无法进入预览**
   - 现象：若未把全部章节标记为 `done`，写作页向导主按钮被禁用，无法“下一步”进入预览。
   - 修复：对写作步骤做例外：允许从写作页直接“下一步：预览阅读”（不改变完成度/百分比口径）。
   - 验证：写作未 100% 时，向导主按钮可跳转预览页；完成度% 仍按全部 `done` 才 100%。
   - 状态：✅ 已修复（`frontend/src/components/atelier/WizardNextBar.tsx`）

---

## 2) 手工回归记录（第 11 节脚本）

> 说明：本轮禁用 MCP，因此 Network/Console 需人工在浏览器中检查并把 `request_id` 抄到这里（严禁记录明文 API Key）。

### 启动
- 后端：`cd backend` → `uvicorn app.main:app --reload --workers 1 --port 8000`
- 前端：`cd frontend && npm run dev`

### 脚本步骤记录模板
1) Dashboard 新建项目：✅/❌  `request_id=`
2) Settings 保存并刷新：✅/❌  `request_id=`
3) Characters 新增/保存/刷新：✅/❌  `request_id=`
4) Prompts profiles + 保存 Key + 测试连接 + 刷新：✅/❌  `request_id=`
5) Outline 非流式生成（至少 1 次）+ 应用并保存：✅/❌  `request_id=`
6) Outline 流式生成（至少 1 次，可取消）：✅/❌  `request_id=`
7) 从大纲 bulk_create ≥10 章 → Writing：✅/❌  `request_id=`
8) Writing 生成第 1 章（replace/append）+ 验证“生成不落库”：✅/❌  `request_id=`
9) “保存并开始下一章生成”：✅/❌  `request_id=`
10) Writing 流式：隐藏 AI 面板不中断 + 浮层展开/取消：✅/❌  `request_id=`
11) Generation runs：列表/详情可追踪：✅/❌  `request_id=`
12) Preview：列表/抽屉/渲染/编辑跳转/下一步：✅/❌  `request_id=`
13) Export：导出 Markdown 下载成功：✅/❌  `request_id=`
14) Dashboard：完成度合理；完成后编辑恢复“下一步”且保留“回到概览”：✅/❌

### 三端尺寸验证记录
- 手机 390x844：✅/❌  备注：
- 平板 768x1024：✅/❌  备注：
- PC 1440x900：✅/❌  备注：

---

## 3) DoD 执行结果（粘贴原始输出）

### Backend
```text
python -m compileall -q backend\app backend\alembic
# OK（成功时无输出）
```

### Frontend
```text
> frontend@0.0.0 lint
> eslint .
```

```text
> frontend@0.0.0 build
> tsc -b && vite build

vite v7.2.7 building client environment for production...
transforming...
✓ 2395 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                  1.14 kB │ gzip:   0.56 kB
(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
dist/assets/index-B7qLpHLU.css  14.17 kB │ gzip:   3.92 kB
dist/assets/index-CRrxuYZv.js  698.86 kB │ gzip: 210.62 kB
✓ built in 5.93s
```

---

## 4) 最小后端 Smoke（非 UI）

- `GET /api/health`：✅ `request_id=6992b8a1-9166-42c9-9811-78b8e942b702`
