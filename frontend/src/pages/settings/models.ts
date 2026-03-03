import type { Project, ProjectSettings } from "../../types";

export type ProjectForm = { name: string; genre: string; logline: string };

export type SettingsForm = {
  world_setting: string;
  style_guide: string;
  constraints: string;
  context_optimizer_enabled: boolean;
  auto_update_worldbook_enabled: boolean;
  auto_update_characters_enabled: boolean;
  auto_update_story_memory_enabled: boolean;
  auto_update_graph_enabled: boolean;
  auto_update_vector_enabled: boolean;
  auto_update_search_enabled: boolean;
  auto_update_fractal_enabled: boolean;
  auto_update_tables_enabled: boolean;
  query_preprocessing_enabled: boolean;
  query_preprocessing_tags: string;
  query_preprocessing_exclusion_rules: string;
  query_preprocessing_index_ref_enhance: boolean;
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

export type SettingsLoaded = { project: Project; settings: ProjectSettings };
export type SaveSnapshot = { projectForm: ProjectForm; settingsForm: SettingsForm };

export type ProjectMembershipItem = {
  project_id: string;
  user: { id: string; display_name: string | null; is_admin: boolean };
  role: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export type QpPreviewState = { normalized: string; obs: unknown; requestId: string };

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

export function createDefaultProjectForm(): ProjectForm {
  return { name: "", genre: "", logline: "" };
}

export function createDefaultSettingsForm(): SettingsForm {
  return {
    world_setting: "",
    style_guide: "",
    constraints: "",
    context_optimizer_enabled: false,
    auto_update_worldbook_enabled: true,
    auto_update_characters_enabled: true,
    auto_update_story_memory_enabled: true,
    auto_update_graph_enabled: true,
    auto_update_vector_enabled: true,
    auto_update_search_enabled: true,
    auto_update_fractal_enabled: true,
    auto_update_tables_enabled: true,
    query_preprocessing_enabled: false,
    query_preprocessing_tags: "",
    query_preprocessing_exclusion_rules: "",
    query_preprocessing_index_ref_enhance: false,
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
}

type LoadedSettingsFormMapping = {
  projectForm: ProjectForm;
  settingsForm: SettingsForm;
  vectorRerankTopKDraft: string;
  vectorRerankTimeoutDraft: string;
  vectorRerankHybridAlphaDraft: string;
};

export function mapLoadedSettingsToForms(loaded: SettingsLoaded): LoadedSettingsFormMapping {
  const { project, settings } = loaded;
  const rerankTopK = Number(settings.vector_rerank_effective_top_k ?? 20) || 20;
  return {
    projectForm: {
      name: project.name ?? "",
      genre: project.genre ?? "",
      logline: project.logline ?? "",
    },
    settingsForm: {
      world_setting: settings.world_setting ?? "",
      style_guide: settings.style_guide ?? "",
      constraints: settings.constraints ?? "",
      context_optimizer_enabled: Boolean(settings.context_optimizer_enabled),
      auto_update_worldbook_enabled: Boolean(settings.auto_update_worldbook_enabled ?? true),
      auto_update_characters_enabled: Boolean(settings.auto_update_characters_enabled ?? true),
      auto_update_story_memory_enabled: Boolean(settings.auto_update_story_memory_enabled ?? true),
      auto_update_graph_enabled: Boolean(settings.auto_update_graph_enabled ?? true),
      auto_update_vector_enabled: Boolean(settings.auto_update_vector_enabled ?? true),
      auto_update_search_enabled: Boolean(settings.auto_update_search_enabled ?? true),
      auto_update_fractal_enabled: Boolean(settings.auto_update_fractal_enabled ?? true),
      auto_update_tables_enabled: Boolean(settings.auto_update_tables_enabled ?? true),
      query_preprocessing_enabled: Boolean(settings.query_preprocessing_effective?.enabled),
      query_preprocessing_tags: Array.isArray(settings.query_preprocessing_effective?.tags)
        ? settings.query_preprocessing_effective?.tags.join("\n")
        : "",
      query_preprocessing_exclusion_rules: Array.isArray(settings.query_preprocessing_effective?.exclusion_rules)
        ? settings.query_preprocessing_effective?.exclusion_rules.join("\n")
        : "",
      query_preprocessing_index_ref_enhance: Boolean(settings.query_preprocessing_effective?.index_ref_enhance),
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
