import type { Dispatch, SetStateAction } from "react";

import { RequestIdBadge } from "../../components/ui/RequestIdBadge";
import { UI_COPY } from "../../lib/uiCopy";
import type { ProjectSettings } from "../../types";

import { PROMPTS_COPY } from "./promptsCopy";
import type { VectorEmbeddingDryRunResult, VectorRagForm, VectorRerankDryRunResult } from "./models";

type DryRunErrorState = {
  message: string;
  code: string;
  requestId?: string;
};

type DryRunState<T> = {
  requestId: string;
  result: T;
};

export type PromptsVectorRagSectionProps = {
  baselineSettings: ProjectSettings | null;
  vectorForm: VectorRagForm;
  setVectorForm: Dispatch<SetStateAction<VectorRagForm>>;
  vectorRerankTopKDraft: string;
  setVectorRerankTopKDraft: Dispatch<SetStateAction<string>>;
  vectorRerankTimeoutDraft: string;
  setVectorRerankTimeoutDraft: Dispatch<SetStateAction<string>>;
  vectorRerankHybridAlphaDraft: string;
  setVectorRerankHybridAlphaDraft: Dispatch<SetStateAction<string>>;
  vectorApiKeyDraft: string;
  setVectorApiKeyDraft: Dispatch<SetStateAction<string>>;
  vectorApiKeyClearRequested: boolean;
  setVectorApiKeyClearRequested: Dispatch<SetStateAction<boolean>>;
  rerankApiKeyDraft: string;
  setRerankApiKeyDraft: Dispatch<SetStateAction<string>>;
  rerankApiKeyClearRequested: boolean;
  setRerankApiKeyClearRequested: Dispatch<SetStateAction<boolean>>;
  savingVector: boolean;
  vectorRagDirty: boolean;
  vectorApiKeyDirty: boolean;
  rerankApiKeyDirty: boolean;
  embeddingProviderPreview: string;
  embeddingDryRunLoading: boolean;
  embeddingDryRun: DryRunState<VectorEmbeddingDryRunResult> | null;
  embeddingDryRunError: DryRunErrorState | null;
  rerankDryRunLoading: boolean;
  rerankDryRun: DryRunState<VectorRerankDryRunResult> | null;
  rerankDryRunError: DryRunErrorState | null;
  onSave: () => void;
  onRunEmbeddingDryRun: () => void;
  onRunRerankDryRun: () => void;
};

