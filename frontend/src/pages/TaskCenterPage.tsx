import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { DebugDetails } from "../components/atelier/DebugPageShell";
import { Drawer } from "../components/ui/Drawer";
import { useProjectData } from "../hooks/useProjectData";
import { humanizeChangeSetStatus, humanizeTaskStatus } from "../lib/humanize";
import { apiJson } from "../services/apiClient";
import { UI_COPY } from "../lib/uiCopy";

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
  const label = props.kind === "change_set" ? humanizeChangeSetStatus(props.status) : humanizeTaskStatus(props.status);
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
      const res = await apiJson<PagedResult<MemoryChangeSetSummary>>(
        `/api/projects/${id}/memory_change_sets${qs ? `?${qs}` : ""}`,
      );
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
      const res = await apiJson<PagedResult<MemoryTaskSummary>>(
        `/api/projects/${id}/memory_tasks${qs ? `?${qs}` : ""}`,
      );
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

  const changeSets = useMemo(() => changeSetsQuery.data?.items ?? [], [changeSetsQuery.data?.items]);
  const tasks = useMemo(() => tasksQuery.data?.items ?? [], [tasksQuery.data?.items]);

  const changeSetSummary = useMemo(() => {
    const out = { all: changeSets.length, proposed: 0, applied: 0, rolled_back: 0, failed: 0, other: 0 };
    for (const it of changeSets) {
      const s = String(it.status || "").trim();
      if (s === "proposed") out.proposed += 1;
      else if (s === "applied") out.applied += 1;
      else if (s === "rolled_back") out.rolled_back += 1;
      else if (s === "failed") out.failed += 1;
      else out.other += 1;
    }
    return out;
  }, [changeSets]);

  const taskSummary = useMemo(() => {
    const out = { all: tasks.length, queued: 0, running: 0, done: 0, failed: 0, other: 0 };
    for (const it of tasks) {
      const s = String(it.status || "").trim();
      if (s === "queued") out.queued += 1;
      else if (s === "running") out.running += 1;
      else if (s === "done") out.done += 1;
      else if (s === "failed") out.failed += 1;
      else out.other += 1;
    }
    return out;
  }, [tasks]);

  const [selected, setSelected] = useState<
    { kind: "change_set"; item: MemoryChangeSetSummary } | { kind: "task"; item: MemoryTaskSummary } | null
  >(null);

  const detailTitle = useMemo(() => {
    if (!selected) return "";
    if (selected.kind === "change_set") return "ChangeSet 详情";
    return "Task 详情";
  }, [selected]);

  const detailHeading = useMemo(() => {
    if (!selected) return "";
    if (selected.kind === "change_set") return "变更集详情";
    return "任务详情";
  }, [selected]);

  const refreshAll = useCallback(() => {
    void refreshChangeSets();
    void refreshTasks();
  }, [refreshChangeSets, refreshTasks]);

  const copyDebugInfo = useCallback(async () => {
    if (!selected) return;
    if (selected.kind === "change_set") {
      const it = selected.item;
      const lines = [
        "[TaskCenter][ChangeSet]",
        `id=${it.id}`,
        `status=${String(it.status || "-")} (${humanizeChangeSetStatus(String(it.status || ""))})`,
        `chapter_id=${it.chapter_id || "-"}`,
        `request_id=${it.request_id || "-"}`,
        `idempotency_key=${it.idempotency_key || "-"}`,
        `created_at=${it.created_at || "-"}`,
        `updated_at=${it.updated_at || "-"}`,
      ];
      await navigator.clipboard.writeText(lines.join("\n"));
      return;
    }

    const t = selected.item;
    const lines = [
      "[TaskCenter][Task]",
      `id=${t.id}`,
      `kind=${t.kind}`,
      `status=${String(t.status || "-")} (${humanizeTaskStatus(String(t.status || ""))})`,
      `change_set_id=${t.change_set_id}`,
      `request_id=${t.request_id || "-"}`,
      `error_type=${t.error_type || "-"}`,
      `error_message=${t.error_message || "-"}`,
    ];
    await navigator.clipboard.writeText(lines.join("\n"));
  }, [selected]);

  if (!projectId) return <div className="text-subtext">缺少 projectId</div>;

  return (
    <div className="grid gap-4">
      <div className="panel p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="font-content text-xl text-ink">{UI_COPY.taskCenter.title}</div>
            <div className="mt-1 text-xs text-subtext">{UI_COPY.taskCenter.subtitle}</div>
          </div>
          <button
            className="btn btn-secondary"
            onClick={refreshAll}
            aria-label="刷新 (taskcenter_refresh)"
            type="button"
          >
            刷新
          </button>
        </div>

        <div className="mt-3">
          <DebugDetails title={UI_COPY.help.title}>
            <div className="grid gap-2 text-xs text-subtext">
              <div>{UI_COPY.taskCenter.usageHint}</div>
              <div className="text-amber-700 dark:text-amber-300">{UI_COPY.taskCenter.riskHint}</div>
            </div>
          </DebugDetails>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="panel p-4" aria-label="变更集 (taskcenter_changesets_section)">
          <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
              <div className="text-sm text-ink">变更集（Change Set）</div>
              <div className="mt-1 text-xs text-subtext">按状态筛选；点击条目查看摘要与原始数据（默认折叠）</div>
              <div className="mt-1 text-[11px] text-subtext">
                状态说明：未应用=仅提议 | 已应用=已落库 | 已回滚=已撤销 | 失败=执行异常
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-subtext">
                <span>总计 {changeSetSummary.all}</span>
                <span>未应用 {changeSetSummary.proposed}</span>
                <span>已应用 {changeSetSummary.applied}</span>
                <span>已回滚 {changeSetSummary.rolled_back}</span>
                <span>失败 {changeSetSummary.failed}</span>
              </div>
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
                <option value="proposed">{humanizeChangeSetStatus("proposed")}</option>
                <option value="applied">{humanizeChangeSetStatus("applied")}</option>
                <option value="rolled_back">{humanizeChangeSetStatus("rolled_back")}</option>
                <option value="failed">{humanizeChangeSetStatus("failed")}</option>
              </select>
            </label>
          </div>

          {changeSetsQuery.loading ? <div className="mt-3 text-sm text-subtext">加载中...</div> : null}
          {!changeSetsQuery.loading && changeSets.length === 0 ? (
            <div className="mt-3 text-sm text-subtext">暂无变更集</div>
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
                      章节 ID：{it.chapter_id || "-"} | 更新时间：{it.updated_at || it.created_at || "-"}
                    </div>
                    {it.request_id ? (
                      <div className="mt-1 flex items-center gap-2 text-[11px] text-subtext">
                        <span className="truncate">
                          {UI_COPY.common.requestIdLabel}: <span className="font-mono">{it.request_id}</span>
                        </span>
                        <button
                          className="btn btn-ghost px-2 py-1 text-[11px]"
                          onClick={async () => {
                            await navigator.clipboard.writeText(it.request_id ?? "");
                          }}
                          type="button"
                        >
                          {UI_COPY.common.copy}
                        </button>
                      </div>
                    ) : null}
                  </div>
                  <StatusBadge status={it.status} kind="change_set" />
                </div>
              </button>
            ))}
          </div>
        </section>

        <section className="panel p-4" aria-label="任务列表 (taskcenter_tasks_section)">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm text-ink">任务（Task）</div>
              <div className="mt-1 text-xs text-subtext">失败任务会显示错误摘要与 {UI_COPY.common.requestIdLabel}</div>
              <div className="mt-1 text-[11px] text-subtext">
                状态说明：排队中→运行中→完成/失败（如失败可用 request_id 查后端日志）
              </div>
              <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-subtext">
                <span>总计 {taskSummary.all}</span>
                <span>排队中 {taskSummary.queued}</span>
                <span>运行中 {taskSummary.running}</span>
                <span>完成 {taskSummary.done}</span>
                <span>失败 {taskSummary.failed}</span>
              </div>
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <button
                className="btn btn-secondary"
                aria-label="失败任务筛选 (taskcenter_failed_only)"
                onClick={() => setTaskStatus((prev) => (prev === "failed" ? "all" : "failed"))}
                type="button"
              >
                仅看失败
              </button>
              <label className="grid gap-1">
                <span className="text-[11px] text-subtext">状态</span>
                <select
                  className="select"
                  aria-label="taskcenter_task_status"
                  value={taskStatus}
                  onChange={(e) => setTaskStatus(e.target.value)}
                >
                  <option value="all">全部</option>
                  <option value="queued">{humanizeTaskStatus("queued")}</option>
                  <option value="running">{humanizeTaskStatus("running")}</option>
                  <option value="done">{humanizeTaskStatus("done")}</option>
                  <option value="failed">{humanizeTaskStatus("failed")}</option>
                </select>
              </label>
            </div>
          </div>

          {tasksQuery.loading ? <div className="mt-3 text-sm text-subtext">加载中...</div> : null}
          {!tasksQuery.loading && tasks.length === 0 ? <div className="mt-3 text-sm text-subtext">暂无任务</div> : null}

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
                    <div className="mt-1 truncate text-xs text-subtext">变更集 ID：{t.change_set_id}</div>
                    {t.request_id ? (
                      <div className="mt-1 flex items-center gap-2 text-[11px] text-subtext">
                        <span className="truncate">
                          {UI_COPY.common.requestIdLabel}: <span className="font-mono">{t.request_id}</span>
                        </span>
                        <button
                          className="btn btn-ghost px-2 py-1 text-[11px]"
                          onClick={async () => {
                            await navigator.clipboard.writeText(t.request_id ?? "");
                          }}
                          type="button"
                        >
                          {UI_COPY.common.copy}
                        </button>
                      </div>
                    ) : null}
                    {t.status === "failed" ? (
                      <div className="mt-1 truncate text-xs text-red-700 dark:text-red-300">
                        {t.error_type || "ERROR"}: {t.error_message || "未知错误"}
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
            <div className="font-content text-2xl text-ink">{detailHeading || detailTitle}</div>
            {selected ? (
              <div className="mt-1 text-xs text-subtext">
                ID：{selected.item.id}{" "}
                {selected.kind === "task"
                  ? `| ${UI_COPY.common.requestIdLabel}: ${selected.item.request_id ?? "-"}`
                  : ""}
              </div>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn btn-secondary" onClick={() => void copyDebugInfo()} type="button">
              复制排障信息
            </button>
            <button className="btn btn-secondary" onClick={() => setSelected(null)} type="button">
              关闭
            </button>
          </div>
        </div>

        {selected ? (
          <details className="mt-5 rounded-atelier border border-border bg-surface p-3">
            <summary className="cursor-pointer select-none text-sm text-ink">原始数据（JSON）</summary>
            <pre className="mt-3 max-h-[70vh] overflow-auto rounded-atelier border border-border bg-canvas p-3 text-xs text-ink">
              {safeJsonStringify(selected.item)}
            </pre>
          </details>
        ) : null}
      </Drawer>
    </div>
  );
}
