import { useId } from "react";

import type { ProjectTaskRuntime } from "../../services/projectTaskRuntime";
import { Modal } from "../ui/Modal";
import { ProgressBar } from "../ui/ProgressBar";

import type { BatchGenerationTask, BatchGenerationTaskItem } from "./types";

function tryExtractRequestId(raw: string | null | undefined): string | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === "object") {
      const obj = parsed as Record<string, unknown>;
      const direct = obj.request_id ?? obj.requestId;
      if (typeof direct === "string" && direct.trim()) return direct;

      const nestedError = obj.error;
      if (nestedError && typeof nestedError === "object") {
        const err = nestedError as Record<string, unknown>;
        const nested = err.request_id ?? err.requestId;
        if (typeof nested === "string" && nested.trim()) return nested;
      }
    }
  } catch {
    return null;
  }

  const match = raw.match(/request[_-]?id\s*[:=]\s*([A-Za-z0-9_-]+)/i);
  return match?.[1] ?? null;
}

function tryParseJsonObject(raw: string | null | undefined): Record<string, unknown> | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return null;
  }
  return null;
}

function readNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function readString(value: unknown, fallback = "-"): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function formatProjectTaskStreamStatus(status: "idle" | "connecting" | "open" | "error"): string {
  if (status === "open") return "connected";
  if (status === "connecting") return "reconnecting";
  if (status === "error") return "fallback polling";
  return "idle";
}

function buildStepLabel(item: BatchGenerationTaskItem): string {
  const requestId = item.last_request_id ? ` ? request_id ${item.last_request_id}` : "";
  const attempts = ` ? attempt ${item.attempt_count}`;
  const error = item.error_message ? ` ? ${item.error_message}` : "";
  return `${item.status}${attempts}${requestId}${error}`;
}

