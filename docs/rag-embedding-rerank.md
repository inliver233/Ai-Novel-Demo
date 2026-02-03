# 向量检索（Vector RAG）：Embedding 与 Rerank 配置与测试

本项目的向量检索包含两段可独立配置的能力：

- **Embedding（向量化）**：用于构建索引与查询向量（影响“召回”）。
- **Rerank（重排）**：对候选片段做二次排序（影响“排序质量”，通常更准，但可能更慢/更贵）。

两者可以分别使用不同的 `provider/base_url/model/api_key`（例如本地 Embedding + 远端 Rerank）。

## 1) 配置入口（UI）

进入项目后：

1. 打开「模型配置」页
2. 找到「向量检索（Vector RAG）」面板
3. 分别完成 **Embedding** 与（可选）**Rerank** 配置

说明：

- UI 中保存到 DB 的 API Key 会被加密存储；返回到前端只会显示 `has_api_key/masked_api_key`，不会返回明文。
- 若某些字段留空，后端会尝试从环境变量读取作为 fallback。

## 2) Embedding 配置（召回）

常见字段：

- `provider`：Embedding 提供方（例如 `openai_compatible`、`azure_openai`、`sentence_transformers`）
- `base_url` / `model` / `api_key`：按 provider 选择配置（Azure/SentenceTransformers 会出现额外字段）

后端环境变量（fallback）参考：

- `VECTOR_EMBEDDING_BASE_URL`
- `VECTOR_EMBEDDING_MODEL`
- `VECTOR_EMBEDDING_API_KEY`

## 3) Rerank 配置（重排）

Rerank 有两层配置：

- **是否启用**：`vector_rerank_enabled`
- **算法与候选数**：`vector_rerank_method` / `vector_rerank_top_k`
- **提供方**（可选）：`vector_rerank_provider/base_url/model/api_key/timeout_seconds`

当 provider 选择 `external_rerank_api` 时，后端会按 OpenAI 兼容路径访问 `POST /v1/rerank`（因此 `base_url` 通常以 `/v1` 结尾）。

后端环境变量（fallback）参考：

- `VECTOR_RERANK_ENABLED`
- `VECTOR_RERANK_EXTERNAL_BASE_URL`
- `VECTOR_RERANK_EXTERNAL_MODEL`
- `VECTOR_RERANK_EXTERNAL_API_KEY`
- `VECTOR_RERANK_EXTERNAL_TIMEOUT_SECONDS`

## 4) 自检（dry-run）

在「向量检索（Vector RAG）」面板顶部提供两按钮：

- “测试 embedding”：验证 embedding endpoint 是否可用，并返回 `dims/耗时/request_id`
- “测试 rerank”：验证 rerank endpoint 是否可用，并返回 `order/耗时/request_id`

若测试失败：

- 先检查 `base_url/model/api_key` 是否正确
- 再到后端日志按 `request_id` 检索详细错误

## 5) 端到端验证：在 RagPage 看 rerank_obs 是否生效

1. 打开「RAG」页（项目内）
2. 确保已导入资料并构建索引（索引 dirty 时先 rebuild）
3. 在 Query 输入框输入任意 query 并点击“查询”

若 rerank 生效：

- 结果面板会出现 `rerank:` 概要行（用于快速确认启用/方法/top_k 等）
- 可展开 `rerank_obs` 查看更完整的观测信息（排障用）

若没有看到 rerank 信息，通常意味着：

- 没有启用 rerank（`vector_rerank_enabled=false`），或
- 向量检索未启用/索引未构建（`disabled_reason` 非空），或
- 本次查询未产生候选（候选数为 0），因此没有可重排内容

