import clsx from "clsx";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ApiError } from "../../services/apiClient";
import type { StoryMemory } from "../../services/storyMemoryApi";
import {
  createStoryMemory,
  deleteStoryMemory,
  markStoryMemoryDone,
  mergeStoryMemories,
  updateStoryMemory,
} from "../../services/storyMemoryApi";
import { UI_COPY } from "../../lib/uiCopy";
import { Drawer } from "../ui/Drawer";
import { useConfirm } from "../ui/confirm";
import { useToast } from "../ui/toast";
import type { MemoryAnnotation } from "./types";
import { labelForAnnotationType, sortKeyForAnnotationType } from "./types";

function normalizeTitle(annotation: MemoryAnnotation): string {
  const title = (annotation.title ?? "").trim();
  if (title) return title;
  const content = (annotation.content ?? "").trim();
  if (content) return content.slice(0, 60);
  return "（无标题）";
}

type StoryMemoryForm = {
  memory_type: string;
  title: string;
  content: string;
  tags_raw: string;
  importance_score: number;
  text_position: number;
  text_length: number;
};

function parseTags(raw: string): string[] {
  const tokens = String(raw || "")
    .split(/[\n,，;；]/g)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const t of tokens) {
    const k = t.toLowerCase();
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(t);
    if (out.length >= 80) break;
  }
  return out;
}

function joinTags(tags: string[] | null | undefined): string {
  return (tags ?? []).filter(Boolean).join("\n");
}

function isDone(a: MemoryAnnotation): boolean {
  const meta = a.metadata;
  if (!meta || typeof meta !== "object") return false;
  const value = (meta as Record<string, unknown>).done;
  return Boolean(value);
}

function toForm(a: MemoryAnnotation | null): StoryMemoryForm {
  return {
    memory_type: String(a?.type ?? "plot_point") || "plot_point",
    title: String(a?.title ?? ""),
    content: String(a?.content ?? ""),
    tags_raw: joinTags(a?.tags ?? []),
    importance_score: Number.isFinite(a?.importance) ? Number(a?.importance) : 0.0,
    text_position: Number.isFinite(a?.position) ? Number(a?.position) : -1,
    text_length: Number.isFinite(a?.length) ? Number(a?.length) : 0,
  };
}

const TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "chapter_summary", label: labelForAnnotationType("chapter_summary") },
  { value: "hook", label: labelForAnnotationType("hook") },
  { value: "foreshadow", label: labelForAnnotationType("foreshadow") },
  { value: "plot_point", label: labelForAnnotationType("plot_point") },
  { value: "character_state", label: labelForAnnotationType("character_state") },
  { value: "other", label: "其他" },
];

