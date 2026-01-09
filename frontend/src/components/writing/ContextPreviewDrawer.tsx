import { useCallback, useEffect, useMemo, useState } from "react";

import { UI_COPY } from "../../lib/uiCopy";
import { ApiError, apiJson } from "../../services/apiClient";
import { Drawer } from "../ui/Drawer";
import type { MemoryContextPack } from "./types";

type Props = {
  open: boolean;
  onClose: () => void;
  projectId?: string;
  memoryInjectionEnabled: boolean;
  onChangeMemoryInjectionEnabled?: (enabled: boolean) => void;
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

export function ContextPreviewDrawer(props: Props) {
  const { onClose, open, projectId, memoryInjectionEnabled, onChangeMemoryInjectionEnabled } = props;
  const [loading, setLoading] = useState(false);
  const [pack, setPack] = useState<MemoryContextPack>(EMPTY_PACK);
  const [error, setError] = useState<{ code: string; message: string; requestId?: string } | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);

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

  const worldbookPreview = useMemo(() => {
    const raw = (effectivePack.worldbook ?? {}) as Record<string, unknown>;
    const triggered = Array.isArray(raw.triggered) ? raw.triggered : [];
    const textMd = typeof raw.text_md === "string" ? raw.text_md : "";
    const truncated = Boolean(raw.truncated);
    return { triggered, textMd, truncated, raw };
  }, [effectivePack.worldbook]);

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
      panelClassName="h-full w-full max-w-2xl border-l border-border bg-canvas p-6 shadow-sm"
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
      </div>
    </Drawer>
  );
}
