import { TASK_CENTER_COPY } from "./taskCenterCopy";

export type MemoryChangeSetSummary = {
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

export type MemoryTaskSummary = {
  id: string;
  project_id: string;
  change_set_id: string;
  request_id?: string | null;
  actor_user_id?: string | null;
  kind: string;
  status: string;
  error_type?: string | null;
  error_message?: string | null;
  error?: unknown;
  timings?: Record<string, unknown>;
};

export type ProjectTaskSummary = {
  id: string;
  project_id: string;
  actor_user_id?: string | null;
  kind: string;
  status: string;
  idempotency_key?: string | null;
  error_type?: string | null;
  error_message?: string | null;
  timings?: Record<string, unknown>;
  params?: unknown;
  result?: unknown;
  error?: unknown;
};

export type PagedResult<T> = { items: T[]; next_before?: string | null };

export type ChangeSetApplyResult = {
  idempotent: boolean;
  change_set?: { id?: string | null; status?: string | null } | null;
  warnings?: unknown;
};

export type HealthData = {
  status: string;
  version?: string;
  queue_backend?: string | null;
  effective_backend?: string | null;
  redis_ok?: boolean | null;
  rq_queue_name?: string | null;
  redis_error_type?: string | null;
  worker_hint?: string | null;
};

export type TaskCenterSelectedItem =
  | { kind: "change_set"; item: MemoryChangeSetSummary }
  | { kind: "task"; item: MemoryTaskSummary }
  | { kind: "project_task"; item: ProjectTaskSummary }
  | null;

export function summarizeChangeSets(items: MemoryChangeSetSummary[]) {
  const out = { all: items.length, proposed: 0, applied: 0, rolled_back: 0, failed: 0, other: 0 };
  for (const item of items) {
    const status = String(item.status || "").trim();
    if (status === "proposed") out.proposed += 1;
    else if (status === "applied") out.applied += 1;
    else if (status === "rolled_back") out.rolled_back += 1;
    else if (status === "failed") out.failed += 1;
    else out.other += 1;
  }
  return out;
}

export function summarizeTasks(
  items: Array<MemoryTaskSummary | ProjectTaskSummary>,
  options?: { succeededAsDone?: boolean },
) {
  const out = { all: items.length, queued: 0, running: 0, done: 0, failed: 0, other: 0 };
  for (const item of items) {
    const status = String(item.status || "").trim();
    if (status === "queued") out.queued += 1;
    else if (status === "running") out.running += 1;
    else if (status === "done" || (options?.succeededAsDone && status === "succeeded")) out.done += 1;
    else if (status === "failed") out.failed += 1;
    else out.other += 1;
  }
  return out;
}

export function getTaskCenterDetailTitle(selected: TaskCenterSelectedItem): string {
  if (!selected) return "";
  if (selected.kind === "change_set") return "ChangeSet 详情";
  if (selected.kind === "task") return "Task 详情";
  return "ProjectTask 详情";
}

export function getTaskCenterDetailHeading(selected: TaskCenterSelectedItem): string {
  if (!selected) return "";
  if (selected.kind === "change_set") return "变更集详情";
  if (selected.kind === "task") return "任务详情";
  return "项目任务详情";
}

export function getProjectTaskLiveStatusLabel(status: "idle" | "connecting" | "open" | "error"): string {
  return TASK_CENTER_COPY.projectTasksLiveLabels[status];
}

function readNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function readString(value: unknown, fallback = "-"): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

export function formatTaskCenterErrorText(errorType?: string | null, errorMessage?: string | null) {
  return `${errorType || TASK_CENTER_COPY.unknownErrorType}: ${errorMessage || TASK_CENTER_COPY.unknownErrorMessage}`;
}

export function formatRuntimeCheckpointSummary(checkpoint: {
  status?: unknown;
  completed_count?: unknown;
  failed_count?: unknown;
  skipped_count?: unknown;
}) {
  return `last_checkpoint: ${readString(checkpoint.status)} | completed ${readNumber(checkpoint.completed_count)} | failed ${readNumber(checkpoint.failed_count)} | skipped ${readNumber(checkpoint.skipped_count)}`;
}

export function formatRuntimeBatchProgress(task: {
  completed_count?: unknown;
  total_count?: unknown;
  failed_count?: unknown;
  skipped_count?: unknown;
}) {
  return `completed ${readNumber(task.completed_count)}/${readNumber(task.total_count)} | failed ${readNumber(task.failed_count)} | skipped ${readNumber(task.skipped_count)}`;
}

export function formatRuntimeBatchFlags(task: { pause_requested?: unknown; cancel_requested?: unknown }) {
  return `pause_requested: ${String(Boolean(task.pause_requested))} | cancel_requested: ${String(Boolean(task.cancel_requested))}`;
}

export function formatRuntimeBatchItemSummary(item: {
  status?: unknown;
  attempt_count?: unknown;
  last_request_id?: unknown;
}) {
  const requestId =
    typeof item.last_request_id === "string" && item.last_request_id.trim()
      ? ` | request_id ${item.last_request_id.trim()}`
      : "";
  return `${readString(item.status)} | attempt ${readNumber(item.attempt_count)}${requestId}`;
}

export function formatRuntimeTimelineMeta(entry: { reason?: unknown; source?: unknown }) {
  const reason = readString(entry.reason);
  const source = typeof entry.source === "string" && entry.source.trim() ? ` | source: ${entry.source.trim()}` : "";
  return `reason: ${reason}${source}`;
}

export function formatRuntimeTimelineStep(step: unknown) {
  if (!step || typeof step !== "object") return null;
  const data = step as Record<string, unknown>;
  return `chapter ${readNumber(data.chapter_number)} | status ${readString(data.status)}`;
}