export function MemorySidebar(props: {
  projectId?: string;
  chapterId?: string | null;
  annotations: MemoryAnnotation[];
  validIds: Set<string>;
  activeAnnotationId?: string | null;
  onSelect: (annotation: MemoryAnnotation) => void;
  onRefresh?: () => Promise<void> | void;
  onSetActiveAnnotationId?: (id: string | null) => void;
}) {
  const toast = useToast();
  const confirm = useConfirm();

  const allTypes = useMemo(() => {
    const counts = new Map<string, number>();
    for (const a of props.annotations) {
      counts.set(a.type, (counts.get(a.type) ?? 0) + 1);
    }
    return Array.from(counts.entries())
      .map(([type, count]) => ({ type, count }))
      .sort(
        (a, b) => sortKeyForAnnotationType(a.type) - sortKeyForAnnotationType(b.type) || a.type.localeCompare(b.type),
      );
  }, [props.annotations]);

  const [enabledTypes, setEnabledTypes] = useState<Set<string>>(() => new Set(allTypes.map((t) => t.type)));
  const prevAllTypesRef = useRef<Set<string>>(new Set(allTypes.map((t) => t.type)));

  useEffect(() => {
    const prevTypes = prevAllTypesRef.current;
    const nextTypes = new Set(allTypes.map((t) => t.type));
    prevAllTypesRef.current = nextTypes;

    const newlyAdded: string[] = [];
    for (const t of nextTypes) {
      if (!prevTypes.has(t)) newlyAdded.push(t);
    }
    if (!newlyAdded.length) return;

    setEnabledTypes((prev) => {
      const out = new Set(prev);
      for (const t of newlyAdded) out.add(t);
      return out;
    });
  }, [allTypes]);

  const filtered = useMemo(() => {
    const out = props.annotations.filter((a) => enabledTypes.has(a.type));
    out.sort(
      (a, b) => sortKeyForAnnotationType(a.type) - sortKeyForAnnotationType(b.type) || b.importance - a.importance,
    );
    return out;
  }, [enabledTypes, props.annotations]);

  const groups = useMemo(() => {
    const map = new Map<string, MemoryAnnotation[]>();
    for (const a of filtered) {
      const list = map.get(a.type) ?? [];
      list.push(a);
      map.set(a.type, list);
    }
    return Array.from(map.entries()).sort(
      (a, b) => sortKeyForAnnotationType(a[0]) - sortKeyForAnnotationType(b[0]) || a[0].localeCompare(b[0]),
    );
  }, [filtered]);

  const invalidCount = props.annotations.length - props.validIds.size;

  const active = useMemo(() => {
    const id = props.activeAnnotationId;
    if (!id) return null;
    return props.annotations.find((a) => a.id === id) ?? null;
  }, [props.activeAnnotationId, props.annotations]);

  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<MemoryAnnotation | null>(null);
  const [form, setForm] = useState<StoryMemoryForm>(() => toForm(null));
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);

  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeSources, setMergeSources] = useState<Set<string>>(() => new Set());
  const [mergeSaving, setMergeSaving] = useState(false);
  const mergeSavingRef = useRef(false);

  const openCreate = useCallback(() => {
    setEditing(null);
    setForm(toForm(null));
    setEditorOpen(true);
  }, []);

  const openEdit = useCallback(() => {
    if (!active) return;
    setEditing(active);
    setForm(toForm(active));
    setEditorOpen(true);
  }, [active]);

  const closeEditor = useCallback(() => {
    if (savingRef.current) return;
    setEditorOpen(false);
  }, []);

  const saveStoryMemory = useCallback(async () => {
    const projectId = props.projectId;
    if (!projectId) {
      toast.toastError("缺少 projectId：无法保存");
      return;
    }
    if (!String(form.content || "").trim()) {
      toast.toastWarning("内容不能为空");
      return;
    }
    if (savingRef.current) return;

    savingRef.current = true;
    setSaving(true);
    try {
      const memoryType = String(form.memory_type || "").trim() || "plot_point";
      const body = {
        chapter_id: props.chapterId ?? null,
        memory_type: memoryType,
        title: form.title.trim() ? form.title.trim() : null,
        content: String(form.content || ""),
        importance_score: Number.isFinite(form.importance_score) ? Number(form.importance_score) : 0.0,
        tags: parseTags(form.tags_raw),
        text_position: Number.isFinite(form.text_position) ? Number(form.text_position) : -1,
        text_length: Number.isFinite(form.text_length) ? Math.max(0, Number(form.text_length)) : 0,
        is_foreshadow: memoryType === "foreshadow",
      };

      let saved: StoryMemory;
      if (editing) saved = await updateStoryMemory(projectId, editing.id, body);
      else saved = await createStoryMemory(projectId, body);

      toast.toastSuccess(editing ? "已保存剧情记忆" : "已新增剧情记忆");
      props.onSetActiveAnnotationId?.(saved.id);
      await props.onRefresh?.();
      setEditorOpen(false);
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`保存失败：${err.message} (${err.code})`, err.requestId);
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }, [
    editing,
    form.content,
    form.importance_score,
    form.memory_type,
    form.tags_raw,
    form.text_length,
    form.text_position,
    form.title,
    props,
    toast,
  ]);

  const deleteSelected = useCallback(async () => {
    const projectId = props.projectId;
    if (!projectId) {
      toast.toastError("缺少 projectId：无法删除");
      return;
    }
    if (!active) return;
    const ok = await confirm.confirm({
      title: "删除该条剧情记忆？",
      description: `将删除「${normalizeTitle(active)}」。此操作不可撤销。`,
      confirmText: "删除",
      cancelText: "取消",
      danger: true,
    });
    if (!ok) return;

    setSaving(true);
    try {
      await deleteStoryMemory(projectId, active.id);
      toast.toastSuccess("已删除剧情记忆");
      props.onSetActiveAnnotationId?.(null);
      await props.onRefresh?.();
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`删除失败：${err.message} (${err.code})`, err.requestId);
    } finally {
      setSaving(false);
    }
  }, [active, confirm, props, toast]);

  const toggleDone = useCallback(async () => {
    const projectId = props.projectId;
    if (!projectId) {
      toast.toastError("缺少 projectId：无法操作");
      return;
    }
    if (!active) return;
    const done = isDone(active);

    setSaving(true);
    try {
      await markStoryMemoryDone(projectId, active.id, !done);
      toast.toastSuccess(!done ? "已标记完成" : "已取消完成");
      await props.onRefresh?.();
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`操作失败：${err.message} (${err.code})`, err.requestId);
    } finally {
      setSaving(false);
    }
  }, [active, props, toast]);

  const openMerge = useCallback(() => {
    if (!active) return;
    setMergeSources(new Set());
    setMergeOpen(true);
  }, [active]);

  const closeMerge = useCallback(() => {
    if (mergeSavingRef.current) return;
    setMergeOpen(false);
  }, []);

  const mergeCandidates = useMemo(() => {
    if (!active) return [];
    const out = props.annotations.filter((a) => a.id !== active.id);
    out.sort(
      (a, b) => sortKeyForAnnotationType(a.type) - sortKeyForAnnotationType(b.type) || b.importance - a.importance,
    );
    return out;
  }, [active, props.annotations]);

  const applyMerge = useCallback(async () => {
    const projectId = props.projectId;
    if (!projectId) {
      toast.toastError("缺少 projectId：无法合并");
      return;
    }
    if (!active) return;
    const sourceIds = Array.from(mergeSources);
    if (sourceIds.length === 0) {
      toast.toastWarning("请先选择要合并的条目");
      return;
    }
    const ok = await confirm.confirm({
      title: "确认合并？",
      description: `将把 ${sourceIds.length} 条剧情记忆合并到「${normalizeTitle(active)}」，并删除被合并条目。`,
      confirmText: "合并",
      cancelText: "取消",
    });
    if (!ok) return;

    if (mergeSavingRef.current) return;
    mergeSavingRef.current = true;
    setMergeSaving(true);
    try {
      await mergeStoryMemories(projectId, { targetId: active.id, sourceIds });
      toast.toastSuccess("已合并剧情记忆");
      setMergeOpen(false);
      setMergeSources(new Set());
      props.onSetActiveAnnotationId?.(active.id);
      await props.onRefresh?.();
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`合并失败：${err.message} (${err.code})`, err.requestId);
    } finally {
      mergeSavingRef.current = false;
      setMergeSaving(false);
    }
  }, [active, confirm, mergeSources, props, toast]);

  const selectedInfo = useMemo(() => {
    if (!active) return null;
    const done = isDone(active);
    const valid = props.validIds.has(active.id);
    return { done, valid };
  }, [active, props.validIds]);

  return (
    <aside className="min-w-0 grid gap-2" aria-label="story_memory_sidebar">
      <div className="rounded-atelier border border-border bg-surface p-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm text-ink">{UI_COPY.chapterAnalysis.storyMemoryTitle}</div>
            <div className="mt-1 text-xs text-subtext">
              共 {props.annotations.length} 条{invalidCount > 0 ? `（${invalidCount} 条未定位）` : ""}
            </div>
            <div className="mt-2 callout-info">{UI_COPY.chapterAnalysis.storyMemorySubtitle}</div>
          </div>
          <button
            className="btn btn-primary px-3 py-1 text-xs"
            type="button"
            onClick={openCreate}
            disabled={saving}
            aria-label="story_memory_create"
          >
            新增剧情记忆
          </button>
        </div>

        <div className="mt-2 flex flex-wrap gap-2">
          {allTypes.map((t) => {
            const enabled = enabledTypes.has(t.type);
            return (
              <button
                key={t.type}
                className={clsx("btn btn-ghost px-2 py-1 text-xs", enabled ? "bg-canvas text-ink" : "text-subtext")}
                type="button"
                onClick={() => {
                  setEnabledTypes((prev) => {
                    const next = new Set(prev);
                    if (next.has(t.type)) next.delete(t.type);
                    else next.add(t.type);
                    if (next.size === 0) return new Set([t.type]);
                    return next;
                  });
                }}
                aria-pressed={enabled}
                title={enabled ? "点击取消过滤" : "点击启用过滤"}
              >
                {labelForAnnotationType(t.type)}
                <span className="ml-1 text-subtext">· {t.count}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="rounded-atelier border border-border bg-surface p-2">
        {groups.length === 0 ? (
          <div className="p-3 text-sm text-subtext">暂无记忆。请先在写作页分析并“保存到记忆库”。</div>
        ) : (
          <div className="grid gap-3">
            {groups.map(([type, list]) => (
              <section key={type} className="grid gap-2">
                <div className="px-1 text-xs text-subtext">
                  {labelForAnnotationType(type)} · {list.length}
                </div>
                <div className="grid gap-2">
                  {list.map((a) => {
                    const selected = props.activeAnnotationId === a.id;
                    const valid = props.validIds.has(a.id);
                    const done = isDone(a);
                    return (
                      <button
                        key={a.id}
                        className={clsx(
                          "ui-transition-fast w-full rounded-atelier border px-3 py-2 text-left",
                          selected ? "border-accent bg-canvas" : "border-border bg-canvas hover:bg-surface",
                          !valid && "opacity-70",
                        )}
                        type="button"
                        onClick={() => props.onSelect(a)}
                        aria-label={`story_memory_item:${normalizeTitle(a)}`}
                        title={valid ? "点击定位到正文" : "未定位：无法在正文中高亮"}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <div className="truncate text-sm text-ink">{normalizeTitle(a)}</div>
                              {done ? (
                                <span className="rounded bg-success/20 px-1.5 py-0.5 text-[11px] text-ink">已完成</span>
                              ) : null}
                            </div>
                            <div className="mt-1 line-clamp-2 break-words text-xs text-subtext">
                              {(a.content ?? "").trim().slice(0, 140)}
                            </div>
                          </div>
                          <div className="shrink-0 text-right">
                            <div className="text-xs text-subtext">{(a.importance * 10).toFixed(1)}</div>
                            {!valid ? <div className="mt-1 text-xs text-accent">未定位</div> : null}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-atelier border border-border bg-surface p-2">
        <div className="grid gap-2">
          <div className="min-w-0">
            <div className="text-xs text-subtext">{active ? "已选中" : "未选择"}</div>
            <div className="mt-1 truncate text-sm text-ink">
              {active ? normalizeTitle(active) : "请先在上方选择条目"}
            </div>
            {active ? (
              <div className="mt-1 text-[11px] text-subtext">
                类型：{labelForAnnotationType(active.type)} · 重要度：{(active.importance * 10).toFixed(1)} ·{" "}
                {selectedInfo?.valid ? "可定位" : "未定位"}
                {selectedInfo?.done ? " · 已完成" : ""}
              </div>
            ) : (
              <div className="mt-1 text-[11px] text-subtext">
                提示：点击上方条目可定位到正文，并在此处进行编辑/合并/完成标记/删除。
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              className="btn btn-secondary px-3 py-1 text-xs"
              type="button"
              onClick={openEdit}
              disabled={!active || saving}
              aria-label="story_memory_edit"
            >
              编辑
            </button>
            <button
              className="btn btn-secondary px-3 py-1 text-xs"
              type="button"
              onClick={toggleDone}
              disabled={!active || saving}
              aria-label="story_memory_toggle_done"
            >
              {selectedInfo?.done ? "取消完成" : "标记完成"}
            </button>
            <button
              className="btn btn-secondary px-3 py-1 text-xs"
              type="button"
              onClick={openMerge}
              disabled={!active || saving || props.annotations.length < 2}
              aria-label="story_memory_merge"
            >
              合并
            </button>
            <button
              className="btn btn-danger px-3 py-1 text-xs"
              type="button"
              onClick={() => void deleteSelected()}
              disabled={!active || saving}
              aria-label="story_memory_delete"
            >
              删除
            </button>
          </div>
        </div>
      </div>

      <Drawer
        open={editorOpen}
        onClose={closeEditor}
        panelClassName="h-full w-full max-w-xl border-l border-border bg-canvas p-6 shadow-sm"
        ariaLabel={editing ? "编辑剧情记忆" : "新增剧情记忆"}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-content text-2xl text-ink">{editing ? "编辑剧情记忆" : "新增剧情记忆"}</div>
            <div className="mt-1 text-xs text-subtext">
              {saving ? "保存中..." : "可直接编辑后保存（失败不影响正文）"}
            </div>
          </div>
          <div className="flex gap-2">
            <button
              className="btn btn-secondary"
              type="button"
              onClick={closeEditor}
              disabled={saving}
              aria-label="story_memory_close"
            >
              关闭
            </button>
            <button
              className="btn btn-primary"
              type="button"
              onClick={() => void saveStoryMemory()}
              disabled={saving || !form.content.trim()}
              aria-label="story_memory_save"
            >
              保存
            </button>
          </div>
        </div>

        <div className="mt-5 grid gap-4">
          <label className="grid gap-1">
            <span className="text-xs text-subtext">类型</span>
            <select
              className="select"
              value={form.memory_type}
              onChange={(e) => setForm((v) => ({ ...v, memory_type: e.target.value }))}
              aria-label="story_memory_type"
              disabled={saving}
            >
              {TYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>

          <label className="grid gap-1">
            <span className="text-xs text-subtext">标题（可选）</span>
            <input
              className="input"
              value={form.title}
              onChange={(e) => setForm((v) => ({ ...v, title: e.target.value }))}
              placeholder="例如：主角发现异常线索"
              disabled={saving}
              aria-label="story_memory_title"
            />
          </label>

          <label className="grid gap-1">
            <span className="text-xs text-subtext">内容</span>
            <textarea
              className="textarea atelier-content"
              rows={10}
              value={form.content}
              onChange={(e) => setForm((v) => ({ ...v, content: e.target.value }))}
              placeholder="写下可复用、可检索的剧情记忆条目…"
              disabled={saving}
              aria-label="story_memory_content"
            />
          </label>

          <label className="grid gap-1">
            <span className="text-xs text-subtext">标签（可选，每行一个）</span>
            <textarea
              className="textarea"
              rows={4}
              value={form.tags_raw}
              onChange={(e) => setForm((v) => ({ ...v, tags_raw: e.target.value }))}
              placeholder="例如：伏笔\n人物状态\n时间线"
              disabled={saving}
              aria-label="story_memory_tags"
            />
          </label>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="grid gap-1">
              <span className="text-xs text-subtext">重要度（0~1，侧栏显示为 *10）</span>
              <input
                className="input"
                type="number"
                step="0.05"
                min="0"
                max="1"
                value={Number.isFinite(form.importance_score) ? form.importance_score : 0}
                onChange={(e) => setForm((v) => ({ ...v, importance_score: Number(e.target.value) }))}
                disabled={saving}
                aria-label="story_memory_importance"
              />
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="grid gap-1">
                <span className="text-xs text-subtext">定位 position</span>
                <input
                  className="input"
                  type="number"
                  value={Number.isFinite(form.text_position) ? form.text_position : -1}
                  onChange={(e) => setForm((v) => ({ ...v, text_position: Number(e.target.value) }))}
                  disabled={saving}
                  aria-label="story_memory_position"
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs text-subtext">定位 length</span>
                <input
                  className="input"
                  type="number"
                  min="0"
                  value={Number.isFinite(form.text_length) ? form.text_length : 0}
                  onChange={(e) => setForm((v) => ({ ...v, text_length: Number(e.target.value) }))}
                  disabled={saving}
                  aria-label="story_memory_length"
                />
              </label>
            </div>
          </div>

          <div className="text-[11px] text-subtext">
            说明：position/length 用于“回溯定位”。若不确定可留空（-1/0），系统会尝试用内容片段做 fallback 定位。
          </div>
        </div>
      </Drawer>

      <Drawer
        open={mergeOpen}
        onClose={closeMerge}
        panelClassName="h-full w-full max-w-xl border-l border-border bg-canvas p-6 shadow-sm"
        ariaLabel="合并剧情记忆"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-content text-2xl text-ink">合并剧情记忆</div>
            <div className="mt-1 text-xs text-subtext">
              目标：{active ? normalizeTitle(active) : "（未选择）"} · 已选 {mergeSources.size} 条
            </div>
          </div>
          <div className="flex gap-2">
            <button className="btn btn-secondary" type="button" onClick={closeMerge} disabled={mergeSaving}>
              关闭
            </button>
            <button
              className="btn btn-primary"
              type="button"
              onClick={() => void applyMerge()}
              disabled={mergeSaving || mergeSources.size === 0 || !active}
              aria-label="story_memory_merge_apply"
            >
              合并
            </button>
          </div>
        </div>

        <div className="mt-5 grid gap-2">
          {mergeCandidates.length === 0 ? (
            <div className="rounded-atelier border border-border bg-surface p-3 text-sm text-subtext">
              当前章节没有可合并的其他条目。
            </div>
          ) : (
            mergeCandidates.map((a) => {
              const checked = mergeSources.has(a.id);
              return (
                <label
                  key={a.id}
                  className={clsx(
                    "flex cursor-pointer items-start gap-3 rounded-atelier border bg-surface px-3 py-2",
                    checked ? "border-accent" : "border-border",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => {
                      setMergeSources((prev) => {
                        const next = new Set(prev);
                        if (e.target.checked) next.add(a.id);
                        else next.delete(a.id);
                        return next;
                      });
                    }}
                    aria-label={`story_memory_merge_source:${normalizeTitle(a)}`}
                    disabled={mergeSaving}
                    className="checkbox mt-1"
                  />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <div className="truncate text-sm text-ink">{normalizeTitle(a)}</div>
                      <div className="text-xs text-subtext">{labelForAnnotationType(a.type)}</div>
                    </div>
                    <div className="mt-1 line-clamp-2 break-words text-xs text-subtext">
                      {(a.content ?? "").trim().slice(0, 160)}
                    </div>
                  </div>
                </label>
              );
            })
          )}
        </div>
      </Drawer>
    </aside>
  );
}
