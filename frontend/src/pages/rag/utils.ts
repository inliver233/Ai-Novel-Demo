import type { VectorRerankObs, VectorSuperSortObs } from "./types";

export function safeJson(obj: unknown): string {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

export function formatIsoToLocal(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString();
}

export function normalizeRerankObs(raw: unknown): VectorRerankObs | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;

  const before = Array.isArray(o.before) ? o.before.map((v) => String(v)) : [];
  const after = Array.isArray(o.after) ? o.after.map((v) => String(v)) : [];
  const afterRerank = Array.isArray(o.after_rerank) ? o.after_rerank.map((v) => String(v)) : undefined;
  const topK = typeof o.top_k === "number" ? o.top_k : Number(o.top_k);
  const timingMs = typeof o.timing_ms === "number" ? o.timing_ms : Number(o.timing_ms);
  const hybridAlpha = typeof o.hybrid_alpha === "number" ? o.hybrid_alpha : Number(o.hybrid_alpha);

  return {
    enabled: Boolean(o.enabled),
    applied: Boolean(o.applied),
    requested_method: typeof o.requested_method === "string" ? o.requested_method : "",
    method: typeof o.method === "string" ? o.method : null,
    provider: typeof o.provider === "string" ? o.provider : null,
    model: typeof o.model === "string" ? o.model : null,
    top_k: Number.isFinite(topK) ? topK : 0,
    hybrid_alpha: Number.isFinite(hybridAlpha) ? hybridAlpha : null,
    hybrid_applied: typeof o.hybrid_applied === "boolean" ? o.hybrid_applied : undefined,
    after_rerank: afterRerank,
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
  const providerText = obs.provider ?? "-";
  const modelText = obs.model ?? "-";
  const hybridText =
    typeof obs.hybrid_alpha === "number" ? ` | hybrid_alpha:${obs.hybrid_alpha}` : obs.hybrid_alpha === null ? "" : "";
  const hybridAppliedText =
    typeof obs.hybrid_applied === "boolean" ? ` | hybrid_applied:${String(obs.hybrid_applied)}` : "";
  const errText = obs.error_type ? ` | error:${obs.error_type}` : "";
  const changesText = delta.compared
    ? ` | changed_in_top_k:${comparedText} | entered:${delta.entered} | left:${delta.left}`
    : "";
  return `enabled:${String(obs.enabled)} | applied:${String(obs.applied)} | reason:${reasonText} | requested:${reqText} | method:${methodText} | provider:${providerText} | model:${modelText}${hybridText}${hybridAppliedText} | top_k:${obs.top_k} | timing_ms:${obs.timing_ms}${changesText}${errText}`;
}

export function normalizeSuperSortObs(raw: unknown): VectorSuperSortObs | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;

  const before = Array.isArray(o.before) ? o.before.map((v) => String(v)) : undefined;
  const after = Array.isArray(o.after) ? o.after.map((v) => String(v)) : undefined;

  const sourceOrder = Array.isArray(o.source_order) ? o.source_order.map((v) => String(v)) : null;
  const sourceOrderEffective = Array.isArray(o.source_order_effective)
    ? o.source_order_effective.map((v) => String(v))
    : null;
  const bySource = o.by_source && typeof o.by_source === "object" ? (o.by_source as Record<string, number>) : null;

  return {
    enabled: Boolean(o.enabled),
    applied: Boolean(o.applied),
    reason: typeof o.reason === "string" ? o.reason : null,
    before,
    after,
    source_order: sourceOrder,
    source_order_effective: sourceOrderEffective,
    source_weights:
      o.source_weights && typeof o.source_weights === "object" ? (o.source_weights as Record<string, number>) : null,
    source_weights_effective:
      o.source_weights_effective && typeof o.source_weights_effective === "object"
        ? (o.source_weights_effective as Record<string, number>)
        : null,
    by_source: bySource,
    override_enabled: typeof o.override_enabled === "boolean" ? o.override_enabled : null,
    requested: o.requested,
  };
}

export function formatSuperSortSummary(obs: VectorSuperSortObs): string {
  const reasonText = obs.reason ?? "-";
  const bySourceText = obs.by_source
    ? Object.entries(obs.by_source)
        .map(([k, v]) => `${k}:${v}`)
        .join(" | ")
    : "-";
  const orderText = obs.source_order_effective?.length
    ? obs.source_order_effective.join(",")
    : obs.source_order?.length
      ? obs.source_order.join(",")
      : "-";
  return `enabled:${String(obs.enabled)} | applied:${String(obs.applied)} | reason:${reasonText} | order:${orderText} | by_source:${bySourceText}`;
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
