import { useCallback, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { DebugDetails, DebugPageShell } from "../components/atelier/DebugPageShell";
import { useToast } from "../components/ui/toast";
import { copyText } from "../lib/copyText";
import { UI_COPY } from "../lib/uiCopy";
import { ApiError, apiJson } from "../services/apiClient";

type SearchItem = {
  source_type: string;
  source_id: string;
  title: string;
  snippet: string;
  jump_url: string | null;
};

type SearchQueryResponse = {
  items: SearchItem[];
  next_offset: number | null;
  mode?: string;
  fts_enabled?: boolean;
};

const SOURCE_OPTIONS: Array<{ key: string; label: string }> = [
  { key: "chapter", label: UI_COPY.search.sourceLabels.chapter },
  { key: "outline", label: UI_COPY.search.sourceLabels.outline },
  { key: "worldbook_entry", label: UI_COPY.search.sourceLabels.worldbookEntry },
  { key: "character", label: UI_COPY.search.sourceLabels.character },
  { key: "story_memory", label: UI_COPY.search.sourceLabels.storyMemory },
];

function dedupeItems(items: SearchItem[]): SearchItem[] {
  const out: SearchItem[] = [];
  const seen = new Set<string>();
  for (const it of items) {
    const key = `${it.source_type}:${it.source_id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(it);
  }
  return out;
}

export function SearchPage() {
  const { projectId } = useParams();
  const toast = useToast();
  const navigate = useNavigate();

  const [query, setQuery] = useState("");
  const [sourcesState, setSourcesState] = useState<Record<string, boolean>>({});

  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<SearchItem[]>([]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [debug, setDebug] = useState<{ mode?: string; fts_enabled?: boolean } | null>(null);

  const selectedSources = useMemo(() => {
    const selected = SOURCE_OPTIONS.filter((s) => sourcesState[s.key]).map((s) => s.key);
    return selected.length ? selected : null;
  }, [sourcesState]);

  const runQuery = useCallback(
    async (opts?: { append?: boolean }) => {
      if (!projectId) return;
      const append = Boolean(opts?.append);
      const q = query.trim();
      if (!q) return;
      if (loading) return;
      setLoading(true);
      try {
        const offset = append ? (nextOffset ?? 0) : 0;
        const res = await apiJson<SearchQueryResponse>(`/api/projects/${projectId}/search/query`, {
          method: "POST",
          body: JSON.stringify({
            q,
            sources: selectedSources ?? [],
            limit: 20,
            offset,
          }),
        });

        const data = res.data;
        const nextItems = Array.isArray(data.items) ? data.items : [];
        setItems((prev) => (append ? dedupeItems([...prev, ...nextItems]) : dedupeItems(nextItems)));
        setNextOffset(typeof data.next_offset === "number" ? data.next_offset : null);
        setDebug({ mode: data.mode, fts_enabled: data.fts_enabled });
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setLoading(false);
      }
    },
    [loading, nextOffset, projectId, query, selectedSources, toast],
  );

  const clear = useCallback(() => {
    setQuery("");
    setItems([]);
    setNextOffset(null);
    setDebug(null);
  }, []);

  const toggleSource = useCallback((key: string) => {
    setSourcesState((prev) => ({ ...prev, [key]: !prev[key] }));
  }, []);

  const canJump = useCallback((it: SearchItem) => {
    return (
      it.source_type === "chapter" ||
      it.source_type === "outline" ||
      it.source_type === "worldbook_entry" ||
      it.source_type === "character"
    );
  }, []);

  const jump = useCallback(
    (it: SearchItem) => {
      if (!projectId) return;
      if (it.source_type === "chapter") {
        navigate(`/projects/${projectId}/writing?chapterId=${encodeURIComponent(it.source_id)}`);
        return;
      }
      if (it.source_type === "outline") {
        navigate(`/projects/${projectId}/outline`);
        return;
      }
      if (it.source_type === "worldbook_entry") {
        const key = `ainovel:worldbook:filter:${projectId}`;
        let sortMode = "updated_desc";
        try {
          const raw = localStorage.getItem(key) || "";
          if (raw) {
            const prev = JSON.parse(raw) as { sortMode?: unknown } | null;
            if (prev && typeof prev === "object" && typeof prev.sortMode === "string") sortMode = prev.sortMode;
          }
        } catch {
          // ignore
        }
        try {
          localStorage.setItem(key, JSON.stringify({ searchText: it.title || query.trim(), sortMode }));
        } catch {
          // ignore
        }
        navigate(`/projects/${projectId}/worldbook`);
        return;
      }
      if (it.source_type === "character") {
        navigate(`/projects/${projectId}/characters`);
      }
    },
    [navigate, projectId, query],
  );

  const copySourceId = useCallback(
    async (it: SearchItem) => {
      const ok = await copyText(it.source_id, { title: UI_COPY.search.copyIdFailTitle });
      if (ok) toast.toastSuccess(UI_COPY.search.copiedId);
      else toast.toastWarning(UI_COPY.search.copyFailedToast);
    },
    [toast],
  );

  return (
    <DebugPageShell
      title={UI_COPY.search.title}
      description={UI_COPY.search.subtitle}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn btn-secondary"
            aria-label="search_clear"
            disabled={loading && Boolean(query.trim())}
            onClick={clear}
          >
            {UI_COPY.search.clear}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            aria-label="search_submit"
            disabled={!projectId || !query.trim() || loading}
            onClick={() => void runQuery({ append: false })}
          >
            {loading ? UI_COPY.common.loading : UI_COPY.search.search}
          </button>
        </div>
      }
    >
      <div className="grid gap-3">
        <div className="grid gap-2">
          <input
            className="input w-full"
            aria-label="search_query"
            placeholder={UI_COPY.search.queryPlaceholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void runQuery({ append: false });
            }}
          />

          <div className="flex flex-wrap items-center gap-3">
            <div className="text-xs text-subtext">{UI_COPY.search.sourcesTitle}</div>
            {SOURCE_OPTIONS.map((s) => (
              <label key={s.key} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  aria-label={`search_source_${s.key}`}
                  name={`search_source_${s.key}`}
                  className="checkbox"
                  checked={Boolean(sourcesState[s.key])}
                  onChange={() => toggleSource(s.key)}
                />
                <span>{s.label}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="grid gap-2" aria-label="search_results">
          {!items.length ? (
            <div className="text-sm text-subtext">{UI_COPY.search.emptyHint}</div>
          ) : (
            items.map((it) => (
              <div key={`${it.source_type}:${it.source_id}`} className="panel p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-ink">{it.title || it.source_id}</div>
                    <div className="mt-0.5 text-xs text-subtext">
                      <span className="font-mono">{it.source_type}</span>
                      <span className="mx-2">·</span>
                      <span className="font-mono">{it.source_id}</span>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      aria-label="search_copy_id"
                      onClick={() => void copySourceId(it)}
                    >
                      {UI_COPY.search.copyId}
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary"
                      aria-label="search_jump"
                      disabled={!canJump(it)}
                      onClick={() => jump(it)}
                    >
                      {UI_COPY.search.jump}
                    </button>
                  </div>
                </div>
                {it.snippet ? (
                  <div className="mt-2 whitespace-pre-wrap break-words rounded-atelier border border-border bg-canvas px-3 py-2 text-xs text-ink">
                    {it.snippet}
                  </div>
                ) : null}
              </div>
            ))
          )}
        </div>

        {nextOffset !== null ? (
          <div className="flex justify-center">
            <button
              type="button"
              className="btn btn-secondary"
              aria-label="search_load_more"
              disabled={loading}
              onClick={() => void runQuery({ append: true })}
            >
              {UI_COPY.search.loadMore}
            </button>
          </div>
        ) : null}

        <DebugDetails title={UI_COPY.search.debugTitle} defaultOpen={false}>
          <pre className="overflow-auto whitespace-pre-wrap break-words text-xs text-subtext">
            {JSON.stringify({ projectId, selectedSources, nextOffset, debug }, null, 2)}
          </pre>
        </DebugDetails>
      </div>
    </DebugPageShell>
  );
}
