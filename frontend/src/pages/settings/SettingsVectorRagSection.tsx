import type { Dispatch, SetStateAction } from "react";

import { RequestIdBadge } from "../../components/ui/RequestIdBadge";
import { UI_COPY } from "../../lib/uiCopy";
import type { ProjectSettings } from "../../types";

import type { SettingsForm, VectorEmbeddingDryRunResult, VectorRerankDryRunResult } from "./models";
import { SETTINGS_COPY } from "./settingsCopy";

export type SettingsVectorRagSectionProps = {
  projectId?: string;
  onOpenPromptsConfig: () => void;
  baselineSettings: ProjectSettings;
  settingsForm: SettingsForm;
  setSettingsForm: Dispatch<SetStateAction<SettingsForm>>;
  saving: boolean;
  dirty: boolean;
  vectorApiKeyDirty: boolean;
  rerankApiKeyDirty: boolean;
  vectorRerankTopKDraft: string;
  setVectorRerankTopKDraft: Dispatch<SetStateAction<string>>;
  vectorRerankTimeoutDraft: string;
  setVectorRerankTimeoutDraft: Dispatch<SetStateAction<string>>;
  vectorRerankHybridAlphaDraft: string;
  setVectorRerankHybridAlphaDraft: Dispatch<SetStateAction<string>>;
  rerankApiKeyDraft: string;
  setRerankApiKeyDraft: Dispatch<SetStateAction<string>>;
  rerankApiKeyClearRequested: boolean;
  setRerankApiKeyClearRequested: Dispatch<SetStateAction<boolean>>;
  vectorApiKeyDraft: string;
  setVectorApiKeyDraft: Dispatch<SetStateAction<string>>;
  vectorApiKeyClearRequested: boolean;
  setVectorApiKeyClearRequested: Dispatch<SetStateAction<boolean>>;
  embeddingProviderPreview: string;
  embeddingDryRunLoading: boolean;
  embeddingDryRun: null | { requestId: string; result: VectorEmbeddingDryRunResult };
  embeddingDryRunError: null | { message: string; code: string; requestId?: string };
  rerankDryRunLoading: boolean;
  rerankDryRun: null | { requestId: string; result: VectorRerankDryRunResult };
  rerankDryRunError: null | { message: string; code: string; requestId?: string };
  onRunEmbeddingDryRun: () => void;
  onRunRerankDryRun: () => void;
};

