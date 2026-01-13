import { useCallback, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { Drawer } from "../components/ui/Drawer";
import { useConfirm } from "../components/ui/confirm";
import { useToast } from "../components/ui/toast";
import { useProjectData } from "../hooks/useProjectData";
import { UI_COPY } from "../lib/uiCopy";
import type { ApiError } from "../services/apiClient";
import {
  createWorldBookEntry,
  deleteWorldBookEntry,
  listWorldBookEntries,
  previewWorldBookTrigger,
  type WorldBookEntry,
  type WorldBookPreviewTriggerResult,
  type WorldBookPriority,
  updateWorldBookEntry,
} from "../services/worldbookApi";

type WorldBookEntryForm = {
  title: string;
  content_md: string;
  enabled: boolean;
  constant: boolean;
  keywords_raw: string;
  exclude_recursion: boolean;
  prevent_recursion: boolean;
  char_limit: number;
  priority: WorldBookPriority;
};

function parseKeywords(raw: string): string[] {
  const tokens = raw
    .split(/[\n,，;；]/g)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const t of tokens) {
    const key = t.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(t);
  }
  return out;
}

function joinKeywords(keywords: string[]): string {
  return (keywords ?? []).filter(Boolean).join("\n");
}

function toForm(entry: WorldBookEntry | null): WorldBookEntryForm {
  return {
    title: entry?.title ?? "",
    content_md: entry?.content_md ?? "",
    enabled: entry?.enabled ?? true,
    constant: entry?.constant ?? false,
    keywords_raw: joinKeywords(entry?.keywords ?? []),
    exclude_recursion: entry?.exclude_recursion ?? false,
    prevent_recursion: entry?.prevent_recursion ?? false,
    char_limit: entry?.char_limit ?? 12000,
    priority: entry?.priority ?? "important",
  };
}

