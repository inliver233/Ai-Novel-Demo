import { useCallback, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import type { ConfirmApi } from "../../components/ui/confirm";
import type { ToastApi } from "../../components/ui/toast";
import type { CreateChapterForm } from "../../components/writing/types";
import { ApiError, apiJson } from "../../services/apiClient";
import { markWizardProjectChanged } from "../../services/wizard";
import type { Chapter } from "../../types";
import { nextChapterNumber } from "./writingUtils";

export function useChapterCrud(args: {
  projectId: string | undefined;
  chapters: Chapter[];
  setChapters: Dispatch<SetStateAction<Chapter[]>>;
  activeChapter: Chapter | null;
  setActiveId: (next: string | null) => void;
  refreshChapters: () => Promise<void>;
  requestSelectChapter: (chapterId: string) => Promise<void>;
  toast: ToastApi;
  confirm: ConfirmApi;
  bumpWizardLocal: () => void;
  refreshWizard: () => Promise<void>;
}) {
  const {
    projectId,
    chapters,
    setChapters,
    activeChapter,
    setActiveId,
    refreshChapters,
    requestSelectChapter,
    toast,
    confirm,
    bumpWizardLocal,
    refreshWizard,
  } = args;

  const [createOpen, setCreateOpen] = useState(false);
  const [createSaving, setCreateSaving] = useState(false);
  const [createForm, setCreateForm] = useState<CreateChapterForm>({ number: 1, title: "", plan: "" });

  const openCreate = useCallback(() => {
    setCreateForm({ number: nextChapterNumber(chapters), title: "", plan: "" });
    setCreateOpen(true);
  }, [chapters]);

  const createChapter = useCallback(async () => {
    if (!projectId) return;
    if (createSaving) return;
    if (!createForm.number || createForm.number < 1) {
      toast.toastError("章号必须 >= 1");
      return;
    }
    setCreateSaving(true);
    try {
      const res = await apiJson<{ chapter: Chapter }>(`/api/projects/${projectId}/chapters`, {
        method: "POST",
        body: JSON.stringify({
          number: createForm.number,
          title: createForm.title.trim() || null,
          plan: createForm.plan.trim() || null,
          status: "planned",
        }),
      });
      setChapters((prev) => [...prev, res.data.chapter].sort((a, b) => a.number - b.number));
      markWizardProjectChanged(projectId);
      bumpWizardLocal();
      void refreshWizard();
      toast.toastSuccess("已创建", res.request_id);
      setCreateOpen(false);
      await requestSelectChapter(res.data.chapter.id);
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setCreateSaving(false);
    }
  }, [bumpWizardLocal, createForm, createSaving, projectId, refreshWizard, requestSelectChapter, setChapters, toast]);

  const deleteChapter = useCallback(async () => {
    if (!activeChapter) return;
    const ok = await confirm.confirm({
      title: "删除章节？",
      description: "删除后该章节正文与摘要将丢失。",
      confirmText: "删除",
      danger: true,
    });
    if (!ok) return;

    try {
      await apiJson<Record<string, never>>(`/api/chapters/${activeChapter.id}`, { method: "DELETE" });
      markWizardProjectChanged(activeChapter.project_id);
      bumpWizardLocal();
      void refreshWizard();
      toast.toastSuccess("已删除");
      const idx = chapters.findIndex((c) => c.id === activeChapter.id);
      const next = chapters[idx - 1]?.id ?? chapters[idx + 1]?.id ?? null;
      setActiveId(next);
      await refreshChapters();
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    }
  }, [activeChapter, bumpWizardLocal, chapters, confirm, refreshChapters, refreshWizard, setActiveId, toast]);

  return {
    createOpen,
    setCreateOpen,
    createSaving,
    createForm,
    setCreateForm,
    openCreate,
    createChapter,
    deleteChapter,
  };
}
