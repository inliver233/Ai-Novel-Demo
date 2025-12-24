import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { LayoutGroup, motion } from "framer-motion";
import clsx from "clsx";

import { transition } from "../../lib/motion";

export function MarkdownEditor(props: {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  minRows?: number;
  mono?: boolean;
  name?: string;
  readOnly?: boolean;
}) {
  const [tab, setTab] = useState<"edit" | "preview">("edit");

  return (
    <div className="surface ui-transition-fast focus-within:border-accent/40 focus-within:ring-1 focus-within:ring-accent focus-within:ring-offset-2 focus-within:ring-offset-canvas">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <LayoutGroup id="atelier-markdown-editor-tabs">
          <div className="flex gap-1 rounded-atelier bg-surface p-1 text-xs">
            <button
              className={clsx(
                "ui-focus-ring ui-transition-fast relative rounded-atelier px-2 py-1",
                tab === "edit" ? "text-ink" : "text-subtext hover:text-ink",
              )}
              onClick={() => setTab("edit")}
              type="button"
            >
              {tab === "edit" ? (
                <motion.span
                  layoutId="atelier-markdown-editor-tab"
                  className="absolute inset-0 rounded-atelier bg-canvas"
                  transition={transition.fast}
                />
              ) : null}
              <span className="relative z-10">编辑</span>
            </button>
            <button
              className={clsx(
                "ui-focus-ring ui-transition-fast relative rounded-atelier px-2 py-1",
                tab === "preview" ? "text-ink" : "text-subtext hover:text-ink",
              )}
              onClick={() => setTab("preview")}
              type="button"
            >
              {tab === "preview" ? (
                <motion.span
                  layoutId="atelier-markdown-editor-tab"
                  className="absolute inset-0 rounded-atelier bg-canvas"
                  transition={transition.fast}
                />
              ) : null}
              <span className="relative z-10">预览</span>
            </button>
          </div>
        </LayoutGroup>
        <div className="text-xs text-subtext">{props.value.length} chars</div>
      </div>
      {tab === "edit" ? (
        <textarea
          className={clsx(
            props.mono ? "atelier-mono" : "atelier-content",
            "w-full resize-y bg-transparent px-3 py-3 text-ink outline-none placeholder:text-subtext/70",
          )}
          name={props.name}
          placeholder={props.placeholder}
          readOnly={Boolean(props.readOnly)}
          rows={props.minRows ?? 12}
          value={props.value}
          onChange={(e) => {
            if (props.readOnly) return;
            props.onChange(e.target.value);
          }}
        />
      ) : (
        <div className="atelier-content max-w-none px-3 py-4 text-ink">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{props.value || "_（空）_"}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}
