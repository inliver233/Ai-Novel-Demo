export type VectorSource = "worldbook" | "outline" | "chapter";

export type VectorIndexState = {
  dirty: boolean;
  last_build_at: string | null;
};

export type VectorRagCounts = {
  candidates_total: number;
  candidates_returned: number;
  unique_sources: number;
  final_selected: number;
  dropped_total: number;
  dropped_by_reason: Record<string, number>;
};

export type VectorRerankObs = {
  enabled: boolean;
  applied: boolean;
  requested_method: string;
  method: string | null;
  top_k: number;
  reason: string | null;
  error_type: string | null;
  before: string[];
  after: string[];
  timing_ms: number;
  errors: Array<Record<string, unknown>>;
};

export type VectorHybridObs = {
  enabled: boolean;
  ranks?: unknown;
  counts?: unknown;
  overfilter?: unknown;
};

export type VectorChunk = {
  id: string;
  distance?: number;
  text?: string;
  metadata?: Record<string, unknown>;
};

export type VectorRagResult = {
  enabled: boolean;
  disabled_reason?: string | null;
  query_text: string;
  filters?: { project_id: string; sources: VectorSource[] };
  index?: VectorIndexState;
  timings_ms?: Record<string, number>;
  candidates?: VectorChunk[];
  final?: { chunks: VectorChunk[]; text_md: string; truncated: boolean };
  dropped?: Array<{ id?: string; reason: string }>;
  counts?: VectorRagCounts;
  prompt_block?: { identifier: string; role: string; text_md: string };
  backend_preferred?: string;
  hybrid_enabled?: boolean;
  backend?: string;
  hybrid?: VectorHybridObs;
  rerank?: VectorRerankObs;
  kbs?: {
    selected?: string[];
    per_kb?: Record<
      string,
      {
        enabled?: boolean;
        disabled_reason?: string | null;
        error?: string;
        counts?: VectorRagCounts;
        overfilter?: unknown;
        weight?: number;
        order?: number;
      }
    >;
  };
  error?: string;
};

export const EMPTY_CHUNKS: VectorChunk[] = [];

export type KnowledgeBase = {
  kb_id: string;
  name: string;
  enabled: boolean;
  weight: number;
  order: number;
  created_at?: string | null;
  updated_at?: string | null;
};

