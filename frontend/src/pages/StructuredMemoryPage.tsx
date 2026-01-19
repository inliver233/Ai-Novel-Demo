import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { useToast } from "../components/ui/toast";
import { MemoryUpdateDrawer } from "../components/writing/MemoryUpdateDrawer";
import { useProjectData } from "../hooks/useProjectData";
import { ApiError, apiJson } from "../services/apiClient";

type TableName = "entities" | "relations" | "events" | "foreshadows" | "evidence";

type Counts = Record<TableName, number>;

type EntityRow = {
  id: string;
  entity_type: string;
  name: string;
  summary_md?: string | null;
  deleted_at?: string | null;
  updated_at?: string | null;
};

type RelationRow = {
  id: string;
  relation_type: string;
  from_entity_id: string;
  to_entity_id: string;
  description_md?: string | null;
  deleted_at?: string | null;
  updated_at?: string | null;
};

type EventRow = {
  id: string;
  chapter_id?: string | null;
  event_type: string;
  title?: string | null;
  content_md?: string | null;
  deleted_at?: string | null;
  updated_at?: string | null;
};

type ForeshadowRow = {
  id: string;
  chapter_id?: string | null;
  resolved_at_chapter_id?: string | null;
  title?: string | null;
  content_md?: string | null;
  resolved: number;
  deleted_at?: string | null;
  updated_at?: string | null;
};

type EvidenceRow = {
  id: string;
  source_type: string;
  source_id?: string | null;
  quote_md?: string | null;
  deleted_at?: string | null;
  created_at?: string | null;
};

type StructuredMemoryResponse = {
  counts: Counts;
  cursor: Partial<Record<TableName, string | null>>;
  entities?: EntityRow[];
  relations?: RelationRow[];
  events?: EventRow[];
  foreshadows?: ForeshadowRow[];
  evidence?: EvidenceRow[];
};

type PageData = {
  table: TableName;
  q: string;
  include_deleted: boolean;
  counts: Counts;
  cursor: string | null;
  items: Array<Record<string, unknown>>;
};

function tableLabel(t: TableName): string {
  if (t === "entities") return "entities";
  if (t === "relations") return "relations";
  if (t === "events") return "events";
  if (t === "foreshadows") return "foreshadows";
  return "evidence";
}

