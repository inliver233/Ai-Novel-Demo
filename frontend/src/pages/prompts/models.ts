import type { ProjectSettings } from "../../types";

export type LlmCapabilities = {
  provider: string;
  model: string;
  max_tokens_limit: number | null;
  max_tokens_recommended: number | null;
  context_window_limit: number | null;
};

export type VectorRagForm = {
  vector_rerank_enabled: boolean;
  vector_rerank_method: string;
  vector_rerank_top_k: number;
  vector_rerank_provider: string;
  vector_rerank_base_url: string;
  vector_rerank_model: string;
  vector_rerank_timeout_seconds: number | null;
  vector_rerank_hybrid_alpha: number | null;
  vector_embedding_provider: string;
  vector_embedding_base_url: string;
  vector_embedding_model: string;
  vector_embedding_azure_deployment: string;
  vector_embedding_azure_api_version: string;
  vector_embedding_sentence_transformers_model: string;
};

export type VectorEmbeddingDryRunResult = {
  enabled: boolean;
  disabled_reason?: string | null;
  provider?: string | null;
  dims?: number | null;
  timings_ms?: { total?: number | null } | null;
  error?: string | null;
  embedding?: {
    provider?: string | null;
    base_url?: string | null;
    model?: string | null;
    has_api_key?: boolean;
    masked_api_key?: string;
  };
};

export type VectorRerankDryRunResult = {
  enabled: boolean;
  documents_count?: number;
  method?: string | null;
  top_k?: number | null;
  hybrid_alpha?: number | null;
  order?: number[];
  timings_ms?: { total?: number | null } | null;
  obs?: unknown;
  rerank?: {
    provider?: string | null;
    base_url?: string | null;
    model?: string | null;
    timeout_seconds?: number | null;
    hybrid_alpha?: number | null;
    has_api_key?: boolean;
    masked_api_key?: string;
  };
};

export const DEFAULT_VECTOR_RAG_FORM: VectorRagForm = {
  vector_rerank_enabled: false,
  vector_rerank_method: "auto",
  vector_rerank_top_k: 20,
  vector_rerank_provider: "",
  vector_rerank_base_url: "",
  vector_rerank_model: "",
  vector_rerank_timeout_seconds: null,
  vector_rerank_hybrid_alpha: null,
  vector_embedding_provider: "",
  vector_embedding_base_url: "",
  vector_embedding_model: "",
  vector_embedding_azure_deployment: "",
  vector_embedding_azure_api_version: "",
  vector_embedding_sentence_transformers_model: "",
};

export function parseNumber(value: string): number | null {
  const v = value.trim();
  if (!v) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function parseStopList(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  return trimmed
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function parseTimeoutSecondsForTest(value: string): number {
  const n = parseNumber(value);
  const i = Math.trunc(n ?? 180);
  if (i < 1) return 1;
  if (i > 1800) return 1800;
  return i;
}

export function parseTimeoutSecondsForPreset(value: string): number | null {
  const n = parseNumber(value);
  if (n === null) return null;
  const i = Math.trunc(n);
  if (i < 1) return 1;
  if (i > 1800) return 1800;
  return i;
}

type LoadedVectorFormState = {
  vectorForm: VectorRagForm;
  vectorRerankTopKDraft: string;
  vectorRerankTimeoutDraft: string;
  vectorRerankHybridAlphaDraft: string;
};

export function mapVectorFormFromSettings(settings: ProjectSettings): LoadedVectorFormState {
  const rerankTopK = Number(settings.vector_rerank_effective_top_k ?? 20) || 20;
  return {
    vectorForm: {
      vector_rerank_enabled: Boolean(settings.vector_rerank_effective_enabled),
      vector_rerank_method: String(settings.vector_rerank_effective_method ?? "auto") || "auto",
      vector_rerank_top_k: rerankTopK,
      vector_rerank_provider: settings.vector_rerank_provider ?? "",
      vector_rerank_base_url: settings.vector_rerank_base_url ?? "",
      vector_rerank_model: settings.vector_rerank_model ?? "",
      vector_rerank_timeout_seconds: settings.vector_rerank_timeout_seconds ?? null,
      vector_rerank_hybrid_alpha: settings.vector_rerank_hybrid_alpha ?? null,
      vector_embedding_provider: settings.vector_embedding_provider ?? "",
      vector_embedding_base_url: settings.vector_embedding_base_url ?? "",
      vector_embedding_model: settings.vector_embedding_model ?? "",
      vector_embedding_azure_deployment: settings.vector_embedding_azure_deployment ?? "",
      vector_embedding_azure_api_version: settings.vector_embedding_azure_api_version ?? "",
      vector_embedding_sentence_transformers_model: settings.vector_embedding_sentence_transformers_model ?? "",
    },
    vectorRerankTopKDraft: String(rerankTopK),
    vectorRerankTimeoutDraft:
      settings.vector_rerank_timeout_seconds != null ? String(settings.vector_rerank_timeout_seconds) : "",
    vectorRerankHybridAlphaDraft:
      settings.vector_rerank_hybrid_alpha != null ? String(settings.vector_rerank_hybrid_alpha) : "",
  };
}
