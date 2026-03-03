import { useCallback, useId, useLayoutEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { LayoutGroup, motion, useReducedMotion } from "framer-motion";
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
  textareaRef?: (el: HTMLTextAreaElement | null) => void;
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
  const internalTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const userChangeRef = useRef(false);
  const followOutputRef = useRef(true);
  const lastScrollTopRef = useRef(0);
  const reduceMotion = useReducedMotion();
  const tabIndicatorTransition = reduceMotion ? { duration: 0.01 } : transition.fast;

  const setTextareaRef = useCallback(
    (el: HTMLTextAreaElement | null) => {
      internalTextareaRef.current = el;
      textareaRef?.(el);
    },
    [textareaRef],
  );

  useLayoutEffect(() => {
    if (tab !== "edit") return;
    const el = internalTextareaRef.current;
    if (!el) return;
    if (userChangeRef.current) {
      userChangeRef.current = false;
      return;
    }
    if (followOutputRef.current) {
      el.scrollTop = el.scrollHeight;
      lastScrollTopRef.current = el.scrollTop;
      return;
    }
    el.scrollTop = Math.min(el.scrollHeight, lastScrollTopRef.current);
  }, [tab, value]);
  const setTab = (next: EditorTab) => {
    if (onTabChange) onTabChange(next);
    else setInternalTab(next);
  };
  const isReadOnly = Boolean(readOnly);

  return (
    <div className="surface ui-transition-fast focus-within:border-accent/40">
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
                  transition={tabIndicatorTransition}
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
                  transition={tabIndicatorTransition}
                />
              ) : null}
              <span className="relative z-10">预览</span>
            </button>
          </div>
        </LayoutGroup>
        <div className="text-xs text-subtext">字数：{value.length}</div>
      </div>
      {tab === "edit" ? (
        <textarea
          className={clsx(
            mono ? "atelier-mono" : "atelier-content",
            "w-full resize-y bg-transparent px-3 py-3 text-ink outline-none placeholder:text-subtext/70",
          )}
          ref={setTextareaRef}
          name={name}
          placeholder={placeholder}
          readOnly={isReadOnly}
          rows={minRows ?? 12}
          value={value}
          onScroll={(e) => {
            const el = e.currentTarget;
            lastScrollTopRef.current = el.scrollTop;
            const atBottom = el.scrollHeight - el.clientHeight - el.scrollTop <= 24;
            followOutputRef.current = atBottom;
          }}
          onChange={(e) => {
            if (isReadOnly) return;
            userChangeRef.current = true;
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
