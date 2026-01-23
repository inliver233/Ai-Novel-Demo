export type VectorSource = "worldbook" | "outline" | "chapter";

export type VectorCandidate = {
  id: string;
  distance: number;
  text: string;
  metadata: Record<string, unknown>;
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

export type VectorRagQueryResult = {
  enabled: boolean;
  disabled_reason: string | null;
  query_text: string;
  filters: { project_id: string; sources: VectorSource[] };
  timings_ms: Record<string, number>;
  rerank: VectorRerankObs | null;
  backend: string | null;
  hybrid: VectorHybridObs | null;
  candidates: VectorCandidate[];
  final: { chunks: VectorCandidate[]; text_md: string; truncated: boolean };
  dropped: Array<{ id?: string; reason: string }>;
  counts?: VectorRagCounts;
  prompt_block: { identifier: string; role: string; text_md: string };
  error?: string;
};

function hasOwn<K extends string>(obj: unknown, key: K): obj is Record<K, unknown> {
  return typeof obj === "object" && obj !== null && Object.prototype.hasOwnProperty.call(obj, key);
}

function normalizeRerankObs(raw: unknown): VectorRerankObs | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;

  const before = Array.isArray(o.before) ? o.before.map((v) => String(v)) : [];
  const after = Array.isArray(o.after) ? o.after.map((v) => String(v)) : [];
  const topK = typeof o.top_k === "number" ? o.top_k : Number(o.top_k);
  const timingMs = typeof o.timing_ms === "number" ? o.timing_ms : Number(o.timing_ms);

  return {
    enabled: Boolean(o.enabled),
    applied: Boolean(o.applied),
    requested_method: typeof o.requested_method === "string" ? o.requested_method : "",
    method: typeof o.method === "string" ? o.method : null,
    top_k: Number.isFinite(topK) ? topK : 0,
    reason: typeof o.reason === "string" ? o.reason : null,
    error_type: typeof o.error_type === "string" ? o.error_type : null,
    before,
    after,
    timing_ms: Number.isFinite(timingMs) ? timingMs : 0,
    errors: Array.isArray(o.errors) ? (o.errors as Array<Record<string, unknown>>) : [],
  };
}

function rerankDelta(obs: VectorRerankObs): {
  compared: number;
  changedPositions: number;
  entered: number;
  left: number;
} {
  const compared = Math.min(obs.top_k || 0, obs.before.length, obs.after.length);
  if (compared <= 0) return { compared: 0, changedPositions: 0, entered: 0, left: 0 };
  let changedPositions = 0;
  for (let i = 0; i < compared; i++) {
    if (obs.before[i] !== obs.after[i]) changedPositions++;
  }
  const beforeSet = new Set(obs.before.slice(0, compared));
  const afterSet = new Set(obs.after.slice(0, compared));
  let entered = 0;
  for (const id of afterSet) {
    if (!beforeSet.has(id)) entered++;
  }
  let left = 0;
  for (const id of beforeSet) {
    if (!afterSet.has(id)) left++;
  }
  return { compared, changedPositions, entered, left };
}

export function formatRerankSummary(obs: VectorRerankObs): string {
  const delta = rerankDelta(obs);
  const comparedText = delta.compared ? `${delta.changedPositions}/${delta.compared}` : "-";
  const methodText = obs.method ?? "-";
  const reqText = obs.requested_method || "-";
  const reasonText = obs.reason ?? "-";
  const errText = obs.error_type ? ` | error:${obs.error_type}` : "";
  const changesText = delta.compared
    ? ` | changed_in_top_k:${comparedText} | entered:${delta.entered} | left:${delta.left}`
    : "";
  return `enabled:${String(obs.enabled)} | applied:${String(obs.applied)} | reason:${reasonText} | requested:${reqText} | method:${methodText} | top_k:${obs.top_k} | timing_ms:${obs.timing_ms}${changesText}${errText}`;
}

export function formatHybridCounts(raw: unknown): string {
  if (!raw || typeof raw !== "object") return "-";
  const o = raw as Record<string, unknown>;
  const parts: string[] = [];
  for (const key of ["vector", "fts", "union"] as const) {
    const v = o[key];
    const n = typeof v === "number" ? v : Number(v);
    if (Number.isFinite(n)) parts.push(`${key}:${n}`);
  }
  if (parts.length) return parts.join(" | ");
  const fallback = Object.entries(o)
    .map(([k, v]) => {
      const n = typeof v === "number" ? v : Number(v);
      return Number.isFinite(n) ? `${k}:${n}` : null;
    })
    .filter((v): v is string => Boolean(v));
  return fallback.length ? fallback.join(" | ") : "-";
}

