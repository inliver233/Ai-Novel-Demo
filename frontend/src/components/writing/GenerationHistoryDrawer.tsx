import { useCallback, useEffect, useId, useState } from "react";

import { ApiError, apiDownloadAttachment } from "../../services/apiClient";
import { Drawer } from "../ui/Drawer";
import { useToast } from "../ui/toast";
import type { GenerationRun } from "./types";

type Props = {
  open: boolean;
  onClose: () => void;
  loading: boolean;
  runs: GenerationRun[];
  selectedRun: GenerationRun | null;
  onSelectRun: (run: GenerationRun) => void;
};

export function GenerationHistoryDrawer(props: Props) {
  const { onClose, open } = props;
  const toast = useToast();
  const titleId = useId();
  const [downloading, setDownloading] = useState(false);

  const selectedRun = props.selectedRun;
  const paramsObj =
    selectedRun?.params && typeof selectedRun.params === "object"
      ? (selectedRun.params as Record<string, unknown>)
      : null;
  const memoryLogRaw = paramsObj?.memory_retrieval_log_json;
  const memoryLog = memoryLogRaw && typeof memoryLogRaw === "object" ? (memoryLogRaw as Record<string, unknown>) : null;
  const perSectionRaw = memoryLog?.per_section;
  const perSection =
    perSectionRaw && typeof perSectionRaw === "object" ? (perSectionRaw as Record<string, unknown>) : null;

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  const downloadDebugBundle = useCallback(async () => {
    if (!selectedRun) return;
    if (downloading) return;
    setDownloading(true);
    try {
      const { filename, blob, requestId } = await apiDownloadAttachment(
        `/api/generation_runs/${selectedRun.id}/debug_bundle`,
      );
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = filename || `debug_bundle_${selectedRun.id}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      toast.toastSuccess("已下载 debug bundle", requestId);
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setDownloading(false);
    }
  }, [downloading, selectedRun, toast]);

  return (
    <Drawer
      open={open}
      onClose={onClose}
      ariaLabelledBy={titleId}
      panelClassName="h-full w-full max-w-2xl border-l border-border bg-canvas p-6 shadow-sm"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-content text-2xl text-ink" id={titleId}>
            生成记录
          </div>
          <div className="mt-1 text-xs text-subtext">最近 5 条</div>
        </div>
        <button className="btn btn-secondary" aria-label="关闭" onClick={onClose} type="button">
          关闭
        </button>
      </div>

      <div className="mt-5 grid gap-4">
        {props.loading ? <div className="text-sm text-subtext">加载中...</div> : null}

        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-atelier border border-border bg-surface p-2">
            {props.runs.length === 0 ? (
              <div className="p-3 text-sm text-subtext">暂无生成记录。</div>
            ) : (
              <div className="flex flex-col gap-1">
                {props.runs.map((r) => {
                  const active = props.selectedRun?.id === r.id;
                  const failed = Boolean(r.error);
                  return (
                    <button
                      key={r.id}
                      className={
                        active
                          ? "ui-focus-ring ui-transition-fast rounded-atelier bg-canvas px-3 py-2 text-left text-sm text-ink"
                          : "ui-focus-ring ui-transition-fast rounded-atelier px-3 py-2 text-left text-sm text-subtext hover:bg-canvas hover:text-ink"
                      }
                      onClick={() => props.onSelectRun(r)}
                      type="button"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0 truncate">
                          <span className="mr-2 text-xs text-subtext">{new Date(r.created_at).toLocaleString()}</span>
                          <span className="truncate">{r.type}</span>
                        </div>
                        <span className="shrink-0 text-[11px] text-subtext">{failed ? "failed" : "ok"}</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="rounded-atelier border border-border bg-surface p-4">
            {!selectedRun ? (
              <div className="text-sm text-subtext">选择一条记录查看详情。</div>
            ) : (
              <div className="grid gap-3">
                <div className="text-sm text-ink">{selectedRun.type}</div>
                <div className="text-xs text-subtext">
                  {selectedRun.provider ?? "unknown"} / {selectedRun.model ?? "unknown"}
                </div>
                <div className="flex items-center gap-2 text-xs text-subtext">
                  <span className="truncate">run_id: {selectedRun.id}</span>
                  <button
                    className="btn btn-ghost px-2 py-1 text-xs"
                    onClick={async () => {
                      await navigator.clipboard.writeText(selectedRun.id ?? "");
                    }}
                    type="button"
                  >
                    复制
                  </button>
                </div>
                {selectedRun.request_id ? (
                  <div className="flex items-center gap-2 text-xs text-subtext">
                    <span className="truncate">request_id: {selectedRun.request_id}</span>
                    <button
                      className="btn btn-ghost px-2 py-1 text-xs"
                      onClick={async () => {
                        await navigator.clipboard.writeText(selectedRun.request_id ?? "");
                      }}
                      type="button"
                    >
                      复制
                    </button>
                  </div>
                ) : null}
                <div>
                  <button
                    className="btn btn-secondary"
                    disabled={downloading}
                    onClick={() => void downloadDebugBundle()}
                    type="button"
                  >
                    {downloading ? "下载中..." : "下载 debug bundle"}
                  </button>
                </div>

                {memoryLog ? (
                  <details open>
                    <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                      memory_retrieval_log_json
                    </summary>
                    <div className="mt-2 grid gap-2 text-xs text-subtext">
                      <div>
                        enabled: {String(memoryLog.enabled ?? "")} | phase: {String(memoryLog.phase ?? "")}
                      </div>
                      <div className="truncate">query_text: {String(memoryLog.query_text ?? "")}</div>
                      {Array.isArray(memoryLog.errors) && memoryLog.errors.length ? (
                        <div className="text-amber-600 dark:text-amber-400">errors: {memoryLog.errors.join(", ")}</div>
                      ) : null}
                    </div>

                    {perSection ? (
                      <div className="mt-3 grid gap-2">
                        {Object.entries(perSection)
                          .sort(([a], [b]) => a.localeCompare(b))
                          .map(([section, raw]) => {
                            const o = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
                            const enabled = Boolean(o.enabled);
                            const disabledReason = typeof o.disabled_reason === "string" ? o.disabled_reason : null;
                            return (
                              <div key={section} className="rounded-atelier border border-border bg-canvas p-2">
                                <div className="flex items-center justify-between gap-2 text-xs">
                                  <span className="font-mono text-ink">{section}</span>
                                  {enabled ? (
                                    <span className="text-emerald-600 dark:text-emerald-400">enabled</span>
                                  ) : (
                                    <span className="text-amber-600 dark:text-amber-400">
                                      disabled: {disabledReason ?? "unknown"}
                                    </span>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                      </div>
                    ) : (
                      <pre className="mt-2 max-h-40 overflow-auto rounded-atelier border border-border bg-canvas p-3 text-xs text-ink">
                        {JSON.stringify(memoryLog, null, 2)}
                      </pre>
                    )}
                  </details>
                ) : null}

                <details open>
                  <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                    params
                  </summary>
                  <pre className="mt-2 max-h-40 overflow-auto rounded-atelier border border-border bg-canvas p-3 text-xs text-ink">
                    {JSON.stringify(selectedRun.params ?? {}, null, 2)}
                  </pre>
                </details>
                <details>
                  <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                    prompt_system
                  </summary>
                  <pre className="mt-2 max-h-40 overflow-auto rounded-atelier border border-border bg-canvas p-3 text-xs text-ink">
                    {selectedRun.prompt_system ?? ""}
                  </pre>
                </details>
                <details>
                  <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                    prompt_user
                  </summary>
                  <pre className="mt-2 max-h-40 overflow-auto rounded-atelier border border-border bg-canvas p-3 text-xs text-ink">
                    {selectedRun.prompt_user ?? ""}
                  </pre>
                </details>
                <details open>
                  <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                    output / error
                  </summary>
                  <pre className="mt-2 max-h-56 overflow-auto rounded-atelier border border-border bg-canvas p-3 text-xs text-ink">
                    {selectedRun.error ? JSON.stringify(selectedRun.error, null, 2) : (selectedRun.output_text ?? "")}
                  </pre>
                </details>
              </div>
            )}
          </div>
        </div>
      </div>
    </Drawer>
  );
}
