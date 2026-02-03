import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { ApiError, apiJson } from "../../services/apiClient";
import { Drawer } from "../ui/Drawer";
import { useConfirm } from "../ui/confirm";
import { useToast } from "../ui/toast";

type TableColumn = { key: string; type: string; label?: string | null; required?: boolean };
type TableSchema = { version?: number; columns?: TableColumn[] };

type ProjectTable = {
  id: string;
  project_id: string;
  table_key: string;
  name: string;
  auto_update_enabled?: boolean;
  schema_version: number;
  schema?: TableSchema;
  row_count?: number;
  created_at?: string | null;
  updated_at?: string | null;
};

type ProjectTableRow = {
  id: string;
  project_id: string;
  table_id: string;
  row_index: number;
  data: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

const DEFAULT_KV_SCHEMA: TableSchema = {
  version: 1,
  columns: [
    { key: "key", type: "string", label: "Key", required: true },
    { key: "value", type: "string", label: "Value", required: false },
  ],
};

function normalizeColumns(schema: unknown): TableColumn[] {
  if (!schema || typeof schema !== "object") return [];
  const o = schema as Record<string, unknown>;
  const cols = Array.isArray(o.columns) ? o.columns : [];
  const out: TableColumn[] = [];
  for (const c of cols) {
    if (!c || typeof c !== "object") continue;
    const it = c as Record<string, unknown>;
    const key = typeof it.key === "string" ? it.key.trim() : "";
    if (!key) continue;
    const type = typeof it.type === "string" ? it.type.trim() : "string";
    const label = typeof it.label === "string" ? it.label : null;
    const required = Boolean(it.required);
    out.push({ key, type, label, required });
  }
  return out;
}

function isKeyValueSchema(cols: TableColumn[]): boolean {
  if (cols.length !== 2) return false;
  const keys = cols.map((c) => c.key).sort();
  if (keys[0] !== "key" || keys[1] !== "value") return false;
  const keyCol = cols.find((c) => c.key === "key");
  if (!keyCol?.required) return false;
  return true;
}

function toInputString(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function requiredFieldError(col: TableColumn, value: unknown): string | null {
  if (!col.required) return null;
  if (value === null || value === undefined) return `${col.key} 为必填字段`;
  if (typeof value === "string" && !value.trim()) return `${col.key} 为必填字段`;
  return null;
}

function toCreateRowDefaults(cols: TableColumn[], nextIndex: number): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const c of cols) {
    const type = (c.type || "string").trim().toLowerCase();
    if (!c.required) continue;
    if (type === "number") out[c.key] = 0;
    else if (type === "boolean") out[c.key] = false;
    else if (type === "json") out[c.key] = {};
    else out[c.key] = c.key === "key" ? `item_${nextIndex}` : `new_${c.key}_${nextIndex}`;
  }
  return out;
}

function parseJsonMaybe(value: unknown): { ok: true; value: unknown } | { ok: false; message: string } {
  if (value === null || value === undefined) return { ok: true, value: null };
  if (typeof value !== "string") return { ok: true, value };
  const raw = value.trim();
  if (!raw) return { ok: true, value: null };
  try {
    return { ok: true, value: JSON.parse(raw) };
  } catch {
    return { ok: false, message: "JSON 解析失败" };
  }
}

type TablesPanelContentProps = {
  enabled: boolean;
  titleId: string;
  projectId?: string;
  onClose?: () => void;
  showClose?: boolean;
};

