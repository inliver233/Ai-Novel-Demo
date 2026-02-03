import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { DebugDetails, DebugPageShell } from "../components/atelier/DebugPageShell";
import { TablesPanelInline } from "../components/writing/TablesPanel";
import { useToast } from "../components/ui/toast";
import { copyText } from "../lib/copyText";
import { UI_COPY } from "../lib/uiCopy";
import { ApiError, apiJson } from "../services/apiClient";

type ProjectTable = {
  id: string;
  project_id: string;
  table_key: string;
  name: string;
  row_count?: number;
  updated_at?: string | null;
};

export function NumericTablesPage() {
  const { projectId } = useParams();
  const toast = useToast();
  const pid = String(projectId || "");

  const [tablesLoading, setTablesLoading] = useState(false);
  const [tablesError, setTablesError] = useState<string | null>(null);
  const [tables, setTables] = useState<ProjectTable[]>([]);
  const [selectedTableId, setSelectedTableId] = useState<string>("");

  const [focus, setFocus] = useState<string>("");
  const [scheduling, setScheduling] = useState(false);
  const [lastTaskId, setLastTaskId] = useState<string>("");

  const selectedTable = useMemo(() => tables.find((t) => t.id === selectedTableId) ?? null, [selectedTableId, tables]);

  const loadTables = useCallback(async () => {
    if (!pid) return;
    setTablesLoading(true);
    setTablesError(null);
    try {
      const res = await apiJson<{ tables: ProjectTable[] }>(`/api/projects/${pid}/tables?include_schema=false`);
      const next = Array.isArray(res.data?.tables) ? res.data.tables : [];
      setTables(next);
      setSelectedTableId((prev) => {
        if (prev && next.some((t) => t.id === prev)) return prev;
        return next[0]?.id ?? "";
      });
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      setTablesError(`${err.message} (${err.code})${err.requestId ? ` request_id:${err.requestId}` : ""}`);
    } finally {
      setTablesLoading(false);
    }
  }, [pid]);

  useEffect(() => {
    if (!pid) return;
    void loadTables();
  }, [loadTables, pid]);

  const scheduleAiUpdate = useCallback(async () => {
    if (!pid) return;
    const tableId = selectedTableId.trim();
    if (!tableId) {
      toast.toastError("请先选择一个表格");
      return;
    }
    setScheduling(true);
    try {
      const res = await apiJson<{ task_id: string; chapter_id?: string | null; table_id?: string | null }>(
        `/api/projects/${pid}/tables/${encodeURIComponent(tableId)}/ai_update`,
        {
          method: "POST",
          body: JSON.stringify({ focus: focus.trim() || null }),
        },
      );
      const taskId = String(res.data?.task_id || "").trim();
      if (taskId) setLastTaskId(taskId);
      toast.toastSuccess("已创建 AI 更新任务", res.request_id);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setScheduling(false);
    }
  }, [focus, pid, selectedTableId, toast]);

  if (!pid) return <div className="text-subtext">缺少 projectId</div>;

  return (
    <DebugPageShell
      title={UI_COPY.nav.numericTables}
      description="数值表格（NumericTables）：用于记录可数字化状态（例如金钱/时间/等级/资源）；与图谱底座数据（StructuredMemory）不同。"
    >
      <DebugDetails title="说明">
        <div className="grid gap-1 text-xs text-subtext">
          <div>
            本页为「数值表格（NumericTables）」的 AdvancedDebug：用表格记录钱/时间/等级/资源；不是图谱底座数据。
          </div>
          <div>支持直接编辑表与行（project_tables / project_table_rows）。</div>
        </div>
      </DebugDetails>

      <DebugDetails title="AI 更新（table_ai_update）">
        <div className="grid gap-3">
          <div className="grid gap-1 text-xs text-subtext">
            <div>点击后会创建一个 ProjectTask（可在 Task Center 查看结果、失败可重试）。</div>
            <div>任务成功后会产出一个 ChangeSet（可 apply / rollback）。</div>
          </div>

          <div className="grid gap-2 lg:grid-cols-[1fr,2fr]">
            <label className="grid gap-1">
              <div className="text-xs text-subtext">目标表</div>
              <select
                className="select"
                id="numeric_tables_select_table"
                name="numeric_tables_select_table"
                value={selectedTableId}
                onChange={(e) => setSelectedTableId(e.target.value)}
                aria-label="选择目标表 (numeric_tables_select_table)"
              >
                <option value="" disabled>
                  {tablesLoading ? "加载中..." : tablesError ? "加载失败" : "请选择"}
                </option>
                {tables.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.table_key})
                  </option>
                ))}
              </select>
              {tablesError ? <div className="text-xs text-danger">{tablesError}</div> : null}
              <div className="flex flex-wrap items-center gap-2">
                <button className="btn btn-secondary btn-sm" onClick={() => void loadTables()} type="button">
                  刷新表列表
                </button>
              </div>
            </label>

            <label className="grid gap-1">
              <div className="text-xs text-subtext">Focus（可选）</div>
              <textarea
                className="textarea min-h-[88px]"
                id="numeric_tables_ai_focus"
                name="numeric_tables_ai_focus"
                value={focus}
                onChange={(e) => setFocus(e.target.value)}
                placeholder="例如：根据最新章节更新金币与装备数量；不要捏造"
                aria-label="AI 更新 focus (numeric_tables_ai_focus)"
              />
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              className="btn btn-primary"
              onClick={() => void scheduleAiUpdate()}
              disabled={scheduling || !selectedTableId}
              aria-label="创建 AI 更新任务 (numeric_tables_ai_schedule)"
              type="button"
            >
              {scheduling ? "创建中..." : `AI 提议更新${selectedTable ? `：${selectedTable.name}` : ""}`}
            </button>

            {lastTaskId ? (
              <>
                <Link
                  className="btn btn-secondary"
                  to={`/projects/${pid}/tasks?project_task_id=${encodeURIComponent(lastTaskId)}`}
                >
                  打开 Task Center（定位本次任务）
                </Link>
                <button
                  className="btn btn-secondary"
                  onClick={() => void copyText(lastTaskId, { title: "复制失败：请手动复制 task_id" })}
                  type="button"
                >
                  复制 task_id
                </button>
              </>
            ) : (
              <Link className="btn btn-secondary" to={`/projects/${pid}/tasks`}>
                打开 Task Center
              </Link>
            )}
          </div>
        </div>
      </DebugDetails>

      <TablesPanelInline projectId={pid} />
    </DebugPageShell>
  );
}
