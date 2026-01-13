import { useCallback, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { useToast } from "../components/ui/toast";
import { ApiError, apiJson } from "../services/apiClient";

type VectorSource = "worldbook" | "outline" | "chapter";

type VectorRagCounts = {
  candidates_total: number;
  candidates_returned: number;
  unique_sources: number;
  final_selected: number;
  dropped_total: number;
  dropped_by_reason: Record<string, number>;
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
  error?: string;
};

function safeJson(obj: unknown): string {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

export function RagPage() {
  const { projectId } = useParams();
  const toast = useToast();

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

  const busy = statusLoading || ingestLoading || rebuildLoading || queryLoading;

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
