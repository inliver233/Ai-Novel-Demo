import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ConfirmApi } from "../../components/ui/confirm";
import type { ToastApi } from "../../components/ui/toast";
import { useAutoSave } from "../../hooks/useAutoSave";
import { useSaveHotkey } from "../../hooks/useSaveHotkey";
import { createRequestSeqGuard } from "../../lib/requestSeqGuard";
import { ApiError, apiJson } from "../../services/apiClient";
import { markWizardProjectChanged } from "../../services/wizard";
import type { Chapter } from "../../types";
import { chapterToForm } from "./writingUtils";
import type { ChapterForm } from "./writingUtils";

export function useChapterEditor(args: {
  projectId: string | undefined;
  requestedChapterId: string | null;
  searchParams: URLSearchParams;
  setSearchParams: (next: URLSearchParams, opts?: { replace?: boolean }) => void;
  toast: ToastApi;
  confirm: ConfirmApi;
  refreshWizard: () => Promise<void>;
  bumpWizardLocal: () => void;
}) {
  const {
    projectId,
    requestedChapterId,
    searchParams,
    setSearchParams,
    toast,
    confirm,
    refreshWizard,
    bumpWizardLocal,
  } = args;

  const [loading, setLoading] = useState(true);
  const [chapters, setChapters] = useState<Chapter[]>([]);

  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeChapter, setActiveChapter] = useState<Chapter | null>(null);
  const [baseline, setBaseline] = useState<ChapterForm | null>(null);
  const [form, setForm] = useState<ChapterForm | null>(null);
  const [loadingChapter, setLoadingChapter] = useState(false);
  const [saving, setSaving] = useState(false);
  const requestedChapterHandledRef = useRef(false);
  const chapterListGuardRef = useRef(createRequestSeqGuard());
  const chapterLoadGuardRef = useRef(createRequestSeqGuard());
  const saveGuardRef = useRef(createRequestSeqGuard());
  const refreshWizardDebounceRef = useRef<number | null>(null);
  const activeChapterRef = useRef<Chapter | null>(null);
  const formRef = useRef<ChapterForm | null>(null);
  const savingRef = useRef(false);
  const saveQueuedRef = useRef(false);
  const queuedSnapshotRef = useRef<ChapterForm | null>(null);
  const queuedSilentRef = useRef(true);

  useEffect(() => {
    const listGuard = chapterListGuardRef.current;
    const loadGuard = chapterLoadGuardRef.current;
    const saveGuard = saveGuardRef.current;
    return () => {
      listGuard.invalidate();
      loadGuard.invalidate();
      saveGuard.invalidate();
      if (refreshWizardDebounceRef.current !== null) {
        window.clearTimeout(refreshWizardDebounceRef.current);
        refreshWizardDebounceRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    activeChapterRef.current = activeChapter;
    formRef.current = form;
  }, [activeChapter, form]);

  const dirty = useMemo(() => {
    if (!baseline || !form) return false;
    return (
      form.title !== baseline.title ||
      form.plan !== baseline.plan ||
      form.content_md !== baseline.content_md ||
      form.summary !== baseline.summary ||
      form.status !== baseline.status
    );
  }, [baseline, form]);

  const refreshChapters = useCallback(async () => {
    if (!projectId) return;
    const seq = chapterListGuardRef.current.next();
    setLoading(true);
    try {
      const res = await apiJson<{ chapters: Chapter[] }>(`/api/projects/${projectId}/chapters`);
      if (!chapterListGuardRef.current.isLatest(seq)) return;
      setChapters(res.data.chapters);
      setActiveId((prev) => {
        if (prev && res.data.chapters.some((c) => c.id === prev)) return prev;
        return res.data.chapters[0]?.id ?? null;
      });
    } catch (e) {
      if (!chapterListGuardRef.current.isLatest(seq)) return;
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      if (chapterListGuardRef.current.isLatest(seq)) {
        setLoading(false);
      }
    }
  }, [projectId, toast]);

  useEffect(() => {
    void refreshChapters();
  }, [refreshChapters]);

  useEffect(() => {
    if (requestedChapterHandledRef.current) return;
    if (!requestedChapterId) return;
    if (!chapters.some((c) => c.id === requestedChapterId)) return;
    requestedChapterHandledRef.current = true;
    setActiveId(requestedChapterId);
    const next = new URLSearchParams(searchParams);
    next.delete("chapterId");
    setSearchParams(next, { replace: true });
  }, [chapters, requestedChapterId, searchParams, setSearchParams]);

  useEffect(() => {
    if (!activeId) {
      chapterLoadGuardRef.current.invalidate();
      setActiveChapter(null);
      setBaseline(null);
      setForm(null);
      setLoadingChapter(false);
      return;
    }
    const seq = chapterLoadGuardRef.current.next();
    setLoadingChapter(true);
    void (async () => {
      try {
        const res = await apiJson<{ chapter: Chapter }>(`/api/chapters/${activeId}`);
        if (!chapterLoadGuardRef.current.isLatest(seq)) return;
        setActiveChapter(res.data.chapter);
        const next = chapterToForm(res.data.chapter);
        setBaseline(next);
        setForm(next);
      } catch (e) {
        if (!chapterLoadGuardRef.current.isLatest(seq)) return;
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
        setActiveChapter(null);
        setBaseline(null);
        setForm(null);
      } finally {
        if (chapterLoadGuardRef.current.isLatest(seq)) {
          setLoadingChapter(false);
        }
      }
    })();
  }, [activeId, toast]);

  const saveChapter = useCallback(
    async (opts?: { snapshot?: ChapterForm; silent?: boolean }) => {
      const chapter = activeChapterRef.current;
      const current = formRef.current;
      if (!chapter || !current) return false;

      const silent = Boolean(opts?.silent);
      const snapshot = opts?.snapshot ?? current;
      if (!dirty && !opts?.snapshot) return true;
      if (savingRef.current) {
        saveQueuedRef.current = true;
        queuedSnapshotRef.current = snapshot;
        queuedSilentRef.current = queuedSilentRef.current && silent;
        return false;
      }

      const scheduleWizardRefresh = () => {
        if (refreshWizardDebounceRef.current !== null) {
          window.clearTimeout(refreshWizardDebounceRef.current);
        }
        refreshWizardDebounceRef.current = window.setTimeout(() => void refreshWizard(), 1200);
      };

      const seq = saveGuardRef.current.next();
      savingRef.current = true;
      setSaving(true);
      try {
        const res = await apiJson<{ chapter: Chapter }>(`/api/chapters/${chapter.id}`, {
          method: "PUT",
          body: JSON.stringify({
            title: snapshot.title.trim(),
            plan: snapshot.plan,
            content_md: snapshot.content_md,
            summary: snapshot.summary,
            status: snapshot.status,
          }),
        });
        if (!saveGuardRef.current.isLatest(seq)) return true;
        setActiveChapter(res.data.chapter);
        const nextBaseline = chapterToForm(res.data.chapter);
        setBaseline(nextBaseline);
        setForm((prev) => {
          if (!prev) return prev;
          if (
            prev.title === snapshot.title &&
            prev.plan === snapshot.plan &&
            prev.content_md === snapshot.content_md &&
            prev.summary === snapshot.summary &&
            prev.status === snapshot.status
          ) {
            return nextBaseline;
          }
          return prev;
        });
        setChapters((prev) => prev.map((c) => (c.id === res.data.chapter.id ? res.data.chapter : c)));
        markWizardProjectChanged(chapter.project_id);
        bumpWizardLocal();
        if (silent) scheduleWizardRefresh();
        else await refreshWizard();
        if (!silent) toast.toastSuccess("已保存", res.request_id);
        return true;
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
        return false;
      } finally {
        setSaving(false);
        savingRef.current = false;
        if (saveQueuedRef.current) {
          const nextSnapshot = queuedSnapshotRef.current ?? formRef.current;
          const nextSilent = queuedSilentRef.current;
          saveQueuedRef.current = false;
          queuedSnapshotRef.current = null;
          queuedSilentRef.current = true;
          if (nextSnapshot && activeChapterRef.current) {
            void saveChapter({ snapshot: nextSnapshot, silent: nextSilent });
          }
        }
      }
    },
    [bumpWizardLocal, dirty, refreshWizard, toast],
  );

  useSaveHotkey(() => void saveChapter(), dirty);

  useAutoSave({
    enabled: Boolean(projectId && activeChapter && form) && !loadingChapter,
    dirty,
    saveOnIdle: false,
    getSnapshot: () => (formRef.current ? { ...formRef.current } : null),
    onSave: async (snapshot) => {
      await saveChapter({ snapshot, silent: true });
    },
  });

  const requestSelectChapter = useCallback(
    async (id: string) => {
      if (id === activeId) return;
      if (dirty) {
        const choice = await confirm.choose({
          title: "章节有未保存修改，是否切换？",
          description: "切换后未保存内容会丢失。",
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
      setActiveId(id);
    },
    [activeId, confirm, dirty, saveChapter],
  );

  return {
    loading,
    chapters,
    setChapters,
    refreshChapters,
    activeId,
    setActiveId,
    activeChapter,
    baseline,
    form,
    setForm,
    dirty,
    saveChapter,
    requestSelectChapter,
    loadingChapter,
    saving,
  };
}
