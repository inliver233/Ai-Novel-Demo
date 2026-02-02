import { downloadJson, writeClipboardText } from "./utils";
import { formatHybridCounts, formatOverfilter, formatRerankSummary } from "./vectorRag";
import { useVectorRagQuery } from "./useVectorRagQuery";

type ToastApi = {
  toastSuccess: (message: string, requestId?: string) => void;
  toastError: (message: string, requestId?: string) => void;
};

export function VectorRagDebugPanel(props: {
  projectId?: string;
  toast: ToastApi;
  vector: ReturnType<typeof useVectorRagQuery>;
}) {
  const { projectId, toast, vector } = props;
  const {
    groupedVectorFinalChunks,
    runVectorQuery,
    setVectorQueryText,
    setVectorSources,
    vectorError,
    vectorLoading,
    vectorNormalizedQueryText,
    vectorPreprocessObs,
    vectorQueryText,
    vectorRawQueryText,
    vectorRequestId,
    vectorResult,
    vectorSources,
  } = vector;

  return (
    <div className="panel p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm text-ink">Vector RAG 调试</div>
          <div className="mt-1 text-[11px] text-subtext">
            {vectorResult ? (
              vectorResult.enabled ? (
                <span className="inline-flex rounded-atelier bg-success/10 px-2 py-0.5 text-success">enabled</span>
              ) : (
                <span className="inline-flex rounded-atelier bg-warning/10 px-2 py-0.5 text-warning">
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
                    {vectorResult.counts.candidates_returned} | unique_sources:{vectorResult.counts.unique_sources} |
                    final_selected:{vectorResult.counts.final_selected} | dropped:{vectorResult.counts.dropped_total} |
                    drop_by_reason:
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

            <details className="mt-1">
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
                final.chunks（按 source/chapter 分组，{vectorResult.final.chunks.length}）
              </summary>
              <div className="mt-2 grid gap-2">
                {vectorResult.final.chunks.length === 0 ? (
                  <div className="text-[11px] text-subtext">（空）</div>
                ) : (
                  groupedVectorFinalChunks.map((src) => (
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
                                  <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-atelier border border-border bg-canvas p-2 text-[11px] leading-4 text-subtext">
                                    {(c.text || "").trim() || "（空）"}
                                  </pre>
                                  <details className="mt-2">
                                    <summary className="cursor-pointer select-none text-[11px] text-subtext hover:text-ink">
                                      metadata
                                    </summary>
                                    <pre className="mt-2 max-h-64 overflow-auto rounded-atelier border border-border bg-canvas p-2 text-[11px] leading-4 text-subtext">
                                      {JSON.stringify(c.metadata, null, 2)}
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
                  const chunkIndexRaw = (meta as Record<string, unknown>).chunk_index;
                  const chunkIndex = typeof chunkIndexRaw === "number" ? chunkIndexRaw : Number(chunkIndexRaw);
                  const chunkIndexText = Number.isFinite(chunkIndex) ? `| chunk_index:${chunkIndex}` : "";
                  const snippet = (c.text || "").replaceAll(/\s+/g, " ").trim().slice(0, 220);
                  return (
                    <div key={c.id} className="rounded-atelier border border-border bg-surface p-2 text-xs">
                      <div className="truncate text-ink">
                        {source || "chunk"} {chunkIndexText ? `${chunkIndexText} ` : ""}
                        {title ? `| ${title} ` : ""}
                        {sourceId ? `| ${sourceId}` : ""}
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
  );
}
