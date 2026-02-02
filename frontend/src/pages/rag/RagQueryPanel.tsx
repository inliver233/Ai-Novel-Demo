import { useCallback, useMemo } from "react";

import { useToast } from "../../components/ui/toast";
import { copyText } from "../../lib/copyText";
import { UI_COPY } from "../../lib/uiCopy";
import { EMPTY_CHUNKS } from "./types";
import type { VectorRagResult, VectorSource } from "./types";
import {
  formatHybridCounts,
  formatOverfilter,
  formatRerankSummary,
  formatSuperSortSummary,
  normalizeRerankObs,
  normalizeSuperSortObs,
  safeJson,
} from "./utils";

const SOURCE_LABEL: Record<VectorSource, string> = {
  worldbook: "世界书（worldbook）",
  outline: "大纲（outline）",
  chapter: "章节（chapter）",
  story_memory: "故事记忆（story_memory）",
};

export function RagQueryPanel(props: {
  busy: boolean;
  sources: VectorSource[];
  toggleSource: (src: VectorSource) => void;
  queryText: string;
  setQueryText: (text: string) => void;
  queryLoading: boolean;
  runQuery: () => Promise<void>;
  projectId: string | undefined;
  sortedSources: VectorSource[];
  queryResult: VectorRagResult | null;
  queryRequestId: string | null;
  rawQueryText: string | null;
  normalizedQueryText: string | null;
  queryPreprocessObs: unknown;
}) {
  const {
    busy,
    normalizedQueryText,
    projectId,
    queryLoading,
    queryPreprocessObs,
    queryRequestId,
    queryResult,
    queryText,
    rawQueryText,
    runQuery,
    setQueryText,
    sortedSources,
    sources,
    toggleSource,
  } = props;

  const toast = useToast();

  const injectionText = (queryResult?.prompt_block?.text_md ?? "").trim();
  const finalChunks = queryResult?.final?.chunks ?? EMPTY_CHUNKS;

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
    const ok = await copyText(injectionText, { title: "复制失败：请手动复制注入文本" });
    if (ok) toast.toastSuccess("已复制注入文本");
    else toast.toastWarning("自动复制失败：已打开手动复制弹窗。");
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
    const ok = await copyText(safeJson(payload), { title: "复制失败：请手动复制排障信息" });
    if (ok) toast.toastSuccess("已复制 debug 信息", queryRequestId ?? undefined);
    else toast.toastWarning("自动复制失败：已打开手动复制弹窗。");
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
    <>
      <div className="mt-6 rounded-atelier border border-border bg-surface p-4">
        <div className="text-sm font-medium text-ink">{UI_COPY.rag.sourcesTitle}</div>
        <div className="mt-3 flex flex-wrap gap-3">
          {(["worldbook", "outline", "chapter", "story_memory"] as const).map((s) => (
            <label key={s} className="flex items-center gap-2 text-sm text-ink">
              <input
                className="checkbox"
                type="checkbox"
                checked={sources.includes(s)}
                onChange={() => toggleSource(s)}
              />
              <span>{SOURCE_LABEL[s]}</span>
            </label>
          ))}
        </div>
      </div>

      <section className="mt-6 rounded-atelier border border-border bg-surface p-4">
        <div className="text-sm font-medium text-ink">{UI_COPY.rag.queryTitle}</div>
        <div className="mt-3">
          <label className="text-xs text-subtext" htmlFor="rag-query-text">
            查询文本（query_text）
          </label>
          <textarea
            id="rag-query-text"
            aria-label="query_text"
            className="textarea mt-1"
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
              aria-label="查询 (rag_query)"
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
            <button
              className="btn btn-secondary"
              disabled={!queryResult}
              onClick={() => void copyQueryDebug()}
              type="button"
            >
              复制排障信息
            </button>
            {queryResult?.counts ? (
              <div className="text-xs text-subtext">
                counts: {queryResult.counts.candidates_total}/{queryResult.counts.candidates_returned} | final:
                {queryResult.counts.final_selected} | dropped:{queryResult.counts.dropped_total}
              </div>
            ) : null}
          </div>
        </div>
      </section>

      <section className="mt-6 rounded-atelier border border-border bg-surface p-4">
        <div className="text-sm font-medium text-ink">{UI_COPY.rag.injectionTitle}</div>
        {queryResult ? (
          <div className="mt-3 text-xs text-subtext">
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
            {normalizeSuperSortObs(queryResult.super_sort) ? (
              <div className="mt-1">
                super_sort: {formatSuperSortSummary(normalizeSuperSortObs(queryResult.super_sort)!)}
              </div>
            ) : null}
            {queryRequestId ? (
              <div className="mt-1 flex items-center gap-2">
                <span className="truncate">
                  {UI_COPY.common.requestIdLabel}: <span className="font-mono">{queryRequestId}</span>
                </span>
                <button
                  className="btn btn-ghost px-2 py-1 text-xs"
                  onClick={async () => {
                    await copyText(queryRequestId ?? "", { title: "复制失败：请手动复制 request_id" });
                  }}
                  type="button"
                >
                  {UI_COPY.common.copy}
                </button>
              </div>
            ) : null}

            <div className="mt-2 grid gap-3 sm:grid-cols-2">
              <div>
                <div className="text-[11px] text-subtext">原始查询（raw_query_text）</div>
                <pre className="mt-1 max-h-24 overflow-auto rounded-atelier border border-border bg-canvas p-2 text-[11px] leading-4 text-subtext">
                  {(rawQueryText ?? "").trim() || "（空）"}
                </pre>
              </div>
              <div>
                <div className="text-[11px] text-subtext">规范化查询（normalized_query_text）</div>
                <pre className="mt-1 max-h-24 overflow-auto rounded-atelier border border-border bg-canvas p-2 text-[11px] leading-4 text-subtext">
                  {(normalizedQueryText ?? "").trim() || "（空）"}
                </pre>
              </div>
            </div>

            {queryPreprocessObs ? (
              <details className="mt-2 rounded-atelier border border-border bg-canvas p-3">
                <summary className="cursor-pointer select-none text-xs">预处理信息（preprocess_obs）</summary>
                <pre className="mt-2 max-h-64 overflow-auto text-[11px] leading-4 text-subtext">
                  {safeJson(queryPreprocessObs)}
                </pre>
              </details>
            ) : null}

            {queryResult.rerank ? (
              <details className="mt-2 rounded-atelier border border-border bg-canvas p-3">
                <summary className="cursor-pointer select-none text-xs">rerank_obs</summary>
                <pre className="mt-2 max-h-64 overflow-auto text-[11px] leading-4 text-subtext">
                  {safeJson(queryResult.rerank)}
                </pre>
              </details>
            ) : null}

            {queryResult.super_sort ? (
              <details className="mt-2 rounded-atelier border border-border bg-canvas p-3">
                <summary className="cursor-pointer select-none text-xs">super_sort_obs</summary>
                <pre className="mt-2 max-h-64 overflow-auto text-[11px] leading-4 text-subtext">
                  {safeJson(queryResult.super_sort)}
                </pre>
              </details>
            ) : null}

            <div className="mt-2">
              混合检索（hybrid）:{" "}
              {queryResult.hybrid
                ? `enabled:${String(queryResult.hybrid.enabled)} | counts:${formatHybridCounts(queryResult.hybrid.counts)} | overfilter:${formatOverfilter(
                    queryResult.hybrid.overfilter,
                  )}`
                : "-"}
            </div>

            <div className="mt-1">
              丢弃原因（drop_by_reason）:{" "}
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
              <div className="mt-2 grid max-h-96 gap-2 overflow-auto overscroll-contain pr-1">
                {finalChunks.length === 0 ? (
                  <div className="text-[11px] text-subtext">（空）</div>
                ) : (
                  groupedFinalChunks.map((src) => (
                    <details key={src.source} className="rounded-atelier border border-border bg-surface p-2">
                      <summary className="cursor-pointer select-none text-xs text-subtext hover:text-ink">
                        source: {src.source}（{src.chapterGroups.reduce((acc, g) => acc + g.chunks.length, 0)}）
                      </summary>
                      <div className="mt-2 grid gap-2">
                        {src.chapterGroups.map((g) => (
                          <details key={g.key} className="rounded-atelier border border-border bg-canvas p-2">
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
                                  <pre className="mt-2 whitespace-pre-wrap rounded-atelier border border-border bg-canvas p-2 text-[11px] leading-4 text-subtext">
                                    {(c.text || "").trim() || "（空）"}
                                  </pre>
                                  <details className="mt-2">
                                    <summary className="cursor-pointer select-none text-[11px] text-subtext hover:text-ink">
                                      metadata
                                    </summary>
                                    <pre className="mt-2 whitespace-pre-wrap rounded-atelier border border-border bg-canvas p-2 text-[11px] leading-4 text-subtext">
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
          <div className="mt-3 text-xs text-subtext">输入 query_text 并点击“查询”获取注入预览。</div>
        )}
      </section>
    </>
  );
}
