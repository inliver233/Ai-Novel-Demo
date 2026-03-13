import type { ComponentProps } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { WizardNextBar } from "../../components/atelier/WizardNextBar";
import { useConfirm } from "../../components/ui/confirm";
import { useToast } from "../../components/ui/toast";
import { usePersistentOutletIsActive } from "../../hooks/usePersistentOutlet";
import { useProjectData } from "../../hooks/useProjectData";
import { useWizardProgress } from "../../hooks/useWizardProgress";
import { ApiError, apiJson } from "../../services/apiClient";
import { getWizardProjectChangedAt } from "../../services/wizard";
import type { Character, LLMPreset, Outline, OutlineListItem } from "../../types";

import type {
  WritingChapterListDrawerProps,
  WritingEditorSectionProps,
  WritingPageOverlaysProps,
  WritingStreamFloatingCardProps,
  WritingWorkspaceProps,
} from "./WritingPageSections";
import { useApplyGenerationRun } from "./useApplyGenerationRun";
import { useBatchGeneration } from "./useBatchGeneration";
import { useChapterAnalysis } from "./useChapterAnalysis";
import { useChapterCrud } from "./useChapterCrud";
import { useChapterEditor } from "./useChapterEditor";
import { useChapterGeneration } from "./useChapterGeneration";
import { useGenerationHistory } from "./useGenerationHistory";
import { useOutlineSwitcher } from "./useOutlineSwitcher";
import type { ChapterForm } from "./writingUtils";
import {
  buildBatchTaskCenterHref,
  buildProjectTaskCenterHref,
  buildWritingTaskCenterHref,
  pickFirstProjectTaskId,
  type ChapterAutoUpdatesTriggerResult,
} from "./writingPageModels";
import {
  getWritingAnalysisHref,
  getWritingDoneOnlyWarning,
  getWritingGenerateIndicatorLabel,
  getWritingNextChapterReplaceTitle,
  WRITING_PAGE_COPY,
} from "./writingPageCopy";

type WritingLoaded = {
  outlines: OutlineListItem[];
  outline: Outline;
  preset: LLMPreset;
  characters: Character[];
};

export type WritingPageState = {
  loading: boolean;
  dirty: boolean;
  showUnsavedGuard: boolean;
  workspaceProps: WritingWorkspaceProps;
  chapterListDrawerProps: WritingChapterListDrawerProps;
  overlaysProps: WritingPageOverlaysProps;
  streamFloatingProps: WritingStreamFloatingCardProps;
  wizardBarProps: ComponentProps<typeof WizardNextBar>;
};

