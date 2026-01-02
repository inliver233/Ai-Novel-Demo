import { Modal } from "../ui/Modal";

import type { BatchGenerationTask, BatchGenerationTaskItem } from "./types";

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
  onClose: () => void;
  onCancelTask: () => void;
  onStartTask: () => void;
  onApplyItemToEditor: (item: BatchGenerationTaskItem) => void;
}) {
  return (
    <Modal
      open={props.open}
      onClose={props.batchLoading ? undefined : props.onClose}
      panelClassName="surface max-w-2xl p-5"
      ariaLabel="批量生成"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-content text-xl text-ink">批量顺序生成</div>
          <div className="mt-1 text-xs text-subtext">
            批量生成只会写入“生成记录”，不会自动保存到章节；你可以逐章“应用到编辑器”后再保存。
          </div>
        </div>
        <button className="btn btn-secondary" onClick={props.onClose} disabled={props.batchLoading} type="button">
          关闭
        </button>
      </div>

      <div className="mt-4 grid gap-3">
        <div className="grid gap-2 rounded-atelier border border-border bg-canvas p-3">
          <div className="text-xs text-subtext">
            起点：{props.activeChapterNumber ? `第 ${props.activeChapterNumber} 章之后` : "从第 1 章开始"}
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="grid gap-1">
              <span className="text-xs text-subtext">数量（1~20）</span>
              <input
                className="input w-28"
                min={1}
                max={20}
                type="number"
                value={props.batchCount}
                onChange={(e) => props.setBatchCount(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
              />
            </label>
            <label className="flex items-center gap-2 pb-2 text-sm text-ink">
              <input
                className="checkbox"
                type="checkbox"
                checked={props.batchIncludeExisting}
                disabled={props.batchLoading}
                onChange={(e) => props.setBatchIncludeExisting(e.target.checked)}
              />
              包含已有内容章节
            </label>
            <div className="flex-1" />
            {props.batchTask && (props.batchTask.status === "queued" || props.batchTask.status === "running") ? (
              <button
                className="btn btn-secondary"
                disabled={props.batchLoading}
                onClick={props.onCancelTask}
                type="button"
              >
                {props.batchLoading ? "取消中..." : "取消任务"}
              </button>
            ) : (
              <button
                className="btn btn-primary"
                disabled={props.batchLoading}
                onClick={props.onStartTask}
                type="button"
              >
                {props.batchLoading ? "启动中..." : "开始批量生成"}
              </button>
            )}
          </div>
        </div>

        {props.batchTask ? (
          <div className="grid gap-2 rounded-atelier border border-border bg-surface p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm text-ink">
                任务状态：{props.batchTask.status}（{props.batchTask.completed_count}/{props.batchTask.total_count}）
              </div>
              {props.batchTask.status === "failed" && props.batchTask.error_json ? (
                <div className="text-xs text-subtext">错误：{props.batchTask.error_json}</div>
              ) : null}
            </div>
            <div className="h-2 w-full rounded bg-border">
              <div
                className="h-2 rounded bg-accent motion-safe:transition-[width] motion-safe:duration-atelier motion-safe:ease-atelier"
                style={{
                  width: `${Math.round(
                    (props.batchTask.total_count > 0
                      ? props.batchTask.completed_count / props.batchTask.total_count
                      : 0) * 100,
                  )}%`,
                }}
              />
            </div>
            <div className="max-h-64 overflow-auto rounded-atelier border border-border bg-canvas">
              {props.batchItems.length === 0 ? (
                <div className="p-3 text-sm text-subtext">暂无任务项</div>
              ) : (
                <div className="divide-y divide-border">
                  {props.batchItems.map((it) => (
                    <div key={it.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                      <div className="min-w-0">
                        <div className="text-sm text-ink">第 {it.chapter_number} 章</div>
                        <div className="text-xs text-subtext">
                          {it.status}
                          {it.error_message ? ` · ${it.error_message}` : ""}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {it.status === "succeeded" && it.chapter_id && it.generation_run_id ? (
                          <button
                            className="btn btn-secondary"
                            onClick={() => props.onApplyItemToEditor(it)}
                            disabled={props.batchLoading}
                            type="button"
                          >
                            应用到编辑器
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="text-sm text-subtext">当前没有进行中的任务。</div>
        )}
      </div>
    </Modal>
  );
}
