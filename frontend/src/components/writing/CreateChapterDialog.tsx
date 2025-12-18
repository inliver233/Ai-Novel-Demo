import { useEffect, type Dispatch, type SetStateAction } from "react";

import type { CreateChapterForm } from "./types";

type Props = {
  open: boolean;
  saving: boolean;
  form: CreateChapterForm;
  setForm: Dispatch<SetStateAction<CreateChapterForm>>;
  onClose: () => void;
  onSubmit: () => void;
};

export function CreateChapterDialog(props: Props) {
  const { onClose, open, saving } = props;

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (saving) return;
      e.preventDefault();
      onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open, saving]);

  if (!open) return null;

  return (
    <div
      aria-label="新增章节"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
      onClick={(e) => {
        if (saving) return;
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
    >
      <div className="w-full max-w-lg rounded-atelier border border-border bg-canvas p-5 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-content text-xl text-ink">新增章节</div>
            <div className="mt-1 text-xs text-subtext">章号 / 标题 / 要点</div>
          </div>
          <button
            className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink hover:bg-canvas"
            onClick={onClose}
            type="button"
          >
            关闭
          </button>
        </div>

        <div className="mt-4 grid gap-3">
          <label className="grid gap-1">
            <span className="text-xs text-subtext">章号</span>
            <input
              className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink outline-none"
              min={1}
              name="number"
              type="number"
              value={props.form.number}
              onChange={(e) => props.setForm((v) => ({ ...v, number: Number(e.target.value) }))}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-subtext">标题</span>
            <input
              className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink outline-none"
              name="title"
              value={props.form.title}
              onChange={(e) => props.setForm((v) => ({ ...v, title: e.target.value }))}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-subtext">要点</span>
            <textarea
              className="atelier-content w-full rounded-atelier border border-border bg-surface px-3 py-3 text-ink outline-none"
              name="plan"
              rows={4}
              value={props.form.plan}
              onChange={(e) => props.setForm((v) => ({ ...v, plan: e.target.value }))}
            />
          </label>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink hover:bg-canvas"
            onClick={onClose}
            type="button"
          >
            取消
          </button>
          <button
            className="rounded-atelier bg-accent px-3 py-2 text-sm text-white hover:opacity-90 disabled:opacity-60"
            disabled={saving}
            onClick={props.onSubmit}
            type="button"
          >
            {saving ? "创建中..." : "创建"}
          </button>
        </div>
      </div>
    </div>
  );
}