function safeSnippet(text: string | null | undefined, max = 80): string {
  const s = String(text || "").replaceAll("\n", " ").trim();
  if (!s) return "-";
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

function safeJsonStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function toCountMap(value: unknown): Counts {
  const base: Counts = { entities: 0, relations: 0, events: 0, foreshadows: 0, evidence: 0 };
  if (!value || typeof value !== "object") return base;
  const o = value as Record<string, unknown>;
  for (const key of Object.keys(base)) {
    const v = o[key];
    if (typeof v === "number" && Number.isFinite(v)) {
      base[key as TableName] = v;
    }
  }
  return base;
}

export function StructuredMemoryPage() {
  const { projectId } = useParams();
  const [searchParams] = useSearchParams();
  const toast = useToast();

  const chapterId = searchParams.get("chapterId") || undefined;

  const [activeTable, setActiveTable] = useState<TableName>("entities");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [queryText, setQueryText] = useState("");

  const [memoryUpdateOpen, setMemoryUpdateOpen] = useState(false);

  const loader = useCallback(
    async (id: string): Promise<PageData> => {
      const params = new URLSearchParams();
      params.set("table", activeTable);
      if (includeDeleted) params.set("include_deleted", "true");
      if (queryText.trim()) params.set("q", queryText.trim());
      params.set("limit", "50");

      const res = await apiJson<StructuredMemoryResponse>(`/api/projects/${id}/memory/structured?${params.toString()}`);
      const data = res.data as unknown as StructuredMemoryResponse;
      const counts = toCountMap(data.counts);
      const cursor = (data.cursor?.[activeTable] ?? null) as string | null;
      const items = ((data as any)[activeTable] ?? []) as Array<Record<string, unknown>>;

      return { table: activeTable, q: queryText.trim(), include_deleted: includeDeleted, counts, cursor, items };
    },
    [activeTable, includeDeleted, queryText],
  );

  const pageQuery = useProjectData(projectId, loader);
  const refresh = pageQuery.refresh;

  useEffect(() => {
    if (!projectId) return;
    void refresh();
  }, [activeTable, includeDeleted, projectId, queryText, refresh]);

  const counts = pageQuery.data?.counts ?? { entities: 0, relations: 0, events: 0, foreshadows: 0, evidence: 0 };
  const cursor = pageQuery.data?.cursor ?? null;
  const items = pageQuery.data?.items ?? [];

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  useEffect(() => {
    setSelectedIds([]);
  }, [activeTable, queryText, includeDeleted]);

  const loadMore = useCallback(async () => {
    if (!projectId) return;
    if (!cursor) return;
    const params = new URLSearchParams();
    params.set("table", activeTable);
    if (includeDeleted) params.set("include_deleted", "true");
    if (queryText.trim()) params.set("q", queryText.trim());
    params.set("before", cursor);
    params.set("limit", "50");

    try {
      const res = await apiJson<StructuredMemoryResponse>(`/api/projects/${projectId}/memory/structured?${params.toString()}`);
      const data = res.data as unknown as StructuredMemoryResponse;
      const nextItems = ((data as any)[activeTable] ?? []) as Array<Record<string, unknown>>;
      const nextCursor = (data.cursor?.[activeTable] ?? null) as string | null;
      pageQuery.setData((prev) => {
        const prevCounts = prev?.counts ?? counts;
        return {
          table: activeTable,
          q: queryText.trim(),
          include_deleted: includeDeleted,
          counts: toCountMap(data.counts) ?? prevCounts,
          cursor: nextCursor,
          items: [...(prev?.items ?? []), ...nextItems],
        };
      });
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    }
  }, [activeTable, counts, cursor, includeDeleted, pageQuery, projectId, queryText, toast]);

  const generatedDeleteOpsJson = useMemo(() => {
    if (selectedIds.length === 0) return "";
    const ops = selectedIds.map((id) => ({ op: "delete", target_table: activeTable, target_id: id }));
    return safeJsonStringify(ops);
  }, [activeTable, selectedIds]);

  const generatedResolvedOpsJson = useMemo(() => {
    if (activeTable !== "foreshadows" || selectedIds.length === 0) return "";
    const ops = selectedIds.map((id) => ({ op: "upsert", target_table: "foreshadows", target_id: id, after: { resolved: 1 } }));
    return safeJsonStringify(ops);
  }, [activeTable, selectedIds]);

  const copyText = useCallback(
    async (text: string, label: string) => {
      if (!text.trim()) return;
      try {
        await navigator.clipboard.writeText(text);
        toast.toastSuccess(`已复制 ${label}`);
      } catch {
        toast.toastWarning(`复制失败，请手动复制下方 JSON（${label}）`);
      }
    },
    [toast],
  );

  const toggleSelected = useCallback((id: string, checked: boolean) => {
    setSelectedIds((prev) => {
      const set = new Set(prev);
      if (checked) set.add(id);
      else set.delete(id);
      return Array.from(set);
    });
  }, []);

  const selectAll = useCallback(() => {
    const ids = items.map((x) => String((x as any).id || "")).filter(Boolean);
    setSelectedIds(ids);
  }, [items]);

  const clearSelected = useCallback(() => setSelectedIds([]), []);

  const applySearch = useCallback(() => {
    setQueryText(searchText.trim());
  }, [searchText]);

  if (!projectId) return <div className="text-subtext">缺少 projectId</div>;

  return (
    <div className="grid gap-4">
      <div className="panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="font-content text-xl text-ink">结构化记忆</div>
            <div className="mt-1 text-xs text-subtext">表格化浏览 entities/relations/events/foreshadows/evidence</div>
            <div className="mt-1 text-[11px] text-subtext">
              批量操作会生成 memory_update_v1 ops JSON（需在 Memory Update 中粘贴并 Apply）。
            </div>
          </div>
          <button className="btn btn-secondary" onClick={() => void pageQuery.refresh()} type="button">
            刷新
          </button>
        </div>
      </div>

      <div className="panel p-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {(["entities", "relations", "events", "foreshadows", "evidence"] as const).map((t) => (
              <button
                key={t}
                className={`btn ${activeTable === t ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setActiveTable(t)}
                type="button"
              >
                {tableLabel(t)} <span className="text-xs opacity-80">({counts[t] ?? 0})</span>
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                className="checkbox"
                checked={includeDeleted}
                onChange={(e) => setIncludeDeleted(e.target.checked)}
                aria-label="structured_include_deleted"
                type="checkbox"
              />
              include_deleted
            </label>
            <button
              className="btn btn-secondary"
              disabled={!chapterId}
              title={chapterId ? undefined : "建议从写作页带上 ?chapterId=... 打开以便 Apply"}
              onClick={() => setMemoryUpdateOpen(true)}
              type="button"
            >
              Memory Update
            </button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1 sm:col-span-2">
            <span className="text-xs text-subtext">搜索（q）</span>
            <div className="flex gap-2">
              <input
                className="input flex-1"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                aria-label="structured_search"
                placeholder="Alice"
              />
              <button className="btn btn-secondary" onClick={applySearch} type="button">
                搜索
              </button>
            </div>
          </label>
        </div>

        {selectedIds.length > 0 ? (
          <div className="mt-4 surface p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm text-ink">
                已选择 {selectedIds.length} 条（{activeTable}）
              </div>
              <div className="flex flex-wrap gap-2">
                <button className="btn btn-secondary" onClick={selectAll} type="button">
                  全选当前页
                </button>
                <button className="btn btn-secondary" onClick={clearSelected} type="button">
                  清空选择
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={() => void copyText(generatedDeleteOpsJson, "delete ops")}
                  type="button"
                >
                  复制 delete ops
                </button>
                {activeTable === "foreshadows" ? (
                  <button
                    className="btn btn-secondary"
                    onClick={() => void copyText(generatedResolvedOpsJson, "resolved ops")}
                    type="button"
                  >
                    复制 resolved ops
                  </button>
                ) : null}
              </div>
            </div>

            <div className="mt-3 grid gap-2">
              <div className="text-xs text-subtext">delete ops</div>
              <textarea className="textarea font-mono text-xs" readOnly rows={Math.min(10, Math.max(3, selectedIds.length + 1))} value={generatedDeleteOpsJson} />
              {activeTable === "foreshadows" ? (
                <>
                  <div className="text-xs text-subtext">resolved ops</div>
                  <textarea
                    className="textarea font-mono text-xs"
                    readOnly
                    rows={Math.min(10, Math.max(3, selectedIds.length + 1))}
                    value={generatedResolvedOpsJson}
                  />
                </>
              ) : null}
            </div>
          </div>
        ) : null}

        <div className="mt-4">
          {pageQuery.loading ? <div className="text-sm text-subtext">加载中...</div> : null}
          {!pageQuery.loading && items.length === 0 ? <div className="text-sm text-subtext">暂无数据</div> : null}

          {items.length > 0 ? (
            <div className="mt-2 overflow-auto rounded-atelier border border-border">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-surface text-xs text-subtext">
                  <tr>
                    <th className="w-10 p-2">
                      <button className="btn btn-secondary btn-icon" onClick={selectAll} type="button" aria-label="structured_select_all">
                        ✓
                      </button>
                    </th>
                    <th className="p-2">主字段</th>
                    <th className="p-2">摘要</th>
                    <th className="p-2">状态</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((row) => {
                    const id = String((row as any).id || "");
                    const deletedAt = String((row as any).deleted_at || "");
                    const checked = selectedSet.has(id);

                    let primary = id;
                    let summary = "-";
                    if (activeTable === "entities") {
                      primary = `${(row as any).entity_type}:${(row as any).name}`;
                      summary = safeSnippet((row as any).summary_md);
                    } else if (activeTable === "relations") {
                      primary = `${(row as any).relation_type}:${(row as any).from_entity_id}→${(row as any).to_entity_id}`;
                      summary = safeSnippet((row as any).description_md);
                    } else if (activeTable === "events") {
                      primary = `${(row as any).event_type}:${(row as any).title || id}`;
                      summary = safeSnippet((row as any).content_md);
                    } else if (activeTable === "foreshadows") {
                      primary = `${(row as any).resolved ? "resolved" : "open"}:${(row as any).title || id}`;
                      summary = safeSnippet((row as any).content_md);
                    } else if (activeTable === "evidence") {
                      primary = `${(row as any).source_type}:${(row as any).source_id || "-"}`;
                      summary = safeSnippet((row as any).quote_md);
                    }

                    return (
                      <tr key={id} className="border-t border-border">
                        <td className="p-2">
                          <input
                            className="checkbox"
                            aria-label={`structured_select_${id}`}
                            checked={checked}
                            onChange={(e) => toggleSelected(id, e.target.checked)}
                            type="checkbox"
                          />
                        </td>
                        <td className="p-2">
                          <div className="truncate text-ink">{primary}</div>
                          <div className="mt-1 truncate text-[11px] text-subtext">{id}</div>
                        </td>
                        <td className="p-2">
                          <div className="max-w-[520px] truncate text-subtext">{summary}</div>
                        </td>
                        <td className="p-2">
                          {deletedAt ? (
                            <span className="rounded bg-red-50 px-2 py-0.5 text-[11px] text-red-700 dark:bg-red-500/10 dark:text-red-300">
                              deleted
                            </span>
                          ) : (
                            <span className="rounded bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300">
                              active
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}

          {cursor ? (
            <div className="mt-3 flex justify-center">
              <button className="btn btn-secondary" onClick={() => void loadMore()} type="button">
                加载更多
              </button>
            </div>
          ) : null}
        </div>
      </div>

      <MemoryUpdateDrawer
        open={memoryUpdateOpen}
        onClose={() => setMemoryUpdateOpen(false)}
        projectId={projectId}
        chapterId={chapterId}
      />
    </div>
  );
}

