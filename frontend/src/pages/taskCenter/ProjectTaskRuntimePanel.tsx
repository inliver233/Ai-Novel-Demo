import { getLatestRuntimeCheckpoint, type ProjectTaskRuntime } from "../../services/projectTaskRuntime";
import { StatusBadge } from "./StatusBadge";
import { TASK_CENTER_COPY } from "./taskCenterCopy";
import {
  formatRuntimeBatchFlags,
  formatRuntimeBatchItemSummary,
  formatRuntimeBatchProgress,
  formatRuntimeCheckpointSummary,
  formatRuntimeTimelineMeta,
  formatRuntimeTimelineStep,
  formatTaskCenterErrorText,
} from "./taskCenterModels";

export function ProjectTaskRuntimePanel(props: {
  runtime: ProjectTaskRuntime | null;
  loading: boolean;
  actionLoading: boolean;
  onRefresh: () => void;
  onPauseBatch: () => void;
  onResumeBatch: () => void;
  onRetryFailedBatch: () => void;
  onSkipFailedBatch: () => void;
  onCancelBatch: () => void;
}) {
  const batch = props.runtime?.batch ?? null;
  const batchItems = batch?.items ?? [];
  const failedItems = batchItems.filter((item) => item.status === "failed");
  const latestCheckpoint = getLatestRuntimeCheckpoint(props.runtime);
  const canPause = Boolean(batch && (batch.task.status === "queued" || batch.task.status === "running"));
  const canResume = Boolean(batch && batch.task.status === "paused" && failedItems.length === 0);
  const canRetryFailed = Boolean(batch && batch.task.status === "paused" && failedItems.length > 0);
  const canSkipFailed = Boolean(batch && batch.task.status === "paused" && failedItems.length > 0);
  const canCancel = Boolean(
    batch && (batch.task.status === "queued" || batch.task.status === "running" || batch.task.status === "paused"),
  );

  return (
    <>
      <section
        className="rounded-atelier border border-border bg-surface p-3"
        aria-label="projecttask_runtime_overview"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm text-ink">{TASK_CENTER_COPY.runtimeTitle}</div>
          <button
            className="btn btn-secondary btn-sm"
            aria-label="Refresh runtime detail (taskcenter_projecttask_runtime_refresh)"
            onClick={props.onRefresh}
            type="button"
          >
            {TASK_CENTER_COPY.runtimeRefreshButton}
          </button>
        </div>
        {props.loading ? <div className="mt-2 text-xs text-subtext">{TASK_CENTER_COPY.loading}</div> : null}
        {!props.loading && !props.runtime ? (
          <div className="mt-2 text-xs text-subtext">{TASK_CENTER_COPY.runtimeEmpty}</div>
        ) : null}
        {props.runtime ? (
          <div className="mt-2 grid gap-1 text-xs text-subtext">
            <div>timeline: {props.runtime.timeline.length}</div>
            <div>checkpoints: {props.runtime.checkpoints.length}</div>
            <div>steps: {props.runtime.steps.length}</div>
            <div>artifacts: {props.runtime.artifacts.length}</div>
            {latestCheckpoint ? <div>{formatRuntimeCheckpointSummary(latestCheckpoint)}</div> : null}
          </div>
        ) : null}
      </section>

      {batch ? (
        <section className="rounded-atelier border border-border bg-surface p-3" aria-label="projecttask_runtime_batch">
          <div className="text-sm text-ink">{TASK_CENTER_COPY.runtimeBatchTitle}</div>
          <div className="mt-2 grid gap-1 text-xs text-subtext">
            <div className="flex flex-wrap items-center gap-2">
              <span>Status:</span>
              <StatusBadge status={batch.task.status} kind="task" />
            </div>
            <div>{formatRuntimeBatchProgress(batch.task)}</div>
            <div>{formatRuntimeBatchFlags(batch.task)}</div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {canPause ? (
              <button
                className="btn btn-secondary btn-sm"
                aria-label="Pause batch (taskcenter_batch_pause)"
                disabled={props.actionLoading}
                onClick={props.onPauseBatch}
                type="button"
              >
                {props.actionLoading ? TASK_CENTER_COPY.runtimeBatchWorking : TASK_CENTER_COPY.runtimeBatchPause}
              </button>
            ) : null}
            {canResume ? (
              <button
                className="btn btn-secondary btn-sm"
                aria-label="Resume batch (taskcenter_batch_resume)"
                disabled={props.actionLoading}
                onClick={props.onResumeBatch}
                type="button"
              >
                {props.actionLoading ? TASK_CENTER_COPY.runtimeBatchWorking : TASK_CENTER_COPY.runtimeBatchResume}
              </button>
            ) : null}
            {canRetryFailed ? (
              <button
                className="btn btn-secondary btn-sm"
                aria-label="Retry failed chapters (taskcenter_batch_retry_failed)"
                disabled={props.actionLoading}
                onClick={props.onRetryFailedBatch}
                type="button"
              >
                {props.actionLoading ? TASK_CENTER_COPY.runtimeBatchWorking : TASK_CENTER_COPY.runtimeBatchRetryFailed}
              </button>
            ) : null}
            {canSkipFailed ? (
              <button
                className="btn btn-secondary btn-sm"
                aria-label="Skip failed chapters (taskcenter_batch_skip_failed)"
                disabled={props.actionLoading}
                onClick={props.onSkipFailedBatch}
                type="button"
              >
                {props.actionLoading ? TASK_CENTER_COPY.runtimeBatchWorking : TASK_CENTER_COPY.runtimeBatchSkipFailed}
              </button>
            ) : null}
            {canCancel ? (
              <button
                className="btn btn-secondary btn-sm"
                aria-label="Cancel batch (taskcenter_batch_cancel)"
                disabled={props.actionLoading}
                onClick={props.onCancelBatch}
                type="button"
              >
                {props.actionLoading ? TASK_CENTER_COPY.runtimeBatchWorking : TASK_CENTER_COPY.runtimeBatchCancel}
              </button>
            ) : null}
          </div>
          <div
            className="mt-3 max-h-64 overflow-auto rounded-atelier border border-border bg-canvas"
            aria-label="projecttask_runtime_batch_items"
          >
            {batchItems.length === 0 ? (
              <div className="p-3 text-xs text-subtext">{TASK_CENTER_COPY.runtimeNoBatchItems}</div>
            ) : (
              <div className="divide-y divide-border">
                {batchItems.map((item) => (
                  <div key={item.id} className="grid gap-1 px-3 py-2 text-xs text-subtext">
                    <div className="text-ink">Chapter {item.chapter_number}</div>
                    <div>{formatRuntimeBatchItemSummary(item)}</div>
                    {item.error_message ? (
                      <div className="text-danger">{formatTaskCenterErrorText(null, item.error_message)}</div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      ) : null}

      {props.runtime?.artifacts.length ? (
        <section
          className="rounded-atelier border border-border bg-surface p-3"
          aria-label="projecttask_runtime_artifacts"
        >
          <div className="text-sm text-ink">{TASK_CENTER_COPY.runtimeArtifactsTitle}</div>
          <div className="mt-2 grid gap-2 text-xs text-subtext">
            {props.runtime.artifacts.map((artifact) => (
              <div key={`${artifact.kind}-${artifact.id}`} className="flex flex-wrap items-center gap-2">
                <span>
                  {artifact.kind}: <span className="font-mono text-ink">{artifact.id}</span>
                </span>
                {artifact.kind === "generation_run" ? (
                  <a
                    className="btn btn-secondary btn-sm"
                    href={`/api/generation_runs/${encodeURIComponent(artifact.id)}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {TASK_CENTER_COPY.runtimeOpenGenerationRun}
                  </a>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {props.runtime ? (
        <section
          className="rounded-atelier border border-border bg-surface p-3"
          aria-label="projecttask_runtime_timeline"
        >
          <div className="text-sm text-ink">{TASK_CENTER_COPY.runtimeTimelineTitle}</div>
          {props.runtime.timeline.length === 0 ? (
            <div className="mt-2 text-xs text-subtext">{TASK_CENTER_COPY.runtimeNoTimeline}</div>
          ) : (
            <div className="mt-3 max-h-72 space-y-2 overflow-auto">
              {props.runtime.timeline.map((entry) => (
                <div
                  key={`${entry.seq}-${entry.event_type}`}
                  className="rounded-atelier border border-border bg-canvas px-3 py-2 text-xs text-subtext"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 text-ink">
                    <span>
                      #{entry.seq} | {entry.event_type}
                    </span>
                    <span>{entry.created_at || "-"}</span>
                  </div>
                  <div className="mt-1">{formatRuntimeTimelineMeta(entry)}</div>
                  {formatRuntimeTimelineStep(entry.step) ? (
                    <div className="mt-1">{formatRuntimeTimelineStep(entry.step)}</div>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </section>
      ) : null}
    </>
  );
}
