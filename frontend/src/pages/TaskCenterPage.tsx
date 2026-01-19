import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { Drawer } from "../components/ui/Drawer";
import { useProjectData } from "../hooks/useProjectData";
import { apiJson } from "../services/apiClient";

type MemoryChangeSetSummary = {
  id: string;
  chapter_id?: string | null;
  request_id?: string | null;
  idempotency_key?: string | null;
  title?: string | null;
  summary_md?: string | null;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
};

type MemoryTaskSummary = {
  id: string;
  project_id: string;
  change_set_id: string;
  request_id?: string | null;
  actor_user_id?: string | null;
  kind: string;
  status: string;
  error_type?: string | null;
  error_message?: string | null;
  timings?: Record<string, unknown>;
};

type PagedResult<T> = { items: T[]; next_before?: string | null };

function humanChangeSetStatus(status: string): string {
  const s = String(status || "").trim();
  if (s === "proposed") return "未应用";
  if (s === "applied") return "已应用";
  if (s === "rolled_back") return "已回滚";
  if (s === "failed") return "失败";
  return s || "未知";
}

function humanTaskStatus(status: string): string {
  const s = String(status || "").trim();
  if (s === "queued") return "排队中";
  if (s === "running") return "执行中";
  if (s === "done") return "完成";
  if (s === "failed") return "失败";
  return s || "未知";
}

function statusTone(status: string): "ok" | "warn" | "bad" | "info" {
  const s = String(status || "").trim();
  if (s === "failed") return "bad";
  if (s === "running") return "warn";
  if (s === "queued" || s === "proposed") return "info";
  return "ok";
}

function StatusBadge(props: { status: string; kind: "change_set" | "task" }) {
  const tone = statusTone(props.status);
  const cls =
    tone === "bad"
      ? "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300"
      : tone === "warn"
        ? "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"
        : tone === "info"
          ? "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-300"
          : "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300";
  const label = props.kind === "change_set" ? humanChangeSetStatus(props.status) : humanTaskStatus(props.status);
  return <span className={`inline-flex rounded px-2 py-0.5 text-[11px] ${cls}`}>{label}</span>;
}

function safeJsonStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function TaskCenterPage() {
  const { projectId } = useParams();

  const [changeSetStatus, setChangeSetStatus] = useState<string>("all");
  const [taskStatus, setTaskStatus] = useState<string>("all");

  const loadChangeSets = useCallback(
    async (id: string): Promise<PagedResult<MemoryChangeSetSummary>> => {
      const params = new URLSearchParams();
      if (changeSetStatus !== "all") params.set("status", changeSetStatus);
      params.set("limit", "50");
      const qs = params.toString();
      const res = await apiJson<PagedResult<MemoryChangeSetSummary>>(`/api/projects/${id}/memory_change_sets${qs ? `?${qs}` : ""}`);
      return res.data;
    },
    [changeSetStatus],
  );

  const loadTasks = useCallback(
    async (id: string): Promise<PagedResult<MemoryTaskSummary>> => {
      const params = new URLSearchParams();
      if (taskStatus !== "all") params.set("status", taskStatus);
      params.set("limit", "50");
      const qs = params.toString();
      const res = await apiJson<PagedResult<MemoryTaskSummary>>(`/api/projects/${id}/memory_tasks${qs ? `?${qs}` : ""}`);
      return res.data;
    },
    [taskStatus],
  );

  const changeSetsQuery = useProjectData(projectId, loadChangeSets);
  const tasksQuery = useProjectData(projectId, loadTasks);

  const refreshChangeSets = changeSetsQuery.refresh;
  const refreshTasks = tasksQuery.refresh;

  useEffect(() => {
    if (!projectId) return;
    void refreshChangeSets();
  }, [changeSetStatus, projectId, refreshChangeSets]);

  useEffect(() => {
    if (!projectId) return;
    void refreshTasks();
  }, [projectId, refreshTasks, taskStatus]);

  const changeSets = changeSetsQuery.data?.items ?? [];
  const tasks = tasksQuery.data?.items ?? [];

  const [selected, setSelected] = useState<
    | { kind: "change_set"; item: MemoryChangeSetSummary }
    | { kind: "task"; item: MemoryTaskSummary }
    | null
  >(null);

  const detailTitle = useMemo(() => {
    if (!selected) return "";
    if (selected.kind === "change_set") return "ChangeSet 详情";
    return "Task 详情";
  }, [selected]);

  const refreshAll = useCallback(() => {
    void refreshChangeSets();
    void refreshTasks();
  }, [refreshChangeSets, refreshTasks]);

  if (!projectId) return <div className="text-subtext">缺少 projectId</div>;

  return (
    <div className="grid gap-4">
      <div className="panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="font-content text-xl text-ink">任务中心</div>
            <div className="mt-1 text-xs text-subtext">查看 Memory ChangeSets / Tasks 的状态与错误</div>
          </div>
          <button className="btn btn-secondary" onClick={refreshAll} type="button">
            刷新
          </button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="panel p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm text-ink">ChangeSets</div>
              <div className="mt-1 text-xs text-subtext">按状态筛选，点击可查看详情</div>
            </div>
            <label className="grid gap-1">
              <span className="text-[11px] text-subtext">状态</span>
              <select
                className="select"
                aria-label="taskcenter_changeset_status"
                value={changeSetStatus}
                onChange={(e) => setChangeSetStatus(e.target.value)}
              >
                <option value="all">全部</option>
                <option value="proposed">proposed</option>
                <option value="applied">applied</option>
                <option value="rolled_back">rolled_back</option>
                <option value="failed">failed</option>
              </select>
            </label>
          </div>

          {changeSetsQuery.loading ? <div className="mt-3 text-sm text-subtext">加载中...</div> : null}
          {!changeSetsQuery.loading && changeSets.length === 0 ? (
            <div className="mt-3 text-sm text-subtext">暂无 ChangeSet</div>
          ) : null}

          <div className="mt-3 grid gap-2">
            {changeSets.map((it) => (
              <button
                key={it.id}
                className="surface ui-transition-fast w-full p-3 text-left hover:bg-canvas"
                onClick={() => setSelected({ kind: "change_set", item: it })}
                type="button"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm text-ink">{it.title || it.summary_md || it.id}</div>
                    <div className="mt-1 truncate text-xs text-subtext">
                      chapter_id: {it.chapter_id || "-"} | updated_at: {it.updated_at || it.created_at || "-"}
                    </div>
                    {it.request_id ? (
                      <div className="mt-1 truncate text-[11px] text-subtext">request_id: {it.request_id}</div>
                    ) : null}
                  </div>
                  <StatusBadge status={it.status} kind="change_set" />
                </div>
              </button>
            ))}
          </div>
        </section>

        <section className="panel p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm text-ink">Tasks</div>
              <div className="mt-1 text-xs text-subtext">失败任务会显示 error 摘要与 request_id</div>
            </div>
            <label className="grid gap-1">
              <span className="text-[11px] text-subtext">状态</span>
              <select
                className="select"
                aria-label="taskcenter_task_status"
                value={taskStatus}
                onChange={(e) => setTaskStatus(e.target.value)}
              >
                <option value="all">全部</option>
                <option value="queued">queued</option>
                <option value="running">running</option>
                <option value="done">done</option>
                <option value="failed">failed</option>
              </select>
            </label>
          </div>

          {tasksQuery.loading ? <div className="mt-3 text-sm text-subtext">加载中...</div> : null}
          {!tasksQuery.loading && tasks.length === 0 ? <div className="mt-3 text-sm text-subtext">暂无 Task</div> : null}

          <div className="mt-3 grid gap-2">
            {tasks.map((t) => (
              <button
                key={t.id}
                className="surface ui-transition-fast w-full p-3 text-left hover:bg-canvas"
                onClick={() => setSelected({ kind: "task", item: t })}
                type="button"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm text-ink">
                      {t.kind} <span className="text-subtext">({t.id})</span>
                    </div>
                    <div className="mt-1 truncate text-xs text-subtext">change_set_id: {t.change_set_id}</div>
                    {t.request_id ? <div className="mt-1 truncate text-[11px] text-subtext">request_id: {t.request_id}</div> : null}
                    {t.status === "failed" ? (
                      <div className="mt-1 truncate text-xs text-red-700 dark:text-red-300">
                        {t.error_type || "ERROR"}: {t.error_message || "unknown"}
                      </div>
                    ) : null}
                  </div>
                  <StatusBadge status={t.status} kind="task" />
                </div>
              </button>
            ))}
          </div>
        </section>
      </div>

      <Drawer
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        ariaLabel={detailTitle}
        panelClassName="h-full w-full max-w-2xl border-l border-border bg-canvas p-6 shadow-sm"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="font-content text-2xl text-ink">{detailTitle}</div>
            {selected ? (
              <div className="mt-1 text-xs text-subtext">
                id: {selected.item.id}{" "}
                {selected.kind === "task" ? `| request_id: ${selected.item.request_id ?? "-"}` : ""}
              </div>
            ) : null}
          </div>
          <button className="btn btn-secondary" onClick={() => setSelected(null)} type="button">
            关闭
          </button>
        </div>

        {selected ? (
          <div className="mt-5 grid gap-3">
            <div className="text-xs text-subtext">原始数据（JSON）</div>
            <pre className="max-h-[70vh] overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
              {safeJsonStringify(selected.item)}
            </pre>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
