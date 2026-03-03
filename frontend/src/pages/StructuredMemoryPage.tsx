import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { DebugDetails, DebugPageShell } from "../components/atelier/DebugPageShell";
import { Drawer } from "../components/ui/Drawer";
import { RequestIdBadge } from "../components/ui/RequestIdBadge";
import { useToast } from "../components/ui/toast";
import { MemoryUpdateDrawer } from "../components/writing/MemoryUpdateDrawer";
import { useProjectData } from "../hooks/useProjectData";
import { UI_COPY } from "../lib/uiCopy";
import { ApiError, apiJson } from "../services/apiClient";
import { CharacterRelationsView } from "./structuredMemory/CharacterRelationsView";

type TableName = "entities" | "relations" | "events" | "foreshadows" | "evidence";
type ViewMode = "table" | "character_relations";

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

const STRUCTURED_TABLE_LABELS: Record<TableName, string> = {
  entities: UI_COPY.structuredMemory.tabs.entities,
  relations: UI_COPY.structuredMemory.tabs.relations,
  events: UI_COPY.structuredMemory.tabs.events,
  foreshadows: UI_COPY.structuredMemory.tabs.foreshadows,
  evidence: UI_COPY.structuredMemory.tabs.evidence,
};

function tableLabel(t: TableName): string {
  return STRUCTURED_TABLE_LABELS[t] ?? t;
}

