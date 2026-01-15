import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useToast } from "../components/ui/toast";
import { useProjectData } from "../hooks/useProjectData";
import { ApiError, apiJson } from "../services/apiClient";
import type { ProjectSettings } from "../types";

type VectorSource = "worldbook" | "outline" | "chapter";

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

type VectorRagResult = {
  enabled: boolean;
  disabled_reason?: string | null;
  query_text: string;
  filters?: { project_id: string; sources: VectorSource[] };
  timings_ms?: Record<string, number>;
  candidates?: Array<{ id: string; distance?: number; text?: string; metadata?: Record<string, unknown> }>;
  final?: { chunks: unknown[]; text_md: string; truncated: boolean };
  dropped?: Array<{ id?: string; reason: string }>;
  counts?: VectorRagCounts;
  prompt_block?: { identifier: string; role: string; text_md: string };
  backend_preferred?: string;
  hybrid_enabled?: boolean;
  backend?: string;
  rerank?: VectorRerankObs;
  error?: string;
};

function safeJson(obj: unknown): string {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
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

  const [statusLoading, setStatusLoading] = useState(false);
  const [ingestLoading, setIngestLoading] = useState(false);
  const [rebuildLoading, setRebuildLoading] = useState(false);
  const [queryLoading, setQueryLoading] = useState(false);

  const [status, setStatus] = useState<VectorRagResult | null>(null);
  const [ingestResult, setIngestResult] = useState<unknown>(null);
  const [rebuildResult, setRebuildResult] = useState<unknown>(null);
  const [queryResult, setQueryResult] = useState<VectorRagResult | null>(null);

  const busy = statusLoading || ingestLoading || rebuildLoading || queryLoading || rerankSaving;

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
  }, [projectId, sortedSources, toast]);

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
        body: JSON.stringify({ sources: sortedSources }),
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
        body: JSON.stringify({ sources: sortedSources }),
      });
      setRebuildResult(res.data?.result ?? null);
      toast.toastSuccess("rebuild 已触发", res.request_id);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setRebuildLoading(false);
    }
  }, [projectId, sortedSources, toast]);

  const runQuery = useCallback(async () => {
    if (!projectId) return;
    if (sortedSources.length === 0) {
      toast.toastError("至少选择一个 source");
      return;
    }
    setQueryLoading(true);
    try {
      const res = await apiJson<{ result: VectorRagResult }>(`/api/projects/${projectId}/vector/query`, {
        method: "POST",
        body: JSON.stringify({ query_text: queryText, sources: sortedSources }),
      });
      setQueryResult(res.data?.result ?? null);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setQueryLoading(false);
    }
  }, [projectId, queryText, sortedSources, toast]);

  const injectionText = (queryResult?.prompt_block?.text_md ?? "").trim();

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
            className="btn btn-secondary"
            disabled={rebuildLoading}
            onClick={() => void runRebuild()}
            type="button"
          >
            {rebuildLoading ? "执行中…" : "Rebuild"}
          </button>
          {projectId ? (
            <Link className="btn btn-secondary" to={`/projects/${projectId}/settings`}>
              Settings
            </Link>
          ) : null}
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

              <details className="mt-3 rounded-atelier border border-border bg-canvas p-3">
                <summary className="cursor-pointer select-none text-xs">注入预览（prompt_block.text_md）</summary>
                <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap text-[11px] leading-4 text-subtext">
                  {injectionText || "(empty)"}
                </pre>
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