export function useWritingPageState(): WritingPageState {
  const { projectId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedChapterId = searchParams.get("chapterId");
  const applyRunId = searchParams.get("applyRunId");
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const outletActive = usePersistentOutletIsActive();
  const wizard = useWizardProgress(projectId);
  const refreshWizard = wizard.refresh;
  const bumpWizardLocal = wizard.bumpLocal;
  const lastProjectChangedAtRef = useRef<string | null>(null);

  const [chapterListOpen, setChapterListOpen] = useState(false);
  const [contentEditorTab, setContentEditorTab] = useState<"edit" | "preview">("edit");
  const contentTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const autoGenerateNextRef = useRef<{ chapterId: string; mode: "replace" | "append" } | null>(null);

  const [aiOpen, setAiOpen] = useState(false);
  const [promptInspectorOpen, setPromptInspectorOpen] = useState(false);
  const [postEditCompareOpen, setPostEditCompareOpen] = useState(false);
  const [contentOptimizeCompareOpen, setContentOptimizeCompareOpen] = useState(false);
  const [tablesOpen, setTablesOpen] = useState(false);
  const [contextPreviewOpen, setContextPreviewOpen] = useState(false);
  const [memoryUpdateOpen, setMemoryUpdateOpen] = useState(false);
  const [foreshadowOpen, setForeshadowOpen] = useState(false);
  const [autoUpdatesTriggering, setAutoUpdatesTriggering] = useState(false);

  const writingQuery = useProjectData<WritingLoaded>(projectId, async (id) => {
    const [outlineRes, presetRes, charactersRes] = await Promise.all([
      apiJson<{ outline: Outline }>(`/api/projects/${id}/outline`),
      apiJson<{ llm_preset: LLMPreset }>(`/api/projects/${id}/llm_preset`),
      apiJson<{ characters: Character[] }>(`/api/projects/${id}/characters`),
    ]);
    const outlinesRes = await apiJson<{ outlines: OutlineListItem[] }>(`/api/projects/${id}/outlines`);
    return {
      outlines: outlinesRes.data.outlines,
      outline: outlineRes.data.outline,
      preset: presetRes.data.llm_preset,
      characters: charactersRes.data.characters,
    };
  });
  const outlines = writingQuery.data?.outlines ?? [];
  const outline = writingQuery.data?.outline ?? null;
  const characters = writingQuery.data?.characters ?? [];
  const preset = writingQuery.data?.preset ?? null;
  const refreshWriting = writingQuery.refresh;

  const chapterEditor = useChapterEditor({
    projectId,
    requestedChapterId,
    searchParams,
    setSearchParams,
    toast,
    confirm,
    refreshWizard,
    bumpWizardLocal,
  });
  const {
    loading,
    chapters,
    refreshChapters,
    activeId,
    setActiveId,
    activeChapter,
    baseline,
    form,
    setForm,
    dirty,
    saveChapter,
    requestSelectChapter: requestSelectChapterBase,
    loadingChapter,
    saving,
  } = chapterEditor;

  useEffect(() => {
    if (!projectId) {
      lastProjectChangedAtRef.current = null;
      return;
    }
    lastProjectChangedAtRef.current = getWizardProjectChangedAt(projectId);
  }, [projectId]);

  useEffect(() => {
    if (!projectId || !outletActive || dirty) return;
    const changedAt = getWizardProjectChangedAt(projectId);
    if ((changedAt ?? null) === (lastProjectChangedAtRef.current ?? null)) return;
    lastProjectChangedAtRef.current = changedAt;
    void refreshWriting();
    void refreshChapters();
    void refreshWizard();
  }, [dirty, outletActive, projectId, refreshChapters, refreshWriting, refreshWizard]);

  useEffect(() => {
    if (!activeChapter) autoGenerateNextRef.current = null;
  }, [activeChapter]);

  const isDoneReadonly = Boolean(baseline && form && baseline.status === "done" && form.status === "done");

  useApplyGenerationRun({
    applyRunId,
    activeChapter,
    form,
    dirty,
    confirm,
    toast,
    saveChapter,
    searchParams,
    setSearchParams,
    setForm,
  });

  const requestSelectChapter = useCallback(
    async (chapterId: string) => {
      autoGenerateNextRef.current = null;
      await requestSelectChapterBase(chapterId);
    },
    [requestSelectChapterBase],
  );

  const chapterCrud = useChapterCrud({
    projectId,
    chapters,
    activeChapter,
    setActiveId,
    requestSelectChapter,
    toast,
    confirm,
    bumpWizardLocal,
    refreshWizard,
  });

  const generation = useChapterGeneration({
    projectId,
    activeChapter,
    chapters,
    form,
    setForm,
    preset,
    dirty,
    saveChapter,
    requestSelectChapter,
    toast,
    confirm,
  });
  const {
    generating,
    genRequestId,
    genStreamProgress,
    genForm,
    setGenForm,
    postEditCompare,
    applyPostEditVariant,
    contentOptimizeCompare,
    applyContentOptimizeVariant,
    generate,
    abortGenerate,
  } = generation;

  const batch = useBatchGeneration({
    projectId,
    preset,
    activeChapter,
    chapters,
    genForm,
    searchParams,
    setSearchParams,
    requestSelectChapter,
    toast,
  });
  const analysis = useChapterAnalysis({ activeChapter, preset, genForm, form, setForm, dirty, saveChapter, toast });
  const history = useGenerationHistory({ projectId, toast });

  const activeOutlineId = outline?.id ?? "";
  const switchOutline = useOutlineSwitcher({
    projectId,
    activeOutlineId,
    dirty,
    confirm,
    toast,
    saveChapter,
    bumpWizardLocal,
    refreshWizard,
    refreshChapters,
    refreshWriting,
  });

  const locateInEditor = useCallback(
    (excerpt: string) => {
      if (!excerpt || !form) return;
      const needleRaw = excerpt.trim();
      if (!needleRaw) return;

      const haystack = form.content_md ?? "";
      let needle = needleRaw;
      let index = haystack.indexOf(needle);
      if (index < 0 && needle.length > 20) {
        needle = needle.slice(0, 20);
        index = haystack.indexOf(needle);
      }
      if (index < 0) {
        toast.toastError(WRITING_PAGE_COPY.locateExcerptFailed);
        return;
      }

      setContentEditorTab("edit");
      window.requestAnimationFrame(() => {
        const element = contentTextareaRef.current;
        if (!element) return;
        element.focus();
        element.setSelectionRange(index, Math.min(haystack.length, index + needle.length));
      });
    },
    [form, toast],
  );

  const saveAndTriggerAutoUpdates = useCallback(async () => {
    if (!projectId || !activeChapter || autoUpdatesTriggering || !dirty) return;

    setAutoUpdatesTriggering(true);
    try {
      const ok = await saveChapter({ silent: true });
      if (!ok) return;

      const response = await apiJson<ChapterAutoUpdatesTriggerResult>(
        `/api/chapters/${activeChapter.id}/trigger_auto_updates`,
        {
          method: "POST",
          body: JSON.stringify({}),
        },
      );
      const taskId = pickFirstProjectTaskId(response.data.tasks);
      toast.toastSuccess(
        WRITING_PAGE_COPY.autoUpdatesCreated,
        response.request_id,
        taskId
          ? {
              label: WRITING_PAGE_COPY.openTaskCenter,
              onClick: () => {
                const href = buildProjectTaskCenterHref(projectId, taskId);
                if (href) navigate(href);
              },
            }
          : undefined,
      );
    } catch (error) {
      const err =
        error instanceof ApiError
          ? error
          : new ApiError({ code: "UNKNOWN", message: String(error), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setAutoUpdatesTriggering(false);
    }
  }, [activeChapter, autoUpdatesTriggering, dirty, navigate, projectId, saveChapter, toast]);

  const saveAndGenerateNext = useCallback(async () => {
    if (!activeChapter) return;

    const ok = await saveChapter();
    if (!ok) return;

    const sorted = [...chapters].sort((a, b) => (a.number ?? 0) - (b.number ?? 0));
    const currentIndex = sorted.findIndex((chapter) => chapter.id === activeChapter.id);
    const nextChapter =
      currentIndex >= 0
        ? (sorted[currentIndex + 1] ?? null)
        : (sorted.find((chapter) => (chapter.number ?? 0) > (activeChapter.number ?? 0)) ?? null);

    if (!nextChapter) {
      toast.toastSuccess(WRITING_PAGE_COPY.saveAndGenerateLastChapter);
      return;
    }

    const nextHasContent = Boolean(nextChapter.has_content || nextChapter.has_summary);
    if (nextHasContent) {
      const replaceOk = await confirm.confirm({
        title: getWritingNextChapterReplaceTitle(nextChapter.number),
        description: WRITING_PAGE_COPY.confirms.nextChapterReplace.description,
        confirmText: WRITING_PAGE_COPY.confirms.nextChapterReplace.confirmText,
        cancelText: WRITING_PAGE_COPY.confirms.nextChapterReplace.cancelText,
        danger: true,
      });
      if (!replaceOk) return;
    }

    autoGenerateNextRef.current = { chapterId: nextChapter.id, mode: "replace" };
    setActiveId(nextChapter.id);
    setAiOpen(true);
  }, [activeChapter, chapters, confirm, saveChapter, setActiveId, toast]);

  useEffect(() => {
    const pending = autoGenerateNextRef.current;
    if (!pending || !activeChapter || !form || generating) return;
    if (activeChapter.id !== pending.chapterId) return;
    autoGenerateNextRef.current = null;
    void generate(pending.mode);
  }, [activeChapter, form, generate, generating]);

  const workspaceProps: WritingWorkspaceProps = {
    toolbarProps: {
      outlines,
      activeOutlineId,
      chaptersCount: chapters.length,
      batchProgressText:
        batch.batchTask && (batch.batchTask.status === "queued" || batch.batchTask.status === "running")
          ? `（${batch.batchTask.completed_count}/${batch.batchTask.total_count}）`
          : "",
      aiGenerateDisabled: !activeChapter || loadingChapter,
      onSwitchOutline: (outlineId) => void switchOutline(outlineId),
      onOpenBatch: batch.openModal,
      onOpenHistory: history.openDrawer,
      onOpenAiGenerate: () => setAiOpen(true),
      onOpenMemoryUpdate: () => {
        if (!activeChapter) return;
        if (dirty) {
          toast.toastWarning(WRITING_PAGE_COPY.memoryUpdateNeedsSaveFirst);
          return;
        }
        if (activeChapter.status !== "done") {
          toast.toastWarning(getWritingDoneOnlyWarning());
          return;
        }
        setMemoryUpdateOpen(true);
      },
      onOpenTaskCenter: () => {
        if (!projectId) return;
        navigate(buildWritingTaskCenterHref(projectId, activeId));
      },
      onOpenForeshadow: () => setForeshadowOpen(true),
      onOpenTables: () => setTablesOpen(true),
      onOpenContextPreview: () => setContextPreviewOpen(true),
      onCreateChapter: chapterCrud.openCreate,
    },
    chapterListProps: {
      chapters,
      activeId,
      onSelectChapter: (chapterId) => void requestSelectChapter(chapterId),
      onOpenDrawer: () => setChapterListOpen(true),
    },
    editorProps: {
      activeChapter,
      form,
      dirty,
      isDoneReadonly,
      loadingChapter,
      generating,
      saving,
      autoUpdatesTriggering,
      contentEditorTab,
      onContentEditorTabChange: setContentEditorTab,
      onTitleChange: (value) => setForm((prev) => (prev ? { ...prev, title: value } : prev)),
      onStatusChange: (status) => setForm((prev) => (prev ? { ...prev, status } : prev)),
      onPlanChange: (value) => setForm((prev) => (prev ? { ...prev, plan: value } : prev)),
      onContentChange: (value) => setForm((prev) => (prev ? { ...prev, content_md: value } : prev)),
      onSummaryChange: (value) => setForm((prev) => (prev ? { ...prev, summary: value } : prev)),
      onContentTextareaRef: (element) => {
        contentTextareaRef.current = element;
      },
      onOpenAnalysis: analysis.openModal,
      onOpenChapterTrace: () => {
        if (!projectId || !activeChapter) return;
        navigate(getWritingAnalysisHref(projectId, activeChapter.id));
      },
      onDeleteChapter: () => void chapterCrud.deleteChapter(),
      onSaveAndTriggerAutoUpdates: () => void saveAndTriggerAutoUpdates(),
      onSaveChapter: () => void saveChapter(),
      onReopenDrafting: () => setForm((prev: ChapterForm | null) => (prev ? { ...prev, status: "drafting" } : prev)),
      generationIndicatorLabel:
        genForm.stream && genStreamProgress
          ? getWritingGenerateIndicatorLabel(genStreamProgress.message, genStreamProgress.progress)
          : undefined,
    } satisfies WritingEditorSectionProps,
  };

  const chapterListDrawerProps: WritingChapterListDrawerProps = {
    open: chapterListOpen,
    chapters,
    activeId,
    onClose: () => setChapterListOpen(false),
    onSelectChapter: (chapterId) => void requestSelectChapter(chapterId),
  };

  const overlaysProps: WritingPageOverlaysProps = {
    createChapterDialogProps: {
      open: chapterCrud.createOpen,
      saving: chapterCrud.createSaving,
      form: chapterCrud.createForm,
      setForm: chapterCrud.setCreateForm,
      onClose: () => chapterCrud.setCreateOpen(false),
      onSubmit: () => void chapterCrud.createChapter(),
    },
    batchGenerationModalProps: {
      open: batch.open,
      batchLoading: batch.batchLoading,
      activeChapterNumber: activeChapter?.number ?? null,
      batchCount: batch.batchCount,
      setBatchCount: batch.setBatchCount,
      batchIncludeExisting: batch.batchIncludeExisting,
      setBatchIncludeExisting: batch.setBatchIncludeExisting,
      batchTask: batch.batchTask,
      batchItems: batch.batchItems,
      batchRuntime: batch.batchRuntime,
      projectTaskStreamStatus: batch.projectTaskStreamStatus,
      taskCenterHref: buildBatchTaskCenterHref(projectId, batch.batchTask?.project_task_id),
      onClose: batch.closeModal,
      onCancelTask: () => void batch.cancelBatchGeneration(),
      onPauseTask: () => void batch.pauseBatchGeneration(),
      onResumeTask: () => void batch.resumeBatchGeneration(),
      onRetryFailedTask: () => void batch.retryFailedBatchGeneration(),
      onSkipFailedTask: () => void batch.skipFailedBatchGeneration(),
      onStartTask: () => void batch.startBatchGeneration(),
      onApplyItemToEditor: (item) => void batch.applyBatchItemToEditor(item),
    },
    chapterAnalysisModalProps: {
      open: analysis.open,
      analysisLoading: analysis.analysisLoading,
      rewriteLoading: analysis.rewriteLoading,
      applyLoading: analysis.applyLoading,
      analysisFocus: analysis.analysisFocus,
      setAnalysisFocus: analysis.setAnalysisFocus,
      analysisResult: analysis.analysisResult,
      rewriteInstruction: analysis.rewriteInstruction,
      setRewriteInstruction: analysis.setRewriteInstruction,
      onClose: analysis.closeModal,
      onAnalyze: () => void analysis.analyzeChapter(),
      onApplyAnalysisToMemory: () => void analysis.applyAnalysisToMemory(),
      onLocateInEditor: locateInEditor,
      onRewriteFromAnalysis: () => void analysis.rewriteFromAnalysis(),
    },
    aiGenerateDrawerProps: {
      open: aiOpen,
      generating,
      preset,
      projectId,
      activeChapter: Boolean(activeChapter),
      dirty,
      saving: saving || loadingChapter,
      genForm,
      setGenForm,
      characters,
      streamProgress: genStreamProgress,
      onClose: () => setAiOpen(false),
      onSave: () => void saveChapter(),
      onSaveAndGenerateNext: () => void saveAndGenerateNext(),
      onGenerateAppend: () => void generate("append"),
      onGenerateReplace: () => void generate("replace"),
      onCancelGenerate: abortGenerate,
      onOpenPromptInspector: () => setPromptInspectorOpen(true),
      postEditCompareAvailable: Boolean(postEditCompare),
      onOpenPostEditCompare: () => setPostEditCompareOpen(true),
      contentOptimizeCompareAvailable: Boolean(contentOptimizeCompare),
      onOpenContentOptimizeCompare: () => setContentOptimizeCompareOpen(true),
    },
    postEditCompareDrawerProps: {
      open: postEditCompareOpen && Boolean(postEditCompare),
      onClose: () => setPostEditCompareOpen(false),
      rawContentMd: postEditCompare?.rawContentMd ?? "",
      editedContentMd: postEditCompare?.editedContentMd ?? "",
      requestId: postEditCompare?.requestId ?? null,
      appliedChoice: postEditCompare?.appliedChoice ?? "post_edit",
      onApplyRaw: () => void applyPostEditVariant("raw"),
      onApplyPostEdit: () => void applyPostEditVariant("post_edit"),
    },
    contentOptimizeCompareDrawerProps: {
      open: contentOptimizeCompareOpen && Boolean(contentOptimizeCompare),
      onClose: () => setContentOptimizeCompareOpen(false),
      rawContentMd: contentOptimizeCompare?.rawContentMd ?? "",
      optimizedContentMd: contentOptimizeCompare?.optimizedContentMd ?? "",
      requestId: contentOptimizeCompare?.requestId ?? null,
      appliedChoice: contentOptimizeCompare?.appliedChoice ?? "content_optimize",
      onApplyRaw: () => void applyContentOptimizeVariant("raw"),
      onApplyOptimized: () => void applyContentOptimizeVariant("content_optimize"),
    },
    promptInspectorDrawerProps: {
      open: promptInspectorOpen,
      onClose: () => setPromptInspectorOpen(false),
      preset,
      chapterId: activeChapter?.id ?? undefined,
      draftContentMd: form?.content_md ?? "",
      generating,
      genForm,
      setGenForm,
      onGenerate: generate,
    },
    contextPreviewDrawerProps: {
      open: contextPreviewOpen,
      onClose: () => setContextPreviewOpen(false),
      projectId,
      memoryInjectionEnabled: genForm.memory_injection_enabled,
      genInstruction: genForm.instruction,
      genChapterPlan: activeChapter?.plan ?? "",
      genMemoryQueryText: genForm.memory_query_text,
      genMemoryModules: genForm.memory_modules,
      onChangeMemoryInjectionEnabled: (enabled) =>
        setGenForm((prev) => ({ ...prev, memory_injection_enabled: Boolean(enabled) })),
    },
    tablesPanelProps: {
      open: tablesOpen,
      onClose: () => setTablesOpen(false),
      projectId,
    },
    memoryUpdateDrawerProps: {
      open: memoryUpdateOpen,
      onClose: () => setMemoryUpdateOpen(false),
      projectId,
      chapterId: activeId ?? undefined,
    },
    foreshadowDrawerProps: {
      open: foreshadowOpen,
      onClose: () => setForeshadowOpen(false),
      projectId,
      activeChapterId: activeId ?? undefined,
    },
    generationHistoryDrawerProps: {
      open: history.open,
      onClose: history.closeDrawer,
      loading: history.runsLoading,
      runs: history.runs,
      selectedRun: history.selectedRun,
      onSelectRun: (run) => void history.selectRun(run),
    },
  };

  const streamFloatingProps: WritingStreamFloatingCardProps = {
    open: generating && genForm.stream && !aiOpen,
    requestId: genRequestId,
    message: genStreamProgress?.message,
    progress: genStreamProgress?.progress ?? 0,
    onExpand: () => setAiOpen(true),
    onCancel: abortGenerate,
  };

  return {
    loading,
    dirty,
    showUnsavedGuard: dirty && outletActive,
    workspaceProps,
    chapterListDrawerProps,
    overlaysProps,
    streamFloatingProps,
    wizardBarProps: {
      projectId,
      currentStep: "writing",
      progress: wizard.progress,
      loading: wizard.loading,
      dirty,
      saving: saving || loadingChapter || generating,
      onSave: saveChapter,
    },
  };
}
