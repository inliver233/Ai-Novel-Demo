import { getLatestRuntimeCheckpoint, type ProjectTaskRuntime } from "../../services/projectTaskRuntime";
import { StatusBadge } from "./StatusBadge";

function readNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function readString(value: unknown, fallback = "-"): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

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
          <div className="text-sm text-ink">Runtime</div>
          <button
            className="btn btn-secondary btn-sm"
            aria-label="Refresh runtime detail (taskcenter_projecttask_runtime_refresh)"
            onClick={props.onRefresh}
            type="button"
          >
            Refresh runtime
          </button>
        </div>
        {props.loading ? <div className="mt-2 text-xs text-subtext">Loading...</div> : null}
        {!props.loading && !props.runtime ? (
          <div className="mt-2 text-xs text-subtext">No unified runtime data yet.</div>
        ) : null}
        {props.runtime ? (
          <div className="mt-2 grid gap-1 text-xs text-subtext">
            <div>timeline: {props.runtime.timeline.length}</div>
            <div>checkpoints: {props.runtime.checkpoints.length}</div>
            <div>steps: {props.runtime.steps.length}</div>
            <div>artifacts: {props.runtime.artifacts.length}</div>
            {latestCheckpoint ? (
              <div>
                last_checkpoint: {readString(latestCheckpoint.status)} ? completed{" "}
                {readNumber(latestCheckpoint.completed_count)} ? failed {readNumber(latestCheckpoint.failed_count)} ?
                skipped {readNumber(latestCheckpoint.skipped_count)}
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      {batch ? (
        <section className="rounded-atelier border border-border bg-surface p-3" aria-label="projecttask_runtime_batch">
          <div className="text-sm text-ink">Batch</div>
          <div className="mt-2 grid gap-1 text-xs text-subtext">
            <div className="flex flex-wrap items-center gap-2">
              <span>Status:</span>
              <StatusBadge status={batch.task.status} kind="task" />
            </div>
            <div>
              completed {batch.task.completed_count}/{batch.task.total_count} ? failed {batch.task.failed_count} ?
              skipped {batch.task.skipped_count}
            </div>
            <div>
              pause_requested: {String(batch.task.pause_requested)} ? cancel_requested:{" "}
              {String(batch.task.cancel_requested)}
            </div>
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
                {props.actionLoading ? "Working..." : "Pause"}
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
                {props.actionLoading ? "Working..." : "Resume"}
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
                {props.actionLoading ? "Working..." : "Retry failed chapters"}
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
                {props.actionLoading ? "Working..." : "Skip failed chapters"}
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
                {props.actionLoading ? "Working..." : "Cancel batch"}
              </button>
            ) : null}
          </div>
          <div
            className="mt-3 max-h-64 overflow-auto rounded-atelier border border-border bg-canvas"
            aria-label="projecttask_runtime_batch_items"
          >
            {batchItems.length === 0 ? (
              <div className="p-3 text-xs text-subtext">No batch steps yet.</div>
            ) : (
              <div className="divide-y divide-border">
                {batchItems.map((item) => (
                  <div key={item.id} className="grid gap-1 px-3 py-2 text-xs text-subtext">
                    <div className="text-ink">Chapter {item.chapter_number}</div>
                    <div>
                      {item.status} ? attempt {item.attempt_count}
                      {item.last_request_id ? ` ? request_id ${item.last_request_id}` : ""}
                    </div>
                    {item.error_message ? <div className="text-danger">{item.error_message}</div> : null}
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
          <div className="text-sm text-ink">Artifacts</div>
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
                    Open generation run
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
          <div className="text-sm text-ink">Timeline</div>
          {props.runtime.timeline.length === 0 ? (
            <div className="mt-2 text-xs text-subtext">No timeline events yet.</div>
          ) : (
            <div className="mt-3 max-h-72 space-y-2 overflow-auto">
              {props.runtime.timeline.map((entry) => (
                <div
                  key={`${entry.seq}-${entry.event_type}`}
                  className="rounded-atelier border border-border bg-canvas px-3 py-2 text-xs text-subtext"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 text-ink">
                    <span>
                      #{entry.seq} ? {entry.event_type}
                    </span>
                    <span>{entry.created_at || "-"}</span>
                  </div>
                  <div className="mt-1">
                    {entry.reason ? `reason: ${entry.reason}` : "reason: -"}
                    {entry.source ? ` ? source: ${entry.source}` : ""}
                  </div>
                  {entry.step && typeof entry.step === "object" ? (
                    <div className="mt-1">
                      chapter {readNumber((entry.step as Record<string, unknown>).chapter_number)} ? status{" "}
                      {readString((entry.step as Record<string, unknown>).status)}
                    </div>
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