function TablesPanelContent(props: TablesPanelContentProps) {
  const toast = useToast();
  const confirm = useConfirm();

  const [tablesLoading, setTablesLoading] = useState(false);
  const [tablesError, setTablesError] = useState<string | null>(null);
  const [tables, setTables] = useState<ProjectTable[]>([]);

  const [selectedTableId, setSelectedTableId] = useState<string>("");
  const selectedTable = useMemo(() => tables.find((t) => t.id === selectedTableId) ?? null, [selectedTableId, tables]);
  const selectedColumns = useMemo(() => normalizeColumns(selectedTable?.schema ?? null), [selectedTable?.schema]);
  const keyValueMode = useMemo(() => isKeyValueSchema(selectedColumns), [selectedColumns]);

  const [rowsLoading, setRowsLoading] = useState(false);
  const [rowsError, setRowsError] = useState<string | null>(null);
  const [rows, setRows] = useState<ProjectTableRow[]>([]);

  const [draftRows, setDraftRows] = useState<Record<string, Record<string, unknown>>>({});
  const draftRowsRef = useRef(draftRows);
  useEffect(() => {
    draftRowsRef.current = draftRows;
  }, [draftRows]);

  const [createName, setCreateName] = useState("");
  const [createKey, setCreateKey] = useState("");
  const [creating, setCreating] = useState(false);

  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [autoUpdateSaving, setAutoUpdateSaving] = useState(false);

  const loadTables = useCallback(async () => {
    const projectId = props.projectId;
    if (!projectId) {
      setTables([]);
      setTablesError("缺少 projectId");
      return;
    }
    setTablesLoading(true);
    setTablesError(null);
    try {
      const res = await apiJson<{ tables: ProjectTable[] }>(`/api/projects/${projectId}/tables?include_schema=true`);
      const next = Array.isArray(res.data?.tables) ? res.data.tables : [];
      setTables(next);
      setTablesError(null);

      if (!next.find((t) => t.id === selectedTableId)) {
        setSelectedTableId(next[0]?.id ?? "");
      }
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? `${e.message} (${e.code})${e.requestId ? ` request_id:${e.requestId}` : ""}`
          : "加载失败";
      setTablesError(msg);
    } finally {
      setTablesLoading(false);
    }
  }, [props.projectId, selectedTableId]);

  const loadRows = useCallback(async () => {
    const projectId = props.projectId;
    if (!projectId) return;
    if (!selectedTableId) {
      setRows([]);
      setRowsError(null);
      return;
    }
    setRowsLoading(true);
    setRowsError(null);
    try {
      const res = await apiJson<{ rows: ProjectTableRow[]; total: number }>(
        `/api/projects/${projectId}/tables/${selectedTableId}/rows?limit=200`,
      );
      const next = Array.isArray(res.data?.rows) ? res.data.rows : [];
      setRows(next);
      const initDraft: Record<string, Record<string, unknown>> = {};
      for (const r of next) initDraft[r.id] = { ...(r.data ?? {}) };
      setDraftRows(initDraft);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? `${e.message} (${e.code})${e.requestId ? ` request_id:${e.requestId}` : ""}`
          : "加载失败";
      setRowsError(msg);
    } finally {
      setRowsLoading(false);
    }
  }, [props.projectId, selectedTableId]);

  useEffect(() => {
    if (!props.enabled) return;
    void loadTables();
  }, [loadTables, props.enabled]);

  useEffect(() => {
    if (!props.enabled) return;
    void loadRows();
  }, [loadRows, props.enabled, selectedTableId]);

  useEffect(() => {
    setRenameValue(selectedTable?.name ?? "");
  }, [selectedTable?.name]);

  const createTable = useCallback(async () => {
    const projectId = props.projectId;
    if (!projectId) return;
    const name = createName.trim();
    const key = createKey.trim();
    if (!name) {
      toast.toastError("表名不能为空");
      return;
    }

    setCreating(true);
    try {
      const res = await apiJson<{ table: ProjectTable }>(`/api/projects/${projectId}/tables`, {
        method: "POST",
        body: JSON.stringify({
          name,
          table_key: key || null,
          schema: DEFAULT_KV_SCHEMA,
        }),
      });
      const table = res.data?.table;
      if (table?.id) {
        toast.toastSuccess("已创建表格");
        setCreateName("");
        setCreateKey("");
        await loadTables();
        setSelectedTableId(table.id);
      } else {
        toast.toastError("创建失败");
      }
    } catch (e) {
      if (e instanceof ApiError) toast.toastError(`${e.message} (${e.code})`);
      else toast.toastError("创建失败");
    } finally {
      setCreating(false);
    }
  }, [createKey, createName, loadTables, props.projectId, toast]);

  const renameTable = useCallback(async () => {
    const projectId = props.projectId;
    if (!projectId) return;
    if (!selectedTable) return;
    const nextName = renameValue.trim();
    if (!nextName) {
      toast.toastError("表名不能为空");
      return;
    }

    setRenaming(true);
    try {
      await apiJson<{ table: ProjectTable }>(`/api/projects/${projectId}/tables/${selectedTable.id}`, {
        method: "PUT",
        body: JSON.stringify({ name: nextName }),
      });
      toast.toastSuccess("已更新表名");
      await loadTables();
    } catch (e) {
      if (e instanceof ApiError) toast.toastError(`${e.message} (${e.code})`);
      else toast.toastError("更新失败");
    } finally {
      setRenaming(false);
    }
  }, [loadTables, props.projectId, renameValue, selectedTable, toast]);

  const updateTableAutoUpdateEnabled = useCallback(
    async (enabled: boolean) => {
      const projectId = props.projectId;
      if (!projectId) return;
      if (!selectedTable) return;
      if (autoUpdateSaving) return;

      setAutoUpdateSaving(true);
      try {
        await apiJson<{ table: ProjectTable }>(`/api/projects/${projectId}/tables/${selectedTable.id}`, {
          method: "PUT",
          body: JSON.stringify({ auto_update_enabled: enabled }),
        });
        toast.toastSuccess("已更新自动更新设置");
        await loadTables();
      } catch (e) {
        if (e instanceof ApiError) toast.toastError(`${e.message} (${e.code})`);
        else toast.toastError("更新失败");
      } finally {
        setAutoUpdateSaving(false);
      }
    },
    [autoUpdateSaving, loadTables, props.projectId, selectedTable, toast],
  );

  const deleteTable = useCallback(async () => {
    const projectId = props.projectId;
    if (!projectId) return;
    if (!selectedTable) return;
    const ok = await confirm.confirm({
      title: "删除表格？",
      description: `将删除「${selectedTable.name}」及其所有行，且不可恢复。`,
      confirmText: "删除",
      cancelText: "取消",
      danger: true,
    });
    if (!ok) return;

    try {
      await apiJson<{ deleted: boolean }>(`/api/projects/${projectId}/tables/${selectedTable.id}`, {
        method: "DELETE",
      });
      toast.toastSuccess("已删除表格");
      setSelectedTableId("");
      setRows([]);
      setDraftRows({});
      await loadTables();
    } catch (e) {
      if (e instanceof ApiError) toast.toastError(`${e.message} (${e.code})`);
      else toast.toastError("删除失败");
    }
  }, [confirm, loadTables, props.projectId, selectedTable, toast]);

  const saveRow = useCallback(
    async (rowId: string) => {
      const projectId = props.projectId;
      if (!projectId) return;
      const tableId = selectedTable?.id;
      if (!tableId) return;
      const row = rows.find((r) => r.id === rowId);
      if (!row) return;
      const cols = selectedColumns;

      const currentDraft = draftRowsRef.current[rowId] ?? {};
      const nextData: Record<string, unknown> = {};
      for (const c of cols) {
        const rawValue = currentDraft[c.key];
        if (c.type.trim().toLowerCase() === "json") {
          const parsed = parseJsonMaybe(rawValue);
          if (!parsed.ok) {
            toast.toastError(`${c.key}: ${parsed.message}`);
            return;
          }
          nextData[c.key] = parsed.value;
        } else if (c.type.trim().toLowerCase() === "number") {
          if (rawValue === null || rawValue === undefined || rawValue === "") nextData[c.key] = null;
          else if (typeof rawValue === "number") nextData[c.key] = rawValue;
          else {
            const n = Number(rawValue);
            if (!Number.isFinite(n)) {
              toast.toastError(`${c.key}: number 非法`);
              return;
            }
            nextData[c.key] = n;
          }
        } else if (c.type.trim().toLowerCase() === "boolean") {
          nextData[c.key] = Boolean(rawValue);
        } else {
          nextData[c.key] = rawValue ?? null;
        }
        const err = requiredFieldError(c, nextData[c.key]);
        if (err) {
          toast.toastError(err);
          return;
        }
      }

      try {
        await apiJson<{ row: ProjectTableRow }>(`/api/projects/${projectId}/tables/${tableId}/rows/${rowId}`, {
          method: "PUT",
          body: JSON.stringify({ data: nextData }),
        });
        toast.toastSuccess("已保存行");
        await loadRows();
        await loadTables();
      } catch (e) {
        if (e instanceof ApiError) toast.toastError(`${e.message} (${e.code})`);
        else toast.toastError("保存失败");
      }
    },
    [loadRows, loadTables, props.projectId, rows, selectedColumns, selectedTable?.id, toast],
  );

  const deleteRow = useCallback(
    async (rowId: string) => {
      const projectId = props.projectId;
      if (!projectId) return;
      const tableId = selectedTable?.id;
      if (!tableId) return;
      const ok = await confirm.confirm({
        title: "删除行？",
        description: "将删除该行数据，且不可恢复。",
        confirmText: "删除",
        cancelText: "取消",
        danger: true,
      });
      if (!ok) return;

      try {
        await apiJson<{ deleted: boolean }>(`/api/projects/${projectId}/tables/${tableId}/rows/${rowId}`, {
          method: "DELETE",
        });
        toast.toastSuccess("已删除行");
        await loadRows();
        await loadTables();
      } catch (e) {
        if (e instanceof ApiError) toast.toastError(`${e.message} (${e.code})`);
        else toast.toastError("删除失败");
      }
    },
    [confirm, loadRows, loadTables, props.projectId, selectedTable?.id, toast],
  );

  const addRow = useCallback(async () => {
    const projectId = props.projectId;
    if (!projectId) return;
    const tableId = selectedTable?.id;
    if (!tableId) return;

    const cols = selectedColumns;
    const nextIdx = rows.length + 1;
    const defaults = toCreateRowDefaults(cols, nextIdx);

    if (keyValueMode) {
      const key = String(defaults.key ?? "").trim();
      if (!key) defaults.key = `item_${nextIdx}`;
      defaults.value ??= "";
    }

    try {
      await apiJson<{ row: ProjectTableRow }>(`/api/projects/${projectId}/tables/${tableId}/rows`, {
        method: "POST",
        body: JSON.stringify({ data: defaults }),
      });
      toast.toastSuccess("已新增行");
      await loadRows();
      await loadTables();
    } catch (e) {
      if (e instanceof ApiError) toast.toastError(`${e.message} (${e.code})`);
      else toast.toastError("新增失败");
    }
  }, [keyValueMode, loadRows, loadTables, props.projectId, rows.length, selectedColumns, selectedTable?.id, toast]);

  return (
    <>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-content text-2xl text-ink" id={props.titleId}>
            表格面板（Tables）
          </div>
          <div className="mt-1 text-xs text-subtext">用于维护写作过程中的结构化状态（project_tables）。</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn btn-secondary"
            disabled={!props.projectId || tablesLoading}
            onClick={loadTables}
            type="button"
          >
            刷新
          </button>
          {props.showClose ? (
            <button className="btn btn-secondary" aria-label="关闭" onClick={props.onClose} type="button">
              关闭
            </button>
          ) : null}
        </div>
      </div>

      {!props.projectId ? (
        <div className="mt-4 text-sm text-subtext">缺少 projectId，无法加载。</div>
      ) : (
        <div className="mt-5 grid gap-4">
          <div className="panel p-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div className="grid gap-2">
                <div className="text-sm text-ink">选择表格</div>
                <select
                  className="select"
                  aria-label="tables_select"
                  value={selectedTableId}
                  onChange={(e) => setSelectedTableId(e.target.value)}
                >
                  <option value="">（未选择）</option>
                  {tables.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({t.table_key}){typeof t.row_count === "number" ? ` · rows:${t.row_count}` : ""}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid gap-1 text-xs text-subtext">
                <div>schema_version: {selectedTable?.schema_version ?? "-"}</div>
                <div>rows: {typeof selectedTable?.row_count === "number" ? selectedTable.row_count : "-"}</div>
              </div>
            </div>

            {tablesError ? <div className="mt-3 text-sm text-danger">{tablesError}</div> : null}
            {tablesLoading ? <div className="mt-3 text-sm text-subtext">加载中...</div> : null}
          </div>

          <div className="panel p-4">
            <div className="text-sm text-ink">新建表格（默认 Key/Value）</div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-xs text-subtext">
                <span>表名</span>
                <input
                  className="input"
                  aria-label="create_table_name"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                />
              </label>
              <label className="grid gap-1 text-xs text-subtext">
                <span>table_key（可选）</span>
                <input
                  className="input"
                  aria-label="create_table_key"
                  value={createKey}
                  onChange={(e) => setCreateKey(e.target.value)}
                />
              </label>
            </div>
            <div className="mt-3 flex justify-end">
              <button className="btn btn-primary" disabled={creating} onClick={() => void createTable()} type="button">
                {creating ? "创建中..." : "创建"}
              </button>
            </div>
          </div>

          {selectedTable ? (
            <div className="panel p-4">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div className="grid gap-1">
                  <div className="text-sm text-ink">表信息</div>
                  <div className="text-xs text-subtext">
                    id: <span className="font-mono">{selectedTable.id}</span>
                  </div>
                  <div className="text-xs text-subtext">
                    table_key: <span className="font-mono">{selectedTable.table_key}</span>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <button
                    className="btn btn-secondary"
                    disabled={renaming}
                    onClick={() => void renameTable()}
                    type="button"
                  >
                    保存表名
                  </button>
                  <button className="btn btn-secondary" onClick={() => void deleteTable()} type="button">
                    删除表格
                  </button>
                </div>
              </div>
              <label className="mt-3 grid gap-1 text-xs text-subtext">
                <span>表名</span>
                <input
                  className="input"
                  aria-label="rename_table_name"
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                />
              </label>
              <label className="mt-3 flex items-center justify-between gap-3 text-sm text-ink">
                <span>章节定稿自动更新（table_ai_update）</span>
                <input
                  className="checkbox"
                  type="checkbox"
                  checked={Boolean(selectedTable.auto_update_enabled ?? true)}
                  disabled={autoUpdateSaving}
                  onChange={(e) => void updateTableAutoUpdateEnabled(e.target.checked)}
                />
              </label>
              <div className="mt-1 text-[11px] text-subtext">
                启用后：章节定稿（done）会按项目设置自动排队更新该表；关闭可减少任务数量。
              </div>
            </div>
          ) : null}

          {selectedTable ? (
            <div className="panel p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="text-sm text-ink">表内容</div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    className="btn btn-secondary"
                    disabled={rowsLoading}
                    onClick={() => void loadRows()}
                    type="button"
                  >
                    刷新行
                  </button>
                  <button
                    className="btn btn-primary"
                    disabled={rowsLoading}
                    onClick={() => void addRow()}
                    type="button"
                  >
                    新增行
                  </button>
                </div>
              </div>

              {rowsError ? <div className="mt-3 text-sm text-danger">{rowsError}</div> : null}
              {rowsLoading ? <div className="mt-3 text-sm text-subtext">加载中...</div> : null}

              {selectedColumns.length ? (
                <div className="mt-4 overflow-auto">
                  <table className="min-w-full border-separate border-spacing-0">
                    <thead>
                      <tr>
                        {selectedColumns.map((c) => (
                          <th
                            key={c.key}
                            className="sticky top-0 border-b border-border bg-canvas px-2 py-1 text-left text-xs font-medium text-subtext"
                          >
                            {c.label || c.key}
                            {c.required ? <span className="ml-1 text-danger">*</span> : null}
                            <span className="ml-1 font-mono text-[10px] text-subtext/70">({c.type})</span>
                          </th>
                        ))}
                        <th className="sticky top-0 border-b border-border bg-canvas px-2 py-1 text-left text-xs font-medium text-subtext">
                          操作
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.length === 0 ? (
                        <tr>
                          <td className="px-2 py-2 text-sm text-subtext" colSpan={selectedColumns.length + 1}>
                            暂无数据。可点击「新增行」快速添加。
                          </td>
                        </tr>
                      ) : null}
                      {rows.map((r) => {
                        const draft = draftRows[r.id] ?? {};
                        return (
                          <tr key={r.id} className="border-b border-border">
                            {selectedColumns.map((c) => {
                              const type = c.type.trim().toLowerCase();
                              const value = draft[c.key];
                              if (type === "boolean") {
                                return (
                                  <td key={c.key} className="border-b border-border px-2 py-2 align-top">
                                    <input
                                      className="checkbox"
                                      aria-label={`cell_${r.id}_${c.key}`}
                                      checked={Boolean(value)}
                                      onChange={(e) =>
                                        setDraftRows((prev) => ({
                                          ...prev,
                                          [r.id]: { ...(prev[r.id] ?? {}), [c.key]: e.currentTarget.checked },
                                        }))
                                      }
                                      type="checkbox"
                                    />
                                  </td>
                                );
                              }
                              if (type === "md" || type === "json") {
                                return (
                                  <td key={c.key} className="border-b border-border px-2 py-2 align-top">
                                    <textarea
                                      className="textarea-underline min-h-10 w-64 border-transparent py-1 text-sm hover:border-border hover:bg-surface/50 focus:bg-surface/50"
                                      aria-label={`cell_${r.id}_${c.key}`}
                                      value={toInputString(value)}
                                      onChange={(e) =>
                                        setDraftRows((prev) => ({
                                          ...prev,
                                          [r.id]: { ...(prev[r.id] ?? {}), [c.key]: e.currentTarget.value },
                                        }))
                                      }
                                    />
                                  </td>
                                );
                              }
                              return (
                                <td key={c.key} className="border-b border-border px-2 py-2 align-top">
                                  <input
                                    className="input-underline w-56 border-transparent py-1 text-sm hover:border-border hover:bg-surface/50 focus:bg-surface/50"
                                    aria-label={`cell_${r.id}_${c.key}`}
                                    inputMode={type === "number" ? "numeric" : undefined}
                                    value={toInputString(value)}
                                    onChange={(e) => {
                                      const nextRaw = e.currentTarget.value;
                                      setDraftRows((prev) => ({
                                        ...prev,
                                        [r.id]: {
                                          ...(prev[r.id] ?? {}),
                                          [c.key]: type === "number" ? nextRaw.replace(/[^\d.-]/g, "") : nextRaw,
                                        },
                                      }));
                                    }}
                                  />
                                </td>
                              );
                            })}
                            <td className="border-b border-border px-2 py-2 align-top">
                              <div className="flex flex-wrap gap-2">
                                <button
                                  className="btn btn-secondary px-3 py-1 text-sm"
                                  onClick={() => void saveRow(r.id)}
                                  type="button"
                                >
                                  保存
                                </button>
                                <button
                                  className="btn btn-secondary px-3 py-1 text-sm"
                                  onClick={() => void deleteRow(r.id)}
                                  type="button"
                                >
                                  删除
                                </button>
                              </div>
                              <div className="mt-1 text-[10px] text-subtext">
                                row_index: {r.row_index} · id: <span className="font-mono">{r.id.slice(0, 8)}</span>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="mt-3 text-sm text-subtext">
                  未找到 schema.columns。可通过 API 更新 schema 后再编辑行数据。
                </div>
              )}
            </div>
          ) : null}
        </div>
      )}
    </>
  );
}

export function TablesPanel(props: { open: boolean; onClose: () => void; projectId?: string }) {
  const titleId = useId();
  return (
    <Drawer
      open={props.open}
      onClose={props.onClose}
      ariaLabelledBy={titleId}
      panelClassName="h-full w-full max-w-3xl overflow-y-auto border-l border-border bg-canvas p-6 shadow-sm"
    >
      <TablesPanelContent
        enabled={props.open}
        titleId={titleId}
        projectId={props.projectId}
        onClose={props.onClose}
        showClose
      />
    </Drawer>
  );
}

export function TablesPanelInline(props: { projectId?: string }) {
  const titleId = useId();
  return <TablesPanelContent enabled titleId={titleId} projectId={props.projectId} />;
}