export function SettingsVectorRagSection(props: SettingsVectorRagSectionProps) {
  return (
    <details className="panel" aria-label="向量检索（Vector RAG）">
      <summary className="ui-focus-ring ui-transition-fast cursor-pointer select-none p-6">
        <div className="grid gap-1">
          <div className="font-content text-xl text-ink">{UI_COPY.vectorRag.title}</div>
          <div className="text-xs text-subtext">{UI_COPY.vectorRag.subtitle}</div>
          <div className="text-xs text-subtext">{UI_COPY.vectorRag.apiKeyHint}</div>
        </div>
      </summary>

      <div className="px-6 pb-6 pt-0">
        <div className="mt-4 grid gap-4">
          {props.projectId ? (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-atelier border border-border bg-canvas p-4 text-xs text-subtext">
              <div className="min-w-0">{SETTINGS_COPY.vectorRag.openPromptsConfigHint}</div>
              <button className="btn btn-secondary" onClick={props.onOpenPromptsConfig} type="button">
                {SETTINGS_COPY.vectorRag.openPromptsConfigCta}
              </button>
            </div>
          ) : null}

          <div className="rounded-atelier border border-border bg-canvas p-4 text-xs text-subtext">
            <div className="font-medium text-ink">配置说明（Embedding vs Rerank）</div>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              <li>
                <span className="font-mono">Embedding</span> 用于向量化（索引/召回）；
                <span className="font-mono">Rerank</span>
                用于对候选片段做二次排序。两者可分别配置（provider/base_url/model/api_key 可不同）。
              </li>
              <li>
                保存后可用上方 “测试 embedding / 测试 rerank” 做 <span className="font-mono">dry-run</span>
                自检（会返回 request_id，便于看后端日志排障）。
              </li>
              <li>
                验证是否生效：到项目内「RAG」页运行 Query；结果面板会显示 <span className="font-mono">rerank:</span>
                概要，并可展开 <span className="font-mono">rerank_obs</span> 查看详情。
              </li>
            </ul>
          </div>

          <div className="rounded-atelier border border-border bg-canvas p-4 text-xs text-subtext">
            <div>
              当前生效：Embedding 提供方（provider）=
              {props.baselineSettings.vector_embedding_effective_provider || "openai_compatible"}
              （状态: {props.baselineSettings.vector_embedding_effective_disabled_reason ?? "enabled"}；来源：
              {props.baselineSettings.vector_embedding_effective_source}）
            </div>
            <div className="mt-1">
              Rerank：{props.baselineSettings.vector_rerank_effective_enabled ? "enabled" : "disabled"}（method:
              {props.baselineSettings.vector_rerank_effective_method}；provider:
              {props.baselineSettings.vector_rerank_effective_provider || "（空）"}；model:
              {props.baselineSettings.vector_rerank_effective_model || "（空）"}；top_k:
              {props.baselineSettings.vector_rerank_effective_top_k}；alpha:
              {props.baselineSettings.vector_rerank_effective_hybrid_alpha ?? 0}；来源:
              {props.baselineSettings.vector_rerank_effective_source}；配置:
              {props.baselineSettings.vector_rerank_effective_config_source}）
            </div>
          </div>

          <div className="rounded-atelier border border-border bg-canvas p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-sm text-ink">{UI_COPY.vectorRag.dryRunTitle}</div>
              <div className="flex flex-wrap gap-2">
                <button
                  className="btn btn-secondary"
                  disabled={
                    props.saving ||
                    props.dirty ||
                    props.embeddingDryRunLoading ||
                    props.rerankDryRunLoading ||
                    props.vectorApiKeyDirty ||
                    props.rerankApiKeyDirty
                  }
                  onClick={props.onRunEmbeddingDryRun}
                  type="button"
                >
                  {props.embeddingDryRunLoading ? "测试 embedding…" : "测试 embedding"}
                </button>
                <button
                  className="btn btn-secondary"
                  disabled={
                    props.saving ||
                    props.dirty ||
                    props.embeddingDryRunLoading ||
                    props.rerankDryRunLoading ||
                    props.vectorApiKeyDirty ||
                    props.rerankApiKeyDirty
                  }
                  onClick={props.onRunRerankDryRun}
                  type="button"
                >
                  {props.rerankDryRunLoading ? "测试 rerank…" : "测试 rerank"}
                </button>
              </div>
            </div>
            {props.dirty || props.vectorApiKeyDirty || props.rerankApiKeyDirty ? (
              <div className="mt-1 text-[11px] text-subtext">{SETTINGS_COPY.vectorRag.saveBeforeTestHint}</div>
            ) : null}

            {props.embeddingDryRunError ? (
              <div className="mt-3 rounded-atelier border border-border bg-surface p-3">
                <div className="text-xs text-danger">
                  Embedding 测试失败：{props.embeddingDryRunError.message} ({props.embeddingDryRunError.code})
                </div>
                <RequestIdBadge requestId={props.embeddingDryRunError.requestId} className="mt-2" />
                <div className="mt-1 text-[11px] text-subtext">
                  排障：检查 embedding base_url/model/api_key；打开后端日志并搜索 request_id。
                </div>
              </div>
            ) : null}

            {props.embeddingDryRun ? (
              <div className="mt-3 rounded-atelier border border-border bg-surface p-3">
                <div className="text-xs text-subtext">
                  Embedding：{props.embeddingDryRun.result.enabled ? "enabled" : "disabled"}；dims:
                  {props.embeddingDryRun.result.dims ?? "（未知）"}；耗时:
                  {props.embeddingDryRun.result.timings_ms?.total ?? "（未知）"}ms
                  {props.embeddingDryRun.result.error ? `；error: ${props.embeddingDryRun.result.error}` : ""}
                </div>
                <RequestIdBadge requestId={props.embeddingDryRun.requestId} className="mt-2" />
              </div>
            ) : null}

            {props.rerankDryRunError ? (
              <div className="mt-3 rounded-atelier border border-border bg-surface p-3">
                <div className="text-xs text-danger">
                  Rerank 测试失败：{props.rerankDryRunError.message} ({props.rerankDryRunError.code})
                </div>
                <RequestIdBadge requestId={props.rerankDryRunError.requestId} className="mt-2" />
                <div className="mt-1 text-[11px] text-subtext">
                  排障：检查 rerank base_url/model/api_key；若使用 external_rerank_api，确认 /v1/rerank 可访问。
                </div>
              </div>
            ) : null}

            {props.rerankDryRun ? (
              <div className="mt-3 rounded-atelier border border-border bg-surface p-3">
                <div className="text-xs text-subtext">
                  Rerank：{props.rerankDryRun.result.enabled ? "enabled" : "disabled"}；method:
                  {props.rerankDryRun.result.method ?? "（未知）"}；provider:
                  {(props.rerankDryRun.result.rerank as { provider?: string } | undefined)?.provider ?? "（未知）"}
                  ；耗时:
                  {props.rerankDryRun.result.timings_ms?.total ?? "（未知）"}ms；order:
                  {(props.rerankDryRun.result.order ?? []).join(" → ") || "（空）"}
                </div>
                <RequestIdBadge requestId={props.rerankDryRun.requestId} className="mt-2" />
              </div>
            ) : null}
          </div>

          <div className="grid gap-2">
            <div className="text-sm text-ink">{UI_COPY.vectorRag.rerankTitle}</div>
            <div className="grid gap-4 sm:grid-cols-3">
              <label className="flex items-center gap-2 text-sm text-ink sm:col-span-3">
                <input
                  className="checkbox"
                  checked={props.settingsForm.vector_rerank_enabled}
                  onChange={(e) =>
                    props.setSettingsForm((value) => ({ ...value, vector_rerank_enabled: e.target.checked }))
                  }
                  type="checkbox"
                />
                启用 rerank（对候选片段做相关性重排）
              </label>
              <label className="grid gap-1 sm:col-span-2">
                <span className="text-xs text-subtext">重排算法（rerank method）</span>
                <select
                  className="select"
                  id="settings_vector_rerank_method"
                  name="vector_rerank_method"
                  aria-label="settings_vector_rerank_method"
                  value={props.settingsForm.vector_rerank_method}
                  onChange={(e) =>
                    props.setSettingsForm((value) => ({ ...value, vector_rerank_method: e.target.value }))
                  }
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
                  id="settings_vector_rerank_top_k"
                  name="vector_rerank_top_k"
                  aria-label="settings_vector_rerank_top_k"
                  type="number"
                  min={1}
                  max={1000}
                  value={props.vectorRerankTopKDraft}
                  onBlur={() => {
                    const raw = props.vectorRerankTopKDraft.trim();
                    if (!raw) {
                      props.setVectorRerankTopKDraft(String(props.settingsForm.vector_rerank_top_k));
                      return;
                    }
                    const next = Math.floor(Number(raw));
                    if (!Number.isFinite(next)) {
                      props.setVectorRerankTopKDraft(String(props.settingsForm.vector_rerank_top_k));
                      return;
                    }
                    const clamped = Math.max(1, Math.min(1000, next));
                    props.setSettingsForm((value) => ({ ...value, vector_rerank_top_k: clamped }));
                    props.setVectorRerankTopKDraft(String(clamped));
                  }}
                  onChange={(e) => props.setVectorRerankTopKDraft(e.target.value)}
                />
              </label>
            </div>
            <div className="text-[11px] text-subtext">
              提示：启用后会对候选结果做二次排序，通常命中更好，但可能增加耗时/成本。
            </div>

            <details className="rounded-atelier border border-border bg-canvas p-4" aria-label="Rerank 提供方配置">
              <summary className="ui-transition-fast cursor-pointer select-none text-sm text-ink hover:text-ink">
                {UI_COPY.vectorRag.rerankConfigDetailsTitle}
              </summary>
              <div className="mt-4 grid gap-4">
                <div className="text-xs text-subtext">{UI_COPY.vectorRag.backendEnvFallbackHint}</div>

                <label className="grid gap-1">
                  <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankProviderLabel}</span>
                  <select
                    className="select"
                    id="settings_vector_rerank_provider"
                    name="vector_rerank_provider"
                    aria-label="settings_vector_rerank_provider"
                    value={props.settingsForm.vector_rerank_provider}
                    onChange={(e) =>
                      props.setSettingsForm((value) => ({ ...value, vector_rerank_provider: e.target.value }))
                    }
                  >
                    <option value="">（使用后端环境变量）</option>
                    <option value="external_rerank_api">external_rerank_api</option>
                  </select>
                  <div className="text-[11px] text-subtext">
                    当前有效：{props.baselineSettings.vector_rerank_effective_provider || "（空）"}
                  </div>
                </label>

                <label className="grid gap-1">
                  <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankBaseUrlLabel}</span>
                  <input
                    className="input"
                    id="settings_vector_rerank_base_url"
                    name="vector_rerank_base_url"
                    aria-label="settings_vector_rerank_base_url"
                    value={props.settingsForm.vector_rerank_base_url}
                    onChange={(e) => {
                      const next = e.target.value;
                      props.setSettingsForm((value) => {
                        const shouldAutoSetProvider = !value.vector_rerank_provider.trim() && next.trim().length > 0;
                        return {
                          ...value,
                          vector_rerank_base_url: next,
                          ...(shouldAutoSetProvider ? { vector_rerank_provider: "external_rerank_api" } : {}),
                        };
                      });
                    }}
                  />
                  <div className="text-[11px] text-subtext">
                    当前有效：{props.baselineSettings.vector_rerank_effective_base_url || "（空）"}
                  </div>
                </label>

                <label className="grid gap-1">
                  <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankModelLabel}</span>
                  <input
                    className="input"
                    id="settings_vector_rerank_model"
                    name="vector_rerank_model"
                    aria-label="settings_vector_rerank_model"
                    value={props.settingsForm.vector_rerank_model}
                    onChange={(e) =>
                      props.setSettingsForm((value) => ({ ...value, vector_rerank_model: e.target.value }))
                    }
                  />
                  <div className="text-[11px] text-subtext">
                    当前有效：{props.baselineSettings.vector_rerank_effective_model || "（空）"}
                  </div>
                </label>

                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="grid gap-1">
                    <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankTimeoutLabel}</span>
                    <input
                      className="input"
                      id="settings_vector_rerank_timeout_seconds"
                      name="vector_rerank_timeout_seconds"
                      aria-label="settings_vector_rerank_timeout_seconds"
                      type="number"
                      min={1}
                      max={120}
                      value={props.vectorRerankTimeoutDraft}
                      onBlur={() => {
                        const raw = props.vectorRerankTimeoutDraft.trim();
                        if (!raw) {
                          props.setSettingsForm((value) => ({ ...value, vector_rerank_timeout_seconds: null }));
                          props.setVectorRerankTimeoutDraft("");
                          return;
                        }
                        const next = Math.floor(Number(raw));
                        if (!Number.isFinite(next)) {
                          props.setVectorRerankTimeoutDraft(
                            props.settingsForm.vector_rerank_timeout_seconds != null
                              ? String(props.settingsForm.vector_rerank_timeout_seconds)
                              : "",
                          );
                          return;
                        }
                        const clamped = Math.max(1, Math.min(120, next));
                        props.setSettingsForm((value) => ({ ...value, vector_rerank_timeout_seconds: clamped }));
                        props.setVectorRerankTimeoutDraft(String(clamped));
                      }}
                      onChange={(e) => props.setVectorRerankTimeoutDraft(e.target.value)}
                    />
                    <div className="text-[11px] text-subtext">
                      当前有效：{props.baselineSettings.vector_rerank_effective_timeout_seconds ?? 15}
                    </div>
                  </label>

                  <label className="grid gap-1">
                    <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankHybridAlphaLabel}</span>
                    <input
                      className="input"
                      id="settings_vector_rerank_hybrid_alpha"
                      name="vector_rerank_hybrid_alpha"
                      aria-label="settings_vector_rerank_hybrid_alpha"
                      type="number"
                      min={0}
                      max={1}
                      step={0.05}
                      value={props.vectorRerankHybridAlphaDraft}
                      onBlur={() => {
                        const raw = props.vectorRerankHybridAlphaDraft.trim();
                        if (!raw) {
                          props.setSettingsForm((value) => ({ ...value, vector_rerank_hybrid_alpha: null }));
                          props.setVectorRerankHybridAlphaDraft("");
                          return;
                        }
                        const next = Number(raw);
                        if (!Number.isFinite(next)) {
                          props.setVectorRerankHybridAlphaDraft(
                            props.settingsForm.vector_rerank_hybrid_alpha != null
                              ? String(props.settingsForm.vector_rerank_hybrid_alpha)
                              : "",
                          );
                          return;
                        }
                        const clamped = Math.max(0, Math.min(1, next));
                        props.setSettingsForm((value) => ({ ...value, vector_rerank_hybrid_alpha: clamped }));
                        props.setVectorRerankHybridAlphaDraft(String(clamped));
                      }}
                      onChange={(e) => props.setVectorRerankHybridAlphaDraft(e.target.value)}
                    />
                    <div className="text-[11px] text-subtext">
                      当前有效：{props.baselineSettings.vector_rerank_effective_hybrid_alpha ?? 0}
                    </div>
                  </label>
                </div>

                <label className="grid gap-1">
                  <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankApiKeyLabel}</span>
                  <input
                    className="input"
                    id="settings_vector_rerank_api_key"
                    name="vector_rerank_api_key"
                    aria-label="settings_vector_rerank_api_key"
                    type="password"
                    autoComplete="off"
                    value={props.rerankApiKeyDraft}
                    onChange={(e) => {
                      props.setRerankApiKeyDraft(e.target.value);
                      props.setRerankApiKeyClearRequested(false);
                    }}
                  />
                  <div className="text-[11px] text-subtext">
                    已保存（项目覆盖）：
                    {props.baselineSettings.vector_rerank_has_api_key
                      ? props.baselineSettings.vector_rerank_masked_api_key
                      : "（无）"}
                    {props.baselineSettings.vector_rerank_effective_has_api_key
                      ? ` | 当前有效：${props.baselineSettings.vector_rerank_effective_masked_api_key}`
                      : " | 当前有效：（无）"}
                    {props.rerankApiKeyClearRequested ? UI_COPY.vectorRag.pendingClearSuffix : ""}
                  </div>
                </label>

                <div className="flex flex-wrap gap-2">
                  <button
                    className="btn btn-secondary"
                    aria-label="settings_vector_rerank_api_key_clear"
                    disabled={props.saving || !props.baselineSettings.vector_rerank_has_api_key}
                    onClick={() => {
                      props.setRerankApiKeyDraft("");
                      props.setRerankApiKeyClearRequested(true);
                    }}
                    type="button"
                  >
                    {UI_COPY.vectorRag.rerankClearApiKey}
                  </button>
                  <button
                    className="btn btn-secondary"
                    aria-label="settings_vector_rerank_reset_overrides"
                    disabled={props.saving}
                    onClick={() => {
                      props.setSettingsForm((value) => ({
                        ...value,
                        vector_rerank_provider: "",
                        vector_rerank_base_url: "",
                        vector_rerank_model: "",
                        vector_rerank_timeout_seconds: null,
                        vector_rerank_hybrid_alpha: null,
                      }));
                      props.setVectorRerankTimeoutDraft("");
                      props.setVectorRerankHybridAlphaDraft("");
                      props.setRerankApiKeyDraft("");
                      props.setRerankApiKeyClearRequested(true);
                    }}
                    type="button"
                  >
                    {UI_COPY.vectorRag.rerankResetOverrides}
                  </button>
                </div>
              </div>
            </details>
          </div>

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
                  value={props.settingsForm.vector_embedding_provider}
                  onChange={(e) =>
                    props.setSettingsForm((value) => ({ ...value, vector_embedding_provider: e.target.value }))
                  }
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
                  当前有效：{props.baselineSettings.vector_embedding_effective_provider || "openai_compatible"}
                </div>
              </label>

              {props.embeddingProviderPreview === "azure_openai" ? (
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="grid gap-1">
                    <span className="text-xs text-subtext">
                      Azure 部署名（deployment；项目覆盖；留空=使用后端环境变量）
                    </span>
                    <input
                      className="input"
                      value={props.settingsForm.vector_embedding_azure_deployment}
                      onChange={(e) =>
                        props.setSettingsForm((value) => ({
                          ...value,
                          vector_embedding_azure_deployment: e.target.value,
                        }))
                      }
                    />
                    <div className="text-[11px] text-subtext">
                      当前有效：{props.baselineSettings.vector_embedding_effective_azure_deployment || "（空）"}
                    </div>
                  </label>
                  <label className="grid gap-1">
                    <span className="text-xs text-subtext">
                      Azure API 版本（api_version；项目覆盖；留空=使用后端环境变量）
                    </span>
                    <input
                      className="input"
                      value={props.settingsForm.vector_embedding_azure_api_version}
                      onChange={(e) =>
                        props.setSettingsForm((value) => ({
                          ...value,
                          vector_embedding_azure_api_version: e.target.value,
                        }))
                      }
                    />
                    <div className="text-[11px] text-subtext">
                      当前有效：{props.baselineSettings.vector_embedding_effective_azure_api_version || "（空）"}
                    </div>
                  </label>
                </div>
              ) : null}

              {props.embeddingProviderPreview === "sentence_transformers" ? (
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">
                    SentenceTransformers 模型（项目覆盖；留空=使用后端环境变量）
                  </span>
                  <input
                    className="input"
                    value={props.settingsForm.vector_embedding_sentence_transformers_model}
                    onChange={(e) =>
                      props.setSettingsForm((value) => ({
                        ...value,
                        vector_embedding_sentence_transformers_model: e.target.value,
                      }))
                    }
                  />
                  <div className="text-[11px] text-subtext">
                    当前有效：
                    {props.baselineSettings.vector_embedding_effective_sentence_transformers_model || "（空）"}
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
                  value={props.settingsForm.vector_embedding_base_url}
                  onChange={(e) =>
                    props.setSettingsForm((value) => ({ ...value, vector_embedding_base_url: e.target.value }))
                  }
                />
                <div className="text-[11px] text-subtext">
                  当前有效：{props.baselineSettings.vector_embedding_effective_base_url || "（空）"}
                </div>
              </label>

              <label className="grid gap-1">
                <span className="text-xs text-subtext">Embedding 模型（model；项目覆盖；留空=使用后端环境变量）</span>
                <input
                  className="input"
                  id="vector_embedding_model"
                  name="vector_embedding_model"
                  value={props.settingsForm.vector_embedding_model}
                  onChange={(e) =>
                    props.setSettingsForm((value) => ({ ...value, vector_embedding_model: e.target.value }))
                  }
                />
                <div className="text-[11px] text-subtext">
                  当前有效：{props.baselineSettings.vector_embedding_effective_model || "（空）"}
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
                  value={props.vectorApiKeyDraft}
                  onChange={(e) => {
                    props.setVectorApiKeyDraft(e.target.value);
                    props.setVectorApiKeyClearRequested(false);
                  }}
                />
                <div className="text-[11px] text-subtext">
                  已保存（项目覆盖）：
                  {props.baselineSettings.vector_embedding_has_api_key
                    ? props.baselineSettings.vector_embedding_masked_api_key
                    : "（无）"}
                  {props.baselineSettings.vector_embedding_effective_has_api_key
                    ? ` | 当前有效：${props.baselineSettings.vector_embedding_effective_masked_api_key}`
                    : " | 当前有效：（无）"}
                  {props.vectorApiKeyClearRequested ? UI_COPY.vectorRag.pendingClearSuffix : ""}
                </div>
              </label>

              <div className="flex flex-wrap gap-2">
                <button
                  className="btn btn-secondary"
                  disabled={props.saving || !props.baselineSettings.vector_embedding_has_api_key}
                  onClick={() => {
                    props.setVectorApiKeyDraft("");
                    props.setVectorApiKeyClearRequested(true);
                  }}
                  type="button"
                >
                  {UI_COPY.vectorRag.embeddingClearApiKey}
                </button>
                <button
                  className="btn btn-secondary"
                  disabled={props.saving}
                  onClick={() => {
                    props.setSettingsForm((value) => ({
                      ...value,
                      vector_embedding_provider: "",
                      vector_embedding_base_url: "",
                      vector_embedding_model: "",
                      vector_embedding_azure_deployment: "",
                      vector_embedding_azure_api_version: "",
                      vector_embedding_sentence_transformers_model: "",
                    }));
                    props.setVectorApiKeyDraft("");
                    props.setVectorApiKeyClearRequested(true);
                  }}
                  type="button"
                >
                  恢复使用后端环境变量（清除项目覆盖）
                </button>
              </div>
            </div>
          </details>
        </div>
      </div>
    </details>
  );
}
