import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MarkdownEditor(props: {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  minRows?: number;
  mono?: boolean;
}) {
  const [tab, setTab] = useState<"edit" | "preview">("edit");

  return (
    <div className="rounded-atelier border border-border bg-canvas">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex gap-2 text-xs">
          <button
            className={tab === "edit" ? "text-ink" : "text-subtext hover:text-ink"}
            onClick={() => setTab("edit")}
            type="button"
          >
            编辑
          </button>
          <button
            className={tab === "preview" ? "text-ink" : "text-subtext hover:text-ink"}
            onClick={() => setTab("preview")}
            type="button"
          >
            预览
          </button>
        </div>
        <div className="text-xs text-subtext">{props.value.length} chars</div>
      </div>
      {tab === "edit" ? (
        <textarea
          className={(props.mono ? "atelier-mono" : "atelier-content") + " w-full resize-y bg-transparent px-3 py-3 text-ink outline-none"}
          placeholder={props.placeholder}
          rows={props.minRows ?? 12}
          value={props.value}
          onChange={(e) => props.onChange(e.target.value)}
        />
      ) : (
        <div className="atelier-content max-w-none px-3 py-4 text-ink">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{props.value || "_（空）_"}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}
