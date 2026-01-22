import type { VectorRagResult } from "./types";
import { formatRerankSummary, normalizeRerankObs, safeJson } from "./utils";

export function RagStatusPanel(props: { status: VectorRagResult | null }) {
  const { status } = props;

  return (
    <section className="mt-6 rounded-atelier border border-border bg-surface p-4" aria-label="状态 (rag_status_section)">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-ink">状态</div>
        <div className="text-xs text-subtext">
          {status ? `enabled:${String(status.enabled)} | backend_preferred:${status.backend_preferred ?? "-"}` : null}
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
  );
}

