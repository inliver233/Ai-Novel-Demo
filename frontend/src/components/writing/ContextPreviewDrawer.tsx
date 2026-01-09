import { useCallback, useEffect, useMemo, useState } from "react";

import { UI_COPY } from "../../lib/uiCopy";
import { ApiError, apiJson } from "../../services/apiClient";
import { Drawer } from "../ui/Drawer";
import type { MemoryContextPack } from "./types";

type Props = {
  open: boolean;
  onClose: () => void;
  projectId?: string;
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
  const { onClose, open, projectId } = props;
  const [loading, setLoading] = useState(false);
  const [pack, setPack] = useState<MemoryContextPack>(EMPTY_PACK);
  const [error, setError] = useState<{ code: string; message: string; requestId?: string } | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);

  const isEmptyPack = useMemo(() => {
    return (
      Object.keys(pack.worldbook ?? {}).length === 0 &&
      Object.keys(pack.story_memory ?? {}).length === 0 &&
      Object.keys(pack.structured ?? {}).length === 0 &&
      Object.keys(pack.vector_rag ?? {}).length === 0 &&
      Object.keys(pack.graph ?? {}).length === 0 &&
      Object.keys(pack.fractal ?? {}).length === 0 &&
      (pack.logs ?? []).length === 0
    );
  }, [pack]);

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
    void load();
  }, [load, open]);

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
          <button className="btn btn-secondary" onClick={() => void load()} type="button">
            {UI_COPY.writing.contextPreviewRefresh}
          </button>
          <button className="btn btn-secondary" onClick={onClose} type="button">
            {UI_COPY.writing.contextPreviewClose}
          </button>
        </div>
      </div>

      <div className="mt-5 grid gap-4">
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

        {isEmptyPack ? <div className="text-sm text-subtext">{UI_COPY.writing.memoryPackEmpty}</div> : null}

        <div className="grid gap-3">
          {(
            [
              ["worldbook", pack.worldbook],
              ["story_memory", pack.story_memory],
              ["structured", pack.structured],
              ["vector_rag", pack.vector_rag],
              ["graph", pack.graph],
              ["fractal", pack.fractal],
              ["logs", pack.logs],
            ] as const
          ).map(([key, value]) => (
            <details key={key} open>
              <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">{key}</summary>
              <pre className="mt-2 max-h-56 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                {JSON.stringify(value ?? (key === "logs" ? [] : {}), null, 2)}
              </pre>
            </details>
          ))}
        </div>
      </div>
    </Drawer>
  );
}
