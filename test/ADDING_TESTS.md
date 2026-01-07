# 如何新增测试

## UI 测试（推荐）

位置：`test/specs/ui/*.spec.ts`

建议模板：

- UI spec 请从 `../../lib/ui-test` 导入（内置外网阻断 guard），不要直接从 `@playwright/test` 导入
- 用 `bootstrapProject(request)` 准备一个项目（会绑定 Mock LLM Profile）
- 如需覆盖非 OpenAI provider 场景，可用 `bootstrapProjectWithLlmProfile(request, ...)` 自定义 provider/base_url/model
  - 注意：Mock LLM 默认 base_url 为 `http://127.0.0.1:4010/v1`（OpenAI-compatible）；Anthropic/Gemini 这类 provider 需要用不带 `/v1` 的 host base（例如 `http://127.0.0.1:4010`）
- 用 `getByRole(..., { exact: true })` 规避 strict mode
- 需要验证布局/UI 回归时，使用 `toHaveScreenshot` 并在变更后跑 `--update-snapshots`

## API 测试

位置：`test/specs/api/*.spec.ts`

- 直接请求 `loadState().backendUrl` 下的 `/api/...`
- 断言 `ok/data/request_id` 结构与关键字段

## DB 测试（Schema 回归）

位置：`test/specs/db/*.spec.ts`

- 基线文件：`test/contracts/db_schema.json`
- 更新基线：`pwsh test/scripts/snapshot-db.ps1`