export function WorldBookPage() {
  const { projectId } = useParams();
  const toast = useToast();
  const confirm = useConfirm();

  const entriesQuery = useProjectData<WorldBookEntry[]>(projectId, async (id) => listWorldBookEntries(id));
  const entries = entriesQuery.data ?? [];
  const loading = entriesQuery.loading;
  const setEntries = entriesQuery.setData;

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<WorldBookEntry | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);

  const [baseline, setBaseline] = useState<WorldBookEntryForm | null>(null);
  const [form, setForm] = useState<WorldBookEntryForm>(() => toForm(null));

  const dirty = useMemo(() => {
    if (!baseline) return false;
    return (
      form.title !== baseline.title ||
      form.content_md !== baseline.content_md ||
      form.enabled !== baseline.enabled ||
      form.constant !== baseline.constant ||
      form.keywords_raw !== baseline.keywords_raw ||
      form.exclude_recursion !== baseline.exclude_recursion ||
      form.prevent_recursion !== baseline.prevent_recursion ||
      form.char_limit !== baseline.char_limit ||
      form.priority !== baseline.priority
    );
  }, [baseline, form]);

  const openNew = () => {
    setEditing(null);
    const next = toForm(null);
    setForm(next);
    setBaseline(next);
    setDrawerOpen(true);
  };

  const openEdit = (entry: WorldBookEntry) => {
    setEditing(entry);
    const next = toForm(entry);
    setForm(next);
    setBaseline(next);
    setDrawerOpen(true);
  };

  const closeDrawer = useCallback(async () => {
    if (dirty) {
      const ok = await confirm.confirm({
        title: UI_COPY.worldbook.discardChangesTitle,
        description: UI_COPY.worldbook.discardChangesDesc,
        confirmText: UI_COPY.worldbook.discardChangesConfirm,
        cancelText: UI_COPY.worldbook.discardChangesCancel,
        danger: true,
      });
      if (!ok) return;
    }
    setDrawerOpen(false);
  }, [confirm, dirty]);

  const saveEntry = useCallback(async () => {
    if (!projectId) return;
    if (!form.title.trim()) {
      toast.toastError(UI_COPY.worldbook.validationTitleRequired);
      return;
    }
    if (savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    try {
      const payload = {
        title: form.title.trim(),
        content_md: form.content_md ?? "",
        enabled: Boolean(form.enabled),
        constant: Boolean(form.constant),
        keywords: parseKeywords(form.keywords_raw),
        exclude_recursion: Boolean(form.exclude_recursion),
        prevent_recursion: Boolean(form.prevent_recursion),
        char_limit: Number.isFinite(form.char_limit) ? Math.max(0, Math.floor(form.char_limit)) : 12000,
        priority: form.priority,
      };
      const saved = editing
        ? await updateWorldBookEntry(editing.id, payload)
        : await createWorldBookEntry(projectId, payload);
      setEntries((prev) => {
        const list = prev ?? [];
        const idx = list.findIndex((e) => e.id === saved.id);
        if (idx >= 0) return list.map((e) => (e.id === saved.id ? saved : e));
        return [saved, ...list];
      });
      const nextBaseline = toForm(saved);
      setBaseline(nextBaseline);
      setForm((prev) => {
        if (
          prev.title === form.title &&
          prev.content_md === form.content_md &&
          prev.enabled === form.enabled &&
          prev.constant === form.constant &&
          prev.keywords_raw === form.keywords_raw &&
          prev.exclude_recursion === form.exclude_recursion &&
          prev.prevent_recursion === form.prevent_recursion &&
          prev.char_limit === form.char_limit &&
          prev.priority === form.priority
        ) {
          return nextBaseline;
        }
        return prev;
      });
      toast.toastSuccess(UI_COPY.worldbook.saved);
      setEditing(saved);
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setSaving(false);
      savingRef.current = false;
    }
  }, [editing, form, projectId, setEntries, toast]);

  const deleteEntry = useCallback(async () => {
    if (!editing) return;
    const ok = await confirm.confirm({
      title: UI_COPY.worldbook.deleteTitle,
      description: UI_COPY.worldbook.deleteDesc,
      confirmText: UI_COPY.worldbook.deleteConfirm,
      cancelText: UI_COPY.worldbook.deleteCancel,
      danger: true,
    });
    if (!ok) return;

    setSaving(true);
    try {
      await deleteWorldBookEntry(editing.id);
      setEntries((prev) => (prev ?? []).filter((e) => e.id !== editing.id));
      toast.toastSuccess(UI_COPY.worldbook.deleted);
      setDrawerOpen(false);
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setSaving(false);
    }
  }, [confirm, editing, setEntries, toast]);

  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewRequestId, setPreviewRequestId] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<{ message: string; code: string; requestId?: string } | null>(null);
  const [previewQueryText, setPreviewQueryText] = useState("");
  const [previewIncludeConstant, setPreviewIncludeConstant] = useState(true);
  const [previewEnableRecursion, setPreviewEnableRecursion] = useState(true);
  const [previewCharLimit, setPreviewCharLimit] = useState(12000);
  const [previewResult, setPreviewResult] = useState<WorldBookPreviewTriggerResult | null>(null);

  const runPreview = useCallback(async () => {
    if (!projectId) {
      setPreviewError({ message: UI_COPY.worldbook.missingProjectId, code: "NO_PROJECT" });
      return;
    }
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const safeCharLimit = Number.isFinite(previewCharLimit) ? Math.max(0, Math.floor(previewCharLimit)) : 12000;
      const res = await previewWorldBookTrigger(projectId, {
        query_text: previewQueryText,
        include_constant: previewIncludeConstant,
        enable_recursion: previewEnableRecursion,
        char_limit: safeCharLimit,
      });
      setPreviewResult(res.data);
      setPreviewRequestId(res.request_id ?? null);
    } catch (e) {
      const err = e as ApiError;
      setPreviewError({ message: err.message, code: err.code, requestId: err.requestId });
      setPreviewResult(null);
      setPreviewRequestId(null);
    } finally {
      setPreviewLoading(false);
    }
  }, [previewCharLimit, previewEnableRecursion, previewIncludeConstant, previewQueryText, projectId]);

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm text-subtext">
          {UI_COPY.worldbook.entriesCountPrefix}
          {entries.length}
          {UI_COPY.worldbook.entriesCountSuffix}
        </div>
        <div className="flex gap-2">
          <button className="btn btn-secondary" onClick={() => void entriesQuery.refresh()} type="button">
            {UI_COPY.worldbook.refresh}
          </button>
          <button className="btn btn-primary" onClick={openNew} type="button">
            {UI_COPY.worldbook.create}
          </button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="panel p-4">
          <div className="text-sm text-ink">{UI_COPY.worldbook.entriesTitle}</div>
          <div className="mt-1 text-xs text-subtext">{UI_COPY.worldbook.entriesHint}</div>

          {loading ? <div className="mt-3 text-sm text-subtext">{UI_COPY.common.loading}</div> : null}

          <div className="mt-4 grid gap-3">
            {entries.length === 0 ? (
              <div className="text-sm text-subtext">{UI_COPY.worldbook.empty}</div>
            ) : (
              entries.map((e) => (
                <button
                  key={e.id}
                  className="panel-interactive ui-focus-ring p-4 text-left"
                  onClick={() => openEdit(e)}
                  type="button"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate font-content text-lg text-ink">{e.title}</div>
                      <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-subtext">
                        <span>{e.enabled ? UI_COPY.worldbook.tagEnabled : UI_COPY.worldbook.tagDisabled}</span>
                        <span>{e.constant ? UI_COPY.worldbook.tagBlue : UI_COPY.worldbook.tagGreen}</span>
                        <span>{UI_COPY.worldbook.tagPriorityPrefix + e.priority}</span>
                        <span>{UI_COPY.worldbook.tagCharLimitPrefix + e.char_limit}</span>
                      </div>
                    </div>
                    <div className="shrink-0 text-[11px] text-subtext">{e.updated_at}</div>
                  </div>
                  {e.constant ? null : (
                    <div className="mt-2 line-clamp-2 text-xs text-subtext">
                      {UI_COPY.worldbook.keywordsPrefix}
                      {(e.keywords ?? []).slice(0, 6).join("、") || UI_COPY.worldbook.keywordsNone}
                    </div>
                  )}
                </button>
              ))
            )}
          </div>
        </div>

        <div className="panel p-4">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="text-sm text-ink">{UI_COPY.worldbook.previewTitle}</div>
              <div className="mt-1 text-xs text-subtext">
                {UI_COPY.worldbook.previewHint}
                {previewRequestId ? <span className="ml-2">request_id: {previewRequestId}</span> : null}
              </div>
            </div>
            <button
              className="btn btn-secondary"
              disabled={previewLoading || drawerOpen}
              title={drawerOpen ? UI_COPY.worldbook.previewUseInDrawerHint : undefined}
              onClick={() => void runPreview()}
              type="button"
            >
              {UI_COPY.worldbook.previewRun}
            </button>
          </div>

          <div className="mt-4 grid gap-3">
            <label className="grid gap-1">
              <span className="text-xs text-subtext">{UI_COPY.worldbook.previewQueryLabel}</span>
              <textarea
                className="textarea atelier-content"
                name="query_text"
                rows={4}
                value={previewQueryText}
                onChange={(e) => setPreviewQueryText(e.target.value)}
              />
            </label>

            <div className="grid gap-2 sm:grid-cols-2">
              <label className="flex items-center justify-between gap-2 text-sm text-ink">
                <span>{UI_COPY.worldbook.previewIncludeConstant}</span>
                <input
                  className="checkbox"
                  checked={previewIncludeConstant}
                  name="include_constant"
                  onChange={(e) => setPreviewIncludeConstant(e.target.checked)}
                  type="checkbox"
                />
              </label>
              <label className="flex items-center justify-between gap-2 text-sm text-ink">
                <span>{UI_COPY.worldbook.previewEnableRecursion}</span>
                <input
                  className="checkbox"
                  checked={previewEnableRecursion}
                  name="enable_recursion"
                  onChange={(e) => setPreviewEnableRecursion(e.target.checked)}
                  type="checkbox"
                />
              </label>
              <label className="grid gap-1 sm:col-span-2">
                <span className="text-xs text-subtext">{UI_COPY.worldbook.previewCharLimit}</span>
                <input
                  className="input"
                  min={0}
                  name="char_limit"
                  type="number"
                  value={previewCharLimit}
                  onChange={(e) => setPreviewCharLimit(e.currentTarget.valueAsNumber)}
                />
              </label>
            </div>

            {previewLoading ? <div className="text-sm text-subtext">{UI_COPY.common.loading}</div> : null}
            {previewError ? (
              <div className="rounded-atelier border border-border bg-surface p-3 text-sm text-subtext">
                <div className="text-ink">{UI_COPY.worldbook.previewFailed}</div>
                <div className="mt-1 text-xs text-subtext">
                  {previewError.message} ({previewError.code})
                  {previewError.requestId ? <span className="ml-2">request_id: {previewError.requestId}</span> : null}
                </div>
              </div>
            ) : null}

            {previewResult ? (
              <div className="grid gap-2">
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-subtext">
                  <span>
                    {UI_COPY.worldbook.previewTriggeredPrefix}
                    {previewResult.triggered.length}
                    {UI_COPY.worldbook.previewTriggeredSuffix}
                  </span>
                  {previewResult.truncated ? (
                    <span className="text-amber-600 dark:text-amber-400">{UI_COPY.worldbook.previewTruncated}</span>
                  ) : null}
                </div>
                <details open>
                  <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                    {UI_COPY.worldbook.previewTriggeredList}
                  </summary>
                  <div className="mt-2 grid gap-2">
                    {previewResult.triggered.length === 0 ? (
                      <div className="text-sm text-subtext">{UI_COPY.worldbook.previewNoTriggered}</div>
                    ) : (
                      previewResult.triggered.map((t) => (
                        <div key={t.id} className="rounded-atelier border border-border bg-surface p-2 text-xs">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <div className="truncate text-ink">{t.title}</div>
                              <div className="mt-1 text-subtext">
                                {t.reason} | priority:{t.priority}
                              </div>
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </details>
                <details open>
                  <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                    {UI_COPY.worldbook.previewText}
                  </summary>
                  <pre className="mt-2 max-h-64 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                    {previewResult.text_md || UI_COPY.worldbook.previewTextEmpty}
                  </pre>
                </details>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <Drawer
        open={drawerOpen}
        onClose={() => void closeDrawer()}
        ariaLabel={UI_COPY.worldbook.drawerTitle}
        panelClassName="h-full w-full max-w-2xl border-l border-border bg-canvas p-6 shadow-sm"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="font-content text-2xl text-ink">{UI_COPY.worldbook.drawerTitle}</div>
            <div className="mt-1 text-xs text-subtext">{editing ? editing.id : UI_COPY.worldbook.newEntryHint}</div>
          </div>
          <div className="flex items-center gap-2">
            {editing ? (
              <button className="btn btn-secondary" disabled={saving} onClick={() => void deleteEntry()} type="button">
                {UI_COPY.worldbook.delete}
              </button>
            ) : null}
            <button className="btn btn-secondary" onClick={() => void closeDrawer()} type="button">
              {UI_COPY.worldbook.close}
            </button>
          </div>
        </div>

        <div className="mt-5 grid gap-4">
          <div className="surface p-4">
            <div className="flex items-center justify-between gap-2">
              <div>
                <div className="text-sm text-ink">{UI_COPY.worldbook.previewTitle}</div>
                <div className="mt-1 text-xs text-subtext">
                  {UI_COPY.worldbook.previewHint}
                  {previewRequestId ? <span className="ml-2">request_id: {previewRequestId}</span> : null}
                </div>
              </div>
              <button
                className="btn btn-secondary"
                disabled={previewLoading || dirty}
                title={dirty ? UI_COPY.worldbook.previewRequiresSaveHint : undefined}
                onClick={() => void runPreview()}
                type="button"
              >
                {UI_COPY.worldbook.previewRun}
              </button>
            </div>

            {dirty ? (
              <div className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                {UI_COPY.worldbook.previewRequiresSaveHint}
              </div>
            ) : null}

            <div className="mt-4 grid gap-3">
              <label className="grid gap-1">
                <span className="text-xs text-subtext">{UI_COPY.worldbook.previewQueryLabel}</span>
                <textarea
                  className="textarea atelier-content"
                  name="query_text"
                  rows={3}
                  value={previewQueryText}
                  onChange={(e) => setPreviewQueryText(e.target.value)}
                />
              </label>

              <div className="grid gap-2 sm:grid-cols-2">
                <label className="flex items-center justify-between gap-2 text-sm text-ink">
                  <span>{UI_COPY.worldbook.previewIncludeConstant}</span>
                  <input
                    className="checkbox"
                    checked={previewIncludeConstant}
                    name="include_constant"
                    onChange={(e) => setPreviewIncludeConstant(e.target.checked)}
                    type="checkbox"
                  />
                </label>
                <label className="flex items-center justify-between gap-2 text-sm text-ink">
                  <span>{UI_COPY.worldbook.previewEnableRecursion}</span>
                  <input
                    className="checkbox"
                    checked={previewEnableRecursion}
                    name="enable_recursion"
                    onChange={(e) => setPreviewEnableRecursion(e.target.checked)}
                    type="checkbox"
                  />
                </label>
                <label className="grid gap-1 sm:col-span-2">
                  <span className="text-xs text-subtext">{UI_COPY.worldbook.previewCharLimit}</span>
                  <input
                    className="input"
                    min={0}
                    name="char_limit"
                    type="number"
                    value={previewCharLimit}
                    onChange={(e) => setPreviewCharLimit(e.currentTarget.valueAsNumber)}
                  />
                </label>
              </div>

              {previewLoading ? <div className="text-sm text-subtext">{UI_COPY.common.loading}</div> : null}
              {previewError ? (
                <div className="rounded-atelier border border-border bg-canvas p-3 text-sm text-subtext">
                  <div className="text-ink">{UI_COPY.worldbook.previewFailed}</div>
                  <div className="mt-1 text-xs text-subtext">
                    {previewError.message} ({previewError.code})
                    {previewError.requestId ? (
                      <span className="ml-2">request_id: {previewError.requestId}</span>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {previewResult ? (
                <div className="grid gap-2">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-subtext">
                    <span>
                      {UI_COPY.worldbook.previewTriggeredPrefix}
                      {previewResult.triggered.length}
                      {UI_COPY.worldbook.previewTriggeredSuffix}
                    </span>
                    {previewResult.truncated ? (
                      <span className="text-amber-600 dark:text-amber-400">{UI_COPY.worldbook.previewTruncated}</span>
                    ) : null}
                  </div>
                  <details>
                    <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                      {UI_COPY.worldbook.previewTriggeredList}
                    </summary>
                    <div className="mt-2 grid gap-2">
                      {previewResult.triggered.length === 0 ? (
                        <div className="text-sm text-subtext">{UI_COPY.worldbook.previewNoTriggered}</div>
                      ) : (
                        previewResult.triggered.map((t) => (
                          <div key={t.id} className="rounded-atelier border border-border bg-canvas p-2 text-xs">
                            <div className="flex items-start justify-between gap-2">
                              <div className="min-w-0">
                                <div className="truncate text-ink">{t.title}</div>
                                <div className="mt-1 text-subtext">
                                  {t.reason} | priority:{t.priority}
                                </div>
                              </div>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </details>
                  <details open>
                    <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                      {UI_COPY.worldbook.previewText}
                    </summary>
                    <pre className="mt-2 max-h-64 overflow-auto rounded-atelier border border-border bg-canvas p-3 text-xs text-ink">
                      {previewResult.text_md || UI_COPY.worldbook.previewTextEmpty}
                    </pre>
                  </details>
                </div>
              ) : null}
            </div>
          </div>

          <label className="grid gap-1">
            <span className="text-xs text-subtext">{UI_COPY.worldbook.formTitle}</span>
            <input
              className="input"
              disabled={saving}
              name="title"
              value={form.title}
              onChange={(e) => setForm((v) => ({ ...v, title: e.target.value }))}
            />
          </label>

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="flex items-center justify-between gap-2 text-sm text-ink">
              <span>{UI_COPY.worldbook.formEnabled}</span>
              <input
                className="checkbox"
                checked={form.enabled}
                disabled={saving}
                name="enabled"
                onChange={(e) => setForm((v) => ({ ...v, enabled: e.target.checked }))}
                type="checkbox"
              />
            </label>
            <label className="flex items-center justify-between gap-2 text-sm text-ink">
              <span>{UI_COPY.worldbook.formConstant}</span>
              <input
                className="checkbox"
                checked={form.constant}
                disabled={saving}
                name="constant"
                onChange={(e) => setForm((v) => ({ ...v, constant: e.target.checked }))}
                type="checkbox"
              />
            </label>
            <label className="flex items-center justify-between gap-2 text-sm text-ink">
              <span>{UI_COPY.worldbook.formExcludeRecursion}</span>
              <input
                className="checkbox"
                checked={form.exclude_recursion}
                disabled={saving}
                name="exclude_recursion"
                onChange={(e) => setForm((v) => ({ ...v, exclude_recursion: e.target.checked }))}
                type="checkbox"
              />
            </label>
            <label className="flex items-center justify-between gap-2 text-sm text-ink">
              <span>{UI_COPY.worldbook.formPreventRecursion}</span>
              <input
                className="checkbox"
                checked={form.prevent_recursion}
                disabled={saving}
                name="prevent_recursion"
                onChange={(e) => setForm((v) => ({ ...v, prevent_recursion: e.target.checked }))}
                type="checkbox"
              />
            </label>
            <label className="grid gap-1 sm:col-span-2">
              <span className="text-xs text-subtext">{UI_COPY.worldbook.formKeywords}</span>
              <textarea
                className="textarea atelier-content"
                disabled={saving}
                name="keywords"
                rows={2}
                value={form.keywords_raw}
                onChange={(e) => setForm((v) => ({ ...v, keywords_raw: e.target.value }))}
              />
              <div className="text-[11px] text-subtext">{UI_COPY.worldbook.formKeywordsHint}</div>
            </label>
            <label className="grid gap-1">
              <span className="text-xs text-subtext">{UI_COPY.worldbook.formCharLimit}</span>
              <input
                className="input"
                disabled={saving}
                min={0}
                name="char_limit"
                type="number"
                value={form.char_limit}
                onChange={(e) => setForm((v) => ({ ...v, char_limit: e.currentTarget.valueAsNumber }))}
              />
            </label>
            <label className="grid gap-1">
              <span className="text-xs text-subtext">{UI_COPY.worldbook.formPriority}</span>
              <select
                className="select"
                disabled={saving}
                name="priority"
                value={form.priority}
                onChange={(e) => setForm((v) => ({ ...v, priority: e.target.value as WorldBookPriority }))}
              >
                <option value="must">must</option>
                <option value="important">important</option>
                <option value="optional">optional</option>
                <option value="drop_first">drop_first</option>
              </select>
            </label>
          </div>

          <label className="grid gap-1">
            <span className="text-xs text-subtext">{UI_COPY.worldbook.formContent}</span>
            <textarea
              className="textarea atelier-content"
              disabled={saving}
              name="content_md"
              rows={10}
              value={form.content_md}
              onChange={(e) => setForm((v) => ({ ...v, content_md: e.target.value }))}
            />
          </label>

          <div className="flex items-center justify-end gap-2">
            <button className="btn btn-secondary" disabled={saving} onClick={() => void closeDrawer()} type="button">
              {UI_COPY.worldbook.cancel}
            </button>
            <button
              className="btn btn-primary"
              disabled={saving || !dirty}
              onClick={() => void saveEntry()}
              type="button"
            >
              {saving ? UI_COPY.worldbook.saving : UI_COPY.worldbook.save}
            </button>
          </div>
        </div>
      </Drawer>
    </div>
  );
}
