import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useToast } from "../components/ui/toast";
import { useProjectData } from "../hooks/useProjectData";
import { ApiError, apiJson } from "../services/apiClient";
import type { ProjectSettings } from "../types";

type VectorSource = "worldbook" | "outline" | "chapter";

type VectorIndexState = {
  dirty: boolean;
  last_build_at: string | null;
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

type VectorRagResult = {
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

type VectorChunk = {
  id: string;
  distance?: number;
  text?: string;
  metadata?: Record<string, unknown>;
};

type KnowledgeBase = {
  kb_id: string;
  name: string;
  enabled: boolean;
  weight: number;
  order: number;
  created_at?: string | null;
  updated_at?: string | null;
};

function safeJson(obj: unknown): string {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

function formatIsoToLocal(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString();
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

export function RagPage() {
  const { projectId } = useParams();
  const toast = useToast();

  const settingsQuery = useProjectData<ProjectSettings>(projectId, async (id) => {
    const res = await apiJson<{ settings: ProjectSettings }>(`/api/projects/${id}/settings`);
    return res.data.settings;
  });

  const [rerankEnabled, setRerankEnabled] = useState(false);
  const [rerankMethod, setRerankMethod] = useState("auto");
  const [rerankTopK, setRerankTopK] = useState(20);
  const [rerankSaving, setRerankSaving] = useState(false);

  const [sources, setSources] = useState<VectorSource[]>(["worldbook", "outline", "chapter"]);
  const [queryText, setQueryText] = useState("");

  const [kbLoading, setKbLoading] = useState(false);
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [selectedKbIds, setSelectedKbIds] = useState<string[]>([]);
  const [kbDraftById, setKbDraftById] = useState<Record<string, Pick<KnowledgeBase, "name" | "enabled" | "weight">>>({});
  const [kbDirtyById, setKbDirtyById] = useState<Record<string, boolean>>({});
  const [kbOrderDirty, setKbOrderDirty] = useState(false);
  const [kbDragId, setKbDragId] = useState<string | null>(null);
  const [kbCreateName, setKbCreateName] = useState("");
  const [kbCreateLoading, setKbCreateLoading] = useState(false);
  const [kbSaveLoadingId, setKbSaveLoadingId] = useState<string | null>(null);
  const [kbDeleteLoadingId, setKbDeleteLoadingId] = useState<string | null>(null);

  const [statusLoading, setStatusLoading] = useState(false);
  const [ingestLoading, setIngestLoading] = useState(false);
  const [rebuildLoading, setRebuildLoading] = useState(false);
  const [queryLoading, setQueryLoading] = useState(false);

  const [status, setStatus] = useState<VectorRagResult | null>(null);
  const [ingestResult, setIngestResult] = useState<unknown>(null);
  const [rebuildResult, setRebuildResult] = useState<unknown>(null);
  const [queryResult, setQueryResult] = useState<VectorRagResult | null>(null);
  const [queryRequestId, setQueryRequestId] = useState<string | null>(null);
  const [rawQueryText, setRawQueryText] = useState<string | null>(null);
  const [normalizedQueryText, setNormalizedQueryText] = useState<string | null>(null);
  const [queryPreprocessObs, setQueryPreprocessObs] = useState<unknown>(null);

  const busy = statusLoading || ingestLoading || rebuildLoading || queryLoading || rerankSaving;

  const vectorIndexDirty = status?.index ? Boolean(status.index.dirty) : null;
  const lastVectorBuildAt = status?.index ? status.index.last_build_at ?? null : null;
  const vectorEnabled = status ? Boolean(status.enabled) : null;
  const vectorDisabledReason = status && typeof status.disabled_reason === "string" ? status.disabled_reason : null;

  useEffect(() => {
    if (!settingsQuery.data) return;
    setRerankEnabled(Boolean(settingsQuery.data.vector_rerank_effective_enabled));
    setRerankMethod(String(settingsQuery.data.vector_rerank_effective_method ?? "auto") || "auto");
    setRerankTopK(Number(settingsQuery.data.vector_rerank_effective_top_k ?? 20) || 20);
  }, [settingsQuery.data]);

  const applyRerank = useCallback(async () => {
    if (!projectId) return;
    setRerankSaving(true);
    try {
      const method = rerankMethod.trim() || "auto";
      const topK = Math.max(1, Math.min(1000, Math.floor(rerankTopK)));
      const res = await apiJson<{ settings: ProjectSettings }>(`/api/projects/${projectId}/settings`, {
        method: "PUT",
        body: JSON.stringify({
          vector_rerank_enabled: Boolean(rerankEnabled),
          vector_rerank_method: method,
          vector_rerank_top_k: topK,
        }),
      });
      settingsQuery.setData(res.data.settings);
      toast.toastSuccess("已更新 rerank 配置", res.request_id);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setRerankSaving(false);
    }
  }, [projectId, rerankEnabled, rerankMethod, rerankTopK, settingsQuery, toast]);

  const toggleSource = useCallback((src: VectorSource) => {
    setSources((prev) => (prev.includes(src) ? prev.filter((v) => v !== src) : [...prev, src]));
  }, []);

  const sortedSources = useMemo(
    () => ["worldbook", "outline", "chapter"].filter((s) => sources.includes(s as VectorSource)) as VectorSource[],
    [sources],
  );

  const loadKbs = useCallback(async () => {
    if (!projectId) return;
    setKbLoading(true);
    try {
      const res = await apiJson<{ kbs: KnowledgeBase[] }>(`/api/projects/${projectId}/vector/kbs`);
      const list = Array.isArray(res.data?.kbs) ? res.data.kbs : [];
      setKbs(list);
      setKbDraftById((prev) => {
        const next = { ...prev };
        for (const kb of list) {
          if (!next[kb.kb_id]) next[kb.kb_id] = { name: kb.name, enabled: kb.enabled, weight: kb.weight };
        }
        return next;
      });
      setKbDirtyById((prev) => {
        const next = { ...prev };
        for (const kb of list) {
          if (!(kb.kb_id in next)) next[kb.kb_id] = false;
        }
        return next;
      });
      setSelectedKbIds((prev) => {
        const valid = prev.filter((id) => list.some((kb) => kb.kb_id === id));
        if (valid.length) return valid;
        const enabledIds = list.filter((kb) => kb.enabled).map((kb) => kb.kb_id);
        return enabledIds.length ? enabledIds : list.length ? [list[0].kb_id] : [];
      });
      setKbOrderDirty(false);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setKbLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    if (!projectId) return;
    void loadKbs();
  }, [loadKbs, projectId]);

  const toggleKbSelected = useCallback((kbId: string) => {
    const kid = String(kbId || "").trim();
    if (!kid) return;
    setSelectedKbIds((prev) => (prev.includes(kid) ? prev.filter((v) => v !== kid) : [...prev, kid]));
  }, []);

  const updateKbDraft = useCallback(
    (kbId: string, patch: Partial<Pick<KnowledgeBase, "name" | "enabled" | "weight">>) => {
      const kid = String(kbId || "").trim();
      if (!kid) return;
      setKbDraftById((prev) => ({ ...prev, [kid]: { ...prev[kid], ...patch } }));
      setKbDirtyById((prev) => ({ ...prev, [kid]: true }));
    },
    [],
  );

  const createKb = useCallback(async () => {
    if (!projectId) return;
    const name = kbCreateName.trim();
    if (!name) {
      toast.toastError("KB 名称不能为空");
      return;
    }
    setKbCreateLoading(true);
    try {
      const res = await apiJson<{ kb: KnowledgeBase }>(`/api/projects/${projectId}/vector/kbs`, {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      toast.toastSuccess("已创建 KB", res.request_id);
      setKbCreateName("");
      await loadKbs();
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setKbCreateLoading(false);
    }
  }, [kbCreateName, loadKbs, projectId, toast]);

  const saveKb = useCallback(
    async (kbId: string) => {
      if (!projectId) return;
      const kid = String(kbId || "").trim();
      if (!kid) return;
      const draft = kbDraftById[kid];
      if (!draft) {
        toast.toastError("KB 未加载");
        return;
      }
      setKbSaveLoadingId(kid);
      try {
        const res = await apiJson<{ kb: KnowledgeBase }>(`/api/projects/${projectId}/vector/kbs/${encodeURIComponent(kid)}`, {
          method: "PUT",
          body: JSON.stringify({ name: draft.name, enabled: draft.enabled, weight: draft.weight }),
        });
        setKbs((prev) => prev.map((kb) => (kb.kb_id === kid ? res.data.kb : kb)));
        setKbDraftById((prev) => ({ ...prev, [kid]: { name: res.data.kb.name, enabled: res.data.kb.enabled, weight: res.data.kb.weight } }));
        setKbDirtyById((prev) => ({ ...prev, [kid]: false }));
        toast.toastSuccess("已保存 KB", res.request_id);
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setKbSaveLoadingId(null);
      }
    },
    [kbDraftById, projectId, toast],
  );

  const deleteKb = useCallback(
    async (kbId: string) => {
      if (!projectId) return;
      const kid = String(kbId || "").trim();
      if (!kid) return;
      setKbDeleteLoadingId(kid);
      try {
        const res = await apiJson<{ deleted: boolean }>(`/api/projects/${projectId}/vector/kbs/${encodeURIComponent(kid)}`, {
          method: "DELETE",
        });
        toast.toastSuccess("已删除 KB", res.request_id);
        await loadKbs();
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setKbDeleteLoadingId(null);
      }
    },
    [loadKbs, projectId, toast],
  );

  const saveKbOrder = useCallback(async () => {
    if (!projectId) return;
    const ids = kbs.map((kb) => kb.kb_id);
    if (!ids.length) return;
    setKbLoading(true);
    try {
      const res = await apiJson<{ kbs: KnowledgeBase[] }>(`/api/projects/${projectId}/vector/kbs/reorder`, {
        method: "POST",
        body: JSON.stringify({ kb_ids: ids }),
      });
      setKbs(res.data.kbs ?? []);
      setKbOrderDirty(false);
      toast.toastSuccess("已保存 KB 排序", res.request_id);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setKbLoading(false);
    }
  }, [kbs, projectId, toast]);

  const moveKb = useCallback((fromKbId: string, toKbId: string) => {
    const from = String(fromKbId || "").trim();
    const to = String(toKbId || "").trim();
    if (!from || !to || from === to) return;
    setKbs((prev) => {
      const items = [...prev];
      const fromIdx = items.findIndex((kb) => kb.kb_id === from);
      const toIdx = items.findIndex((kb) => kb.kb_id === to);
      if (fromIdx < 0 || toIdx < 0) return prev;
      const [item] = items.splice(fromIdx, 1);
      items.splice(toIdx, 0, item);
      return items.map((kb, idx) => ({ ...kb, order: idx }));
    });
    setKbOrderDirty(true);
  }, []);

  const runStatus = useCallback(async () => {
    if (!projectId) return;
    if (sortedSources.length === 0) {
      toast.toastError("至少选择一个 source");
      return;
    }
    setStatusLoading(true);
    try {
      const res = await apiJson<{ result: VectorRagResult }>(`/api/projects/${projectId}/vector/status`, {
        method: "POST",
        body: JSON.stringify({ sources: sortedSources }),
      });
      setStatus(res.data?.result ?? null);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setStatusLoading(false);
    }
  }, [projectId, selectedKbIds, sortedSources, toast]);

  useEffect(() => {
    if (!projectId) return;
    if (sortedSources.length === 0) return;
    void runStatus();
  }, [projectId, runStatus, sortedSources]);

  const runIngest = useCallback(async () => {
    if (!projectId) return;
    if (sortedSources.length === 0) {
      toast.toastError("至少选择一个 source");
      return;
    }
    setIngestLoading(true);
    try {
      const res = await apiJson<{ result: unknown }>(`/api/projects/${projectId}/vector/ingest`, {
        method: "POST",
        body: JSON.stringify({ sources: sortedSources, kb_ids: selectedKbIds }),
      });
      setIngestResult(res.data?.result ?? null);
      toast.toastSuccess("ingest 已触发", res.request_id);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setIngestLoading(false);
    }
  }, [projectId, sortedSources, toast]);

  const runRebuild = useCallback(async () => {
    if (!projectId) return;
    if (sortedSources.length === 0) {
      toast.toastError("至少选择一个 source");
      return;
    }
    setRebuildLoading(true);
    try {
      const res = await apiJson<{ result: unknown }>(`/api/projects/${projectId}/vector/rebuild`, {
        method: "POST",
        body: JSON.stringify({ sources: sortedSources, kb_ids: selectedKbIds }),
      });
      const result = res.data?.result ?? null;
      setRebuildResult(result);
      if (result && typeof result === "object") {
        const out = result as Record<string, unknown>;
        const enabled = Boolean(out.enabled);
        const skipped = Boolean(out.skipped);
        const disabledReason = typeof out.disabled_reason === "string" ? out.disabled_reason : null;
        const error = typeof out.error === "string" ? out.error : null;
        if (!enabled || skipped) {
          toast.toastError(`rebuild 未执行：${disabledReason ?? error ?? "unknown"}`, res.request_id);
        } else {
          toast.toastSuccess("rebuild 已触发", res.request_id);
        }
      } else {
        toast.toastSuccess("rebuild 已触发", res.request_id);
      }
      await runStatus();
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setRebuildLoading(false);
    }
  }, [projectId, runStatus, selectedKbIds, sortedSources, toast]);

  const runQuery = useCallback(async () => {
    if (!projectId) return;
    if (sortedSources.length === 0) {
      toast.toastError("至少选择一个 source");
      return;
    }
    setQueryLoading(true);
    try {
      const res = await apiJson<{
        result: VectorRagResult;
        raw_query_text?: unknown;
        normalized_query_text?: unknown;
        preprocess_obs?: unknown;
      }>(`/api/projects/${projectId}/vector/query`, {
        method: "POST",
        body: JSON.stringify({ query_text: queryText, sources: sortedSources, kb_ids: selectedKbIds }),
      });
      setQueryResult(res.data?.result ?? null);
      setQueryRequestId(res.request_id ?? null);
      setRawQueryText(typeof res.data?.raw_query_text === "string" ? res.data.raw_query_text : queryText);
      setNormalizedQueryText(typeof res.data?.normalized_query_text === "string" ? res.data.normalized_query_text : null);
      setQueryPreprocessObs(res.data?.preprocess_obs ?? null);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setQueryLoading(false);
    }
  }, [projectId, queryText, selectedKbIds, sortedSources, toast]);

  const injectionText = (queryResult?.prompt_block?.text_md ?? "").trim();
  const finalChunks = queryResult?.final?.chunks ?? [];

  const groupedFinalChunks = useMemo(() => {
    type GroupChunk = {
      id: string;
      distance: number | null;
      text: string;
      source: string;
      sourceId: string;
      title: string;
      chapterNumber: number | null;
      chunkIndex: number;
      metadata: Record<string, unknown>;
    };

    type ChapterGroup = {
      key: string;
      sourceId: string;
      title: string;
      chapterNumber: number | null;
      chunks: GroupChunk[];
    };

    const bySource = new Map<string, Map<string, ChapterGroup>>();

    for (const raw of finalChunks) {
      const meta = (raw.metadata ?? {}) as Record<string, unknown>;
      const source = typeof meta.source === "string" ? meta.source : "unknown";
      const sourceId = typeof meta.source_id === "string" ? meta.source_id : "";
      const title = typeof meta.title === "string" ? meta.title : "";
      const chapterRaw = meta.chapter_number;
      const chapterNumber = typeof chapterRaw === "number" ? chapterRaw : Number(chapterRaw);
      const chapter = Number.isFinite(chapterNumber) ? chapterNumber : null;
      const chunkRaw = meta.chunk_index;
      const chunkIndex = typeof chunkRaw === "number" ? chunkRaw : Number(chunkRaw);
      const idx = Number.isFinite(chunkIndex) ? chunkIndex : 0;

      const groupKey = `${chapter ?? "-"}::${sourceId || title || raw.id}`;
      const chunk: GroupChunk = {
        id: raw.id,
        distance: typeof raw.distance === "number" && Number.isFinite(raw.distance) ? raw.distance : null,
        text: String(raw.text ?? ""),
        source,
        sourceId,
        title,
        chapterNumber: chapter,
        chunkIndex: idx,
        metadata: meta,
      };

      let sourceMap = bySource.get(source);
      if (!sourceMap) {
        sourceMap = new Map<string, ChapterGroup>();
        bySource.set(source, sourceMap);
      }
      let chapterGroup = sourceMap.get(groupKey);
      if (!chapterGroup) {
        chapterGroup = { key: groupKey, sourceId, title, chapterNumber: chapter, chunks: [] };
        sourceMap.set(groupKey, chapterGroup);
      }
      chapterGroup.chunks.push(chunk);
    }

    const sources = [...bySource.entries()].map(([source, chapters]) => {
      const chapterGroups = [...chapters.values()];
      chapterGroups.sort((a, b) => {
        if (a.chapterNumber != null && b.chapterNumber != null) return a.chapterNumber - b.chapterNumber;
        const at = a.title || a.sourceId || a.key;
        const bt = b.title || b.sourceId || b.key;
        return at.localeCompare(bt);
      });
      for (const g of chapterGroups) {
        g.chunks.sort((a, b) => a.chunkIndex - b.chunkIndex || a.id.localeCompare(b.id));
      }
      return { source, chapterGroups };
    });
    sources.sort((a, b) => a.source.localeCompare(b.source));
    return sources;
  }, [finalChunks]);

  const copyInjectionText = useCallback(async () => {
    if (!injectionText) {
      toast.toastError("没有可复制的注入文本");
      return;
    }
    try {
      await navigator.clipboard.writeText(injectionText);
      toast.toastSuccess("已复制注入文本");
    } catch {
      toast.toastError("复制失败（Clipboard API 不可用）");
    }
  }, [injectionText, toast]);

  const copyQueryDebug = useCallback(async () => {
    if (!projectId) return;
    if (!queryResult) {
      toast.toastError("还没有 query 结果可复制");
      return;
    }
    const payload = {
      request_id: queryRequestId,
      project_id: projectId,
      sources: sortedSources,
      raw_query_text: rawQueryText,
      normalized_query_text: normalizedQueryText,
      preprocess_obs: queryPreprocessObs,
      result: queryResult,
    };
    try {
      await navigator.clipboard.writeText(safeJson(payload));
      toast.toastSuccess("已复制 debug 信息", queryRequestId ?? undefined);
    } catch {
      toast.toastError("复制失败（Clipboard API 不可用）");
    }
  }, [
    normalizedQueryText,
    projectId,
    queryPreprocessObs,
    queryRequestId,
    queryResult,
    rawQueryText,
    sortedSources,
    toast,
  ]);

  return (
    <div className="mx-auto max-w-screen-xl px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-content text-2xl text-ink">Vector RAG 管理</div>
          <div className="mt-1 text-xs text-subtext">ingest / rebuild / status / query（用于排查注入与索引状态）</div>
        </div>
        <div className="flex gap-2">
          <button className="btn btn-secondary" disabled={statusLoading} onClick={() => void runStatus()} type="button">
            {statusLoading ? "加载中…" : "刷新状态"}
          </button>
          <button className="btn btn-secondary" disabled={ingestLoading} onClick={() => void runIngest()} type="button">
            {ingestLoading ? "执行中…" : "Ingest"}
          </button>
          <button
            className={vectorIndexDirty ? "btn btn-primary" : "btn btn-secondary"}
            disabled={rebuildLoading}
            onClick={() => void runRebuild()}
            type="button"
          >
            {rebuildLoading
              ? "执行中…"
              : vectorIndexDirty && vectorEnabled === false
                ? "Rebuild（需配置）"
                : vectorIndexDirty
                  ? "Rebuild（建议）"
                  : "Rebuild"}
          </button>
          {projectId ? (
            <Link className="btn btn-secondary" to={`/projects/${projectId}/settings`}>
              Settings
            </Link>
          ) : null}
        </div>
      </div>

      <div className="mt-3 rounded-atelier border border-border bg-canvas p-3 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-subtext">
            vector_index_dirty: {vectorIndexDirty === null ? "loading…" : String(vectorIndexDirty)} | last_vector_build_at:{" "}
            {lastVectorBuildAt ?? "-"}
            {lastVectorBuildAt ? ` (${formatIsoToLocal(lastVectorBuildAt)})` : ""}
          </div>
          {vectorIndexDirty === null ? (
            <div className="text-subtext">索引状态加载中…</div>
          ) : vectorIndexDirty ? (
            vectorEnabled === false ? (
              <div className="text-ink">
                索引已过期，但向量服务未启用（disabled_reason: {vectorDisabledReason ?? "-"}）。请先在 Settings 配置 embedding，再 rebuild。
              </div>
            ) : (
              <div className="text-ink">索引已过期：建议点击右上角 “Rebuild（建议）” 重新构建。</div>
            )
          ) : (
            <div className="text-subtext">索引为 clean，无需重建。</div>
          )}
        </div>
      </div>

      <div className="mt-6 rounded-atelier border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-medium text-ink">Knowledge Bases</div>
          <div className="flex gap-2">
            <button className="btn btn-secondary" disabled={!projectId || kbLoading} onClick={() => void loadKbs()} type="button">
              {kbLoading ? "加载中…" : "刷新 KB"}
            </button>
            <button className="btn btn-primary" disabled={!projectId || kbLoading || !kbOrderDirty} onClick={() => void saveKbOrder()} type="button">
              保存排序
            </button>
          </div>
        </div>

        <div className="mt-2 text-xs text-subtext">
          selected_kb_ids: {selectedKbIds.length ? selectedKbIds.join(", ") : "（空：query 默认用 enabled 集合）"}
          {queryResult?.kbs?.selected?.length ? (
            <span className="ml-2">
              | query_selected: {queryResult.kbs.selected.join(", ")}
            </span>
          ) : null}
        </div>

        <div className="mt-3 grid gap-2">
          {kbs.length ? (
            kbs.map((kb) => {
              const draft = kbDraftById[kb.kb_id] ?? { name: kb.name, enabled: kb.enabled, weight: kb.weight };
              const dirty = Boolean(kbDirtyById[kb.kb_id]);
              const perKb = queryResult?.kbs?.per_kb?.[kb.kb_id];
              const counts = perKb?.counts;
              const isDragging = kbDragId === kb.kb_id;

              return (
                <div
                  key={kb.kb_id}
                  className={isDragging ? "rounded-atelier border border-border bg-canvas p-3 opacity-80" : "rounded-atelier border border-border bg-canvas p-3"}
                  draggable
                  onDragStart={() => setKbDragId(kb.kb_id)}
                  onDragEnd={() => setKbDragId(null)}
                  onDragOver={(e) => {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = "move";
                  }}
                  onDrop={() => {
                    if (!kbDragId) return;
                    moveKb(kbDragId, kb.kb_id);
                    setKbDragId(null);
                  }}
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-3">
                      <label className="flex items-center gap-2 text-sm text-ink">
                        <input
                          type="checkbox"
                          checked={selectedKbIds.includes(kb.kb_id)}
                          onChange={() => toggleKbSelected(kb.kb_id)}
                          aria-label={`选择 KB ${kb.kb_id}`}
                        />
                        <span className="font-medium">{kb.kb_id}</span>
                      </label>
                      <label className="flex items-center gap-2 text-sm text-ink">
                        <input
                          type="checkbox"
                          checked={Boolean(draft.enabled)}
                          onChange={(e) => updateKbDraft(kb.kb_id, { enabled: e.target.checked })}
                          aria-label={`启用 KB ${kb.kb_id}`}
                        />
                        启用
                      </label>
                      <label className="flex items-center gap-2 text-sm text-ink">
                        <span className="text-xs text-subtext">weight</span>
                        <input
                          className="input w-24"
                          type="number"
                          step="0.1"
                          value={String(draft.weight ?? 1)}
                          onChange={(e) => {
                            const next = Number(e.target.value);
                            if (!Number.isFinite(next)) return;
                            updateKbDraft(kb.kb_id, { weight: next });
                          }}
                          aria-label={`KB 权重 ${kb.kb_id}`}
                        />
                      </label>
                      <label className="flex items-center gap-2 text-sm text-ink">
                        <span className="text-xs text-subtext">name</span>
                        <input
                          className="input w-56"
                          value={draft.name}
                          onChange={(e) => updateKbDraft(kb.kb_id, { name: e.target.value })}
                          aria-label={`KB 名称 ${kb.kb_id}`}
                        />
                      </label>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        className="btn btn-primary"
                        disabled={!projectId || kbSaveLoadingId === kb.kb_id || !dirty}
                        onClick={() => void saveKb(kb.kb_id)}
                        aria-label={`保存 KB ${kb.kb_id}`}
                        type="button"
                      >
                        {kbSaveLoadingId === kb.kb_id ? "保存中…" : dirty ? "保存" : "已保存"}
                      </button>
                      <button
                        className="btn btn-danger"
                        disabled={!projectId || kbDeleteLoadingId === kb.kb_id || Boolean(draft.enabled) || kb.kb_id === "default"}
                        onClick={() => void deleteKb(kb.kb_id)}
                        aria-label={`删除 KB ${kb.kb_id}`}
                        type="button"
                      >
                        {kbDeleteLoadingId === kb.kb_id ? "删除中…" : "删除"}
                      </button>
                    </div>
                  </div>

                  <div className="mt-2 flex flex-wrap gap-3 text-xs text-subtext">
                    <div>order: {kb.order}</div>
                    <div>enabled: {String(Boolean(draft.enabled))}</div>
                    <div>weight: {String(draft.weight)}</div>
                    {counts ? (
                      <div>
                        query_counts: {counts.candidates_total}/{counts.candidates_returned} | final:{counts.final_selected} | dropped:{counts.dropped_total}
                      </div>
                    ) : (
                      <div>query_counts: -</div>
                    )}
                  </div>
                </div>
              );
            })
          ) : (
            <div className="text-xs text-subtext">暂无 KB（将自动创建 default）。</div>
          )}
        </div>

        <div className="mt-4 grid gap-2 sm:grid-cols-4">
          <label className="grid gap-1 sm:col-span-3">
            <span className="text-xs text-subtext">new kb name</span>
            <input
              className="input"
              value={kbCreateName}
              onChange={(e) => setKbCreateName(e.target.value)}
              aria-label="kb_create_name"
              placeholder="My KB"
            />
          </label>
          <div className="flex items-end">
            <button className="btn btn-primary w-full" disabled={!projectId || kbCreateLoading} onClick={() => void createKb()} type="button">
              {kbCreateLoading ? "创建中…" : "创建 KB"}
            </button>
          </div>
        </div>
      </div>

      <div className="mt-6 rounded-atelier border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm font-medium text-ink">Rerank</div>
          <button
            className="btn btn-secondary"
            disabled={!projectId || settingsQuery.loading || busy}
            onClick={() => void settingsQuery.refresh()}
            type="button"
          >
            {settingsQuery.loading ? "加载中…" : "刷新配置"}
          </button>
        </div>
        <div className="mt-2 text-xs text-subtext">
          {settingsQuery.data ? (
            <>
              effective: enabled:{String(settingsQuery.data.vector_rerank_effective_enabled)} | method:
              {settingsQuery.data.vector_rerank_effective_method} | top_k:{settingsQuery.data.vector_rerank_effective_top_k} |
              source:{settingsQuery.data.vector_rerank_effective_source}
            </>
          ) : (
            "（未加载 settings）"
          )}
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <label className="flex items-center gap-2 text-sm text-ink sm:col-span-3">
            <input
              type="checkbox"
              checked={rerankEnabled}
              onChange={(e) => setRerankEnabled(e.target.checked)}
              disabled={rerankSaving || settingsQuery.loading}
            />
            启用 rerank
          </label>
          <label className="grid gap-1 sm:col-span-2">
            <span className="text-xs text-subtext">rerank method</span>
            <select
              className="select"
              value={rerankMethod}
              onChange={(e) => setRerankMethod(e.target.value)}
              disabled={rerankSaving || settingsQuery.loading}
            >
              <option value="auto">auto</option>
              <option value="rapidfuzz_token_set_ratio">rapidfuzz_token_set_ratio</option>
              <option value="token_overlap">token_overlap</option>
            </select>
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-subtext">rerank top_k</span>
            <input
              className="input"
              type="number"
              min={1}
              max={1000}
              value={rerankTopK}
              onChange={(e) => {
                const next = Math.floor(Number(e.target.value));
                if (!Number.isFinite(next)) return;
                setRerankTopK(Math.max(1, Math.min(1000, next)));
              }}
              disabled={rerankSaving || settingsQuery.loading}
            />
          </label>
          <div className="sm:col-span-3">
            <button className="btn btn-primary" disabled={!projectId || rerankSaving || settingsQuery.loading} onClick={() => void applyRerank()} type="button">
              {rerankSaving ? "保存中…" : "应用 rerank 配置"}
            </button>
          </div>
        </div>
      </div>

      <div className="mt-6 rounded-atelier border border-border bg-surface p-4">
        <div className="text-sm font-medium text-ink">Sources</div>
        <div className="mt-3 flex flex-wrap gap-3">
          {(["worldbook", "outline", "chapter"] as const).map((s) => (
            <label key={s} className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" checked={sources.includes(s)} onChange={() => toggleSource(s)} />
              <span>{s}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <section className="rounded-atelier border border-border bg-surface p-4">
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-medium text-ink">Status</div>
            <div className="text-xs text-subtext">
              {status
                ? `enabled:${String(status.enabled)} | backend_preferred:${status.backend_preferred ?? "-"}`
                : null}
            </div>
          </div>
          {status ? (
            <div className="mt-3 text-xs text-subtext">
              <div>disabled_reason: {status.disabled_reason ?? "-"}</div>
              <div>hybrid_enabled: {String(status.hybrid_enabled ?? "-")}</div>
              {normalizeRerankObs(status.rerank) ? (
                <div className="mt-2">rerank: {formatRerankSummary(normalizeRerankObs(status.rerank)!)}</div>
              ) : null}
              {status.counts ? (
                <div className="mt-2">
                  counts: {status.counts.candidates_total}/{status.counts.candidates_returned} | final:
                  {status.counts.final_selected} | dropped:{status.counts.dropped_total}
                </div>
              ) : null}
              <details className="mt-3 rounded-atelier border border-border bg-canvas p-3">
                <summary className="cursor-pointer select-none text-xs">raw status result</summary>
                <pre className="mt-2 max-h-80 overflow-auto text-[11px] leading-4 text-subtext">{safeJson(status)}</pre>
              </details>
            </div>
          ) : (
            <div className="mt-3 text-xs text-subtext">点击“刷新状态”获取 vector_rag_status。</div>
          )}
        </section>

        <section className="rounded-atelier border border-border bg-surface p-4">
          <div className="text-sm font-medium text-ink">Query</div>
          <div className="mt-3">
            <label className="text-xs text-subtext" htmlFor="rag-query-text">
              query_text
            </label>
            <textarea
              id="rag-query-text"
              aria-label="query_text"
              className="mt-1 w-full rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none"
              rows={3}
              value={queryText}
              onChange={(e) => setQueryText(e.target.value)}
              placeholder="dragon"
            />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                className="btn btn-primary"
                disabled={queryLoading || busy}
                onClick={() => void runQuery()}
                type="button"
              >
                {queryLoading ? "查询中…" : "查询"}
              </button>
              <button
                className="btn btn-secondary"
                disabled={!injectionText}
                onClick={() => void copyInjectionText()}
                type="button"
              >
                复制注入文本
              </button>
              <button className="btn btn-secondary" disabled={!queryResult} onClick={() => void copyQueryDebug()} type="button">
                复制 debug
              </button>
              {queryResult?.counts ? (
                <div className="text-xs text-subtext">
                  counts: {queryResult.counts.candidates_total}/{queryResult.counts.candidates_returned} | final:
                  {queryResult.counts.final_selected} | dropped:{queryResult.counts.dropped_total}
                </div>
              ) : null}
            </div>
          </div>

          {queryResult ? (
            <div className="mt-4 text-xs text-subtext">
              <div>
                enabled:{String(queryResult.enabled)} | disabled_reason:{queryResult.disabled_reason ?? "-"} | backend:
                {queryResult.backend ?? "-"}
              </div>
              <div className="mt-1">
                timings_ms:{" "}
                {queryResult.timings_ms
                  ? Object.entries(queryResult.timings_ms)
                      .map(([k, v]) => `${k}:${v}`)
                      .join(" | ")
                  : "-"}
              </div>
              {normalizeRerankObs(queryResult.rerank) ? (
                <div className="mt-1">rerank: {formatRerankSummary(normalizeRerankObs(queryResult.rerank)!)}</div>
              ) : null}
              {queryRequestId ? <div className="mt-1">request_id: {queryRequestId}</div> : null}
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                <div>
                  <div className="text-[11px] text-subtext">raw_query_text</div>
                  <pre className="mt-1 max-h-24 overflow-auto rounded-atelier border border-border bg-canvas p-2 text-[11px] leading-4 text-subtext">
                    {(rawQueryText ?? "").trim() || "（空）"}
                  </pre>
                </div>
                <div>
                  <div className="text-[11px] text-subtext">normalized_query_text</div>
                  <pre className="mt-1 max-h-24 overflow-auto rounded-atelier border border-border bg-canvas p-2 text-[11px] leading-4 text-subtext">
                    {(normalizedQueryText ?? "").trim() || "（空）"}
                  </pre>
                </div>
              </div>

              {queryPreprocessObs ? (
                <details className="mt-2 rounded-atelier border border-border bg-canvas p-3">
                  <summary className="cursor-pointer select-none text-xs">preprocess_obs</summary>
                  <pre className="mt-2 max-h-64 overflow-auto text-[11px] leading-4 text-subtext">
                    {safeJson(queryPreprocessObs)}
                  </pre>
                </details>
              ) : null}

              <div className="mt-2">
                hybrid:{" "}
                {queryResult.hybrid
                  ? `enabled:${String(queryResult.hybrid.enabled)} | counts:${formatHybridCounts(queryResult.hybrid.counts)} | overfilter:${formatOverfilter(queryResult.hybrid.overfilter)}`
                  : "-"}
              </div>

              <div className="mt-1">
                drop_by_reason:{" "}
                {queryResult.counts
                  ? Object.keys(queryResult.counts.dropped_by_reason ?? {}).length
                    ? Object.entries(queryResult.counts.dropped_by_reason)
                        .map(([k, v]) => `${k}:${v}`)
                        .join(" | ")
                    : "-"
                  : "-"}
              </div>

              <details className="mt-3 rounded-atelier border border-border bg-canvas p-3">
                <summary className="cursor-pointer select-none text-xs">注入预览（prompt_block.text_md）</summary>
                <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap text-[11px] leading-4 text-subtext">
                  {injectionText || "(empty)"}
                </pre>
              </details>

              <details className="mt-3 rounded-atelier border border-border bg-canvas p-3">
                <summary className="cursor-pointer select-none text-xs">final.chunks（按 source/chapter 分组）</summary>
                <div className="mt-2 grid gap-2">
                  {finalChunks.length === 0 ? (
                    <div className="text-[11px] text-subtext">（空）</div>
                  ) : (
                    groupedFinalChunks.map((src) => (
                      <details key={src.source} className="rounded-atelier border border-border bg-surface p-2" open>
                        <summary className="cursor-pointer select-none text-xs text-subtext hover:text-ink">
                          source: {src.source}（{src.chapterGroups.reduce((acc, g) => acc + g.chunks.length, 0)}）
                        </summary>
                        <div className="mt-2 grid gap-2">
                          {src.chapterGroups.map((g) => (
                            <details key={g.key} className="rounded-atelier border border-border bg-canvas p-2" open>
                              <summary className="cursor-pointer select-none text-xs text-subtext hover:text-ink">
                                {g.chapterNumber != null ? `chapter ${g.chapterNumber}` : "entry"}
                                {g.title ? ` | ${g.title}` : ""}
                                {g.sourceId ? ` | ${g.sourceId}` : ""}（{g.chunks.length}）
                              </summary>
                              <div className="mt-2 grid gap-2">
                                {g.chunks.map((c) => (
                                  <details key={c.id} className="rounded-atelier border border-border bg-surface p-2">
                                    <summary className="cursor-pointer select-none text-xs text-subtext hover:text-ink">
                                      chunk_index:{c.chunkIndex}
                                      {c.distance != null ? ` | distance:${c.distance.toFixed(4)}` : ""}
                                      {c.title ? ` | ${c.title}` : ""}
                                    </summary>
                                    <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-atelier border border-border bg-canvas p-2 text-[11px] leading-4 text-subtext">
                                      {(c.text || "").trim() || "（空）"}
                                    </pre>
                                    <details className="mt-2">
                                      <summary className="cursor-pointer select-none text-[11px] text-subtext hover:text-ink">
                                        metadata
                                      </summary>
                                      <pre className="mt-2 max-h-48 overflow-auto rounded-atelier border border-border bg-canvas p-2 text-[11px] leading-4 text-subtext">
                                        {safeJson(c.metadata)}
                                      </pre>
                                    </details>
                                  </details>
                                ))}
                              </div>
                            </details>
                          ))}
                        </div>
                      </details>
                    ))
                  )}
                </div>
              </details>

              <details className="mt-3 rounded-atelier border border-border bg-canvas p-3">
                <summary className="cursor-pointer select-none text-xs">raw vector query result</summary>
                <pre className="mt-2 max-h-80 overflow-auto text-[11px] leading-4 text-subtext">
                  {safeJson(queryResult)}
                </pre>
              </details>
            </div>
          ) : (
            <div className="mt-4 text-xs text-subtext">输入 query_text 并点击“查询”获取注入预览。</div>
          )}
        </section>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <section className="rounded-atelier border border-border bg-surface p-4">
          <div className="text-sm font-medium text-ink">Ingest result</div>
          {ingestResult ? (
            <pre className="mt-2 max-h-80 overflow-auto text-[11px] leading-4 text-subtext">
              {safeJson(ingestResult)}
            </pre>
          ) : (
            <div className="mt-2 text-xs text-subtext">点击 “Ingest” 后展示结果。</div>
          )}
        </section>
        <section className="rounded-atelier border border-border bg-surface p-4">
          <div className="text-sm font-medium text-ink">Rebuild result</div>
          {rebuildResult ? (
            <pre className="mt-2 max-h-80 overflow-auto text-[11px] leading-4 text-subtext">
              {safeJson(rebuildResult)}
            </pre>
          ) : (
            <div className="mt-2 text-xs text-subtext">点击 “Rebuild” 后展示结果。</div>
          )}
        </section>
      </div>
    </div>
  );
}