export function PromptsVectorRagSection(props: PromptsVectorRagSectionProps) {
  const {
    baselineSettings,
    vectorForm,
    setVectorForm,
    vectorRerankTopKDraft,
    setVectorRerankTopKDraft,
    vectorRerankTimeoutDraft,
    setVectorRerankTimeoutDraft,
    vectorRerankHybridAlphaDraft,
    setVectorRerankHybridAlphaDraft,
    vectorApiKeyDraft,
    setVectorApiKeyDraft,
    vectorApiKeyClearRequested,
    setVectorApiKeyClearRequested,
    rerankApiKeyDraft,
    setRerankApiKeyDraft,
    rerankApiKeyClearRequested,
    setRerankApiKeyClearRequested,
    savingVector,
    vectorRagDirty,
    vectorApiKeyDirty,
    rerankApiKeyDirty,
    embeddingProviderPreview,
    embeddingDryRunLoading,
    embeddingDryRun,
    embeddingDryRunError,
    rerankDryRunLoading,
    rerankDryRun,
    rerankDryRunError,
    onSave,
    onRunEmbeddingDryRun,
    onRunRerankDryRun,
  } = props;

  return (
    <section className="panel p-6" id="rag-config" aria-label={UI_COPY.vectorRag.title} role="region">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="grid gap-1">
          <div className="font-content text-xl text-ink">{UI_COPY.vectorRag.title}</div>
          <div className="text-xs text-subtext">{UI_COPY.vectorRag.subtitle}</div>
          <div className="text-xs text-subtext">{UI_COPY.vectorRag.apiKeyHint}</div>
        </div>
        <button
          className="btn btn-primary"
          disabled={savingVector || (!vectorRagDirty && !vectorApiKeyDirty && !rerankApiKeyDirty)}
          onClick={onSave}
          type="button"
        >
          {UI_COPY.vectorRag.save}
        </button>
      </div>

      {baselineSettings ? (
        <div className="mt-4 grid gap-4">
          <div className="rounded-atelier border border-border bg-canvas p-4 text-xs text-subtext">
            <div>
              当前生效：Embedding 提供方（provider）=
              {baselineSettings.vector_embedding_effective_provider || "openai_compatible"}
              （状态: {baselineSettings.vector_embedding_effective_disabled_reason ?? "enabled"}；来源:{" "}
              {baselineSettings.vector_embedding_effective_source}）
            </div>
            <div className="mt-1">
              Rerank：{baselineSettings.vector_rerank_effective_enabled ? "enabled" : "disabled"}（method:{" "}
              {baselineSettings.vector_rerank_effective_method}；provider:{" "}
              {baselineSettings.vector_rerank_effective_provider || "（空）"}；model:{" "}
              {baselineSettings.vector_rerank_effective_model || "（空）"}；top_k:{" "}
              {baselineSettings.vector_rerank_effective_top_k}；alpha:{" "}
              {baselineSettings.vector_rerank_effective_hybrid_alpha ?? 0}；来源:{" "}
              {baselineSettings.vector_rerank_effective_source}；配置:{" "}
              {baselineSettings.vector_rerank_effective_config_source}）
            </div>
          </div>

          <div className="rounded-atelier border border-border bg-canvas p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-sm text-ink">{UI_COPY.vectorRag.dryRunTitle}</div>
              <div className="flex flex-wrap gap-2">
                <button
                  className="btn btn-secondary"
                  disabled={
                    savingVector ||
                    embeddingDryRunLoading ||
                    rerankDryRunLoading ||
                    vectorRagDirty ||
                    vectorApiKeyDirty ||
                    rerankApiKeyDirty
                  }
                  onClick={onRunEmbeddingDryRun}
                  type="button"
                >
                  {embeddingDryRunLoading ? "测试 embedding…" : "测试 embedding"}
                </button>
                <button
                  className="btn btn-secondary"
                  disabled={
                    savingVector ||
                    embeddingDryRunLoading ||
                    rerankDryRunLoading ||
                    vectorRagDirty ||
                    vectorApiKeyDirty ||
                    rerankApiKeyDirty
                  }
                  onClick={onRunRerankDryRun}
                  type="button"
                >
                  {rerankDryRunLoading ? "测试 rerank…" : "测试 rerank"}
                </button>
              </div>
            </div>
            {vectorRagDirty || vectorApiKeyDirty || rerankApiKeyDirty ? (
              <div className="mt-1 text-[11px] text-subtext">{PROMPTS_COPY.vectorRag.saveBeforeTestHint}</div>
            ) : null}

            {embeddingDryRunError ? (
              <div className="mt-3 rounded-atelier border border-border bg-surface p-3">
                <div className="text-xs text-danger">
                  Embedding 测试失败：{embeddingDryRunError.message} ({embeddingDryRunError.code})
                </div>
                <RequestIdBadge requestId={embeddingDryRunError.requestId} className="mt-2" />
                <div className="mt-1 text-[11px] text-subtext">
                  排障：检查 embedding base_url/model/api_key；打开后端日志并搜索 request_id。
                </div>
              </div>
            ) : null}

            {embeddingDryRun ? (
              <div className="mt-3 rounded-atelier border border-border bg-surface p-3">
                <div className="text-xs text-subtext">
                  Embedding：{embeddingDryRun.result.enabled ? "enabled" : "disabled"}；dims:
                  {embeddingDryRun.result.dims ?? "（未知）"}；耗时:
                  {embeddingDryRun.result.timings_ms?.total ?? "（未知）"}ms
                  {embeddingDryRun.result.error ? `；error: ${embeddingDryRun.result.error}` : ""}
                </div>
                <RequestIdBadge requestId={embeddingDryRun.requestId} className="mt-2" />
              </div>
            ) : null}

            {rerankDryRunError ? (
              <div className="mt-3 rounded-atelier border border-border bg-surface p-3">
                <div className="text-xs text-danger">
                  Rerank 测试失败：{rerankDryRunError.message} ({rerankDryRunError.code})
                </div>
                <RequestIdBadge requestId={rerankDryRunError.requestId} className="mt-2" />
                <div className="mt-1 text-[11px] text-subtext">
                  排障：检查 rerank base_url/model/api_key；若使用 external_rerank_api，确认 /v1/rerank 可访问。
                </div>
              </div>
            ) : null}

            {rerankDryRun ? (
              <div className="mt-3 rounded-atelier border border-border bg-surface p-3">
                <div className="text-xs text-subtext">
                  Rerank：{rerankDryRun.result.enabled ? "enabled" : "disabled"}；method:
                  {rerankDryRun.result.method ?? "（未知）"}；provider:
                  {(rerankDryRun.result.rerank as { provider?: string } | undefined)?.provider ?? "（未知）"}；耗时:
                  {rerankDryRun.result.timings_ms?.total ?? "（未知）"}ms；order:
                  {(rerankDryRun.result.order ?? []).join(" → ") || "（空）"}
                </div>
                <RequestIdBadge requestId={rerankDryRun.requestId} className="mt-2" />
              </div>
            ) : null}
          </div>

          <div className="grid gap-2">
            <div className="text-sm text-ink">{UI_COPY.vectorRag.rerankTitle}</div>
            <div className="grid gap-4 sm:grid-cols-3">
              <label className="flex items-center gap-2 text-sm text-ink sm:col-span-3">
                <input
                  className="checkbox"
                  checked={vectorForm.vector_rerank_enabled}
                  onChange={(e) => setVectorForm((v) => ({ ...v, vector_rerank_enabled: e.target.checked }))}
                  type="checkbox"
                  name="vector_rerank_enabled"
                />
                启用 rerank（对候选片段做相关性重排）
              </label>
              <label className="grid gap-1 sm:col-span-2">
                <span className="text-xs text-subtext">重排算法（rerank method）</span>
                <select
                  className="select"
                  value={vectorForm.vector_rerank_method}
                  onChange={(e) => setVectorForm((v) => ({ ...v, vector_rerank_method: e.target.value }))}
                  name="vector_rerank_method"
                >
                  <option value="auto">auto</option>
                  <option value="rapidfuzz_token_set_ratio">rapidfuzz_token_set_ratio</option>
                  <option value="token_overlap">token_overlap</option>
                </select>
              </label>
              <label className="grid gap-1">
                <span className="text-xs text-subtext">候选数量（top_k）</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={1000}
                  value={vectorRerankTopKDraft}
                  onBlur={() => {
                    const raw = vectorRerankTopKDraft.trim();
                    if (!raw) {
                      setVectorRerankTopKDraft(String(vectorForm.vector_rerank_top_k));
                      return;
                    }
                    const next = Math.floor(Number(raw));
                    if (!Number.isFinite(next)) {
                      setVectorRerankTopKDraft(String(vectorForm.vector_rerank_top_k));
                      return;
                    }
                    const clamped = Math.max(1, Math.min(1000, next));
                    setVectorForm((v) => ({ ...v, vector_rerank_top_k: clamped }));
                    setVectorRerankTopKDraft(String(clamped));
                  }}
                  onChange={(e) => setVectorRerankTopKDraft(e.target.value)}
                  name="vector_rerank_top_k"
                />
              </label>
            </div>
            <div className="text-[11px] text-subtext">
              提示：启用后会对候选结果做二次排序，通常命中更好，但可能增加耗时/成本。
            </div>
          </div>

          <details className="rounded-atelier border border-border bg-canvas p-4" aria-label="Rerank 提供方配置">
            <summary className="ui-transition-fast cursor-pointer select-none text-sm text-ink hover:text-ink">
              {UI_COPY.vectorRag.rerankConfigDetailsTitle}
            </summary>
            <div className="mt-4 grid gap-4">
              <div className="text-xs text-subtext">{UI_COPY.vectorRag.backendEnvFallbackHint}</div>
              <div className="text-xs text-subtext">
                启用 external_rerank_api：method 建议保持 auto；provider 选 external_rerank_api，并填写
                base_url/model（可选 api_key）。
              </div>

              <label className="grid gap-1">
                <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankProviderLabel}</span>
                <select
                  className="select"
                  value={vectorForm.vector_rerank_provider}
                  onChange={(e) => setVectorForm((v) => ({ ...v, vector_rerank_provider: e.target.value }))}
                  name="vector_rerank_provider"
                >
                  <option value="">（使用后端环境变量）</option>
                  <option value="external_rerank_api">external_rerank_api</option>
                </select>
                <div className="text-[11px] text-subtext">
                  当前有效：{baselineSettings.vector_rerank_effective_provider || "（空）"}
                </div>
              </label>

              <label className="grid gap-1">
                <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankBaseUrlLabel}</span>
                <input
                  className="input"
                  value={vectorForm.vector_rerank_base_url}
                  onChange={(e) => {
                    const next = e.target.value;
                    setVectorForm((v) => {
                      const shouldAutoSetProvider = !v.vector_rerank_provider.trim() && next.trim().length > 0;
                      return {
                        ...v,
                        vector_rerank_base_url: next,
                        ...(shouldAutoSetProvider ? { vector_rerank_provider: "external_rerank_api" } : {}),
                      };
                    });
                  }}
                  name="vector_rerank_base_url"
                />
                <div className="text-[11px] text-subtext">
                  当前有效：{baselineSettings.vector_rerank_effective_base_url || "（空）"}
                </div>
              </label>

              <label className="grid gap-1">
                <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankModelLabel}</span>
                <input
                  className="input"
                  value={vectorForm.vector_rerank_model}
                  onChange={(e) => setVectorForm((v) => ({ ...v, vector_rerank_model: e.target.value }))}
                  name="vector_rerank_model"
                />
                <div className="text-[11px] text-subtext">
                  当前有效：{baselineSettings.vector_rerank_effective_model || "（空）"}
                </div>
              </label>

              <div className="grid gap-4 sm:grid-cols-2">
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankTimeoutLabel}</span>
                  <input
                    className="input"
                    type="number"
                    min={1}
                    max={120}
                    value={vectorRerankTimeoutDraft}
                    onBlur={() => {
                      const raw = vectorRerankTimeoutDraft.trim();
                      if (!raw) {
                        setVectorForm((v) => ({ ...v, vector_rerank_timeout_seconds: null }));
                        setVectorRerankTimeoutDraft("");
                        return;
                      }
                      const next = Math.floor(Number(raw));
                      if (!Number.isFinite(next)) {
                        setVectorRerankTimeoutDraft(
                          vectorForm.vector_rerank_timeout_seconds != null
                            ? String(vectorForm.vector_rerank_timeout_seconds)
                            : "",
                        );
                        return;
                      }
                      const clamped = Math.max(1, Math.min(120, next));
                      setVectorForm((v) => ({ ...v, vector_rerank_timeout_seconds: clamped }));
                      setVectorRerankTimeoutDraft(String(clamped));
                    }}
                    onChange={(e) => setVectorRerankTimeoutDraft(e.target.value)}
                    name="vector_rerank_timeout_seconds"
                  />
                  <div className="text-[11px] text-subtext">
                    当前有效：{baselineSettings.vector_rerank_effective_timeout_seconds ?? 15}
                  </div>
                </label>

                <label className="grid gap-1">
                  <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankHybridAlphaLabel}</span>
                  <input
                    className="input"
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    value={vectorRerankHybridAlphaDraft}
                    onBlur={() => {
                      const raw = vectorRerankHybridAlphaDraft.trim();
                      if (!raw) {
                        setVectorForm((v) => ({ ...v, vector_rerank_hybrid_alpha: null }));
                        setVectorRerankHybridAlphaDraft("");
                        return;
                      }
                      const next = Number(raw);
                      if (!Number.isFinite(next)) {
                        setVectorRerankHybridAlphaDraft(
                          vectorForm.vector_rerank_hybrid_alpha != null
                            ? String(vectorForm.vector_rerank_hybrid_alpha)
                            : "",
                        );
                        return;
                      }
                      const clamped = Math.max(0, Math.min(1, next));
                      setVectorForm((v) => ({ ...v, vector_rerank_hybrid_alpha: clamped }));
                      setVectorRerankHybridAlphaDraft(String(clamped));
                    }}
                    onChange={(e) => setVectorRerankHybridAlphaDraft(e.target.value)}
                    name="vector_rerank_hybrid_alpha"
                  />
                  <div className="text-[11px] text-subtext">
                    当前有效：{baselineSettings.vector_rerank_effective_hybrid_alpha ?? 0}
                  </div>
                </label>
              </div>

              <label className="grid gap-1">
                <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankApiKeyLabel}</span>
                <input
                  className="input"
                  type="password"
                  autoComplete="off"
                  value={rerankApiKeyDraft}
                  onChange={(e) => {
                    setRerankApiKeyDraft(e.target.value);
                    setRerankApiKeyClearRequested(false);
                  }}
                  name="vector_rerank_api_key"
                />
                <div className="text-[11px] text-subtext">
                  已保存（项目覆盖）：
                  {baselineSettings.vector_rerank_has_api_key
                    ? baselineSettings.vector_rerank_masked_api_key
                    : "（无）"}
                  {baselineSettings.vector_rerank_effective_has_api_key
                    ? ` | 当前有效：${baselineSettings.vector_rerank_effective_masked_api_key}`
                    : " | 当前有效：（无）"}
                  {rerankApiKeyClearRequested ? UI_COPY.vectorRag.pendingClearSuffix : ""}
                </div>
              </label>

              <div className="flex flex-wrap gap-2">
                <button
                  className="btn btn-secondary"
                  disabled={savingVector || !baselineSettings.vector_rerank_has_api_key}
                  onClick={() => {
                    setRerankApiKeyDraft("");
                    setRerankApiKeyClearRequested(true);
                  }}
                  type="button"
                >
                  {UI_COPY.vectorRag.rerankClearApiKey}
                </button>
                <button
                  className="btn btn-secondary"
                  disabled={savingVector}
                  onClick={() => {
                    setVectorForm((v) => ({
                      ...v,
                      vector_rerank_provider: "",
                      vector_rerank_base_url: "",
                      vector_rerank_model: "",
                      vector_rerank_timeout_seconds: null,
                      vector_rerank_hybrid_alpha: null,
                    }));
                    setVectorRerankTimeoutDraft("");
                    setVectorRerankHybridAlphaDraft("");
                    setRerankApiKeyDraft("");
                    setRerankApiKeyClearRequested(true);
                  }}
                  type="button"
                >
                  {UI_COPY.vectorRag.rerankResetOverrides}
                </button>
              </div>
            </div>
          </details>

          <details className="rounded-atelier border border-border bg-canvas p-4">
            <summary className="ui-transition-fast cursor-pointer select-none text-sm text-ink hover:text-ink">
              {UI_COPY.vectorRag.embeddingTitle}
            </summary>
            <div className="mt-4 grid gap-4">
              <div className="text-xs text-subtext">{UI_COPY.vectorRag.backendEnvFallbackHint}</div>

              <label className="grid gap-1">
                <span className="text-xs text-subtext">
                  Embedding 提供方（provider；项目覆盖；留空=使用后端环境变量）
                </span>
                <select
                  className="select"
                  value={vectorForm.vector_embedding_provider}
                  onChange={(e) => setVectorForm((v) => ({ ...v, vector_embedding_provider: e.target.value }))}
                  name="vector_embedding_provider"
                >
                  <option value="">（使用后端环境变量）</option>
                  <option value="openai_compatible">openai_compatible</option>
                  <option value="azure_openai">azure_openai</option>
                  <option value="google">google</option>
                  <option value="custom">custom</option>
                  <option value="local_proxy">local_proxy</option>
                  <option value="sentence_transformers">sentence_transformers</option>
                </select>
                <div className="text-[11px] text-subtext">
                  当前有效：{baselineSettings.vector_embedding_effective_provider || "openai_compatible"}
                </div>
              </label>

              {embeddingProviderPreview === "azure_openai" ? (
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="grid gap-1">
                    <span className="text-xs text-subtext">
                      Azure 部署名（deployment；项目覆盖；留空=使用后端环境变量）
                    </span>
                    <input
                      className="input"
                      value={vectorForm.vector_embedding_azure_deployment}
                      onChange={(e) =>
                        setVectorForm((v) => ({ ...v, vector_embedding_azure_deployment: e.target.value }))
                      }
                      name="vector_embedding_azure_deployment"
                    />
                    <div className="text-[11px] text-subtext">
                      当前有效：{baselineSettings.vector_embedding_effective_azure_deployment || "（空）"}
                    </div>
                  </label>
                  <label className="grid gap-1">
                    <span className="text-xs text-subtext">
                      Azure API 版本（api_version；项目覆盖；留空=使用后端环境变量）
                    </span>
                    <input
                      className="input"
                      value={vectorForm.vector_embedding_azure_api_version}
                      onChange={(e) =>
                        setVectorForm((v) => ({ ...v, vector_embedding_azure_api_version: e.target.value }))
                      }
                      name="vector_embedding_azure_api_version"
                    />
                    <div className="text-[11px] text-subtext">
                      当前有效：{baselineSettings.vector_embedding_effective_azure_api_version || "（空）"}
                    </div>
                  </label>
                </div>
              ) : null}

              {embeddingProviderPreview === "sentence_transformers" ? (
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">
                    SentenceTransformers 模型（项目覆盖；留空=使用后端环境变量）
                  </span>
                  <input
                    className="input"
                    value={vectorForm.vector_embedding_sentence_transformers_model}
                    onChange={(e) =>
                      setVectorForm((v) => ({
                        ...v,
                        vector_embedding_sentence_transformers_model: e.target.value,
                      }))
                    }
                    name="vector_embedding_sentence_transformers_model"
                  />
                  <div className="text-[11px] text-subtext">
                    当前有效：{baselineSettings.vector_embedding_effective_sentence_transformers_model || "（空）"}
                  </div>
                </label>
              ) : null}

              <label className="grid gap-1">
                <span className="text-xs text-subtext">
                  Embedding 基础地址（base_url；项目覆盖；留空=使用后端环境变量）
                </span>
                <input
                  className="input"
                  id="vector_embedding_base_url"
                  name="vector_embedding_base_url"
                  value={vectorForm.vector_embedding_base_url}
                  onChange={(e) => setVectorForm((v) => ({ ...v, vector_embedding_base_url: e.target.value }))}
                />
                <div className="text-[11px] text-subtext">
                  当前有效：{baselineSettings.vector_embedding_effective_base_url || "（空）"}
                </div>
              </label>

              <label className="grid gap-1">
                <span className="text-xs text-subtext">Embedding 模型（model；项目覆盖；留空=使用后端环境变量）</span>
                <input
                  className="input"
                  id="vector_embedding_model"
                  name="vector_embedding_model"
                  value={vectorForm.vector_embedding_model}
                  onChange={(e) => setVectorForm((v) => ({ ...v, vector_embedding_model: e.target.value }))}
                />
                <div className="text-[11px] text-subtext">
                  当前有效：{baselineSettings.vector_embedding_effective_model || "（空）"}
                </div>
              </label>

              <label className="grid gap-1">
                <span className="text-xs text-subtext">API Key（api_key；项目覆盖；留空不修改）</span>
                <input
                  className="input"
                  id="vector_embedding_api_key"
                  name="vector_embedding_api_key"
                  type="password"
                  autoComplete="off"
                  value={vectorApiKeyDraft}
                  onChange={(e) => {
                    setVectorApiKeyDraft(e.target.value);
                    setVectorApiKeyClearRequested(false);
                  }}
                />
                <div className="text-[11px] text-subtext">
                  已保存（项目覆盖）：
                  {baselineSettings.vector_embedding_has_api_key
                    ? baselineSettings.vector_embedding_masked_api_key
                    : "（无）"}
                  {baselineSettings.vector_embedding_effective_has_api_key
                    ? ` | 当前有效：${baselineSettings.vector_embedding_effective_masked_api_key}`
                    : " | 当前有效：（无）"}
                  {vectorApiKeyClearRequested ? UI_COPY.vectorRag.pendingClearSuffix : ""}
                </div>
              </label>

              <div className="flex flex-wrap gap-2">
                <button
                  className="btn btn-secondary"
                  disabled={savingVector || !baselineSettings.vector_embedding_has_api_key}
                  onClick={() => {
                    setVectorApiKeyDraft("");
                    setVectorApiKeyClearRequested(true);
                  }}
                  type="button"
                >
                  {UI_COPY.vectorRag.embeddingClearApiKey}
                </button>
                <button
                  className="btn btn-secondary"
                  disabled={savingVector}
                  onClick={() => {
                    setVectorForm((v) => ({
                      ...v,
                      vector_embedding_provider: "",
                      vector_embedding_base_url: "",
                      vector_embedding_model: "",
                      vector_embedding_azure_deployment: "",
                      vector_embedding_azure_api_version: "",
                      vector_embedding_sentence_transformers_model: "",
                    }));
                    setVectorApiKeyDraft("");
                    setVectorApiKeyClearRequested(true);
                  }}
                  type="button"
                >
                  恢复使用后端环境变量（清除项目覆盖）
                </button>
              </div>
            </div>
          </details>
        </div>
      ) : (
        <div className="mt-4 text-xs text-subtext">正在加载向量检索配置…</div>
      )}
    </section>
  );
}
