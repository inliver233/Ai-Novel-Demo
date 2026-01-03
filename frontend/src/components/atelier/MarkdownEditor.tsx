import { useId, useState } from "react";
import type { Ref } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { LayoutGroup, motion } from "framer-motion";
import clsx from "clsx";

import { transition } from "../../lib/motion";

type EditorTab = "edit" | "preview";

type MarkdownEditorProps = {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  minRows?: number;
  mono?: boolean;
  name?: string;
  readOnly?: boolean;
  tab?: EditorTab;
  onTabChange?: (next: EditorTab) => void;
  textareaRef?: Ref<HTMLTextAreaElement>;
};

export function MarkdownEditor({
  value,
  onChange,
  placeholder,
  minRows,
  mono,
  name,
  readOnly,
  tab: controlledTab,
  onTabChange,
  textareaRef,
}: MarkdownEditorProps) {
  const [internalTab, setInternalTab] = useState<EditorTab>("edit");
  const tab = controlledTab ?? internalTab;
  const motionGroupId = useId();
  const tabIndicatorLayoutId = `atelier-markdown-editor-tab-${motionGroupId}`;
  const setTab = (next: EditorTab) => {
    if (onTabChange) onTabChange(next);
    else setInternalTab(next);
  };
  const isReadOnly = Boolean(readOnly);

  return (
    <div className="surface ui-transition-fast focus-within:border-accent/40 focus-within:ring-1 focus-within:ring-accent focus-within:ring-offset-2 focus-within:ring-offset-canvas">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <LayoutGroup id={`atelier-markdown-editor-tabs-${motionGroupId}`}>
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
                  layoutId={tabIndicatorLayoutId}
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
                  layoutId={tabIndicatorLayoutId}
                  className="absolute inset-0 rounded-atelier bg-canvas"
                  transition={transition.fast}
                />
              ) : null}
              <span className="relative z-10">预览</span>
            </button>
          </div>
        </LayoutGroup>
        <div className="text-xs text-subtext">{value.length} chars</div>
      </div>
      {tab === "edit" ? (
        <textarea
          className={clsx(
            mono ? "atelier-mono" : "atelier-content",
            "w-full resize-y bg-transparent px-3 py-3 text-ink outline-none placeholder:text-subtext/70",
          )}
          ref={textareaRef}
          name={name}
          placeholder={placeholder}
          readOnly={isReadOnly}
          rows={minRows ?? 12}
          value={value}
          onChange={(e) => {
            if (isReadOnly) return;
            onChange(e.target.value);
          }}
        />
      ) : (
        <div className="atelier-content max-w-none px-3 py-4 text-ink">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{value || "_（空）_"}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}
