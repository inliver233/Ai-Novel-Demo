import { useCallback, useEffect, useState } from "react";
import type { SetURLSearchParams } from "react-router-dom";

import type { BatchGenerationTask, BatchGenerationTaskItem, GenerateForm } from "../../components/writing/types";
import { ApiError, apiJson } from "../../services/apiClient";
import type { Chapter, LLMPreset } from "../../types";
import { extractMissingNumbers } from "./writingErrorUtils";

export function useBatchGeneration(args: {
  projectId: string | undefined;
  preset: LLMPreset | null;
  activeChapter: Chapter | null;
  chapters: Chapter[];
  genForm: GenerateForm;
  searchParams: URLSearchParams;
  setSearchParams: SetURLSearchParams;
  requestSelectChapter: (chapterId: string) => Promise<void>;
  toast: {
    toastError: (message: string, requestId?: string, action?: { label: string; onClick: () => void }) => void;
    toastSuccess: (message: string, requestId?: string) => void;
  };
}) {
  const {
    projectId,
    preset,
    activeChapter,
    chapters,
    genForm,
    searchParams,
    setSearchParams,
    requestSelectChapter,
    toast,
  } = args;

  const [open, setOpen] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchCount, setBatchCount] = useState(3);
  const [batchIncludeExisting, setBatchIncludeExisting] = useState(false);
  const [batchTask, setBatchTask] = useState<BatchGenerationTask | null>(null);
  const [batchItems, setBatchItems] = useState<BatchGenerationTaskItem[]>([]);

  const refreshBatchTask = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!projectId) return;
      try {
        const res = await apiJson<{ task: BatchGenerationTask | null; items: BatchGenerationTaskItem[] }>(
          `/api/projects/${projectId}/batch_generation_tasks/active`,
        );
        setBatchTask(res.data.task);
        setBatchItems(res.data.items);
      } catch (e) {
        if (!opts?.silent) {
          const err = e as ApiError;
          toast.toastError(`${err.message} (${err.code})`, err.requestId);
        }
      }
    },
    [projectId, toast],
  );

  useEffect(() => {
    void refreshBatchTask({ silent: true });
  }, [refreshBatchTask]);

  useEffect(() => {
    if (!batchTask) return;
    if (batchTask.status !== "queued" && batchTask.status !== "running") return;
    const id = window.setInterval(() => void refreshBatchTask({ silent: true }), 1500);
    return () => window.clearInterval(id);
  }, [batchTask, refreshBatchTask]);

  const openModal = useCallback(() => {
    setOpen(true);
    void refreshBatchTask();
  }, [refreshBatchTask]);

  const closeModal = useCallback(() => setOpen(false), []);

  const startBatchGeneration = useCallback(async () => {
    if (!projectId) return;
    if (!preset) {
      toast.toastError("请先在 Prompts 页保存 LLM 配置");
      return;
    }
    setBatchLoading(true);
    try {
      const headers: Record<string, string> = { "X-LLM-Provider": preset.provider };
      const safeTargetWordCount =
        typeof genForm.target_word_count === "number" && genForm.target_word_count >= 100
          ? genForm.target_word_count
          : null;
      const payload = {
        after_chapter_id: activeChapter?.id ?? null,
        count: batchCount,
        include_existing: batchIncludeExisting,
        instruction: genForm.instruction,
        target_word_count: safeTargetWordCount,
        plan_first: genForm.plan_first,
        post_edit: genForm.post_edit,
        post_edit_sanitize: genForm.post_edit_sanitize,
        content_optimize: genForm.content_optimize,
        style_id: genForm.style_id,
        context: {
          include_world_setting: genForm.context.include_world_setting,
          include_style_guide: genForm.context.include_style_guide,
          include_constraints: genForm.context.include_constraints,
          include_outline: genForm.context.include_outline,
          include_smart_context: genForm.context.include_smart_context,
          require_sequential: true,
          character_ids: genForm.context.character_ids,
          previous_chapter: genForm.context.previous_chapter === "none" ? null : genForm.context.previous_chapter,
        },
      };

      const res = await apiJson<{ task: BatchGenerationTask; items: BatchGenerationTaskItem[] }>(
        `/api/projects/${projectId}/batch_generation_tasks`,
        { method: "POST", headers, body: JSON.stringify(payload) },
      );
      setBatchTask(res.data.task);
      setBatchItems(res.data.items);
      toast.toastSuccess("已开始批量生成", res.request_id);
    } catch (e) {
      const err = e as ApiError;
      const missingNumbers = extractMissingNumbers(err);
      if (missingNumbers.length > 0) {
        const targetNumber = missingNumbers[0]!;
        const target = chapters.find((c) => c.number === targetNumber);
        toast.toastError(
          `缺少前置章节内容：第 ${missingNumbers.join("、")} 章`,
          err.requestId,
          target
            ? {
                label: `跳转到第 ${targetNumber} 章`,
                onClick: () => void requestSelectChapter(target.id),
              }
            : undefined,
        );
        return;
      }
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setBatchLoading(false);
    }
  }, [
    activeChapter?.id,
    batchCount,
    batchIncludeExisting,
    chapters,
    genForm,
    preset,
    projectId,
    requestSelectChapter,
    toast,
  ]);

  const cancelBatchGeneration = useCallback(async () => {
    if (!batchTask) return;
    setBatchLoading(true);
    try {
      await apiJson(`/api/batch_generation_tasks/${batchTask.id}/cancel`, { method: "POST" });
      toast.toastSuccess("已请求取消批量生成");
      await refreshBatchTask();
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setBatchLoading(false);
    }
  }, [batchTask, refreshBatchTask, toast]);

  const applyBatchItemToEditor = useCallback(
    async (item: BatchGenerationTaskItem) => {
      if (!item.chapter_id || !item.generation_run_id) return;
      setOpen(false);
      await requestSelectChapter(item.chapter_id);
      const next = new URLSearchParams(searchParams);
      next.set("applyRunId", item.generation_run_id);
      setSearchParams(next, { replace: true });
    },
    [requestSelectChapter, searchParams, setSearchParams],
  );

  return {
    open,
    openModal,
    closeModal,
    batchLoading,
    batchCount,
    setBatchCount,
    batchIncludeExisting,
    setBatchIncludeExisting,
    batchTask,
    batchItems,
    refreshBatchTask,
    startBatchGeneration,
    cancelBatchGeneration,
    applyBatchItemToEditor,
  };
}
