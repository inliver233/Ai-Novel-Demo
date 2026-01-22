import { useEffect, useId, type Dispatch, type SetStateAction } from "react";

import { Modal } from "../ui/Modal";
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
  const titleId = useId();

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

  return (
    <Modal
      open={open}
      onClose={saving ? undefined : onClose}
      panelClassName="surface max-w-lg p-5"
      ariaLabelledBy={titleId}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-content text-xl text-ink" id={titleId}>
            新增章节
          </div>
          <div className="mt-1 text-xs text-subtext">章号 / 标题 / 要点</div>
        </div>
        <button className="btn btn-secondary" aria-label="关闭" onClick={onClose} disabled={saving} type="button">
          关闭
        </button>
      </div>

      <div className="mt-4 grid gap-3">
        <label className="grid gap-1">
          <span className="text-xs text-subtext">章号</span>
          <input
            className="input"
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
            className="input"
            name="title"
            value={props.form.title}
            onChange={(e) => props.setForm((v) => ({ ...v, title: e.target.value }))}
          />
        </label>
        <label className="grid gap-1">
          <span className="text-xs text-subtext">要点</span>
          <textarea
            className="textarea atelier-content"
            name="plan"
            rows={4}
            value={props.form.plan}
            onChange={(e) => props.setForm((v) => ({ ...v, plan: e.target.value }))}
          />
        </label>
      </div>

      <div className="mt-5 flex justify-end gap-2">
        <button className="btn btn-secondary" onClick={onClose} disabled={saving} type="button">
          取消
        </button>
        <button className="btn btn-primary" disabled={saving} onClick={props.onSubmit} type="button">
          {saving ? "创建中..." : "创建"}
        </button>
      </div>
    </Modal>
  );
}
