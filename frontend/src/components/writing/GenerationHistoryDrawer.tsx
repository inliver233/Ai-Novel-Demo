import { useEffect } from "react";

import { Drawer } from "../ui/Drawer";
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

  const selectedRun = props.selectedRun;

  return (
    <Drawer
      open={open}
      onClose={onClose}
      ariaLabel="生成记录"
      panelClassName="h-full w-full max-w-2xl border-l border-border bg-canvas p-6 shadow-sm"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-content text-2xl text-ink">生成记录</div>
          <div className="mt-1 text-xs text-subtext">最近 5 条</div>
        </div>
        <button className="btn btn-secondary" onClick={onClose} type="button">
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
