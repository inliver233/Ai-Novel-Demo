# 向量 Embedding 配置（项目级覆盖 + 安全存储）

本项目的 Vector RAG 需要 embeddings 配置（base_url / model / api_key）。为避免仅依赖后端环境变量（`.env`），支持在「项目设置」中保存一份**项目级覆盖**配置：

- `base_url` / `model`：明文存储（非密钥）。
- `api_key`：加密存储（不返回明文，仅回显 `masked_api_key` / `has_api_key`）。
- 若项目未配置某字段，则回退使用后端环境变量 `VECTOR_EMBEDDING_*`（env fallback）。

## 加密与安全

- `api_key` 写入时会通过 `backend/app/core/secrets.py` 加密后存入数据库。
- `APP_ENV=prod` 时必须配置 `SECRET_ENCRYPTION_KEY`（Fernet key），否则无法写入/读取加密密钥。
- `APP_ENV=dev` 且在 Windows 上允许使用 DPAPI（`dpapi:` 前缀）作为本地单机便捷方案；生产环境不允许 DPAPI。

## UI / API 入口

- 前端：`/projects/:id/settings` 页面新增「向量检索（Vector RAG）」配置区。
- 后端：`GET/PUT /api/projects/{project_id}/settings` 会返回并更新向量配置相关字段（不返回明文 key）。

