import { type ComponentProps, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { useConfirm } from "../../components/ui/confirm";
import { useToast } from "../../components/ui/toast";
import { useProjectData } from "../../hooks/useProjectData";
import { UI_COPY } from "../../lib/uiCopy";
import type { ApiError } from "../../services/apiClient";
import {
  bulkDeleteWorldBookEntries,
  bulkUpdateWorldBookEntries,
  createWorldBookEntry,
  deleteWorldBookEntry,
  duplicateWorldBookEntries,
  exportAllWorldBookEntries,
  getLatestWorldBookAutoUpdateTask,
  importAllWorldBookEntries,
  listWorldBookEntries,
  previewWorldBookTrigger,
  retryProjectTask as retryProjectTaskApi,
  triggerWorldBookAutoUpdate,
  type ProjectTask,
  type WorldBookEntry,
  type WorldBookExportAllV1,
  type WorldBookImportAllReport,
  type WorldBookImportMode,
  type WorldBookPreviewTriggerResult,
  type WorldBookPriority,
  updateWorldBookEntry,
} from "../../services/worldbookApi";

import {
  WorldBookAutoUpdateSection,
  WorldBookEditorDrawer,
  WorldBookEntriesSection,
  WorldBookImportDrawer,
  WorldBookPageActionsBar,
  WorldBookPreviewPanel,
} from "./WorldBookPageSections";
import { formatWorldBookActionError, WORLDBOOK_COPY } from "./worldbookCopy";
import {
  buildWorldBookFilterState,
  downloadJson,
  EMPTY_WORLD_BOOK_ENTRIES,
  normalizeWorldBookCharLimit,
  parseKeywords,
  resolveSelectedWorldBookEntryIds,
  toWorldBookEntryForm,
  WORLD_BOOK_ENTRY_PAGE_SIZE,
  WORLD_BOOK_ENTRY_RENDER_THRESHOLD,
  type WorldBookEntryForm,
} from "./worldbookModels";
import { useWorldBookFilters } from "./useWorldBookFilters";
import { useWorldBookPagination } from "./useWorldBookPagination";

type PreviewErrorState = {
  message: string;
  code: string;
  requestId?: string;
} | null;

type WorldBookPageState = {
  actionsBarProps: ComponentProps<typeof WorldBookPageActionsBar>;
  autoUpdateSectionProps: ComponentProps<typeof WorldBookAutoUpdateSection>;
  entriesSectionProps: ComponentProps<typeof WorldBookEntriesSection>;
  pagePreviewPanelProps: ComponentProps<typeof WorldBookPreviewPanel>;
  importDrawerProps: ComponentProps<typeof WorldBookImportDrawer>;
  editorDrawerProps: ComponentProps<typeof WorldBookEditorDrawer>;
};

export function useWorldBookPageState(): WorldBookPageState {
  const { projectId } = useParams();
  const toast = useToast();
  const confirm = useConfirm();

  const entriesQuery = useProjectData<WorldBookEntry[]>(projectId, async (id) => listWorldBookEntries(id));
  const entries = entriesQuery.data ?? EMPTY_WORLD_BOOK_ENTRIES;
  const loading = entriesQuery.loading;
  const setEntries = entriesQuery.setData;

  const autoUpdateTaskQuery = useProjectData<ProjectTask | null>(projectId, async (id) =>
    getLatestWorldBookAutoUpdateTask(id),
  );
  const autoUpdateTask = autoUpdateTaskQuery.data;
  const [autoUpdateActionLoading, setAutoUpdateActionLoading] = useState(false);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<WorldBookEntry | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [baseline, setBaseline] = useState<WorldBookEntryForm | null>(null);
  const [form, setForm] = useState<WorldBookEntryForm>(() => toWorldBookEntryForm(null));

  const { searchText, setSearchText, sortMode, setSortMode } = useWorldBookFilters(projectId);

  const [bulkMode, setBulkMode] = useState(false);
  const [bulkSelectAllActive, setBulkSelectAllActive] = useState(false);
  const [bulkSelectedIds, setBulkSelectedIds] = useState<string[]>([]);
  const [bulkExcludedIds, setBulkExcludedIds] = useState<string[]>([]);
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkPriority, setBulkPriority] = useState<WorldBookPriority>("important");
  const [bulkCharLimit, setBulkCharLimit] = useState(12000);

  const [exporting, setExporting] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [importMode, setImportMode] = useState<WorldBookImportMode>("merge");
  const [importFileName, setImportFileName] = useState("");
  const [importJson, setImportJson] = useState<WorldBookExportAllV1 | null>(null);
  const [importReport, setImportReport] = useState<WorldBookImportAllReport | null>(null);
  const [importLoading, setImportLoading] = useState(false);

  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewRequestId, setPreviewRequestId] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<PreviewErrorState>(null);
  const [previewQueryText, setPreviewQueryText] = useState("");
  const [previewIncludeConstant, setPreviewIncludeConstant] = useState(true);
  const [previewEnableRecursion, setPreviewEnableRecursion] = useState(true);
  const [previewCharLimit, setPreviewCharLimit] = useState(12000);
  const [previewResult, setPreviewResult] = useState<WorldBookPreviewTriggerResult | null>(null);

  const triggerAutoUpdate = useCallback(async () => {
    if (!projectId) {
      toast.toastError(UI_COPY.worldbook.missingProjectId);
      return;
    }
    if (autoUpdateActionLoading) return;
    setAutoUpdateActionLoading(true);
    try {
      await triggerWorldBookAutoUpdate(projectId);
      toast.toastSuccess(WORLDBOOK_COPY.autoUpdateTriggeredToast);
      await autoUpdateTaskQuery.refresh();
    } catch (error) {
      const err = error as ApiError;
      toast.toastError(formatWorldBookActionError(WORLDBOOK_COPY.autoUpdateTriggerFailed, err), err.requestId);
    } finally {
      setAutoUpdateActionLoading(false);
    }
  }, [autoUpdateActionLoading, autoUpdateTaskQuery, projectId, toast]);

  const retryAutoUpdate = useCallback(async () => {
    if (!autoUpdateTask || autoUpdateTask.status !== "failed" || autoUpdateActionLoading) return;
    setAutoUpdateActionLoading(true);
    try {
      await retryProjectTaskApi(autoUpdateTask.id);
      toast.toastSuccess(WORLDBOOK_COPY.autoUpdateRetryToast);
      await autoUpdateTaskQuery.refresh();
    } catch (error) {
      const err = error as ApiError;
      toast.toastError(formatWorldBookActionError(WORLDBOOK_COPY.autoUpdateRetryFailed, err), err.requestId);
    } finally {
      setAutoUpdateActionLoading(false);
    }
  }, [autoUpdateActionLoading, autoUpdateTask, autoUpdateTaskQuery, toast]);

  const openImportDrawer = useCallback(() => {
    setImportOpen(true);
    setImportReport(null);
    setImportJson(null);
    setImportFileName("");
  }, []);

  const closeImportDrawer = useCallback(() => {
    if (importLoading) return;
    setImportOpen(false);
  }, [importLoading]);

  const exportAll = useCallback(async () => {
    if (!projectId) {
      toast.toastError(UI_COPY.worldbook.missingProjectId);
      return;
    }
    if (exporting) return;
    setExporting(true);
    try {
      const out = await exportAllWorldBookEntries(projectId);
      const stamp = new Date().toISOString().replaceAll(":", "-").replaceAll(".", "-");
      downloadJson(`worldbook_export_all_${projectId}_${stamp}.json`, out);
      toast.toastSuccess(WORLDBOOK_COPY.exportSuccess);
    } catch (error) {
      const err = error as ApiError;
      toast.toastError(formatWorldBookActionError(WORLDBOOK_COPY.exportFailed, err), err.requestId);
    } finally {
      setExporting(false);
    }
  }, [exporting, projectId, toast]);

  const loadImportFile = useCallback(
    async (file: File | null) => {
      setImportReport(null);
      setImportJson(null);
      setImportFileName("");
      if (!file) return;

      try {
        const text = await file.text();
        const parsed = JSON.parse(text) as unknown;
        if (!parsed || typeof parsed !== "object") throw new Error("invalid json");
        const data = parsed as Record<string, unknown>;
        const schemaVersion = String(data.schema_version ?? "").trim();
        const entriesRaw = data.entries;
        if (!schemaVersion || !Array.isArray(entriesRaw)) throw new Error("missing schema_version/entries");
        setImportJson({ schema_version: schemaVersion, entries: entriesRaw as never[] } as WorldBookExportAllV1);
        setImportFileName(file.name || "import.json");
        toast.toastSuccess(WORLDBOOK_COPY.importLoadedToast);
      } catch {
        toast.toastError(WORLDBOOK_COPY.importParseFailed);
      }
    },
    [toast],
  );

  const runImport = useCallback(
    async (dryRun: boolean) => {
      if (!projectId) {
        toast.toastError(UI_COPY.worldbook.missingProjectId);
        return;
      }
      if (!importJson) {
        toast.toastError(WORLDBOOK_COPY.importChooseFile);
        return;
      }
      if (importLoading) return;

      if (!dryRun && importMode === "overwrite") {
        const ok = await confirm.confirm({
          title: WORLDBOOK_COPY.importOverwriteConfirmTitle,
          description: WORLDBOOK_COPY.importOverwriteConfirmDescription,
          confirmText: WORLDBOOK_COPY.importOverwriteConfirmText,
          cancelText: WORLDBOOK_COPY.importOverwriteCancelText,
        });
        if (!ok) return;
      }

      setImportLoading(true);
      try {
        const report = await importAllWorldBookEntries(projectId, {
          schema_version: importJson.schema_version,
          dry_run: dryRun,
          mode: importMode,
          entries: importJson.entries ?? [],
        });
        setImportReport(report);
        toast.toastSuccess(dryRun ? WORLDBOOK_COPY.importDryRunDone : WORLDBOOK_COPY.importDone);
        if (!dryRun) {
          setImportOpen(false);
          void entriesQuery.refresh();
          toast.toastWarning(WORLDBOOK_COPY.importPostApplyWarning);
        }
      } catch (error) {
        const err = error as ApiError;
        toast.toastError(formatWorldBookActionError(WORLDBOOK_COPY.importFailed, err), err.requestId);
      } finally {
        setImportLoading(false);
      }
    },
    [confirm, entriesQuery, importJson, importLoading, importMode, projectId, toast],
  );

  useEffect(() => {
    if (!bulkMode) return;
    if (!bulkSelectAllActive && bulkSelectedIds.length === 0 && bulkExcludedIds.length === 0) return;
    const idSet = new Set(entries.map((entry) => entry.id));
    setBulkSelectedIds((prev) => prev.filter((id) => idSet.has(id)));
    setBulkExcludedIds((prev) => prev.filter((id) => idSet.has(id)));
  }, [bulkExcludedIds.length, bulkMode, bulkSelectAllActive, bulkSelectedIds.length, entries]);

  const filterState = useMemo(
    () => buildWorldBookFilterState(entries, searchText, sortMode),
    [entries, searchText, sortMode],
  );
  const filteredEntries = filterState.entries;

  const {
    paginate: paginateEntries,
    totalPages: totalEntryPages,
    pageIndex: entryPageIndex,
    pageStart: entryPageStart,
    pageEnd: entryPageEnd,
    pageItems: visibleEntries,
    setPageIndex: setEntryPageIndex,
  } = useWorldBookPagination(filteredEntries, {
    threshold: WORLD_BOOK_ENTRY_RENDER_THRESHOLD,
    pageSize: WORLD_BOOK_ENTRY_PAGE_SIZE,
    resetToken: `${searchText}::${sortMode}`,
  });

  const bulkSelectedExplicitSet = useMemo(() => new Set(bulkSelectedIds), [bulkSelectedIds]);
  const bulkExcludedSet = useMemo(() => new Set(bulkExcludedIds), [bulkExcludedIds]);
  const bulkSelectedCount = bulkSelectAllActive
    ? Math.max(0, filteredEntries.length - bulkExcludedIds.length)
    : bulkSelectedIds.length;

  useEffect(() => {
    if (!bulkMode || !bulkSelectAllActive || bulkExcludedIds.length === 0) return;
    setBulkExcludedIds([]);
  }, [bulkMode, bulkExcludedIds.length, bulkSelectAllActive, searchText, sortMode]);

  const bulkVisibleSelectedCount = useMemo(() => {
    if (!bulkMode) return 0;
    if (bulkSelectAllActive) return visibleEntries.filter((entry) => !bulkExcludedSet.has(entry.id)).length;
    return visibleEntries.filter((entry) => bulkSelectedExplicitSet.has(entry.id)).length;
  }, [bulkExcludedSet, bulkMode, bulkSelectAllActive, bulkSelectedExplicitSet, visibleEntries]);

  const bulkHiddenSelectedCount = Math.max(0, bulkSelectedCount - bulkVisibleSelectedCount);

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

  const openNew = useCallback(() => {
    setEditing(null);
    const next = toWorldBookEntryForm(null);
    setForm(next);
    setBaseline(next);
    setDrawerOpen(true);
  }, []);

  const openEdit = useCallback((entry: WorldBookEntry) => {
    setEditing(entry);
    const next = toWorldBookEntryForm(entry);
    setForm(next);
    setBaseline(next);
    setDrawerOpen(true);
  }, []);

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

  const updateForm = useCallback((patch: Partial<WorldBookEntryForm>) => {
    setForm((prev) => ({ ...prev, ...patch }));
  }, []);

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
        char_limit: normalizeWorldBookCharLimit(form.char_limit),
        priority: form.priority,
      };
      const saved = editing
        ? await updateWorldBookEntry(editing.id, payload)
        : await createWorldBookEntry(projectId, payload);
      setEntries((prev) => {
        const list = prev ?? [];
        const idx = list.findIndex((entry) => entry.id === saved.id);
        if (idx >= 0) return list.map((entry) => (entry.id === saved.id ? saved : entry));
        return [saved, ...list];
      });
      const nextBaseline = toWorldBookEntryForm(saved);
      setBaseline(nextBaseline);
      setForm(nextBaseline);
      toast.toastSuccess(UI_COPY.worldbook.saved);
      setEditing(saved);
    } catch (error) {
      const err = error as ApiError;
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
      setEntries((prev) => (prev ?? []).filter((entry) => entry.id !== editing.id));
      toast.toastSuccess(UI_COPY.worldbook.deleted);
      setDrawerOpen(false);
    } catch (error) {
      const err = error as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setSaving(false);
    }
  }, [confirm, editing, setEntries, toast]);

  const runPreview = useCallback(async () => {
    if (!projectId) {
      setPreviewError({ message: UI_COPY.worldbook.missingProjectId, code: "NO_PROJECT" });
      return;
    }
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const response = await previewWorldBookTrigger(projectId, {
        query_text: previewQueryText,
        include_constant: previewIncludeConstant,
        enable_recursion: previewEnableRecursion,
        char_limit: normalizeWorldBookCharLimit(previewCharLimit),
      });
      setPreviewResult(response.data);
      setPreviewRequestId(response.request_id ?? null);
    } catch (error) {
      const err = error as ApiError;
      setPreviewError({ message: err.message, code: err.code, requestId: err.requestId });
      setPreviewResult(null);
      setPreviewRequestId(null);
    } finally {
      setPreviewLoading(false);
    }
  }, [previewCharLimit, previewEnableRecursion, previewIncludeConstant, previewQueryText, projectId]);

  const setBulkModeSafe = useCallback((next: boolean) => {
    setBulkMode(next);
    setBulkSelectAllActive(false);
    setBulkSelectedIds([]);
    setBulkExcludedIds([]);
  }, []);

  const toggleBulkSelected = useCallback(
    (entryId: string) => {
      if (bulkSelectAllActive) {
        setBulkExcludedIds((prev) => {
          if (prev.includes(entryId)) return prev.filter((id) => id !== entryId);
          return [...prev, entryId];
        });
        return;
      }

      setBulkSelectedIds((prev) => {
        if (prev.includes(entryId)) return prev.filter((id) => id !== entryId);
        return [...prev, entryId];
      });
    },
    [bulkSelectAllActive],
  );

  const bulkSelectAll = useCallback(() => {
    setBulkSelectAllActive(true);
    setBulkSelectedIds([]);
    setBulkExcludedIds([]);
  }, []);

  const bulkClearSelection = useCallback(() => {
    setBulkSelectAllActive(false);
    setBulkSelectedIds([]);
    setBulkExcludedIds([]);
  }, []);

  const bulkUpdate = useCallback(
    async (options: {
      title: string;
      description: string;
      patch: { enabled?: boolean; priority?: WorldBookPriority; char_limit?: number };
    }) => {
      if (!projectId) return;
      const selectedIds = resolveSelectedWorldBookEntryIds({
        bulkSelectAllActive,
        bulkSelectedIds,
        bulkExcludedIds,
        filteredEntries,
      });
      if (selectedIds.length === 0) {
        toast.toastError(UI_COPY.worldbook.bulkNoSelection);
        return;
      }

      const ok = await confirm.confirm({
        title: options.title,
        description: options.description,
        confirmText: WORLDBOOK_COPY.bulkConfirmText,
        cancelText: UI_COPY.worldbook.cancel,
      });
      if (!ok) return;

      setBulkLoading(true);
      try {
        const updated = await bulkUpdateWorldBookEntries(projectId, { entry_ids: selectedIds, ...options.patch });
        setEntries((prev) => {
          const list = prev ?? [];
          const byId = new Map(updated.map((entry) => [entry.id, entry]));
          return list.map((entry) => byId.get(entry.id) ?? entry);
        });
        toast.toastSuccess(WORLDBOOK_COPY.bulkUpdatedToast);
      } catch (error) {
        const err = error as ApiError;
        toast.toastError(
          formatWorldBookActionError(WORLDBOOK_COPY.bulkUpdateFailed, err, { count: selectedIds.length }),
          err.requestId,
        );
      } finally {
        setBulkLoading(false);
      }
    },
    [bulkExcludedIds, bulkSelectAllActive, bulkSelectedIds, confirm, filteredEntries, projectId, setEntries, toast],
  );

  const bulkDelete = useCallback(async () => {
    if (!projectId) return;
    const selectedIds = resolveSelectedWorldBookEntryIds({
      bulkSelectAllActive,
      bulkSelectedIds,
      bulkExcludedIds,
      filteredEntries,
    });
    if (selectedIds.length === 0) {
      toast.toastError(UI_COPY.worldbook.bulkNoSelection);
      return;
    }

    const ok = await confirm.confirm({
      title: UI_COPY.worldbook.bulkDeleteTitle,
      description: UI_COPY.worldbook.bulkDeleteDescPrefix + selectedIds.length + UI_COPY.worldbook.bulkDeleteDescSuffix,
      confirmText: UI_COPY.worldbook.deleteConfirm,
      cancelText: UI_COPY.worldbook.deleteCancel,
      danger: true,
    });
    if (!ok) return;

    setBulkLoading(true);
    try {
      const deletedIds = await bulkDeleteWorldBookEntries(projectId, selectedIds);
      const deletedSet = new Set(deletedIds);
      setEntries((prev) => (prev ?? []).filter((entry) => !deletedSet.has(entry.id)));
      toast.toastSuccess(WORLDBOOK_COPY.bulkDeletedToast);
      setBulkSelectAllActive(false);
      setBulkSelectedIds([]);
      setBulkExcludedIds([]);
    } catch (error) {
      const err = error as ApiError;
      toast.toastError(
        formatWorldBookActionError(WORLDBOOK_COPY.bulkDeleteFailed, err, { count: selectedIds.length }),
        err.requestId,
      );
    } finally {
      setBulkLoading(false);
    }
  }, [bulkExcludedIds, bulkSelectAllActive, bulkSelectedIds, confirm, filteredEntries, projectId, setEntries, toast]);

  const duplicateAndEdit = useCallback(
    async (entryId: string) => {
      if (!projectId) return;

      const ok = await confirm.confirm({
        title: UI_COPY.worldbook.bulkDuplicateTitle,
        description: UI_COPY.worldbook.bulkDuplicateDescPrefix + "1" + UI_COPY.worldbook.bulkDuplicateDescSuffix,
        confirmText: WORLDBOOK_COPY.duplicateConfirmText,
        cancelText: UI_COPY.worldbook.cancel,
      });
      if (!ok) return;

      setBulkLoading(true);
      try {
        const created = await duplicateWorldBookEntries(projectId, [entryId]);
        if (created.length === 0) {
          toast.toastError(WORLDBOOK_COPY.duplicateFailedEmpty);
          return;
        }
        const createdSet = new Set(created.map((entry) => entry.id));
        setEntries((prev) => {
          const list = prev ?? [];
          const rest = list.filter((entry) => !createdSet.has(entry.id));
          return [...created, ...rest];
        });
        setBulkMode(false);
        setBulkSelectAllActive(false);
        setBulkSelectedIds([]);
        setBulkExcludedIds([]);
        openEdit(created[0]);
        toast.toastSuccess(WORLDBOOK_COPY.duplicateSuccess);
      } catch (error) {
        const err = error as ApiError;
        toast.toastError(formatWorldBookActionError(WORLDBOOK_COPY.duplicateFailed, err), err.requestId);
      } finally {
        setBulkLoading(false);
      }
    },
    [confirm, openEdit, projectId, setEntries, toast],
  );

  const bulkDuplicateEdit = useCallback(async () => {
    if (!bulkSelectAllActive) {
      if (bulkSelectedIds.length !== 1) {
        toast.toastError(WORLDBOOK_COPY.duplicateRequiresSingle);
        return;
      }
      await duplicateAndEdit(bulkSelectedIds[0]);
      return;
    }

    const excludedSet = new Set(bulkExcludedIds);
    let selectedId: string | null = null;
    let count = 0;
    for (const entry of filteredEntries) {
      if (excludedSet.has(entry.id)) continue;
      count += 1;
      selectedId = entry.id;
      if (count > 1) break;
    }

    if (count !== 1 || !selectedId) {
      toast.toastError(WORLDBOOK_COPY.duplicateRequiresSingle);
      return;
    }
    await duplicateAndEdit(selectedId);
  }, [bulkExcludedIds, bulkSelectAllActive, bulkSelectedIds, duplicateAndEdit, filteredEntries, toast]);

  const handleBulkEnable = useCallback(
    () =>
      void bulkUpdate({
        title: UI_COPY.worldbook.bulkEnableTitle,
        description:
          UI_COPY.worldbook.bulkEnableDescPrefix + bulkSelectedCount + UI_COPY.worldbook.bulkEnableDescSuffix,
        patch: { enabled: true },
      }),
    [bulkSelectedCount, bulkUpdate],
  );

  const handleBulkDisable = useCallback(
    () =>
      void bulkUpdate({
        title: UI_COPY.worldbook.bulkDisableTitle,
        description:
          UI_COPY.worldbook.bulkDisableDescPrefix + bulkSelectedCount + UI_COPY.worldbook.bulkDisableDescSuffix,
        patch: { enabled: false },
      }),
    [bulkSelectedCount, bulkUpdate],
  );

  const handleApplyBulkPriority = useCallback(
    () =>
      void bulkUpdate({
        title: UI_COPY.worldbook.bulkUpdateTitle,
        description:
          UI_COPY.worldbook.bulkUpdateDescPrefix + bulkSelectedCount + UI_COPY.worldbook.bulkUpdateDescSuffix,
        patch: { priority: bulkPriority },
      }),
    [bulkPriority, bulkSelectedCount, bulkUpdate],
  );

  const handleApplyBulkCharLimit = useCallback(
    () =>
      void bulkUpdate({
        title: UI_COPY.worldbook.bulkUpdateTitle,
        description:
          UI_COPY.worldbook.bulkUpdateDescPrefix + bulkSelectedCount + UI_COPY.worldbook.bulkUpdateDescSuffix,
        patch: { char_limit: normalizeWorldBookCharLimit(bulkCharLimit) },
      }),
    [bulkCharLimit, bulkSelectedCount, bulkUpdate],
  );

  return {
    actionsBarProps: {
      filteredCount: filteredEntries.length,
      totalCount: entries.length,
      projectId,
      exporting,
      onRefresh: () => void entriesQuery.refresh(),
      onExport: () => void exportAll(),
      onOpenImport: openImportDrawer,
      onOpenNew: openNew,
    },
    autoUpdateSectionProps: {
      projectId,
      loading: autoUpdateTaskQuery.loading,
      actionLoading: autoUpdateActionLoading,
      task: autoUpdateTask,
      onRefresh: () => void autoUpdateTaskQuery.refresh(),
      onRetry: () => void retryAutoUpdate(),
      onTrigger: () => void triggerAutoUpdate(),
    },
    entriesSectionProps: {
      loading,
      searchText,
      onSearchTextChange: setSearchText,
      sortMode,
      onSortModeChange: setSortMode,
      bulkMode,
      onBulkModeChange: setBulkModeSafe,
      bulkLoading,
      bulkSelectedCount,
      bulkHiddenSelectedCount,
      onBulkSelectAll: bulkSelectAll,
      onBulkClearSelection: bulkClearSelection,
      onBulkEnable: handleBulkEnable,
      onBulkDisable: handleBulkDisable,
      onBulkDuplicateEdit: () => void bulkDuplicateEdit(),
      onBulkDelete: () => void bulkDelete(),
      bulkPriority,
      onBulkPriorityChange: setBulkPriority,
      onApplyBulkPriority: handleApplyBulkPriority,
      bulkCharLimit,
      onBulkCharLimitChange: setBulkCharLimit,
      onApplyBulkCharLimit: handleApplyBulkCharLimit,
      filteredEntries,
      visibleEntries,
      filterTokens: filterState.tokens,
      filterMetaById: filterState.metaById,
      bulkSelectAllActive,
      bulkSelectedExplicitSet,
      bulkExcludedSet,
      onToggleEntrySelection: toggleBulkSelected,
      onOpenEntry: openEdit,
      drawerOpen,
      paginateEntries,
      entryPageStart,
      entryPageEnd,
      entryPageIndex,
      totalEntryPages,
      onPrevPage: () => setEntryPageIndex((prev) => Math.max(0, prev - 1)),
      onNextPage: () => setEntryPageIndex((prev) => Math.min(totalEntryPages - 1, prev + 1)),
    },
    pagePreviewPanelProps: {
      variant: "page",
      requestId: previewRequestId,
      queryText: previewQueryText,
      onQueryTextChange: setPreviewQueryText,
      includeConstant: previewIncludeConstant,
      onIncludeConstantChange: setPreviewIncludeConstant,
      enableRecursion: previewEnableRecursion,
      onEnableRecursionChange: setPreviewEnableRecursion,
      charLimit: previewCharLimit,
      onCharLimitChange: setPreviewCharLimit,
      loading: previewLoading,
      error: previewError,
      result: previewResult,
      disabled: drawerOpen,
      disabledHint: drawerOpen ? UI_COPY.worldbook.previewUseInDrawerHint : undefined,
      onRun: () => void runPreview(),
      triggeredListOpenByDefault: true,
    },
    importDrawerProps: {
      open: importOpen,
      loading: importLoading,
      mode: importMode,
      fileName: importFileName,
      importJson,
      report: importReport,
      onClose: closeImportDrawer,
      onLoadFile: (file) => void loadImportFile(file),
      onModeChange: setImportMode,
      onDryRun: () => void runImport(true),
      onApply: () => void runImport(false),
    },
    editorDrawerProps: {
      open: drawerOpen,
      editing,
      form,
      saving,
      bulkLoading,
      dirty,
      onUpdateForm: updateForm,
      onDelete: () => void deleteEntry(),
      onDuplicate: () => void duplicateAndEdit(editing?.id ?? ""),
      onClose: () => void closeDrawer(),
      onSave: () => void saveEntry(),
      previewPanelProps: {
        requestId: previewRequestId,
        queryText: previewQueryText,
        onQueryTextChange: setPreviewQueryText,
        includeConstant: previewIncludeConstant,
        onIncludeConstantChange: setPreviewIncludeConstant,
        enableRecursion: previewEnableRecursion,
        onEnableRecursionChange: setPreviewEnableRecursion,
        charLimit: previewCharLimit,
        onCharLimitChange: setPreviewCharLimit,
        loading: previewLoading,
        error: previewError,
        result: previewResult,
        disabled: dirty,
        disabledHint: dirty ? UI_COPY.worldbook.previewRequiresSaveHint : undefined,
        onRun: () => void runPreview(),
        triggeredListOpenByDefault: false,
      },
    },
  };
}
