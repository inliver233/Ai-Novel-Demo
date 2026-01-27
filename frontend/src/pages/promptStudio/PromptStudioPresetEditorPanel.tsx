import clsx from "clsx";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import { useCallback, useEffect, useMemo, useRef } from "react";

import type { PromptBlock } from "../../types";
import type { BlockDraft, PromptStudioTask } from "./types";
import { formatTriggers, parseTriggersWithValidation } from "./utils";

function highlightTemplateVariables(template: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /{{[\s\S]*?}}/g;
  let last = 0;
  let idx = 0;
  for (const m of template.matchAll(re)) {
    const start = m.index ?? 0;
    if (start > last) out.push(template.slice(last, start));
    const token = m[0] ?? "";
    out.push(
      <span key={`${start}-${idx}`} className="rounded bg-accent/15 px-0.5 text-accent">
        {token}
      </span>,
    );
    last = start + token.length;
    idx += 1;
  }
  if (last < template.length) out.push(template.slice(last));
  if (template.endsWith("\n")) out.push("\n");
  if (out.length === 0) out.push("");
  return out;
}

function HighlightedTemplateTextarea(props: { value: string; disabled: boolean; onChange: (next: string) => void }) {
  const { value, disabled, onChange } = props;
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const overlayContentRef = useRef<HTMLDivElement | null>(null);

  const highlighted = useMemo(() => highlightTemplateVariables(value), [value]);

  const syncOverlayScroll = useCallback(() => {
    const ta = textareaRef.current;
    const overlayContent = overlayContentRef.current;
    if (!ta || !overlayContent) return;
    overlayContent.style.transform = `translate(${-ta.scrollLeft}px, ${-ta.scrollTop}px)`;
  }, []);

  useEffect(() => {
    syncOverlayScroll();
  }, [syncOverlayScroll, value]);

  return (
    <div className="relative rounded-atelier bg-canvas">
      <div
        aria-hidden="true"
        className={clsx(
          "pointer-events-none absolute inset-0 overflow-hidden px-3 py-2 text-xs",
          disabled ? "opacity-60" : null,
        )}
      >
        <div ref={overlayContentRef} className="whitespace-pre-wrap break-words font-mono text-ink">
          {highlighted}
        </div>
      </div>

      <textarea
        ref={textareaRef}
        className="textarea atelier-mono min-h-[140px] resize-y bg-transparent py-2 text-xs text-transparent"
        style={{ caretColor: "rgb(var(--color-ink))" }}
        value={value}
        disabled={disabled}
        onScroll={syncOverlayScroll}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

export function PromptStudioPresetEditorPanel(props: {
  busy: boolean;
  selectedPresetId: string | null;
  tasks: PromptStudioTask[];
  presetDraftName: string;
  setPresetDraftName: (value: string) => void;
  presetDraftActiveFor: string[];
  setPresetDraftActiveFor: (value: string[]) => void;
  savePreset: () => Promise<void>;
  deletePreset: () => Promise<void>;
  blocks: PromptBlock[];
  drafts: Record<string, BlockDraft>;
  setDrafts: Dispatch<SetStateAction<Record<string, BlockDraft>>>;
  addBlock: () => Promise<void>;
  saveBlock: (blockId: string) => Promise<void>;
  deleteBlock: (blockId: string) => Promise<void>;
  onReorder: (orderedIds: string[]) => Promise<void>;
}) {
  const {
    addBlock,
    blocks,
    busy,
    deleteBlock,
    deletePreset,
    drafts,
    onReorder,
    presetDraftActiveFor,
    presetDraftName,
    saveBlock,
    savePreset,
    selectedPresetId,
    setDrafts,
    setPresetDraftActiveFor,
    setPresetDraftName,
    tasks,
  } = props;

  const taskKeySet = useMemo(() => new Set(tasks.map((t) => t.key)), [tasks]);
  const dragIdRef = useRef<string | null>(null);

  return (
    <>
      <div className="panel p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="text-sm font-semibold">预设设置</div>
          <div className="flex gap-2">
            <button
              className="btn btn-primary"
              onClick={() => void savePreset()}
              disabled={busy || !selectedPresetId}
              type="button"
            >
              保存预设
            </button>
            <button
              className="btn btn-ghost text-accent hover:bg-accent/10"
              onClick={() => void deletePreset()}
              disabled={busy || !selectedPresetId}
              type="button"
            >
              删除预设
            </button>
          </div>
        </div>

        <div className="grid gap-4">
          <div className="grid gap-2">
            <div className="text-xs text-subtext">名称</div>
            <input
              className="input"
              value={presetDraftName}
              onChange={(e) => setPresetDraftName(e.target.value)}
              disabled={busy}
            />
          </div>

          <div className="grid gap-2">
            <div className="text-xs text-subtext">active_for（哪些任务使用该预设）</div>
            <div className="flex flex-wrap gap-2">
              {tasks.map((t) => {
                const checked = presetDraftActiveFor.includes(t.key);
                return (
                  <label
                    key={t.key}
                    className={clsx(
                      "ui-transition-fast flex items-center gap-2 rounded-atelier border px-3 py-2 text-sm",
                      checked
                        ? "border-accent/40 bg-accent/10 text-ink"
                        : "border-border bg-canvas text-subtext hover:bg-surface hover:text-ink",
                      busy ? "opacity-60" : "cursor-pointer",
                    )}
                  >
                    <input
                      className="checkbox"
                      type="checkbox"
                      checked={checked}
                      disabled={busy}
                      onChange={(e) => {
                        const next = new Set(presetDraftActiveFor);
                        if (e.target.checked) next.add(t.key);
                        else next.delete(t.key);
                        setPresetDraftActiveFor([...next]);
                      }}
                    />
                    <span>{t.label}</span>
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      <div className="panel p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="text-sm font-semibold">提示块</div>
          <button
            className="btn btn-secondary"
            onClick={() => void addBlock()}
            disabled={busy || !selectedPresetId}
            type="button"
          >
            添加块
          </button>
        </div>

        <div className="grid gap-3">
          {blocks.length === 0 ? <div className="text-sm text-subtext">暂无块</div> : null}
          {blocks.map((b, idx) => {
            const d = drafts[b.id];
            const enabled = d?.enabled ?? b.enabled;
            const role = d?.role ?? b.role;
            const identifier = d?.identifier ?? b.identifier;
            const name = d?.name ?? b.name;
            const triggers = d?.triggers ?? formatTriggers(b.triggers ?? []);
            const triggerValidation = parseTriggersWithValidation(triggers);
            const triggerTokens = triggerValidation.triggers;
            const invalidTriggers = triggerValidation.invalid;
            const customTriggers = triggerTokens.filter((t) => !taskKeySet.has(t));
            const markerKey = d?.marker_key ?? b.marker_key ?? "";
            const template = d?.template ?? b.template ?? "";

            return (
              <div
                key={b.id}
                className="surface p-3"
                draggable
                onDragStart={() => {
                  dragIdRef.current = b.id;
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                }}
                onDrop={() => {
                  const fromId = dragIdRef.current;
                  dragIdRef.current = null;
                  if (!fromId || fromId === b.id) return;
                  const ids = blocks.map((x) => x.id);
                  const fromIdx = ids.indexOf(fromId);
                  const toIdx = ids.indexOf(b.id);
                  if (fromIdx < 0 || toIdx < 0) return;
                  ids.splice(fromIdx, 1);
                  const insertIdx = fromIdx < toIdx ? toIdx - 1 : toIdx;
                  ids.splice(insertIdx, 0, fromId);
                  void onReorder(ids);
                }}
                title="拖拽可调整排序"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="select-none text-subtext">≡</span>
                    <span className="text-xs text-subtext">#{idx + 1}</span>
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        className="checkbox"
                        type="checkbox"
                        checked={enabled}
                        disabled={busy}
                        onChange={(e) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [b.id]: {
                              identifier,
                              name,
                              role,
                              enabled: e.target.checked,
                              template,
                              marker_key: markerKey,
                              triggers,
                            },
                          }))
                        }
                      />
                      <span className="font-semibold">{name}</span>
                    </label>
                  </div>
                  <div className="flex gap-2">
                    <button
                      className="btn btn-secondary px-3 py-1 text-sm"
                      onClick={() => void saveBlock(b.id)}
                      disabled={busy || invalidTriggers.length > 0}
                      type="button"
                    >
                      保存
                    </button>
                    <button
                      className="btn btn-ghost px-3 py-1 text-sm text-accent hover:bg-accent/10"
                      onClick={() => void deleteBlock(b.id)}
                      disabled={busy}
                      type="button"
                    >
                      删除
                    </button>
                  </div>
                </div>

                <div className="mt-3 grid gap-3">
                  <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                    <div className="grid gap-1">
                      <div className="text-xs text-subtext">identifier</div>
                      <input
                        className="input"
                        value={identifier}
                        disabled={busy}
                        onChange={(e) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [b.id]: {
                              identifier: e.target.value,
                              name,
                              role,
                              enabled,
                              template,
                              marker_key: markerKey,
                              triggers,
                            },
                          }))
                        }
                      />
                    </div>
                    <div className="grid gap-1">
                      <div className="text-xs text-subtext">role</div>
                      <select
                        className="select"
                        value={role}
                        disabled={busy}
                        onChange={(e) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [b.id]: {
                              identifier,
                              name,
                              role: e.target.value,
                              enabled,
                              template,
                              marker_key: markerKey,
                              triggers,
                            },
                          }))
                        }
                      >
                        <option value="system">system</option>
                        <option value="user">user</option>
                        <option value="assistant">assistant</option>
                        <option value="tool">tool</option>
                      </select>
                    </div>
                  </div>

                  <div className="grid gap-1">
                    <div className="text-xs text-subtext">name</div>
                    <input
                      className="input"
                      value={name}
                      disabled={busy}
                      onChange={(e) =>
                        setDrafts((prev) => ({
                          ...prev,
                          [b.id]: {
                            identifier,
                            name: e.target.value,
                            role,
                            enabled,
                            template,
                            marker_key: markerKey,
                            triggers,
                          },
                        }))
                      }
                    />
                  </div>

                  <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                    <div className="grid gap-2">
                      <div className="text-xs text-subtext">triggers（按任务触发；不勾选=所有任务）</div>
                      <div className="flex flex-wrap gap-2">
                        {tasks.map((t) => {
                          const checked = triggerTokens.includes(t.key);
                          return (
                            <label
                              key={t.key}
                              className={clsx(
                                "ui-transition-fast flex items-center gap-2 rounded-atelier border px-3 py-2 text-sm",
                                checked
                                  ? "border-accent/40 bg-accent/10 text-ink"
                                  : "border-border bg-canvas text-subtext hover:bg-surface hover:text-ink",
                                busy ? "opacity-60" : "cursor-pointer",
                              )}
                            >
                              <input
                                className="checkbox"
                                type="checkbox"
                                checked={checked}
                                disabled={busy}
                                onChange={(e) => {
                                  const next = new Set(triggerTokens);
                                  if (e.target.checked) next.add(t.key);
                                  else next.delete(t.key);
                                  const nextOrdered = [
                                    ...tasks.filter((x) => next.has(x.key)).map((x) => x.key),
                                    ...customTriggers.filter((x) => next.has(x)),
                                  ];
                                  setDrafts((prev) => ({
                                    ...prev,
                                    [b.id]: {
                                      identifier,
                                      name,
                                      role,
                                      enabled,
                                      template,
                                      marker_key: markerKey,
                                      triggers: formatTriggers(nextOrdered),
                                    },
                                  }));
                                }}
                              />
                              <span>{t.key}</span>
                            </label>
                          );
                        })}
                      </div>
                      <div className="grid gap-1">
                        <div className="text-xs text-subtext">triggers（高级：逗号分隔；可自定义）</div>
                        <input
                          className="input"
                          value={triggers}
                          disabled={busy}
                          onChange={(e) =>
                            setDrafts((prev) => ({
                              ...prev,
                              [b.id]: {
                                identifier,
                                name,
                                role,
                                enabled,
                                template,
                                marker_key: markerKey,
                                triggers: e.target.value,
                              },
                            }))
                          }
                          placeholder="chapter_generate, outline_generate"
                        />
                        {customTriggers.length ? (
                          <div className="text-xs text-subtext">自定义：{customTriggers.join(", ")}</div>
                        ) : null}
                        {invalidTriggers.length ? (
                          <div className="text-xs text-accent">无效 triggers：{invalidTriggers.join(", ")}</div>
                        ) : null}
                      </div>
                    </div>
                    <div className="grid gap-1">
                      <div className="text-xs text-subtext">marker_key（可空）</div>
                      <input
                        className="input"
                        value={markerKey}
                        disabled={busy}
                        onChange={(e) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [b.id]: {
                              identifier,
                              name,
                              role,
                              enabled,
                              template,
                              marker_key: e.target.value,
                              triggers,
                            },
                          }))
                        }
                        placeholder="story.outline / user.instruction / ..."
                      />
                    </div>
                  </div>

                  <div className="grid gap-1">
                    <div className="text-xs text-subtext">template</div>
                    <HighlightedTemplateTextarea
                      value={template}
                      disabled={busy}
                      onChange={(next) =>
                        setDrafts((prev) => ({
                          ...prev,
                          [b.id]: {
                            identifier,
                            name,
                            role,
                            enabled,
                            template: next,
                            marker_key: markerKey,
                            triggers,
                          },
                        }))
                      }
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
