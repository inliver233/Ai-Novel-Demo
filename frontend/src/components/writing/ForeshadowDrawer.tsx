import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { UI_COPY } from "../../lib/uiCopy";
import { ApiError, apiJson } from "../../services/apiClient";
import { Drawer } from "../ui/Drawer";
import { useConfirm } from "../ui/confirm";
import { useToast } from "../ui/toast";

type ForeshadowOpenLoop = {
  id: string;
  chapter_id: string | null;
  memory_type: string;
  title: string | null;
  importance_score: number;
  story_timeline: number;
  is_foreshadow: boolean;
  resolved_at_chapter_id: string | null;
  content_preview: string;
  updated_at: string | null;
};

export function ForeshadowDrawer(props: {
  open: boolean;
  onClose: () => void;
  projectId?: string;
  activeChapterId?: string;
}) {
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const titleId = useId();
  const copy = UI_COPY.writing.foreshadowDrawer;

  const [loading, setLoading] = useState(false);
  const [requestId, setRequestId] = useState<string | null>(null);
  const [items, setItems] = useState<ForeshadowOpenLoop[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [filterText, setFilterText] = useState("");

  const fetchOpenLoops = useCallback(async () => {
    if (!props.projectId) return;
    setLoading(true);
    try {
      const res = await apiJson<{ items: ForeshadowOpenLoop[]; has_more: boolean; returned: number }>(
        `/api/projects/${props.projectId}/story_memories/foreshadows/open_loops?limit=80`,
      );
      setRequestId(res.request_id ?? null);
      setItems(res.data.items ?? []);
      setHasMore(Boolean(res.data.has_more));
    } catch (e) {
      const err = e as ApiError;
      setRequestId(err.requestId ?? null);
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setLoading(false);
    }
  }, [props.projectId, toast]);

  useEffect(() => {
    if (!props.open) return;
    void fetchOpenLoops();
  }, [fetchOpenLoops, props.open]);

  const filtered = useMemo(() => {
    const q = filterText.trim().toLowerCase();
    if (!q) return items;
    const tokens = q.split(/\s+/g).filter(Boolean);
    return items.filter((it) => {
      const title = String(it.title ?? "").toLowerCase();
      const preview = String(it.content_preview ?? "").toLowerCase();
      const chapterId = String(it.chapter_id ?? "").toLowerCase();
      return tokens.every((t) => title.includes(t) || preview.includes(t) || chapterId.includes(t));
    });
  }, [filterText, items]);

  const resolve = useCallback(
    async (foreshadowId: string) => {
      if (!props.projectId) return;
      const ok = await confirm.confirm({
        title: copy.resolveConfirmTitle,
        description: props.activeChapterId
          ? "将把该伏笔标记为已回收，并记录回收发生在当前章节（用于回溯）。"
          : "将把该伏笔标记为已回收，但不记录回收章节（因为当前未选中章节）。",
        confirmText: copy.resolveConfirmText,
        cancelText: copy.resolveCancelText,
      });
      if (!ok) return;

      setLoading(true);
      try {
        const res = await apiJson<{ foreshadow: { id: string } }>(
          `/api/projects/${props.projectId}/story_memories/foreshadows/${foreshadowId}/resolve`,
          {
            method: "POST",
            body: JSON.stringify({ resolved_at_chapter_id: props.activeChapterId ?? null }),
          },
        );
        setRequestId(res.request_id ?? null);
        setItems((prev) => prev.filter((it) => it.id !== foreshadowId));
        toast.toastSuccess(copy.resolveDoneToast, res.request_id ?? undefined);
      } catch (e) {
        const err = e as ApiError;
        setRequestId(err.requestId ?? null);
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setLoading(false);
      }
    },
    [confirm, copy, props.activeChapterId, props.projectId, toast],
  );

  return (
    <Drawer
      open={props.open}
      onClose={props.onClose}
      ariaLabelledBy={titleId}
      panelClassName="h-full w-full max-w-xl border-l border-border bg-canvas p-6 shadow-sm"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-content text-2xl text-ink" id={titleId}>
            {copy.title}
          </div>
          <div className="mt-1 text-xs text-subtext">
            {copy.openCountLabel}：{filtered.length}
            {filtered.length === items.length ? "" : ` / ${items.length}`}
            {hasMore ? copy.hasMoreTag : ""}
            {requestId ? (
              <span className="ml-2">
                {copy.requestIdPrefix} {requestId}
              </span>
            ) : null}
          </div>
          <div className="mt-1 text-xs text-subtext">{copy.openOnlyHint}</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn btn-secondary"
            disabled={!props.projectId || loading}
            onClick={() => void fetchOpenLoops()}
            type="button"
          >
            {loading ? copy.refreshing : copy.refresh}
          </button>
          <button className="btn btn-secondary" aria-label="关闭" onClick={props.onClose} type="button">
            关闭
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-3">
        <label className="grid gap-1">
          <span className="text-xs text-subtext">{copy.filterLabel}</span>
          <input
            className="input"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder={copy.filterPlaceholder}
          />
          <div className="text-[11px] text-subtext">{copy.filterHint}</div>
        </label>

        {filtered.length === 0 ? (
          <div className="text-sm text-subtext">{copy.empty}</div>
        ) : (
          <div className="grid gap-2">
            {filtered.map((it) => (
              <div key={it.id} className="rounded-atelier border border-border bg-surface p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-ink">{it.title || copy.noTitle}</div>
                    <div className="mt-1 text-[11px] text-subtext">
                      {copy.metaChapterId}:{it.chapter_id || "-"} | {copy.metaScore}:{String(it.importance_score ?? 0)}{" "}
                      | {copy.metaTimeline}:{String(it.story_timeline ?? 0)}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <button
                      className="btn btn-secondary"
                      disabled={!it.chapter_id}
                      onClick={() => navigate(`/projects/${props.projectId}/writing?chapterId=${it.chapter_id}`)}
                      type="button"
                    >
                      {copy.jumpChapter}
                    </button>
                    <button
                      className="btn btn-secondary"
                      disabled={!it.chapter_id}
                      onClick={() =>
                        navigate(`/projects/${props.projectId}/chapter-analysis?chapterId=${it.chapter_id}`)
                      }
                      type="button"
                    >
                      {copy.annotatePage}
                    </button>
                    <button
                      className="btn btn-primary"
                      disabled={loading}
                      onClick={() => void resolve(it.id)}
                      type="button"
                    >
                      {copy.resolve}
                    </button>
                  </div>
                </div>
                <div className="mt-2 whitespace-pre-wrap text-xs text-subtext">
                  {it.content_preview || copy.contentEmpty}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Drawer>
  );
}