export function BatchGenerationModal(props: {
  open: boolean;
  batchLoading: boolean;
  activeChapterNumber: number | null;
  batchCount: number;
  setBatchCount: (value: number) => void;
  batchIncludeExisting: boolean;
  setBatchIncludeExisting: (value: boolean) => void;
  batchTask: BatchGenerationTask | null;
  batchItems: BatchGenerationTaskItem[];
  batchRuntime: ProjectTaskRuntime | null;
  projectTaskStreamStatus: "idle" | "connecting" | "open" | "error";
  taskCenterHref?: string | null;
  onClose: () => void;
  onCancelTask: () => void;
  onPauseTask: () => void;
  onResumeTask: () => void;
  onRetryFailedTask: () => void;
  onSkipFailedTask: () => void;
  onStartTask: () => void;
  onApplyItemToEditor: (item: BatchGenerationTaskItem) => void;
}) {
  const titleId = useId();
  const task = props.batchTask;
  const failedItems = props.batchItems.filter((item) => item.status === "failed");
  const taskRunning = Boolean(task && (task.status === "queued" || task.status === "running"));
  const taskPaused = task?.status === "paused";
  const taskTerminal = Boolean(
    task && (task.status === "succeeded" || task.status === "failed" || task.status === "canceled"),
  );
  const requestId =
    tryExtractRequestId(task?.error_json) ??
    failedItems.map((item) => tryExtractRequestId(item.last_error_json)).find(Boolean) ??
    null;
  const processedCount = task ? task.completed_count + task.failed_count + task.skipped_count : 0;
  const taskProgressPercent = task
    ? Math.round((task.total_count > 0 ? processedCount / task.total_count : 0) * 100)
    : 0;
  const latestCheckpoint =
    props.batchRuntime?.checkpoints.at(-1)?.checkpoint ?? tryParseJsonObject(task?.checkpoint_json) ?? null;
  const timeline = props.batchRuntime?.timeline ?? [];
  const streamStatusLabel = formatProjectTaskStreamStatus(props.projectTaskStreamStatus);
  const canResume = Boolean(taskPaused && failedItems.length === 0);
  const canRetryFailed = Boolean(taskPaused && failedItems.length > 0);
  const canSkipFailed = Boolean(taskPaused && failedItems.length > 0);
  const canCancel = Boolean(
    task && (task.status === "queued" || task.status === "running" || task.status === "paused"),
  );

  return (
    <Modal
      open={props.open}
      onClose={props.batchLoading ? undefined : props.onClose}
      panelClassName="surface max-w-3xl p-5"
      ariaLabelledBy={titleId}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-content text-xl text-ink" id={titleId}>
            Batch Generation
          </div>
          <div className="mt-1 text-xs text-subtext">
            Batch generation writes generation runs only. Chapters stay unchanged until you apply a result to the
            editor.
          </div>
        </div>
        <button
          className="btn btn-secondary"
          aria-label="Close"
          onClick={props.onClose}
          disabled={props.batchLoading}
          type="button"
        >
          Close
        </button>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-atelier border border-border bg-canvas px-3 py-2 text-xs text-subtext">
        <span aria-label="batch_generation_live_status">Runtime SSE: {streamStatusLabel}</span>
        {props.taskCenterHref ? (
          <a
            className="btn btn-secondary btn-sm"
            href={props.taskCenterHref}
            aria-label="Open TaskCenter (batch_generation_open_task_center)"
          >
            Open TaskCenter
          </a>
        ) : null}
      </div>

      <div className="mt-4 grid gap-3">
        <div className="grid gap-2 rounded-atelier border border-border bg-canvas p-3">
          <div className="text-sm font-medium text-ink">Step 1 ? Range</div>
          <div className="text-xs text-subtext">
            Start after: {props.activeChapterNumber ? `chapter ${props.activeChapterNumber}` : "chapter 1"}
          </div>
          <div className="text-[11px] text-subtext">
            The active chapter decides the starting point. Generation continues sequentially after it.
          </div>
        </div>

        <div className="grid gap-2 rounded-atelier border border-border bg-canvas p-3">
          <div className="text-sm font-medium text-ink">Step 2 ? Options</div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="grid gap-1">
              <span className="text-xs text-subtext">Count: 1~200</span>
              <input
                className="input w-28"
                min={1}
                max={200}
                type="number"
                value={props.batchCount}
                disabled={props.batchLoading || taskRunning}
                onChange={(e) => props.setBatchCount(Math.max(1, Math.min(200, Number(e.target.value) || 1)))}
              />
            </label>
            <label className="flex items-center gap-2 pb-2 text-sm text-ink">
              <input
                className="checkbox"
                type="checkbox"
                checked={props.batchIncludeExisting}
                disabled={props.batchLoading || taskRunning}
                onChange={(e) => props.setBatchIncludeExisting(e.target.checked)}
              />
              Include chapters that already have content
            </label>
          </div>
        </div>

        <div className="grid gap-3 rounded-atelier border border-border bg-surface p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-medium text-ink">Step 3 ? Run and recovery</div>
            <div className="flex flex-wrap items-center gap-2">
              {!task || taskTerminal ? (
                <button
                  className="btn btn-primary"
                  disabled={props.batchLoading}
                  onClick={props.onStartTask}
                  type="button"
                >
                  {props.batchLoading ? "Starting..." : "Start batch generation"}
                </button>
              ) : null}
              {taskRunning ? (
                <button
                  className="btn btn-secondary"
                  disabled={props.batchLoading}
                  onClick={props.onPauseTask}
                  aria-label="Pause batch generation (batch_generation_pause)"
                  type="button"
                >
                  {props.batchLoading ? "Working..." : "Pause"}
                </button>
              ) : null}
              {canResume ? (
                <button
                  className="btn btn-secondary"
                  disabled={props.batchLoading}
                  onClick={props.onResumeTask}
                  aria-label="Resume batch generation (batch_generation_resume)"
                  type="button"
                >
                  {props.batchLoading ? "Working..." : "Resume"}
                </button>
              ) : null}
              {canRetryFailed ? (
                <button
                  className="btn btn-secondary"
                  disabled={props.batchLoading}
                  onClick={props.onRetryFailedTask}
                  aria-label="Retry failed chapters (batch_generation_retry_failed)"
                  type="button"
                >
                  {props.batchLoading ? "Working..." : "Retry failed chapters"}
                </button>
              ) : null}
              {canSkipFailed ? (
                <button
                  className="btn btn-secondary"
                  disabled={props.batchLoading}
                  onClick={props.onSkipFailedTask}
                  aria-label="Skip failed chapters (batch_generation_skip_failed)"
                  type="button"
                >
                  {props.batchLoading ? "Working..." : "Skip failed chapters"}
                </button>
              ) : null}
              {canCancel ? (
                <button
                  className="btn btn-secondary"
                  disabled={props.batchLoading}
                  onClick={props.onCancelTask}
                  aria-label="Cancel batch generation (batch_generation_cancel)"
                  type="button"
                >
                  {props.batchLoading ? "Working..." : "Cancel batch"}
                </button>
              ) : null}
            </div>
          </div>

          {!task ? (
            <div className="text-sm text-subtext">No batch exists yet. Configure options and start one when ready.</div>
          ) : null}

          {task ? (
            <>
              <section
                className="grid gap-2 rounded-atelier border border-border bg-canvas p-3"
                aria-label="batch_generation_runtime_summary"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-ink">
                  <span>
                    Status: <span className="font-mono">{task.status}</span>
                  </span>
                  <span>
                    completed {task.completed_count}/{task.total_count} ? failed {task.failed_count} ? skipped{" "}
                    {task.skipped_count}
                  </span>
                </div>
                <ProgressBar ariaLabel="Batch generation progress" value={taskProgressPercent} />
                <div className="text-[11px] text-subtext">
                  pause_requested: {String(task.pause_requested)} ? cancel_requested: {String(task.cancel_requested)}
                </div>
                {requestId ? <div className="text-[11px] text-subtext">request_id: {requestId}</div> : null}
              </section>

              {latestCheckpoint ? (
                <section className="rounded-atelier border border-border bg-canvas p-3">
                  <div className="text-sm text-ink">Recovery point</div>
                  <div className="mt-2 grid gap-1 text-xs text-subtext">
                    <div>status: {readString(latestCheckpoint.status, task.status)}</div>
                    <div>completed_count: {readNumber(latestCheckpoint.completed_count, task.completed_count)}</div>
                    <div>failed_count: {readNumber(latestCheckpoint.failed_count, task.failed_count)}</div>
                    <div>skipped_count: {readNumber(latestCheckpoint.skipped_count, task.skipped_count)}</div>
                  </div>
                </section>
              ) : null}

              {task.error_json ? (
                <div className="rounded-atelier border border-border bg-canvas p-3">
                  <div className="text-sm text-ink">Error</div>
                  <div className="mt-1 break-words text-xs text-subtext">{task.error_json}</div>
                </div>
              ) : null}

              <details
                className="rounded-atelier border border-border bg-canvas p-3"
                aria-label="batch_generation_runtime_timeline"
              >
                <summary className="cursor-pointer select-none text-sm text-ink">Runtime timeline</summary>
                {timeline.length === 0 ? (
                  <div className="mt-2 text-xs text-subtext">No runtime events yet.</div>
                ) : (
                  <div className="mt-3 max-h-48 space-y-2 overflow-auto text-xs text-subtext">
                    {timeline.map((entry) => (
                      <div
                        key={`${entry.seq}-${entry.event_type}`}
                        className="rounded-atelier border border-border bg-surface px-3 py-2"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2 text-ink">
                          <span>
                            #{entry.seq} ? {entry.event_type}
                          </span>
                          <span>{entry.created_at || "-"}</span>
                        </div>
                        <div className="mt-1 text-subtext">
                          {entry.reason ? `reason: ${entry.reason}` : "reason: -"}
                          {entry.source ? ` ? source: ${entry.source}` : ""}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </details>

              <section
                className="max-h-72 overflow-auto rounded-atelier border border-border bg-canvas"
                aria-label="batch_generation_items"
              >
                {props.batchItems.length === 0 ? (
                  <div className="p-3 text-sm text-subtext">No batch items yet.</div>
                ) : (
                  <div className="divide-y divide-border">
                    {props.batchItems.map((item) => (
                      <div key={item.id} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2">
                        <div className="min-w-0 flex-1">
                          <div className="text-sm text-ink">Chapter {item.chapter_number}</div>
                          <div className="mt-1 break-words text-xs text-subtext">{buildStepLabel(item)}</div>
                          {item.started_at || item.finished_at ? (
                            <div className="mt-1 text-[11px] text-subtext">
                              started_at: {item.started_at || "-"} ? finished_at: {item.finished_at || "-"}
                            </div>
                          ) : null}
                        </div>
                        <div className="flex items-center gap-2">
                          {item.status === "succeeded" && item.chapter_id && item.generation_run_id ? (
                            <button
                              className="btn btn-secondary"
                              onClick={() => props.onApplyItemToEditor(item)}
                              disabled={props.batchLoading}
                              type="button"
                            >
                              Apply to editor
                            </button>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}
