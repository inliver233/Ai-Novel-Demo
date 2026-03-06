import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { DebugDetails, DebugPageShell } from "../components/atelier/DebugPageShell";
import { useConfirm } from "../components/ui/confirm";
import { useToast } from "../components/ui/toast";
import { RequestIdBadge } from "../components/ui/RequestIdBadge";
import { useChapterMetaList } from "../hooks/useChapterMetaList";
import { createRequestSeqGuard } from "../lib/requestSeqGuard";
import { ApiError, apiJson } from "../services/apiClient";
import type { ChapterListItem } from "../types";

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

type OpenLoopsResponse = { items: ForeshadowOpenLoop[]; has_more: boolean; returned: number };

type OrderKey = "timeline_desc" | "importance_desc" | "updated_desc";

const OPEN_LOOPS_LIMIT_INITIAL = 80;
const OPEN_LOOPS_LIMIT_STEP = 80;
const OPEN_LOOPS_LIMIT_MAX = 200;

function labelForChapter(chapter: ChapterListItem): string {
  const title = String(chapter.title || "").trim();
  return title ? `第${chapter.number}章：${title}` : `第${chapter.number}章`;
}

export function ForeshadowsPage() {
  const { projectId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const titleId = useId();

  const initialResolvedAtChapterId = useMemo(() => searchParams.get("chapterId") || "", [searchParams]);

  const [loading, setLoading] = useState(false);
  const [requestId, setRequestId] = useState<string | null>(null);
  const [items, setItems] = useState<ForeshadowOpenLoop[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [limit, setLimit] = useState(OPEN_LOOPS_LIMIT_INITIAL);

  const [searchText, setSearchText] = useState("");
  const [queryText, setQueryText] = useState("");
  const [order, setOrder] = useState<OrderKey>("timeline_desc");

  const [resolvedAtChapterId, setResolvedAtChapterId] = useState<string>("");

  const listGuard = useMemo(() => createRequestSeqGuard(), []);
  const chapterListQuery = useChapterMetaList(projectId);
  const chapters = chapterListQuery.chapters as ChapterListItem[];
  const loadingChapters = !chapterListQuery.hasLoaded && chapterListQuery.loading;

  const fetchOpenLoops = useCallback(async () => {
    if (!projectId) return;
    const seq = listGuard.next();
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("limit", String(limit));
      if (queryText.trim()) params.set("q", queryText.trim());
      params.set("order", order);
      const res = await apiJson<OpenLoopsResponse>(
        `/api/projects/${projectId}/story_memories/foreshadows/open_loops?${params.toString()}`,
      );
      if (!listGuard.isLatest(seq)) return;
      setRequestId(res.request_id ?? null);
      setItems(res.data.items ?? []);
      setHasMore(Boolean(res.data.has_more));
    } catch (e) {
      if (!listGuard.isLatest(seq)) return;
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      setRequestId(err.requestId ?? null);
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      if (listGuard.isLatest(seq)) {
        setLoading(false);
      }
    }
  }, [limit, listGuard, order, projectId, queryText, toast]);

  useEffect(() => {
    const guard1 = listGuard;
    return () => {
      guard1.invalidate();
    };
  }, [listGuard]);

  useEffect(() => {
    void fetchOpenLoops();
  }, [fetchOpenLoops]);

  useEffect(() => {
    if (!initialResolvedAtChapterId) return;
    if (!chapters.some((c) => c.id === initialResolvedAtChapterId)) return;
    setResolvedAtChapterId(initialResolvedAtChapterId);
  }, [chapters, initialResolvedAtChapterId]);

  const chapterOptions = useMemo(() => chapters.map((c) => ({ id: c.id, label: labelForChapter(c) })), [chapters]);
  const resolvedChapterLabel = useMemo(() => {
    const found = chapters.find((c) => c.id === resolvedAtChapterId);
    return found ? labelForChapter(found) : null;
  }, [chapters, resolvedAtChapterId]);

  const resolve = useCallback(
    async (foreshadowId: string) => {
      if (!projectId) return;
      const chapterId = resolvedAtChapterId || null;
      const ok = await confirm.confirm({
        title: "标记伏笔已回收？",
        description: chapterId
          ? `将把该伏笔标记为已回收，并记录回收发生在所选章节（${resolvedChapterLabel ?? chapterId}）。`
          : "将把该伏笔标记为已回收，但不记录回收章节。",
        confirmText: "标记回收",
        cancelText: "取消",
      });
      if (!ok) return;

      setLoading(true);
      try {
        const res = await apiJson<{ foreshadow: { id: string } }>(
          `/api/projects/${projectId}/story_memories/foreshadows/${foreshadowId}/resolve`,
          {
            method: "POST",
            body: JSON.stringify({ resolved_at_chapter_id: chapterId }),
          },
        );
        setRequestId(res.request_id ?? null);
        setItems((prev) => prev.filter((it) => it.id !== foreshadowId));
        toast.toastSuccess("已标记回收", res.request_id ?? undefined);
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        setRequestId(err.requestId ?? null);
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setLoading(false);
      }
    },
    [confirm, projectId, resolvedAtChapterId, resolvedChapterLabel, toast],
  );

  const submitQuery = useCallback(() => {
    setLimit(OPEN_LOOPS_LIMIT_INITIAL);
    setQueryText(searchText.trim());
  }, [searchText]);

  return (
    <DebugPageShell
      title="伏笔时间线"
      description={<>列出未回收伏笔（open loops），支持筛选/排序与标记回收（可选关联章节用于回溯）。</>}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <RequestIdBadge requestId={requestId} />
          <button className="btn btn-secondary" onClick={() => void fetchOpenLoops()} disabled={loading} type="button">
            {loading ? "刷新中..." : "刷新"}
          </button>
        </div>
      }
    >
      <DebugDetails title="帮助">
        <div className="grid gap-1 text-xs text-subtext">
          <div>只显示未回收伏笔：已回收（resolved_at_chapter_id != null）不会出现在列表中。</div>
          <div>建议：在回收前选择“回收章节”，用于后续追溯伏笔在哪一章闭环。</div>
        </div>
      </DebugDetails>

      <div className="grid gap-3">
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="grid gap-1">
            <span className="text-xs text-subtext">筛选（标题/内容）</span>
            <input
              className="input"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="输入关键词，回车/点击应用"
              onKeyDown={(e) => {
                if (e.key === "Enter") submitQuery();
              }}
              aria-label="foreshadows_query"
            />
            <div className="flex gap-2">
              <button className="btn btn-secondary" onClick={() => submitQuery()} disabled={loading} type="button">
                应用
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setSearchText("");
                  setQueryText("");
                  setLimit(OPEN_LOOPS_LIMIT_INITIAL);
                }}
                disabled={loading}
                type="button"
              >
                清空
              </button>
            </div>
            {queryText ? <div className="text-[11px] text-subtext">当前筛选：{queryText}</div> : null}
          </label>

          <label className="grid gap-1">
            <span className="text-xs text-subtext">排序</span>
            <select
              className="select"
              value={order}
              onChange={(e) => {
                setLimit(OPEN_LOOPS_LIMIT_INITIAL);
                setOrder((e.target.value as OrderKey) || "timeline_desc");
              }}
              aria-label="foreshadows_order"
            >
              <option value="timeline_desc">按时间线（从新到旧）</option>
              <option value="importance_desc">按重要性（从高到低）</option>
              <option value="updated_desc">按更新时间（从新到旧）</option>
            </select>
            <div className="text-[11px] text-subtext">排序会在服务端执行。</div>
          </label>
        </div>

        <label className="grid gap-1">
          <span className="text-xs text-subtext">回收章节（可选，用于回溯）</span>
          <select
            className="select"
            value={resolvedAtChapterId}
            onChange={(e) => setResolvedAtChapterId(e.target.value)}
            disabled={loadingChapters || chapterOptions.length === 0}
            aria-label="foreshadows_resolve_chapter_id"
          >
            <option value="">不关联章节</option>
            {chapterOptions.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
          {chapterOptions.length === 0 ? (
            <div className="text-[11px] text-subtext">暂无章节（可能尚未创建大纲）。仍可直接回收但不关联章节。</div>
          ) : null}
        </label>
      </div>

      <div className="flex items-center justify-between gap-2 text-xs text-subtext" aria-labelledby={titleId}>
        <div id={titleId}>
          未回收：{items.length}
          {hasMore ? "（已截断）" : ""}
        </div>
        <div className="flex items-center gap-2">
          {hasMore ? (
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => {
                setLimit((prev) =>
                  prev >= OPEN_LOOPS_LIMIT_MAX ? prev : Math.min(OPEN_LOOPS_LIMIT_MAX, prev + OPEN_LOOPS_LIMIT_STEP),
                );
              }}
              disabled={loading || limit >= OPEN_LOOPS_LIMIT_MAX}
              type="button"
              aria-label="foreshadows_load_more"
            >
              {limit >= OPEN_LOOPS_LIMIT_MAX ? "已达上限" : "加载更多"}
            </button>
          ) : null}
          {loading ? <div>加载中...</div> : null}
        </div>
      </div>

      {items.length === 0 ? (
        <div className="rounded-atelier border border-border bg-surface p-4 text-sm text-subtext">暂无未回收伏笔。</div>
      ) : (
        <div className="grid gap-2">
          {items.map((it) => (
            <div key={it.id} className="rounded-atelier border border-border bg-surface p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-ink">{it.title || "（无标题）"}</div>
                  <div className="mt-1 text-[11px] text-subtext">
                    chapter_id:{it.chapter_id || "-"} | score:{String(it.importance_score ?? 0)} | timeline:
                    {String(it.story_timeline ?? 0)}
                    {it.updated_at ? ` | updated:${it.updated_at}` : ""}
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <button
                    className="btn btn-secondary"
                    disabled={!it.chapter_id}
                    onClick={() => navigate(`/projects/${projectId}/writing?chapterId=${it.chapter_id}`)}
                    type="button"
                  >
                    跳转章节
                  </button>
                  <button
                    className="btn btn-secondary"
                    disabled={!it.chapter_id}
                    onClick={() => navigate(`/projects/${projectId}/chapter-analysis?chapterId=${it.chapter_id}`)}
                    type="button"
                  >
                    标注页
                  </button>
                  <button
                    className="btn btn-primary"
                    disabled={loading}
                    onClick={() => void resolve(it.id)}
                    type="button"
                  >
                    标记回收
                  </button>
                </div>
              </div>
              <div className="mt-2 whitespace-pre-wrap text-xs text-subtext">{it.content_preview || "（无摘要）"}</div>
            </div>
          ))}
        </div>
      )}
    </DebugPageShell>
  );
}
