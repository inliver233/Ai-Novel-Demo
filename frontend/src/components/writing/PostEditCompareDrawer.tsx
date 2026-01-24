import { useEffect, useId, useMemo, useState } from "react";

import { Drawer } from "../ui/Drawer";

type Props = {
  open: boolean;
  onClose: () => void;
  rawContentMd: string;
  editedContentMd: string;
  requestId: string | null;
  appliedChoice: "raw" | "post_edit";
  onApplyRaw: () => void;
  onApplyPostEdit: () => void;
};

type ViewMode = "diff" | "raw" | "post_edit";

function buildNaiveUnifiedLineDiff(raw: string, edited: string): string {
  const rawLines = raw.split("\n");
  const editedLines = edited.split("\n");
  const max = Math.max(rawLines.length, editedLines.length);

  const out: string[] = [];
  for (let i = 0; i < max; i++) {
    const r = rawLines[i];
    const e = editedLines[i];
    if (r === e) {
      out.push(`  ${r ?? ""}`);
      continue;
    }
    if (typeof r === "string") out.push(`- ${r}`);
    if (typeof e === "string") out.push(`+ ${e}`);
  }
  return out.join("\n");
}

export function PostEditCompareDrawer(props: Props) {
  const { onClose, open } = props;
  const titleId = useId();
  const [mode, setMode] = useState<ViewMode>("diff");

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

  const raw = String(props.rawContentMd ?? "");
  const edited = String(props.editedContentMd ?? "");

  const diffText = useMemo(() => buildNaiveUnifiedLineDiff(raw, edited), [edited, raw]);

  const applyRaw = () => {
    props.onApplyRaw();
    onClose();
  };

  const applyPostEdit = () => {
    props.onApplyPostEdit();
    onClose();
  };

  const hasDiff = raw.trim() !== edited.trim();

  return (
    <Drawer
      open={open}
      onClose={onClose}
      side="bottom"
      ariaLabelledBy={titleId}
      panelClassName="h-[85vh] w-full overflow-y-auto rounded-atelier border-t border-border bg-canvas p-6 shadow-sm sm:h-full sm:max-w-3xl sm:rounded-none sm:border-l sm:border-t-0"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-content text-2xl text-ink" id={titleId}>
            润色对比
          </div>
          <div className="mt-1 text-xs text-subtext">
            {props.requestId ? (
              <>
                request_id: <span className="font-mono">{props.requestId}</span>
              </>
            ) : (
              "request_id: （未知）"
            )}
          </div>
        </div>
        <button className="btn btn-secondary" onClick={onClose} type="button">
          关闭
        </button>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-subtext">视图</span>
          {(["diff", "raw", "post_edit"] as const).map((v) => (
            <button
              key={v}
              className={mode === v ? "btn btn-primary" : "btn btn-secondary"}
              onClick={() => setMode(v)}
              type="button"
            >
              {v === "diff" ? "差异" : v === "raw" ? "原稿" : "后处理稿"}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            className={props.appliedChoice === "raw" ? "btn btn-primary" : "btn btn-secondary"}
            onClick={applyRaw}
            type="button"
          >
            采用原稿
          </button>
          <button
            className={props.appliedChoice === "post_edit" ? "btn btn-primary" : "btn btn-secondary"}
            onClick={applyPostEdit}
            type="button"
          >
            采用后处理稿
          </button>
        </div>
      </div>

      <div className="mt-3 text-[11px] text-subtext">
        {hasDiff ? "提示：- 为原稿行，+ 为后处理行。" : "提示：原稿与后处理稿内容一致，无差异。"}
      </div>

      <div className="mt-4">
        {mode === "raw" ? (
          <pre className="max-h-[60vh] overflow-auto rounded-atelier border border-border bg-surface p-4 text-xs text-ink">
            {raw || "（空）"}
          </pre>
        ) : mode === "post_edit" ? (
          <pre className="max-h-[60vh] overflow-auto rounded-atelier border border-border bg-surface p-4 text-xs text-ink">
            {edited || "（空）"}
          </pre>
        ) : (
          <pre className="max-h-[60vh] overflow-auto rounded-atelier border border-border bg-surface p-4 text-xs text-ink">
            {hasDiff ? diffText : "（无差异）"}
          </pre>
        )}
      </div>
    </Drawer>
  );
}