function safeSnippet(text: string | null | undefined, max = 80): string {
  const s = String(text || "")
    .replaceAll("\n", " ")
    .trim();
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

function toRowItems(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter((x): x is Record<string, unknown> => !!x && typeof x === "object") as Array<
    Record<string, unknown>
  >;
}

function readStringField(row: Record<string, unknown>, key: string): string {
  const value = row[key];
  if (typeof value === "string") return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (value == null) return "";
  return String(value);
}

function readTextField(row: Record<string, unknown>, key: string): string | null | undefined {
  const value = row[key];
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return value;
  return String(value);
}

function readBoolField(row: Record<string, unknown>, key: string): boolean {
  const value = row[key];
  return value === true || value === 1 || value === "1" || value === "true";
}

export function StructuredMemoryPage() {
  const { projectId } = useParams();
  const [searchParams] = useSearchParams();
  const toast = useToast();

  const chapterId = searchParams.get("chapterId") || undefined;
  const initialView: ViewMode = searchParams.get("view") === "character-relations" ? "character_relations" : "table";
  const [viewMode, setViewMode] = useState<ViewMode>(initialView);
  const focusRelationId = String(searchParams.get("relationId") || "").trim() || null;

  const [activeTable, setActiveTable] = useState<TableName>("entities");
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [queryText, setQueryText] = useState("");
  const [requestId, setRequestId] = useState<string | null>(null);

  const [memoryUpdateOpen, setMemoryUpdateOpen] = useState(false);
  const [bulkOpsOpen, setBulkOpsOpen] = useState(false);

  const loader = useCallback(
    async (id: string): Promise<PageData> => {
      const params = new URLSearchParams();
      params.set("table", activeTable);
      if (includeDeleted) params.set("include_deleted", "true");
      if (queryText.trim()) params.set("q", queryText.trim());
      params.set("limit", "50");

      try {
        const res = await apiJson<StructuredMemoryResponse>(
          `/api/projects/${id}/memory/structured?${params.toString()}`,
        );
        setRequestId(res.request_id ?? null);
        const data = res.data as unknown as StructuredMemoryResponse;
        const counts = toCountMap(data.counts);
        const cursor = (data.cursor?.[activeTable] ?? null) as string | null;
        const items = toRowItems(data[activeTable]);

        return { table: activeTable, q: queryText.trim(), include_deleted: includeDeleted, counts, cursor, items };
      } catch (e) {
        if (e instanceof ApiError) setRequestId(e.requestId ?? null);
        throw e;
      }
    },
    [activeTable, includeDeleted, queryText],
  );

  const pageQuery = useProjectData(projectId, loader);
  const refresh = pageQuery.refresh;

  useEffect(() => {
    if (!projectId) return;
    void refresh();
  }, [activeTable, includeDeleted, projectId, queryText, refresh]);

  const counts = useMemo(
    () => pageQuery.data?.counts ?? { entities: 0, relations: 0, events: 0, foreshadows: 0, evidence: 0 },
    [pageQuery.data?.counts],
  );
  const cursor = pageQuery.data?.cursor ?? null;
  const items = useMemo(() => pageQuery.data?.items ?? [], [pageQuery.data?.items]);

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

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
      const res = await apiJson<StructuredMemoryResponse>(
        `/api/projects/${projectId}/memory/structured?${params.toString()}`,
      );
      setRequestId(res.request_id ?? null);
      const data = res.data as unknown as StructuredMemoryResponse;
      const nextItems = toRowItems(data[activeTable]);
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
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      setRequestId(err.requestId ?? null);
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
    const ops = selectedIds.map((id) => ({
      op: "upsert",
      target_table: "foreshadows",
      target_id: id,
      after: { resolved: 1 },
    }));
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
      const next = Array.from(set);
      if (next.length === 0) setBulkOpsOpen(false);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    const ids = items.map((row) => readStringField(row, "id")).filter(Boolean);
    setSelectedIds(ids);
  }, [items]);

  const clearSelected = useCallback(() => {
    setBulkOpsOpen(false);
    setSelectedIds([]);
  }, []);

  const applySearch = useCallback(() => {
    setBulkOpsOpen(false);
    setSelectedIds([]);
    setQueryText(searchText.trim());
  }, [searchText]);

  if (!projectId) return <div className="text-subtext">缺少 projectId</div>;

  return (
    <DebugPageShell
      title={UI_COPY.structuredMemory.title}
      description={UI_COPY.structuredMemory.subtitle}
      actions={
        <>
          <button className="btn btn-secondary" onClick={() => void pageQuery.refresh()} type="button">
            刷新
          </button>
          {selectedIds.length > 0 ? (
            <button className="btn btn-secondary" onClick={() => setBulkOpsOpen(true)} type="button">
              批量操作 ({selectedIds.length})
            </button>
          ) : null}
          <button
            className="btn btn-secondary"
            disabled={!chapterId}
            title={chapterId ? undefined : "建议从写作页带上 ?chapterId=... 打开以便 Apply"}
            onClick={() => setMemoryUpdateOpen(true)}
            type="button"
          >
            Memory Update
          </button>
        </>
      }
    >
      {projectId ? (
        <div className="callout-info text-sm">
          提示：本页是图谱底座数据（实体/关系/事件/伏笔/证据）。金钱/时间/等级/资源等数值状态请到{" "}
          <Link className="underline" to={`/projects/${projectId}/numeric-tables`}>
            {UI_COPY.nav.numericTables}
          </Link>
          。
        </div>
      ) : null}
      <div className="rounded-atelier border border-border bg-canvas p-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <button
              className={`btn ${viewMode === "table" ? "btn-primary" : "btn-secondary"}`}
              onClick={() => {
                setBulkOpsOpen(false);
                setSelectedIds([]);
                setViewMode("table");
              }}
              aria-label="structured_view_table"
              type="button"
            >
              数据表
            </button>
            <button
              className={`btn ${viewMode === "character_relations" ? "btn-primary" : "btn-secondary"}`}
              onClick={() => {
                setBulkOpsOpen(false);
                setSelectedIds([]);
                setViewMode("character_relations");
              }}
              aria-label="structured_view_character_relations"
              type="button"
            >
              人物关系
            </button>

            {viewMode === "table"
              ? (["entities", "relations", "events", "foreshadows", "evidence"] as const).map((t) => (
                  <button
                    key={t}
                    className={`btn ${activeTable === t ? "btn-primary" : "btn-secondary"}`}
                    onClick={() => {
                      setBulkOpsOpen(false);
                      setSelectedIds([]);
                      setActiveTable(t);
                    }}
                    aria-label={`${t}（${tableLabel(t)}） (structured_tab_${t})`}
                    type="button"
                  >
                    {tableLabel(t)} <span className="text-xs opacity-80">({counts[t] ?? 0})</span>
                  </button>
                ))
              : null}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <RequestIdBadge requestId={requestId} />
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                className="checkbox"
                checked={includeDeleted}
                onChange={(e) => {
                  setBulkOpsOpen(false);
                  setSelectedIds([]);
                  setIncludeDeleted(e.target.checked);
                }}
                aria-label="structured_include_deleted"
                type="checkbox"
              />
              {UI_COPY.structuredMemory.includeDeleted}
            </label>
          </div>
        </div>

        {viewMode === "table" ? (
          <>
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
              <div className="mt-4 text-xs text-subtext">
                已选择 <span className="text-ink">{selectedIds.length}</span> 条（{tableLabel(activeTable)}
                ）。可点击右上角“批量操作” 生成 JSON 并打开 Memory Update。
              </div>
            ) : null}
          </>
        ) : (
          <div className="mt-3 text-xs text-subtext">该视图仅用于编辑人物关系（entity_type=character）。</div>
        )}
      </div>

      {viewMode === "table" ? (
        <>
          <div className="rounded-atelier border border-border bg-canvas p-3">
            {pageQuery.loading ? <div className="text-sm text-subtext">加载中...</div> : null}
            {!pageQuery.loading && items.length === 0 ? <div className="text-sm text-subtext">暂无数据</div> : null}

            {items.length > 0 ? (
              <div className="mt-2 overflow-auto rounded-atelier border border-border">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-surface text-xs text-subtext">
                    <tr>
                      <th className="w-10 p-2">
                        <button
                          className="btn btn-secondary btn-icon"
                          onClick={selectAll}
                          type="button"
                          aria-label="structured_select_all"
                        >
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
                      const id = readStringField(row, "id");
                      const deletedAt = readStringField(row, "deleted_at");
                      const checked = selectedSet.has(id);

                      let primary = id;
                      let summary = "-";
                      if (activeTable === "entities") {
                        primary = `${readStringField(row, "entity_type")}:${readStringField(row, "name")}`;
                        summary = safeSnippet(readTextField(row, "summary_md"));
                      } else if (activeTable === "relations") {
                        primary = `${readStringField(row, "relation_type")}:${readStringField(row, "from_entity_id")}→${readStringField(row, "to_entity_id")}`;
                        summary = safeSnippet(readTextField(row, "description_md"));
                      } else if (activeTable === "events") {
                        primary = `${readStringField(row, "event_type")}:${readStringField(row, "title") || id}`;
                        summary = safeSnippet(readTextField(row, "content_md"));
                      } else if (activeTable === "foreshadows") {
                        primary = `${readBoolField(row, "resolved") ? "已解决" : "未解决"}:${readStringField(row, "title") || id}`;
                        summary = safeSnippet(readTextField(row, "content_md"));
                      } else if (activeTable === "evidence") {
                        primary = `${readStringField(row, "source_type")}:${readStringField(row, "source_id") || "-"}`;
                        summary = safeSnippet(readTextField(row, "quote_md"));
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
                              <span className="inline-flex rounded bg-danger/10 px-2 py-0.5 text-[11px] text-danger">
                                已删除
                              </span>
                            ) : (
                              <span className="inline-flex rounded bg-success/10 px-2 py-0.5 text-[11px] text-success">
                                正常
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

          <DebugDetails title={UI_COPY.help.title}>
            <div className="grid gap-2 text-xs text-subtext">
              <div>{UI_COPY.structuredMemory.usageHint}</div>
              <div>{UI_COPY.structuredMemory.exampleHint}</div>
              {projectId ? (
                <div>
                  常用入口：从{" "}
                  <Link className="underline" to={`/projects/${projectId}/writing`}>
                    写作页
                  </Link>{" "}
                  或{" "}
                  <Link className="underline" to={`/projects/${projectId}/chapter-analysis`}>
                    章节分析
                  </Link>{" "}
                  触发“Memory Update”，再在{" "}
                  <Link className="underline" to={`/projects/${projectId}/tasks`}>
                    任务中心
                  </Link>{" "}
                  追踪 ChangeSet/任务状态。
                </div>
              ) : null}
              <div>{UI_COPY.structuredMemory.bulkOpsHint}</div>
              <div className="text-amber-700 dark:text-amber-300">{UI_COPY.structuredMemory.bulkOpsRisk}</div>
            </div>
          </DebugDetails>

          <Drawer
            open={bulkOpsOpen}
            onClose={() => setBulkOpsOpen(false)}
            ariaLabelledBy="structured_bulk_ops_title"
            panelClassName="h-full w-full max-w-[860px] overflow-hidden border-l border-border bg-surface shadow-sm"
          >
            <div className="flex h-full flex-col">
              <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
                <div className="min-w-0">
                  <div className="truncate text-sm text-ink" id="structured_bulk_ops_title">
                    批量操作
                  </div>
                  <div className="mt-0.5 truncate text-xs text-subtext">
                    已选择 {selectedIds.length} 条（{tableLabel(activeTable)}）
                  </div>
                </div>
                <button
                  className="btn btn-secondary"
                  aria-label="关闭"
                  onClick={() => setBulkOpsOpen(false)}
                  type="button"
                >
                  关闭
                </button>
              </div>

              <div className="flex-1 overflow-auto p-4">
                {selectedIds.length === 0 ? (
                  <div className="text-sm text-subtext">请先在表格中选择条目。</div>
                ) : (
                  <div className="grid gap-3">
                    <div className="rounded-atelier border border-border bg-surface p-3">
                      <div className="text-xs text-subtext">1）选择条目</div>
                      <div className="mt-1 text-sm text-ink">
                        已选择 {selectedIds.length} 条（{tableLabel(activeTable)}）
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <button className="btn btn-secondary" onClick={selectAll} type="button">
                          全选当前页
                        </button>
                        <button className="btn btn-secondary" onClick={clearSelected} type="button">
                          清空选择
                        </button>
                      </div>
                    </div>

                    <div className="rounded-atelier border border-border bg-surface p-3">
                      <div className="text-xs text-subtext">2）生成操作</div>
                      <div className="mt-1 text-xs text-subtext">删除操作：{selectedIds.length} 条</div>
                      {activeTable === "foreshadows" ? (
                        <div className="mt-1 text-xs text-subtext">标记已解决：{selectedIds.length} 条（可选）</div>
                      ) : null}
                    </div>

                    <div className="rounded-atelier border border-border bg-surface p-3">
                      <div className="text-xs text-subtext">3）复制并打开 Memory Update</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <button
                          className="btn btn-secondary"
                          onClick={() => void copyText(generatedDeleteOpsJson, "删除操作 JSON")}
                          type="button"
                        >
                          {UI_COPY.structuredMemory.copyDeleteOps}
                        </button>
                        {activeTable === "foreshadows" ? (
                          <button
                            className="btn btn-secondary"
                            onClick={() => void copyText(generatedResolvedOpsJson, "标记已解决 JSON")}
                            type="button"
                          >
                            {UI_COPY.structuredMemory.copyResolvedOps}
                          </button>
                        ) : null}
                        <button
                          className="btn btn-secondary"
                          disabled={!chapterId}
                          title={chapterId ? undefined : "建议从写作页带上 ?chapterId=... 打开以便 Apply"}
                          onClick={() => {
                            setBulkOpsOpen(false);
                            setMemoryUpdateOpen(true);
                          }}
                          type="button"
                        >
                          打开 Memory Update
                        </button>
                      </div>

                      <details className="mt-3 rounded-atelier border border-border bg-canvas p-3">
                        <summary className="cursor-pointer select-none text-xs text-ink">查看 JSON（高级）</summary>
                        <div className="mt-3 grid gap-2">
                          <div className="text-xs text-subtext">{UI_COPY.structuredMemory.deleteOpsLabel}</div>
                          <textarea
                            className="textarea font-mono text-xs"
                            readOnly
                            rows={Math.min(10, Math.max(3, selectedIds.length + 1))}
                            value={generatedDeleteOpsJson}
                          />
                          {activeTable === "foreshadows" ? (
                            <>
                              <div className="text-xs text-subtext">{UI_COPY.structuredMemory.resolvedOpsLabel}</div>
                              <textarea
                                className="textarea font-mono text-xs"
                                readOnly
                                rows={Math.min(10, Math.max(3, selectedIds.length + 1))}
                                value={generatedResolvedOpsJson}
                              />
                            </>
                          ) : null}
                        </div>
                      </details>

                      <div className="mt-3 rounded-atelier border border-border bg-canvas p-3 text-xs text-subtext">
                        <div>{UI_COPY.structuredMemory.bulkOpsHint}</div>
                        <div className="mt-1">{UI_COPY.structuredMemory.bulkOpsRisk}</div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </Drawer>
        </>
      ) : (
        <CharacterRelationsView
          projectId={projectId}
          chapterId={chapterId}
          focusRelationId={focusRelationId}
          includeDeleted={includeDeleted}
          onRequestId={setRequestId}
        />
      )}

      <MemoryUpdateDrawer
        open={memoryUpdateOpen}
        onClose={() => setMemoryUpdateOpen(false)}
        projectId={projectId}
        chapterId={chapterId}
      />
    </DebugPageShell>
  );
}
