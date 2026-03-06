import { useCallback } from "react";

import type { ConfirmApi } from "../../components/ui/confirm";
import type { ToastApi } from "../../components/ui/toast";
import { ApiError, apiJson } from "../../services/apiClient";
import { chapterStore } from "../../services/chapterStore";
import { markWizardProjectChanged } from "../../services/wizard";
import type { Project } from "../../types";

export function useOutlineSwitcher(args: {
  projectId: string | undefined;
  activeOutlineId: string;
  dirty: boolean;
  confirm: ConfirmApi;
  toast: ToastApi;
  saveChapter: () => Promise<boolean>;
  bumpWizardLocal: () => void;
  refreshWizard: () => Promise<void>;
  refreshChapters: () => Promise<unknown>;
  refreshWriting: () => Promise<void>;
}) {
  const {
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
  } = args;

  return useCallback(
    async (nextOutlineId: string) => {
      if (!projectId) return;
      if (!nextOutlineId || nextOutlineId === activeOutlineId) return;

      if (dirty) {
        const choice = await confirm.choose({
          title: "章节有未保存修改，是否切换大纲？",
          description: "切换大纲后未保存内容会丢失。",
          confirmText: "保存并切换",
          secondaryText: "不保存切换",
          cancelText: "取消",
        });
        if (choice === "cancel") return;
        if (choice === "confirm") {
          const ok = await saveChapter();
          if (!ok) return;
        }
      }

      try {
        await apiJson<{ project: Project }>(`/api/projects/${projectId}`, {
          method: "PUT",
          body: JSON.stringify({ active_outline_id: nextOutlineId }),
        });
        markWizardProjectChanged(projectId);
        bumpWizardLocal();
        chapterStore.invalidateProjectChapters(projectId, { dropDetails: true });
        await refreshWriting();
        await refreshChapters();
        await refreshWizard();
        toast.toastSuccess("已切换大纲");
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      }
    },
    [
      activeOutlineId,
      bumpWizardLocal,
      confirm,
      dirty,
      projectId,
      refreshChapters,
      refreshWriting,
      refreshWizard,
      saveChapter,
      toast,
    ],
  );
}
