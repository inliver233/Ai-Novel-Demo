import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { UI_COPY } from "../../lib/uiCopy";
import { ApiError, apiJson } from "../../services/apiClient";
import { Drawer } from "../ui/Drawer";
import { useToast } from "../ui/toast";
import type { MemoryContextPack } from "./types";

type Props = {
  open: boolean;
  onClose: () => void;
  projectId?: string;
  memoryInjectionEnabled: boolean;
  onChangeMemoryInjectionEnabled?: (enabled: boolean) => void;
  genInstruction?: string;
  genChapterPlan?: string;
  genMemoryQueryText?: string;
  genMemoryModules?: {
    worldbook: boolean;
    story_memory: boolean;
    structured: boolean;
    vector_rag: boolean;
    graph: boolean;
    fractal: boolean;
  };
};

type VectorSource = "worldbook" | "outline" | "chapter";

type VectorCandidate = {
  id: string;
  distance: number;
  text: string;
  metadata: Record<string, unknown>;
};

type VectorRagCounts = {
  candidates_total: number;
  candidates_returned: number;
  unique_sources: number;
  final_selected: number;
  dropped_total: number;
  dropped_by_reason: Record<string, number>;
};

type VectorRerankObs = {
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

type VectorHybridObs = {
  enabled: boolean;
  ranks?: unknown;
  counts?: unknown;
  overfilter?: unknown;
};

type VectorRagQueryResult = {
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

type MemoryContextPackLogItem = {
  section: string;
  enabled: boolean;
  disabled_reason: string | null;
  note: string | null;
};

type MemorySectionEnabled = {
  worldbook: boolean;
  story_memory: boolean;
  structured: boolean;
  vector_rag: boolean;
  graph: boolean;
  fractal: boolean;
};

const DEFAULT_PREVIEW_SECTIONS: MemorySectionEnabled = {
  worldbook: true,
  story_memory: true,
  structured: true,
  vector_rag: true,
  graph: true,
  fractal: true,
};

const DEFAULT_BUDGET_INPUTS: Record<string, string> = {
  worldbook: "",
  story_memory: "",
  structured: "",
  vector_rag: "",
  graph: "",
  fractal: "",
};

const EMPTY_PACK: MemoryContextPack = {
  worldbook: {},
  story_memory: {},
  structured: {},
  vector_rag: {},
  graph: {},
  fractal: {},
  logs: [],
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

function rerankDelta(obs: VectorRerankObs): { compared: number; changedPositions: number; entered: number; left: number } {
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

function formatRerankSummary(obs: VectorRerankObs): string {
  const delta = rerankDelta(obs);
  const comparedText = delta.compared ? `${delta.changedPositions}/${delta.compared}` : "-";
  const methodText = obs.method ?? "-";
  const reqText = obs.requested_method || "-";
  const reasonText = obs.reason ?? "-";
  const errText = obs.error_type ? ` | error:${obs.error_type}` : "";
  const changesText = delta.compared ? ` | changed_in_top_k:${comparedText} | entered:${delta.entered} | left:${delta.left}` : "";
  return `enabled:${String(obs.enabled)} | applied:${String(obs.applied)} | reason:${reasonText} | requested:${reqText} | method:${methodText} | top_k:${obs.top_k} | timing_ms:${obs.timing_ms}${changesText}${errText}`;
}

function formatHybridCounts(raw: unknown): string {
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

function formatOverfilter(raw: unknown): string {
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

function normalizeVectorResult(raw: unknown): VectorRagQueryResult | null {
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

function normalizePackLogItem(raw: unknown): MemoryContextPackLogItem | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const section = typeof o.section === "string" ? o.section : "";
  const enabled = typeof o.enabled === "boolean" ? o.enabled : Boolean(o.enabled);
  if (!section) return null;
  return {
    section,
    enabled,
    disabled_reason: typeof o.disabled_reason === "string" ? o.disabled_reason : null,
    note: typeof o.note === "string" ? o.note : null,
  };
}

async function writeClipboardText(text: string): Promise<void> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const el = document.createElement("textarea");
  el.value = text;
  el.setAttribute("readonly", "true");
  el.style.position = "fixed";
  el.style.left = "-9999px";
  el.style.top = "-9999px";
  document.body.appendChild(el);
  el.select();
  document.execCommand("copy");
  document.body.removeChild(el);
}

function downloadJson(filename: string, value: unknown): void {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ContextPreviewDrawer(props: Props) {
  const {
    onClose,
    open,
    projectId,
    memoryInjectionEnabled,
    onChangeMemoryInjectionEnabled,
    genInstruction,
    genChapterPlan,
    genMemoryQueryText,
    genMemoryModules,
  } = props;
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [pack, setPack] = useState<MemoryContextPack>(EMPTY_PACK);
  const [error, setError] = useState<{ code: string; message: string; requestId?: string } | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);

  const syncedOnceRef = useRef(false);

  const [previewQueryText, setPreviewQueryText] = useState("");
  const [previewSections, setPreviewSections] = useState<MemorySectionEnabled>(DEFAULT_PREVIEW_SECTIONS);
  const [budgetOverrideInputs, setBudgetOverrideInputs] = useState<Record<string, string>>(DEFAULT_BUDGET_INPUTS);
  const [syncedAt, setSyncedAt] = useState<string | null>(null);

  const [vectorQueryText, setVectorQueryText] = useState("");
  const [vectorSources, setVectorSources] = useState<Record<VectorSource, boolean>>({
    worldbook: true,
    outline: true,
    chapter: true,
  });
  const selectedVectorSources = useMemo(() => {
    const out: VectorSource[] = [];
    for (const src of ["worldbook", "outline", "chapter"] as const) {
      if (vectorSources[src]) out.push(src);
    }
    return out;
  }, [vectorSources]);

  const [vectorLoading, setVectorLoading] = useState(false);
  const [vectorResult, setVectorResult] = useState<VectorRagQueryResult | null>(null);
  const [vectorRequestId, setVectorRequestId] = useState<string | null>(null);
  const [vectorRawQueryText, setVectorRawQueryText] = useState<string | null>(null);
  const [vectorNormalizedQueryText, setVectorNormalizedQueryText] = useState<string | null>(null);
  const [vectorPreprocessObs, setVectorPreprocessObs] = useState<unknown>(null);
  const [vectorError, setVectorError] = useState<{ code: string; message: string; requestId?: string } | null>(null);

  const effectivePack = useMemo(() => (memoryInjectionEnabled ? pack : EMPTY_PACK), [memoryInjectionEnabled, pack]);

  const parsedBudgetOverrides = useMemo(() => {
    const out: Record<string, number> = {};
    for (const key of ["worldbook", "story_memory", "structured", "vector_rag", "graph", "fractal"] as const) {
      const raw = String(budgetOverrideInputs[key] ?? "").trim();
      if (!raw) continue;
      const parsed = Number(raw);
      if (!Number.isFinite(parsed) || parsed < 0) continue;
      out[key] = Math.floor(parsed);
    }
    return out;
  }, [budgetOverrideInputs]);

  const downloadPreviewBundle = useCallback(() => {
    if (!projectId) {
      toast.toastError(UI_COPY.writing.contextPreviewMissingProjectId);
      return;
    }
    try {
      const stamp = new Date().toISOString().replaceAll(":", "-").replaceAll(".", "-");
      const hint = requestId || stamp;
      const filename = `context_preview_bundle_${projectId}_${hint}.json`;
      downloadJson(filename, {
        schema_version: "context_preview_bundle_v1",
        created_at: new Date().toISOString(),
        project_id: projectId,
        request_id: requestId,
        synced_at: syncedAt,
        preview: {
          query_text: previewQueryText,
          sections: previewSections,
          budget_overrides: parsedBudgetOverrides,
          budget_override_inputs: budgetOverrideInputs,
          memory_injection_enabled: memoryInjectionEnabled,
        },
        pack: effectivePack ?? EMPTY_PACK,
        vector_query: {
          request_id: vectorRequestId,
          query_text: vectorQueryText,
          sources: selectedVectorSources,
          raw_query_text: vectorRawQueryText,
          normalized_query_text: vectorNormalizedQueryText,
          preprocess_obs: vectorPreprocessObs,
          result: vectorResult,
        },
        generate: {
          instruction: genInstruction ?? null,
          chapter_plan: genChapterPlan ?? null,
          memory_query_text: genMemoryQueryText ?? null,
          memory_modules: genMemoryModules ?? null,
        },
      });
      toast.toastSuccess("已导出预览 bundle", requestId ?? undefined);
    } catch {
      toast.toastError("导出失败");
    }
  }, [
    budgetOverrideInputs,
    effectivePack,
    genChapterPlan,
    genInstruction,
    genMemoryModules,
    genMemoryQueryText,
    memoryInjectionEnabled,
    parsedBudgetOverrides,
    previewQueryText,
    previewSections,
    projectId,
    requestId,
    selectedVectorSources,
    syncedAt,
    toast,
    vectorNormalizedQueryText,
    vectorPreprocessObs,
    vectorQueryText,
    vectorRawQueryText,
    vectorRequestId,
    vectorResult,
  ]);

  const computeEffectiveQueryTextFromGenerate = useCallback((): string => {
    const requested = String(genMemoryQueryText ?? "").trim();
    if (requested) return requested;

    const instruction = String(genInstruction ?? "").trim();
    const plan = String(genChapterPlan ?? "").trim();
    if (!instruction && !plan) return "";
    return plan ? `${instruction}\n\n${plan}`.trim() : instruction;
  }, [genChapterPlan, genInstruction, genMemoryQueryText]);

  const isEmptyPack = useMemo(() => {
    const getTextMd = (raw: unknown): string => {
      if (!raw || typeof raw !== "object") return "";
      const o = raw as Record<string, unknown>;
      return typeof o.text_md === "string" ? o.text_md.trim() : "";
    };
    return (
      !getTextMd(effectivePack.worldbook) &&
      !getTextMd(effectivePack.story_memory) &&
      !getTextMd(effectivePack.structured) &&
      !getTextMd(effectivePack.vector_rag) &&
      !getTextMd(effectivePack.graph) &&
      !getTextMd(effectivePack.fractal)
    );
  }, [effectivePack]);

  const packLogs = useMemo(() => {
    const rawLogs = Array.isArray(effectivePack.logs) ? effectivePack.logs : [];
    return rawLogs.map(normalizePackLogItem).filter((v): v is MemoryContextPackLogItem => Boolean(v));
  }, [effectivePack.logs]);

  const worldbookPreview = useMemo(() => {
    const raw = (effectivePack.worldbook ?? {}) as Record<string, unknown>;
    const triggered = Array.isArray(raw.triggered) ? raw.triggered : [];
    const textMd = typeof raw.text_md === "string" ? raw.text_md : "";
    const truncated = Boolean(raw.truncated);
    return { triggered, textMd, truncated, raw };
  }, [effectivePack.worldbook]);

  const runVectorQuery = useCallback(async () => {
    if (!projectId) {
      setVectorError({ code: "NO_PROJECT", message: UI_COPY.writing.contextPreviewMissingProjectId });
      return;
    }
    if (selectedVectorSources.length === 0) {
      toast.toastError("至少选择一个 source");
      return;
    }
    setVectorLoading(true);
    setVectorError(null);
    try {
      const res = await apiJson<{
        result: unknown;
        raw_query_text?: unknown;
        normalized_query_text?: unknown;
        preprocess_obs?: unknown;
      }>(`/api/projects/${projectId}/vector/query`, {
        method: "POST",
        body: JSON.stringify({ query_text: vectorQueryText, sources: selectedVectorSources }),
      });
      const normalized = normalizeVectorResult(res.data?.result);
      if (!normalized)
        throw new ApiError({ code: "BAD_RESPONSE", message: "响应格式错误", requestId: res.request_id, status: 200 });
      setVectorResult(normalized);
      setVectorRequestId(res.request_id ?? null);
      setVectorRawQueryText(typeof res.data?.raw_query_text === "string" ? res.data.raw_query_text : vectorQueryText);
      setVectorNormalizedQueryText(typeof res.data?.normalized_query_text === "string" ? res.data.normalized_query_text : null);
      setVectorPreprocessObs(res.data?.preprocess_obs ?? null);
    } catch (e) {
      setVectorRawQueryText(null);
      setVectorNormalizedQueryText(null);
      setVectorPreprocessObs(null);
      if (e instanceof ApiError) {
        setVectorError({ code: e.code, message: e.message, requestId: e.requestId });
      } else {
        setVectorError({ code: "UNKNOWN", message: "查询失败" });
      }
    } finally {
      setVectorLoading(false);
    }
  }, [projectId, selectedVectorSources, toast, vectorQueryText]);

  const fetchPreview = useCallback(
    async (params: { queryText: string; sections: MemorySectionEnabled; budgets: Record<string, number> }) => {
      if (!projectId) {
        setError({ code: "NO_PROJECT", message: UI_COPY.writing.contextPreviewMissingProjectId });
        return;
      }
      const safeQueryText = String(params.queryText ?? "").slice(0, 5000);
      setLoading(true);
      setError(null);
      try {
        const res = await apiJson<MemoryContextPack>(`/api/projects/${projectId}/memory/preview`, {
          method: "POST",
          body: JSON.stringify({
            query_text: safeQueryText,
            section_enabled: params.sections,
            budget_overrides: params.budgets,
          }),
        });
        setPack(res.data ?? EMPTY_PACK);
        setRequestId(res.request_id ?? null);
      } catch (e) {
        if (e instanceof ApiError) {
          setError({ code: e.code, message: e.message, requestId: e.requestId });
        } else {
          setError({ code: "UNKNOWN", message: "加载失败" });
        }
      } finally {
        setLoading(false);
      }
    },
    [projectId],
  );

  const syncPreviewFromGenerate = useCallback(async () => {
    const queryText = computeEffectiveQueryTextFromGenerate();
    const sections = genMemoryModules ?? DEFAULT_PREVIEW_SECTIONS;
    setPreviewQueryText(queryText);
    setPreviewSections(sections);
    setBudgetOverrideInputs(DEFAULT_BUDGET_INPUTS);
    setSyncedAt(new Date().toISOString().replace("T", " ").slice(0, 19));
    await fetchPreview({ queryText, sections, budgets: {} });
  }, [computeEffectiveQueryTextFromGenerate, fetchPreview, genMemoryModules]);

  const load = useCallback(async () => {
    if (!projectId) {
      setError({ code: "NO_PROJECT", message: UI_COPY.writing.contextPreviewMissingProjectId });
      return;
    }
    await fetchPreview({ queryText: previewQueryText, sections: previewSections, budgets: parsedBudgetOverrides });
  }, [fetchPreview, parsedBudgetOverrides, previewQueryText, previewSections, projectId]);

  useEffect(() => {
    if (!open) return;
    if (!memoryInjectionEnabled) return;
    if (syncedOnceRef.current) return;
    syncedOnceRef.current = true;
    void syncPreviewFromGenerate();
  }, [memoryInjectionEnabled, open, syncPreviewFromGenerate]);

  useEffect(() => {
    if (open) return;
    syncedOnceRef.current = false;
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (memoryInjectionEnabled) return;
    syncedOnceRef.current = false;
    setLoading(false);
    setError(null);
    setPack(EMPTY_PACK);
    setRequestId(null);
  }, [memoryInjectionEnabled, open]);

  useEffect(() => {
    if (!open) return;
    setVectorError(null);
    setVectorRequestId(null);
    setVectorResult(null);
    setVectorLoading(false);
  }, [open, projectId]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  return (
    <Drawer
      open={open}
      onClose={onClose}
      ariaLabel={UI_COPY.writing.contextPreviewTitle}
      panelClassName="h-full w-full max-w-2xl overflow-y-auto border-l border-border bg-canvas p-6 shadow-sm"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-content text-2xl text-ink">{UI_COPY.writing.contextPreviewTitle}</div>
          <div className="mt-1 text-xs text-subtext">
            {UI_COPY.writing.contextPreviewSubtitle}
            {requestId ? <span className="ml-2">request_id: {requestId}</span> : null}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn btn-secondary"
            disabled={!projectId}
            onClick={() => downloadPreviewBundle()}
            type="button"
          >
            下载预览 bundle
          </button>
          <button
            className="btn btn-secondary"
            disabled={loading || !memoryInjectionEnabled}
            onClick={() => void load()}
            type="button"
          >
            {UI_COPY.writing.contextPreviewRefresh}
          </button>
          <button className="btn btn-secondary" onClick={onClose} type="button">
            {UI_COPY.writing.contextPreviewClose}
          </button>
        </div>
      </div>

      <div className="mt-5 grid gap-4">
        <div className="panel p-3">
          <label className="flex items-center justify-between gap-3 text-sm text-ink">
            <span>{UI_COPY.writing.memoryInjectionToggle}</span>
            <input
              className="checkbox"
              checked={memoryInjectionEnabled}
              disabled={!onChangeMemoryInjectionEnabled}
              onChange={(e) => onChangeMemoryInjectionEnabled?.(e.target.checked)}
              type="checkbox"
            />
          </label>
          <div className="mt-1 text-[11px] text-subtext">
            {memoryInjectionEnabled
              ? UI_COPY.writing.memoryInjectionHint
              : UI_COPY.writing.memoryInjectionDisabledPreview}
          </div>
        </div>

        {memoryInjectionEnabled ? (
          <div className="panel p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm text-ink">预览参数（preview API）</div>
                <div className="mt-1 text-[11px] text-subtext">
                  当前预览应尽量与“AI 生成”抽屉一致；可手动修改后点刷新。
                  {syncedAt ? <span className="ml-2">synced_at: {syncedAt}</span> : null}
                </div>
              </div>
              <button
                className="btn btn-secondary"
                disabled={loading || !projectId}
                onClick={() => void syncPreviewFromGenerate()}
                type="button"
              >
                同步生成设置
              </button>
            </div>

            <div className="mt-4 grid gap-3">
              <label className="text-xs text-subtext">
                memory_query_text（用于 pack 预览）
                <textarea
                  className="textarea mt-1 min-h-24 w-full"
                  name="memory_preview_query_text"
                  value={previewQueryText}
                  placeholder="例如：本章要写的角色/地点/冲突（用于检索相关记忆）"
                  onChange={(e) => setPreviewQueryText(e.target.value)}
                />
              </label>

              <div className="grid gap-2">
                <div className="text-xs text-subtext">modules（section_enabled）</div>
                {(
                  [
                    ["worldbook", "世界书（worldbook）"],
                    ["story_memory", "剧情记忆（story_memory）"],
                    ["structured", "结构化记忆（structured）"],
                    ["vector_rag", "向量 RAG（vector_rag）"],
                    ["graph", "关系图（graph）"],
                    ["fractal", "Fractal（fractal）"],
                  ] as const
                ).map(([key, label]) => (
                  <label key={key} className="flex items-center justify-between gap-3 text-sm text-ink">
                    <span>{label}</span>
                    <input
                      className="checkbox"
                      checked={previewSections[key]}
                      onChange={(e) => setPreviewSections((prev) => ({ ...prev, [key]: e.target.checked }))}
                      type="checkbox"
                    />
                  </label>
                ))}
              </div>

              <details className="rounded-atelier border border-border bg-surface p-3">
                <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                  预算覆盖（budget_overrides，可选）
                </summary>
                <div className="mt-3 grid gap-2">
                  {(
                    [
                      ["worldbook", "worldbook char_limit"],
                      ["story_memory", "story_memory char_limit"],
                      ["structured", "structured char_limit"],
                      ["vector_rag", "vector_rag char_limit"],
                      ["graph", "graph char_limit"],
                      ["fractal", "fractal char_limit"],
                    ] as const
                  ).map(([key, label]) => (
                    <label key={key} className="grid gap-1 text-xs text-subtext">
                      <span>{label}</span>
                      <input
                        className="input"
                        inputMode="numeric"
                        placeholder="留空=默认"
                        value={budgetOverrideInputs[key]}
                        onChange={(e) =>
                          setBudgetOverrideInputs((prev) => ({
                            ...prev,
                            [key]: e.currentTarget.value.replace(/[^\d]/g, ""),
                          }))
                        }
                      />
                    </label>
                  ))}
                  <div className="text-[11px] text-subtext">仅影响预览，不会改变实际生成的注入预算。</div>
                </div>
              </details>
            </div>
          </div>
        ) : null}

        {loading ? <div className="text-sm text-subtext">{UI_COPY.common.loading}</div> : null}
        {error ? (
          <div className="rounded-atelier border border-border bg-surface p-3 text-sm text-subtext">
            <div className="text-ink">{UI_COPY.writing.contextPreviewLoadFailedTitle}</div>
            <div className="mt-1 text-xs text-subtext">
              {error.message} ({error.code})
              {error.requestId ? <span className="ml-2">request_id: {error.requestId}</span> : null}
            </div>
          </div>
        ) : null}

        {memoryInjectionEnabled && isEmptyPack ? (
          <div className="text-sm text-subtext">{UI_COPY.writing.memoryPackEmpty}</div>
        ) : null}

        {memoryInjectionEnabled ? (
          <div className="panel p-4">
            <div className="text-sm text-ink">Pack sections</div>
            {packLogs.length ? (
              <div className="mt-2 grid gap-2">
                {packLogs.map((it) => (
                  <div key={it.section} className="rounded-atelier border border-border bg-surface p-2">
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="font-mono text-ink">{it.section}</span>
                      {it.enabled ? (
                        <span className="text-emerald-600 dark:text-emerald-400">enabled</span>
                      ) : (
                        <span className="text-amber-600 dark:text-amber-400">
                          disabled: {it.disabled_reason ?? "unknown"}
                        </span>
                      )}
                    </div>
                    {it.note ? <div className="mt-1 text-[11px] text-subtext">{it.note}</div> : null}
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-2 text-sm text-subtext">No logs available.</div>
            )}
          </div>
        ) : null}

        {memoryInjectionEnabled ? (
          <div className="panel p-4">
            <div className="text-sm text-ink">Memory text_md</div>
            {(["story_memory", "structured", "graph", "fractal"] as const).map((key) => {
              const raw = (effectivePack[key] ?? {}) as Record<string, unknown>;
              const textMd = typeof raw.text_md === "string" ? raw.text_md : "";
              return (
                <details key={key} className="mt-3">
                  <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                    {key}.text_md
                  </summary>
                  <pre className="mt-2 max-h-64 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                    {textMd || "（空）"}
                  </pre>
                </details>
              );
            })}
          </div>
        ) : null}

        {memoryInjectionEnabled ? (
          <div className="panel p-4">
            <div className="text-sm text-ink">{UI_COPY.writing.worldbookSectionTitle}</div>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-subtext">
              <span>
                {UI_COPY.worldbook.previewTriggeredPrefix}
                {worldbookPreview.triggered.length}
                {UI_COPY.worldbook.previewTriggeredSuffix}
              </span>
              {worldbookPreview.truncated ? (
                <span className="text-amber-600 dark:text-amber-400">{UI_COPY.worldbook.previewTruncated}</span>
              ) : null}
            </div>

            <details open className="mt-3">
              <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                {UI_COPY.worldbook.previewTriggeredList}
              </summary>
              <div className="mt-2 grid gap-2">
                {worldbookPreview.triggered.length === 0 ? (
                  <div className="text-sm text-subtext">{UI_COPY.worldbook.previewNoTriggered}</div>
                ) : (
                  worldbookPreview.triggered.map((t) => {
                    if (!t || typeof t !== "object") return null;
                    const o = t as Record<string, unknown>;
                    const id = String(o.id ?? "");
                    const title = String(o.title ?? "");
                    const reason = String(o.reason ?? "");
                    const priority = String(o.priority ?? "");
                    return (
                      <div key={id || title} className="rounded-atelier border border-border bg-surface p-2 text-xs">
                        <div className="truncate text-ink">{title || id}</div>
                        <div className="mt-1 text-subtext">
                          {reason}
                          {priority ? ` | priority:${priority}` : ""}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </details>

            <details className="mt-3">
              <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                {UI_COPY.worldbook.previewText}
              </summary>
              <pre className="mt-2 max-h-64 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                {worldbookPreview.textMd || UI_COPY.worldbook.previewTextEmpty}
              </pre>
            </details>

            <details className="mt-3">
              <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                {UI_COPY.writing.contextPreviewRawPack}
              </summary>
              <pre className="mt-2 max-h-64 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                {JSON.stringify(effectivePack ?? EMPTY_PACK, null, 2)}
              </pre>
            </details>
          </div>
        ) : null}

        <div className="panel p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-sm text-ink">Vector RAG 调试</div>
              <div className="mt-1 text-[11px] text-subtext">
                {vectorResult ? (
                  vectorResult.enabled ? (
                    <span className="text-emerald-600 dark:text-emerald-400">enabled</span>
                  ) : (
                    <span className="text-amber-600 dark:text-amber-400">
                      disabled: {vectorResult.disabled_reason ?? "unknown"}
                      {vectorResult.error ? ` | error:${vectorResult.error}` : ""}
                    </span>
                  )
                ) : (
                  "尚未查询"
                )}
                {vectorRequestId ? <span className="ml-2">request_id: {vectorRequestId}</span> : null}
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-end gap-2">
              <button
                className="btn btn-secondary"
                disabled={!projectId || vectorLoading}
                onClick={() => void runVectorQuery()}
                type="button"
              >
                {vectorLoading ? "查询中..." : "查询"}
              </button>
              <button
                className="btn btn-secondary"
                disabled={!vectorResult}
                onClick={() => {
                  if (!vectorResult) return;
                  void (async () => {
                    try {
                      await writeClipboardText(JSON.stringify(vectorResult, null, 2));
                      toast.toastSuccess("已复制 JSON");
                    } catch {
                      toast.toastError("复制失败");
                    }
                  })();
                }}
                type="button"
              >
                复制结果 JSON
              </button>
              <button
                className="btn btn-secondary"
                disabled={!vectorResult}
                onClick={() => {
                  if (!vectorResult) return;
                  downloadJson(`vector_rag_${projectId ?? "project"}.json`, vectorResult);
                }}
                type="button"
              >
                导出 JSON
              </button>
            </div>
          </div>

          <div className="mt-4 grid gap-3">
            <label className="text-xs text-subtext">
              query_text
              <textarea
                className="textarea mt-1 min-h-24 w-full"
                value={vectorQueryText}
                placeholder="例如：本章要写的角色/地点/冲突（用于检索相关 chunk）"
                onChange={(e) => setVectorQueryText(e.target.value)}
              />
            </label>

            <div className="flex flex-wrap items-center gap-4 text-xs text-subtext">
              <span>sources</span>
              {(["worldbook", "outline", "chapter"] as const).map((src) => (
                <label key={src} className="flex items-center gap-2 text-ink">
                  <input
                    className="checkbox"
                    checked={vectorSources[src]}
                    onChange={(e) => setVectorSources((prev) => ({ ...prev, [src]: e.target.checked }))}
                    type="checkbox"
                  />
                  {src}
                </label>
              ))}
            </div>

            {vectorError ? (
              <div className="rounded-atelier border border-border bg-surface p-3 text-sm text-subtext">
                <div className="text-ink">查询失败</div>
                <div className="mt-1 text-xs text-subtext">
                  {vectorError.message} ({vectorError.code})
                  {vectorError.requestId ? <span className="ml-2">request_id: {vectorError.requestId}</span> : null}
                </div>
              </div>
            ) : null}

            {vectorResult ? (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-subtext">
                  <span>
                    {vectorResult.counts ? (
                      <>
                        counts: total:{vectorResult.counts.candidates_total} | returned:
                        {vectorResult.counts.candidates_returned} | unique_sources:
                        {vectorResult.counts.unique_sources} | final_selected:{vectorResult.counts.final_selected} |
                        dropped:
                        {vectorResult.counts.dropped_total}
                        {" "}
                        | drop_by_reason:
                        {Object.keys(vectorResult.counts.dropped_by_reason).length
                          ? Object.entries(vectorResult.counts.dropped_by_reason)
                              .map(([k, v]) => `${k}:${v}`)
                              .join(" | ")
                          : "-"}
                      </>
                    ) : (
                      <>
                        counts: candidates:{vectorResult.candidates.length} | final_chunks:
                        {vectorResult.final.chunks.length} | dropped:{vectorResult.dropped.length}
                      </>
                    )}
                  </span>
                  <span>
                    timings_ms:{" "}
                    {Object.keys(vectorResult.timings_ms).length
                      ? Object.entries(vectorResult.timings_ms)
                          .map(([k, v]) => `${k}:${v}`)
                          .join(" | ")
                      : "-"}
                  </span>
                </div>

                {vectorResult.rerank ? (
                  <div className="mt-1 text-xs text-subtext">rerank: {formatRerankSummary(vectorResult.rerank)}</div>
                ) : null}

                <div className="mt-1 text-xs text-subtext">
                  hybrid:{" "}
                  {vectorResult.hybrid
                    ? `enabled:${String(vectorResult.hybrid.enabled)} | counts:${formatHybridCounts(vectorResult.hybrid.counts)} | overfilter:${formatOverfilter(vectorResult.hybrid.overfilter)}`
                    : "-"}{" "}
                  | backend: {vectorResult.backend ?? "-"}
                </div>

                <details open className="mt-1">
                  <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                    注入预览（prompt_block.text_md）
                  </summary>
                  <pre className="mt-2 max-h-64 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                    {vectorResult.prompt_block.text_md || "（空）"}
                  </pre>
                </details>

                <details className="mt-1">
                  <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                    query preprocess（raw vs normalized）
                  </summary>
                  <div className="mt-2 grid gap-3">
                    <div>
                      <div className="text-[11px] text-subtext">raw_query_text</div>
                      <pre className="mt-1 max-h-28 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                        {vectorRawQueryText ?? ""}
                      </pre>
                    </div>
                    <div>
                      <div className="text-[11px] text-subtext">normalized_query_text</div>
                      <pre className="mt-1 max-h-28 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                        {vectorNormalizedQueryText ?? ""}
                      </pre>
                    </div>
                    <div>
                      <div className="text-[11px] text-subtext">preprocess_obs</div>
                      <pre className="mt-1 max-h-64 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                        {JSON.stringify(vectorPreprocessObs ?? null, null, 2)}
                      </pre>
                    </div>
                  </div>
                </details>

                <details className="mt-1">
                  <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                    candidates（前 {Math.min(10, vectorResult.candidates.length)}）
                  </summary>
                  <div className="mt-2 grid gap-2">
                    {vectorResult.candidates.slice(0, 10).map((c) => {
                      const meta = c.metadata ?? {};
                      const source = typeof meta.source === "string" ? meta.source : "";
                      const title = typeof meta.title === "string" ? meta.title : "";
                      const sourceId = typeof meta.source_id === "string" ? meta.source_id : "";
                      const snippet = (c.text || "").replaceAll(/\s+/g, " ").trim().slice(0, 220);
                      return (
                        <div key={c.id} className="rounded-atelier border border-border bg-surface p-2 text-xs">
                          <div className="truncate text-ink">
                            {source || "chunk"} {title ? `| ${title}` : ""} {sourceId ? `| ${sourceId}` : ""}
                          </div>
                          <div className="mt-1 text-subtext">distance: {c.distance.toFixed(4)}</div>
                          <div className="mt-1 text-subtext">
                            {snippet || "（空）"}
                            {snippet.length >= 220 ? "…" : ""}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </details>

                <details className="mt-1">
                  <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                    raw vector query result
                  </summary>
                  <pre className="mt-2 max-h-64 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                    {JSON.stringify(vectorResult, null, 2)}
                  </pre>
                </details>
              </>
            ) : (
              <div className="text-sm text-subtext">
                提示：当前环境缺 embedding/chroma 时会返回 disabled_reason，但结构仍可用于排查。
              </div>
            )}
          </div>
        </div>
      </div>
    </Drawer>
  );
}
