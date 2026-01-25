import { UI_COPY } from "../../lib/uiCopy";
import type { ProjectSettings } from "../../types";
import { safeJson } from "./utils";

export function RagAdvancedDebugPanel(props: {
  projectId: string | undefined;
  debugOpen: boolean;
  setDebugOpen: (open: boolean) => void;
  settingsQuery: { data: ProjectSettings | null | undefined; loading: boolean; refresh: () => void };
  busy: boolean;
  rerankEnabled: boolean;
  setRerankEnabled: (enabled: boolean) => void;
  rerankMethod: string;
  setRerankMethod: (method: string) => void;
  rerankTopK: number;
  setRerankTopK: (topK: number) => void;
  rerankHybridAlpha: number;
  setRerankHybridAlpha: (alpha: number) => void;
  superSortMode: "disabled" | "order" | "weights";
  setSuperSortMode: (mode: "disabled" | "order" | "weights") => void;
  superSortOrderText: string;
  setSuperSortOrderText: (text: string) => void;
  superSortWeights: { worldbook: number; outline: number; chapter: number };
  setSuperSortWeights: (next: { worldbook: number; outline: number; chapter: number }) => void;
  rerankSaving: boolean;
  applyRerank: () => Promise<void>;
  ingestResult: unknown;
  rebuildResult: unknown;
}) {
  const {
    applyRerank,
    busy,
    debugOpen,
    ingestResult,
    projectId,
    rebuildResult,
    rerankEnabled,
    rerankMethod,
    rerankSaving,
    rerankTopK,
    rerankHybridAlpha,
    setRerankHybridAlpha,
    superSortMode,
    setSuperSortMode,
    superSortOrderText,
    setSuperSortOrderText,
    superSortWeights,
    setSuperSortWeights,
    setDebugOpen,
    setRerankEnabled,
    setRerankMethod,
    setRerankTopK,
    settingsQuery,
  } = props;

  return (
    <details
      className="mt-6 rounded-atelier border border-border bg-surface p-4"
      open={debugOpen}
      onToggle={(e) => setDebugOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className="cursor-pointer select-none text-sm font-medium text-ink">
        {UI_COPY.rag.advancedDebugTitle}
      </summary>

      <div className="mt-3 grid gap-4">
        <div className="rounded-atelier border border-border bg-canvas p-3 text-xs text-subtext">
          默认仅展示基础信息；{UI_COPY.rag.rerankTitle} 配置与入库/重建（ingest/rebuild）原始结果放在此处统一折叠。
        </div>

        <div className="rounded-atelier border border-border bg-surface p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-medium text-ink">{UI_COPY.rag.rerankTitle}</div>
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
                {settingsQuery.data.vector_rerank_effective_method} | top_k:
                {settingsQuery.data.vector_rerank_effective_top_k} | source:
                {settingsQuery.data.vector_rerank_effective_source}
              </>
            ) : (
              "（未加载 settings）"
            )}
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <label className="flex items-center gap-2 text-sm text-ink sm:col-span-3">
              <input
                className="checkbox"
                type="checkbox"
                checked={rerankEnabled}
                onChange={(e) => setRerankEnabled(e.target.checked)}
                disabled={rerankSaving || settingsQuery.loading}
              />
              启用重排（rerank）
            </label>
            <label className="grid gap-1 sm:col-span-2">
              <span className="text-xs text-subtext">方法（rerank method）</span>
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
              <span className="text-xs text-subtext">Top K（rerank top_k）</span>
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
            <label className="grid gap-1 sm:col-span-3">
              <span className="text-xs text-subtext">
                hybrid_alpha（0=完全使用 rerank；1=完全保持原始顺序；仅影响 Query 调试请求）
              </span>
              <input
                className="input"
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={rerankHybridAlpha}
                onChange={(e) => {
                  const next = Number(e.target.value);
                  if (!Number.isFinite(next)) return;
                  setRerankHybridAlpha(Math.max(0, Math.min(1, next)));
                }}
                disabled={busy}
              />
            </label>
            <div className="sm:col-span-3">
              <button
                className="btn btn-primary"
                disabled={!projectId || rerankSaving || settingsQuery.loading}
                onClick={() => void applyRerank()}
                type="button"
              >
                {rerankSaving ? "保存中…" : "应用重排配置"}
              </button>
            </div>
          </div>
        </div>

        <div className="rounded-atelier border border-border bg-surface p-4">
          <div className="text-sm font-medium text-ink">Super sort（仅影响 Query 调试请求）</div>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            <label className="grid gap-1 sm:col-span-3">
              <span className="text-xs text-subtext">模式</span>
              <select
                className="select"
                value={superSortMode}
                onChange={(e) => setSuperSortMode(e.target.value as "disabled" | "order" | "weights")}
                disabled={busy}
              >
                <option value="disabled">disabled</option>
                <option value="order">source_order</option>
                <option value="weights">source_weights</option>
              </select>
            </label>

            {superSortMode === "order" ? (
              <label className="grid gap-1 sm:col-span-3">
                <span className="text-xs text-subtext">source_order（逗号分隔）</span>
                <input
                  className="input"
                  value={superSortOrderText}
                  onChange={(e) => setSuperSortOrderText(e.target.value)}
                  placeholder="worldbook,outline,chapter"
                  disabled={busy}
                />
              </label>
            ) : null}

            {superSortMode === "weights" ? (
              <>
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">worldbook</span>
                  <input
                    className="input"
                    type="number"
                    min={0}
                    step={0.1}
                    value={superSortWeights.worldbook}
                    onChange={(e) => {
                      const next = Number(e.target.value);
                      if (!Number.isFinite(next)) return;
                      setSuperSortWeights({ ...superSortWeights, worldbook: Math.max(0, next) });
                    }}
                    disabled={busy}
                  />
                </label>
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">outline</span>
                  <input
                    className="input"
                    type="number"
                    min={0}
                    step={0.1}
                    value={superSortWeights.outline}
                    onChange={(e) => {
                      const next = Number(e.target.value);
                      if (!Number.isFinite(next)) return;
                      setSuperSortWeights({ ...superSortWeights, outline: Math.max(0, next) });
                    }}
                    disabled={busy}
                  />
                </label>
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">chapter</span>
                  <input
                    className="input"
                    type="number"
                    min={0}
                    step={0.1}
                    value={superSortWeights.chapter}
                    onChange={(e) => {
                      const next = Number(e.target.value);
                      if (!Number.isFinite(next)) return;
                      setSuperSortWeights({ ...superSortWeights, chapter: Math.max(0, next) });
                    }}
                    disabled={busy}
                  />
                </label>
              </>
            ) : null}
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <section className="rounded-atelier border border-border bg-surface p-4">
            <div className="text-sm font-medium text-ink">{UI_COPY.rag.ingestResultTitle}</div>
            {ingestResult ? (
              <pre className="mt-2 max-h-80 overflow-auto text-[11px] leading-4 text-subtext">
                {safeJson(ingestResult)}
              </pre>
            ) : (
              <div className="mt-2 text-xs text-subtext">点击“{UI_COPY.rag.ingest}”后展示结果。</div>
            )}
          </section>
          <section className="rounded-atelier border border-border bg-surface p-4">
            <div className="text-sm font-medium text-ink">{UI_COPY.rag.rebuildResultTitle}</div>
            {rebuildResult ? (
              <pre className="mt-2 max-h-80 overflow-auto text-[11px] leading-4 text-subtext">
                {safeJson(rebuildResult)}
              </pre>
            ) : (
              <div className="mt-2 text-xs text-subtext">点击“{UI_COPY.rag.rebuild}”后展示结果。</div>
            )}
          </section>
        </div>
      </div>
    </details>
  );
}