export function formatOverfilter(raw: unknown): string {
  if (!raw || typeof raw !== "object") return "-";
  const o = raw as Record<string, unknown>;
  const enabled = Boolean(o.enabled);
  const actions = Array.isArray(o.actions) ? o.actions.map((v) => String(v)).filter((v) => Boolean(v)) : [];
  const usedSources = Array.isArray(o.used_sources)
    ? o.used_sources.map((v) => String(v)).filter((v) => Boolean(v))
    : [];
  const vectorK = typeof o.vector_k === "number" ? o.vector_k : Number(o.vector_k);
  const ftsK = typeof o.fts_k === "number" ? o.fts_k : Number(o.fts_k);

  const parts = [`enabled:${String(enabled)}`];
  if (actions.length) parts.push(`actions:${actions.join(",")}`);
  if (usedSources.length) parts.push(`used_sources:${usedSources.join(",")}`);
  if (Number.isFinite(vectorK)) parts.push(`vector_k:${vectorK}`);
  if (Number.isFinite(ftsK)) parts.push(`fts_k:${ftsK}`);
  return parts.join(" | ");
}

export function normalizeVectorResult(raw: unknown): VectorRagQueryResult | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  if (typeof o.enabled !== "boolean") return null;
  if (typeof o.query_text !== "string") return null;
  if (!hasOwn(o, "filters") || typeof o.filters !== "object" || o.filters === null) return null;
  if (!hasOwn(o, "final") || typeof o.final !== "object" || o.final === null) return null;
  if (!hasOwn(o, "prompt_block") || typeof o.prompt_block !== "object" || o.prompt_block === null) return null;

  const filters = o.filters as Record<string, unknown>;
  const final = o.final as Record<string, unknown>;
  const promptBlock = o.prompt_block as Record<string, unknown>;

  const sources = Array.isArray(filters.sources)
    ? (filters.sources.filter((v) => v === "worldbook" || v === "outline" || v === "chapter") as VectorSource[])
    : [];

  const candidatesRaw = Array.isArray(o.candidates) ? o.candidates : [];
  const candidates: VectorCandidate[] = candidatesRaw
    .map((c): VectorCandidate | null => {
      if (!c || typeof c !== "object") return null;
      const cc = c as Record<string, unknown>;
      const id = typeof cc.id === "string" ? cc.id : "";
      const distance = typeof cc.distance === "number" ? cc.distance : Number(cc.distance);
      const text = typeof cc.text === "string" ? cc.text : "";
      const metadata =
        typeof cc.metadata === "object" && cc.metadata !== null ? (cc.metadata as Record<string, unknown>) : {};
      if (!id) return null;
      if (!Number.isFinite(distance)) return null;
      return { id, distance, text, metadata };
    })
    .filter((v): v is VectorCandidate => Boolean(v));

  const finalChunksRaw = Array.isArray(final.chunks) ? final.chunks : [];
  const finalChunks: VectorCandidate[] = finalChunksRaw
    .map((c): VectorCandidate | null => {
      if (!c || typeof c !== "object") return null;
      const cc = c as Record<string, unknown>;
      const id = typeof cc.id === "string" ? cc.id : "";
      const distance = typeof cc.distance === "number" ? cc.distance : Number(cc.distance);
      const text = typeof cc.text === "string" ? cc.text : "";
      const metadata =
        typeof cc.metadata === "object" && cc.metadata !== null ? (cc.metadata as Record<string, unknown>) : {};
      if (!id) return null;
      if (!Number.isFinite(distance)) return null;
      return { id, distance, text, metadata };
    })
    .filter((v): v is VectorCandidate => Boolean(v));

  const timings =
    typeof o.timings_ms === "object" && o.timings_ms !== null ? (o.timings_ms as Record<string, unknown>) : {};
  const timingsMs: Record<string, number> = Object.fromEntries(
    Object.entries(timings)
      .map(([k, v]) => [k, typeof v === "number" ? v : Number(v)] as const)
      .filter(([, v]) => Number.isFinite(v)),
  );

  const droppedRaw = Array.isArray(o.dropped) ? o.dropped : [];
  const dropped: Array<{ id?: string; reason: string }> = droppedRaw
    .map((d): { id?: string; reason: string } | null => {
      if (!d || typeof d !== "object") return null;
      const dd = d as Record<string, unknown>;
      const reason = typeof dd.reason === "string" ? dd.reason : "";
      if (!reason) return null;
      const id = typeof dd.id === "string" ? dd.id : undefined;
      return { id, reason };
    })
    .filter((v): v is { id?: string; reason: string } => Boolean(v));

  const countsRaw =
    hasOwn(o, "counts") && typeof o.counts === "object" && o.counts !== null
      ? (o.counts as Record<string, unknown>)
      : null;
  let counts: VectorRagCounts | undefined = undefined;
  if (countsRaw) {
    const candidatesTotal =
      typeof countsRaw.candidates_total === "number" ? countsRaw.candidates_total : Number(countsRaw.candidates_total);
    const candidatesReturned =
      typeof countsRaw.candidates_returned === "number"
        ? countsRaw.candidates_returned
        : Number(countsRaw.candidates_returned);
    const uniqueSources =
      typeof countsRaw.unique_sources === "number" ? countsRaw.unique_sources : Number(countsRaw.unique_sources);
    const finalSelected =
      typeof countsRaw.final_selected === "number" ? countsRaw.final_selected : Number(countsRaw.final_selected);
    const droppedTotal =
      typeof countsRaw.dropped_total === "number" ? countsRaw.dropped_total : Number(countsRaw.dropped_total);

    const droppedByReasonRaw =
      typeof countsRaw.dropped_by_reason === "object" && countsRaw.dropped_by_reason !== null
        ? (countsRaw.dropped_by_reason as Record<string, unknown>)
        : {};
    const droppedByReason: Record<string, number> = Object.fromEntries(
      Object.entries(droppedByReasonRaw)
        .map(([k, v]) => [k, typeof v === "number" ? v : Number(v)] as const)
        .filter(([, v]) => Number.isFinite(v) && v >= 0),
    );

    if (
      Number.isFinite(candidatesTotal) &&
      Number.isFinite(candidatesReturned) &&
      Number.isFinite(uniqueSources) &&
      Number.isFinite(finalSelected) &&
      Number.isFinite(droppedTotal)
    ) {
      counts = {
        candidates_total: candidatesTotal,
        candidates_returned: candidatesReturned,
        unique_sources: uniqueSources,
        final_selected: finalSelected,
        dropped_total: droppedTotal,
        dropped_by_reason: droppedByReason,
      };
    }
  }

  const rerank = hasOwn(o, "rerank") ? normalizeRerankObs(o.rerank) : null;
  const backend = typeof o.backend === "string" ? o.backend : null;

  let hybrid: VectorHybridObs | null = null;
  if (hasOwn(o, "hybrid") && typeof o.hybrid === "object" && o.hybrid !== null) {
    const h = o.hybrid as Record<string, unknown>;
    hybrid = {
      enabled: typeof h.enabled === "boolean" ? h.enabled : Boolean(h.enabled),
      ranks: hasOwn(h, "ranks") ? h.ranks : undefined,
      counts: hasOwn(h, "counts") ? h.counts : undefined,
      overfilter: hasOwn(h, "overfilter") ? h.overfilter : undefined,
    };
  }

  return {
    enabled: Boolean(o.enabled),
    disabled_reason: typeof o.disabled_reason === "string" ? o.disabled_reason : null,
    error: typeof o.error === "string" ? o.error : undefined,
    query_text: o.query_text as string,
    filters: {
      project_id: typeof filters.project_id === "string" ? filters.project_id : "",
      sources,
    },
    timings_ms: timingsMs,
    rerank,
    backend,
    hybrid,
    candidates,
    final: {
      chunks: finalChunks,
      text_md: typeof final.text_md === "string" ? final.text_md : "",
      truncated: Boolean(final.truncated),
    },
    prompt_block: {
      identifier: typeof promptBlock.identifier === "string" ? promptBlock.identifier : "",
      role: typeof promptBlock.role === "string" ? promptBlock.role : "",
      text_md: typeof promptBlock.text_md === "string" ? promptBlock.text_md : "",
    },
    dropped,
    counts,
  };
}
