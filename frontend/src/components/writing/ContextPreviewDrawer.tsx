import { useCallback, useEffect, useMemo, useState } from "react";

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
};

type VectorSource = "worldbook" | "outline" | "chapter";

type VectorCandidate = {
  id: string;
  distance: number;
  text: string;
  metadata: Record<string, unknown>;
};

type VectorRagQueryResult = {
  enabled: boolean;
  disabled_reason: string | null;
  query_text: string;
  filters: { project_id: string; sources: VectorSource[] };
  timings_ms: Record<string, number>;
  candidates: VectorCandidate[];
  final: { chunks: VectorCandidate[]; text_md: string; truncated: boolean };
  dropped: Array<{ id?: string; reason: string }>;
  prompt_block: { identifier: string; role: string; text_md: string };
  error?: string;
};

type MemoryContextPackLogItem = {
  section: string;
  enabled: boolean;
  disabled_reason: string | null;
  note: string | null;
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
      const metadata = typeof cc.metadata === "object" && cc.metadata !== null ? (cc.metadata as Record<string, unknown>) : {};
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
      const metadata = typeof cc.metadata === "object" && cc.metadata !== null ? (cc.metadata as Record<string, unknown>) : {};
      if (!id) return null;
      if (!Number.isFinite(distance)) return null;
      return { id, distance, text, metadata };
    })
    .filter((v): v is VectorCandidate => Boolean(v));

  const timings = typeof o.timings_ms === "object" && o.timings_ms !== null ? (o.timings_ms as Record<string, unknown>) : {};
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
  URL.revokeObjectURL(url);
}

export function ContextPreviewDrawer(props: Props) {
  const { onClose, open, projectId, memoryInjectionEnabled, onChangeMemoryInjectionEnabled } = props;
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [pack, setPack] = useState<MemoryContextPack>(EMPTY_PACK);
  const [error, setError] = useState<{ code: string; message: string; requestId?: string } | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);

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
  const [vectorError, setVectorError] = useState<{ code: string; message: string; requestId?: string } | null>(null);

  const effectivePack = useMemo(() => (memoryInjectionEnabled ? pack : EMPTY_PACK), [memoryInjectionEnabled, pack]);

  const isEmptyPack = useMemo(() => {
    return (
      Object.keys(effectivePack.worldbook ?? {}).length === 0 &&
      Object.keys(effectivePack.story_memory ?? {}).length === 0 &&
      Object.keys(effectivePack.structured ?? {}).length === 0 &&
      Object.keys(effectivePack.vector_rag ?? {}).length === 0 &&
      Object.keys(effectivePack.graph ?? {}).length === 0 &&
      Object.keys(effectivePack.fractal ?? {}).length === 0 &&
      (effectivePack.logs ?? []).length === 0
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
      const res = await apiJson<{ result: unknown }>(`/api/projects/${projectId}/vector/query`, {
        method: "POST",
        body: JSON.stringify({ query_text: vectorQueryText, sources: selectedVectorSources }),
      });
      const normalized = normalizeVectorResult(res.data?.result);
      if (!normalized) throw new ApiError({ code: "BAD_RESPONSE", message: "响应格式错误", requestId: res.request_id, status: 200 });
      setVectorResult(normalized);
      setVectorRequestId(res.request_id ?? null);
    } catch (e) {
      if (e instanceof ApiError) {
        setVectorError({ code: e.code, message: e.message, requestId: e.requestId });
      } else {
        setVectorError({ code: "UNKNOWN", message: "查询失败" });
      }
    } finally {
      setVectorLoading(false);
    }
  }, [projectId, selectedVectorSources, toast, vectorQueryText]);

  const load = useCallback(async () => {
    if (!projectId) {
      setError({ code: "NO_PROJECT", message: UI_COPY.writing.contextPreviewMissingProjectId });
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await apiJson<MemoryContextPack>(`/api/projects/${projectId}/memory/retrieve`);
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
  }, [projectId]);

  useEffect(() => {
    if (!open) return;
    if (!memoryInjectionEnabled) return;
    void load();
  }, [load, memoryInjectionEnabled, open]);

  useEffect(() => {
    if (!open) return;
    if (memoryInjectionEnabled) return;
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
              <button className="btn btn-secondary" disabled={!projectId || vectorLoading} onClick={() => void runVectorQuery()} type="button">
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
                    candidates: {vectorResult.candidates.length} | final_chunks: {vectorResult.final.chunks.length} | dropped:{" "}
                    {vectorResult.dropped.length}
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
                          <div className="mt-1 text-subtext">{snippet || "（空）"}{snippet.length >= 220 ? "…" : ""}</div>
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
              <div className="text-sm text-subtext">提示：当前环境缺 embedding/chroma 时会返回 disabled_reason，但结构仍可用于排查。</div>
            )}
          </div>
        </div>
      </div>
    </Drawer>
  );
}
