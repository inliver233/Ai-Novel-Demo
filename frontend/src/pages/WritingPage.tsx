import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { List } from "lucide-react";
import { useParams, useSearchParams } from "react-router-dom";

import { GhostwriterIndicator } from "../components/atelier/GhostwriterIndicator";
import { MarkdownEditor } from "../components/atelier/MarkdownEditor";
import { WizardNextBar } from "../components/atelier/WizardNextBar";
import { Drawer } from "../components/ui/Drawer";
import { Modal } from "../components/ui/Modal";
import { AiGenerateDrawer } from "../components/writing/AiGenerateDrawer";
import { CreateChapterDialog } from "../components/writing/CreateChapterDialog";
import { GenerationHistoryDrawer } from "../components/writing/GenerationHistoryDrawer";
import { useConfirm } from "../components/ui/confirm";
import { useToast } from "../components/ui/toast";
import { useProjectData } from "../hooks/useProjectData";
import { useSaveHotkey } from "../hooks/useSaveHotkey";
import { useUnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";
import { useWizardProgress } from "../hooks/useWizardProgress";
import { ApiError, apiJson } from "../services/apiClient";
import { createChapterMarkerStreamParser } from "../services/chapterMarkerStreamParser";
import { SSEError, SSEPostClient } from "../services/sseClient";
import { markWizardProjectChanged } from "../services/wizard";
import type {
  BatchGenerationTask,
  BatchGenerationTaskItem,
  ChapterAnalyzeResult,
  ChapterRewriteResult,
  CreateChapterForm,
  GenerateForm,
  GenerationRun,
} from "../components/writing/types";
import { appendMarkdown, chapterToForm, nextChapterNumber } from "./writing/writingUtils";
import type { ChapterForm } from "./writing/writingUtils";
import type { Chapter, ChapterStatus, Character, LLMPreset, Outline, OutlineListItem, Project } from "../types";

type WritingLoaded = { outlines: OutlineListItem[]; outline: Outline; preset: LLMPreset; characters: Character[] };

export function WritingPage() {
  const { projectId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedChapterId = searchParams.get("chapterId");
  const applyRunId = searchParams.get("applyRunId");
  const toast = useToast();
  const confirm = useConfirm();
  const wizard = useWizardProgress(projectId);
  const refreshWizard = wizard.refresh;
  const bumpWizardLocal = wizard.bumpLocal;

  const [loading, setLoading] = useState(true);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [chapterListOpen, setChapterListOpen] = useState(false);
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

  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeChapter, setActiveChapter] = useState<Chapter | null>(null);
  const [baseline, setBaseline] = useState<ChapterForm | null>(null);
  const [form, setForm] = useState<ChapterForm | null>(null);
  const [loadingChapter, setLoadingChapter] = useState(false);
  const requestedChapterHandledRef = useRef(false);
  const contentTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [contentEditorTab, setContentEditorTab] = useState<"edit" | "preview">("edit");

  const [createOpen, setCreateOpen] = useState(false);
  const [createSaving, setCreateSaving] = useState(false);
  const [createForm, setCreateForm] = useState<CreateChapterForm>({ number: 1, title: "", plan: "" });

  const [aiOpen, setAiOpen] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [genRequestId, setGenRequestId] = useState<string | null>(null);
  const [genStreamProgress, setGenStreamProgress] = useState<{
    message: string;
    progress: number;
    status: string;
    wordCount?: number;
  } | null>(null);
  const genStreamClientRef = useRef<SSEPostClient | null>(null);
  const genStreamHasChunkRef = useRef(false);
  const autoGenerateNextRef = useRef<{ chapterId: string; mode: "replace" | "append" } | null>(null);
  const [genForm, setGenForm] = useState<GenerateForm>({
    instruction: "写出本章冲突升级，结尾留钩子。",
    target_word_count: 3000,
    stream: false,
    plan_first: false,
    post_edit: false,
    context: {
      include_world_setting: true,
      include_style_guide: true,
      include_constraints: true,
      include_outline: true,
      include_smart_context: true,
      require_sequential: false,
      character_ids: [],
      previous_chapter: "summary",
    },
  });

  const [batchOpen, setBatchOpen] = useState(false);
  const [batchCount, setBatchCount] = useState(3);
  const [batchIncludeExisting, setBatchIncludeExisting] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchTask, setBatchTask] = useState<BatchGenerationTask | null>(null);
  const [batchItems, setBatchItems] = useState<BatchGenerationTaskItem[]>([]);

  const [historyOpen, setHistoryOpen] = useState(false);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runs, setRuns] = useState<GenerationRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<GenerationRun | null>(null);

  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<ChapterAnalyzeResult | null>(null);
  const [analysisFocus, setAnalysisFocus] = useState("");
  const [rewriteInstruction, setRewriteInstruction] = useState("按分析建议重写，减少重复，保持叙事连续。");
  const [rewriteLoading, setRewriteLoading] = useState(false);

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

  useUnsavedChangesGuard(dirty);

  const refreshRuns = useCallback(async () => {
    if (!projectId) return;
    setRunsLoading(true);
    try {
      const res = await apiJson<{ runs: GenerationRun[] }>(`/api/projects/${projectId}/generation_runs?limit=5`);
      setRuns(res.data.runs);
      setSelectedRun(res.data.runs[0] ?? null);
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setRunsLoading(false);
    }
  }, [projectId, toast]);

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

  useEffect(() => {
    setAnalysisOpen(false);
    setAnalysisResult(null);
    setAnalysisLoading(false);
    setRewriteLoading(false);
  }, [activeChapter?.id]);

  const selectRun = useCallback(
    async (run: GenerationRun) => {
      setSelectedRun(run);
      try {
        const res = await apiJson<{ run: GenerationRun }>(`/api/generation_runs/${run.id}`);
        setSelectedRun(res.data.run);
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      }
    },
    [toast],
  );

  const refreshChapters = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const res = await apiJson<{ chapters: Chapter[] }>(`/api/projects/${projectId}/chapters`);
      setChapters(res.data.chapters);
      setActiveId((prev) => {
        if (prev && res.data.chapters.some((c) => c.id === prev)) return prev;
        return res.data.chapters[0]?.id ?? null;
      });
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setLoading(false);
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
      setActiveChapter(null);
      setBaseline(null);
      setForm(null);
      autoGenerateNextRef.current = null;
      return;
    }
    setLoadingChapter(true);
    void (async () => {
      try {
        const res = await apiJson<{ chapter: Chapter }>(`/api/chapters/${activeId}`);
        setActiveChapter(res.data.chapter);
        const next = chapterToForm(res.data.chapter);
        setBaseline(next);
        setForm(next);
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
        setActiveChapter(null);
        setBaseline(null);
        setForm(null);
        autoGenerateNextRef.current = null;
      } finally {
        setLoadingChapter(false);
      }
    })();
  }, [activeId, toast]);

  const saveChapter = useCallback(async () => {
    if (!activeChapter || !form) return false;
    if (!dirty) return true;
    try {
      const res = await apiJson<{ chapter: Chapter }>(`/api/chapters/${activeChapter.id}`, {
        method: "PUT",
        body: JSON.stringify({
          title: form.title.trim(),
          plan: form.plan,
          content_md: form.content_md,
          summary: form.summary,
          status: form.status,
        }),
      });
      setActiveChapter(res.data.chapter);
      const next = chapterToForm(res.data.chapter);
      setBaseline(next);
      setForm(next);
      setChapters((prev) => prev.map((c) => (c.id === res.data.chapter.id ? res.data.chapter : c)));
      markWizardProjectChanged(activeChapter.project_id);
      bumpWizardLocal();
      await refreshWizard();
      toast.toastSuccess("已保存", res.request_id);
      return true;
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
      return false;
    }
  }, [activeChapter, bumpWizardLocal, dirty, form, refreshWizard, toast]);

  useSaveHotkey(() => void saveChapter(), dirty);

  useEffect(() => {
    if (!applyRunId) return;
    if (!activeChapter || !form) return;

    let canceled = false;
    void (async () => {
      try {
        if (dirty) {
          const choice = await confirm.choose({
            title: "章节有未保存修改，是否应用生成记录？",
            description: "应用后会覆盖编辑器内容（不会自动保存）。",
            confirmText: "保存并应用",
            secondaryText: "直接应用（不保存）",
            cancelText: "取消",
          });
          if (choice === "cancel") return;
          if (choice === "confirm") {
            const ok = await saveChapter();
            if (!ok) return;
          }
        }

        const res = await apiJson<{ run: GenerationRun }>(`/api/generation_runs/${applyRunId}`);
        if (canceled) return;

        const run = res.data.run;
        if (run.chapter_id && run.chapter_id !== activeChapter.id) {
          toast.toastError("生成记录不属于当前章节，请先切换到对应章节再应用", res.request_id);
          return;
        }
        const raw = typeof run.output_text === "string" ? run.output_text : "";
        if (!raw.trim()) {
          toast.toastError("生成记录为空，无法应用", res.request_id);
          return;
        }

        const parser = createChapterMarkerStreamParser();
        let content = "";
        let summary = "";
        const out1 = parser.push(raw);
        content += out1.contentDelta;
        summary += out1.summaryDelta;
        const out2 = parser.finalize();
        content += out2.contentDelta;
        summary += out2.summaryDelta;

        const nextContent = content.trim() || raw.trim();
        const nextSummary = summary.trim();
        setForm((prev) =>
          prev ? { ...prev, content_md: nextContent, summary: nextSummary || prev.summary, status: "drafting" } : prev,
        );
        toast.toastSuccess("已应用生成结果（别忘了保存）", res.request_id);
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        const next = new URLSearchParams(searchParams);
        next.delete("applyRunId");
        setSearchParams(next, { replace: true });
      }
    })();

    return () => {
      canceled = true;
    };
  }, [activeChapter, applyRunId, confirm, dirty, form, saveChapter, searchParams, setSearchParams, toast]);

  const requestSelectChapter = useCallback(
    async (id: string) => {
      if (id === activeId) return;
      autoGenerateNextRef.current = null;
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

  const activeOutlineId = outline?.id ?? "";

  const switchOutline = useCallback(
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
  }, [bumpWizardLocal, createForm, createSaving, projectId, refreshWizard, requestSelectChapter, toast]);

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
  }, [activeChapter, bumpWizardLocal, chapters, confirm, refreshChapters, refreshWizard, toast]);

  const generate = useCallback(
    async (mode: "replace" | "append") => {
      if (!activeChapter || !form) return;
      if (!preset) {
        toast.toastError("请先在 Prompts 页保存 LLM 配置");
        return;
      }
      const headers: Record<string, string> = { "X-LLM-Provider": preset.provider };

      if (dirty) {
        const choice = await confirm.choose({
          title: "章节有未保存修改，如何生成？",
          description: "生成结果会写入编辑器，但不会自动保存。",
          confirmText: "保存并生成",
          secondaryText: "直接生成（不保存当前修改）",
          cancelText: "取消",
        });
        if (choice === "cancel") return;
        if (choice === "confirm") {
          const ok = await saveChapter();
          if (!ok) return;
        }
      }

      setGenerating(true);
      setGenRequestId(null);
      setGenStreamProgress(null);
      genStreamClientRef.current = null;
      genStreamHasChunkRef.current = false;
      try {
        const currentDraftTail =
          mode === "append"
            ? (form.content_md ?? "").trimEnd().slice(-1200)
            : null;

          const payload = {
            mode,
            instruction: genForm.instruction,
            target_word_count: genForm.target_word_count > 0 ? genForm.target_word_count : null,
             plan_first: genForm.plan_first,
             post_edit: genForm.post_edit,
             context: {
               include_world_setting: genForm.context.include_world_setting,
               include_style_guide: genForm.context.include_style_guide,
               include_constraints: genForm.context.include_constraints,
              include_outline: genForm.context.include_outline,
              include_smart_context: genForm.context.include_smart_context,
              require_sequential: genForm.context.require_sequential,
              character_ids: genForm.context.character_ids,
              previous_chapter: genForm.context.previous_chapter === "none" ? null : genForm.context.previous_chapter,
              current_draft_tail: currentDraftTail,
            },
          };

         const baseContent = form.content_md;
         const baseSummary = form.summary;

         if (genForm.stream) {
           const parser = createChapterMarkerStreamParser();
           let parsedContent = "";
           let parsedSummary = "";
           let requestId: string | undefined;
           let nonFatalNoticed = false;

           const processChunk = (chunk: string) => {
             const out = parser.push(chunk);
             if (out.contentDelta) parsedContent += out.contentDelta;
             if (out.summaryDelta) parsedSummary += out.summaryDelta;
           };

           const client = new SSEPostClient(`/api/chapters/${activeChapter.id}/generate-stream`, payload, {
             headers,
             onOpen: ({ requestId: rid }) => {
                requestId = rid;
              setGenRequestId(rid ?? null);
            },
             onProgress: ({ message, progress, status, wordCount }) => {
               setGenStreamProgress({ message, progress, status, wordCount });
               if (!nonFatalNoticed && status === "error") {
                 nonFatalNoticed = true;
                 toast.toastError(message, requestId);
               }
             },
            onChunk: (chunk) => {
              genStreamHasChunkRef.current = true;
              processChunk(chunk);
              setForm((prev) => {
                if (!prev) return prev;
                const nextContent = mode === "append" ? appendMarkdown(baseContent, parsedContent) : parsedContent;
                return { ...prev, content_md: nextContent, status: "drafting" };
              });
            },
            onResult: (data) => {
              const obj = data && typeof data === "object" ? (data as Record<string, unknown>) : null;
              const content = typeof obj?.content_md === "string" ? obj.content_md : "";
              const summary = typeof obj?.summary === "string" ? obj.summary : "";
              const parseErrObj =
                obj?.parse_error && typeof obj.parse_error === "object"
                  ? (obj.parse_error as Record<string, unknown>)
                  : null;
              const parseErrCode = typeof parseErrObj?.code === "string" ? parseErrObj.code : undefined;
              const parseErrMessage = typeof parseErrObj?.message === "string" ? parseErrObj.message : undefined;
              if (parseErrCode === "OUTPUT_TRUNCATED") {
                toast.toastError(parseErrMessage ?? "输出被截断", requestId);
              }
              setForm((prev) => {
                if (!prev) return prev;
                const nextContent = mode === "append" ? appendMarkdown(baseContent, content) : content;
                const nextSummary = summary || parsedSummary.trim() || prev.summary || baseSummary;
                return { ...prev, content_md: nextContent, summary: nextSummary, status: "drafting" };
              });
            },
          });
          genStreamClientRef.current = client;

          try {
            await client.connect();
            toast.toastSuccess("生成完成（别忘了保存）", requestId);
          } catch (e) {
            const err = e as unknown;
            if (err instanceof SSEError && err.code === "ABORTED") {
              setForm((prev) => (prev ? { ...prev, content_md: baseContent, summary: baseSummary } : prev));
              toast.toastSuccess("已取消生成", err.requestId ?? requestId);
              return;
            }
            if (err instanceof SSEError && err.code !== "SSE_SERVER_ERROR") {
              if (!genStreamHasChunkRef.current) {
                toast.toastError("流式生成失败，已回退非流式", err.requestId ?? requestId);
                const res = await apiJson<{ content_md: string; summary: string; raw_output: string }>(
                  `/api/chapters/${activeChapter.id}/generate`,
                  {
                    method: "POST",
                    headers,
                    body: JSON.stringify(payload),
                  },
                );

                setForm((prev) => {
                  if (!prev) return prev;
                  const nextContent =
                    mode === "append"
                      ? appendMarkdown(prev.content_md, res.data.content_md ?? "")
                      : (res.data.content_md ?? "");
                  return {
                    ...prev,
                    content_md: nextContent,
                    summary: res.data.summary ?? prev.summary,
                    status: "drafting",
                  };
                });

                toast.toastSuccess("生成完成（别忘了保存）", res.request_id);
                return;
              }
              toast.toastError(`${err.message} (${err.code})`, err.requestId);
              return;
            }
            if (err instanceof SSEError && err.code === "SSE_SERVER_ERROR") {
              toast.toastError(`${err.message} (${err.code})`, err.requestId);
              return;
            }
             if (err instanceof ApiError) {
              const missingNumbers =
                err.code === "CHAPTER_PREREQ_MISSING" &&
                err.details &&
                typeof err.details === "object" &&
                "missing_numbers" in err.details &&
                Array.isArray((err.details as { missing_numbers?: unknown }).missing_numbers)
                  ? ((err.details as { missing_numbers?: unknown }).missing_numbers as unknown[])
                      .filter((n) => typeof n === "number")
                      .map((n) => n as number)
                  : [];
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
              return;
             }
             toast.toastError("生成失败");
           }
         } else {
          const res = await apiJson<{ content_md: string; summary: string; raw_output: string }>(
            `/api/chapters/${activeChapter.id}/generate`,
            {
              method: "POST",
              headers,
              body: JSON.stringify(payload),
            },
          );

          setForm((prev) => {
            if (!prev) return prev;
            const nextContent =
              mode === "append"
                ? appendMarkdown(prev.content_md, res.data.content_md ?? "")
                : (res.data.content_md ?? "");
            return {
              ...prev,
              content_md: nextContent,
              summary: res.data.summary ?? prev.summary,
              status: "drafting",
            };
          });

          toast.toastSuccess("生成完成（别忘了保存）", res.request_id);
        }
        } catch (e) {
        const err = e as ApiError;
        const missingNumbers =
          err.code === "CHAPTER_PREREQ_MISSING" &&
          err.details &&
          typeof err.details === "object" &&
          "missing_numbers" in err.details &&
          Array.isArray((err.details as { missing_numbers?: unknown }).missing_numbers)
            ? ((err.details as { missing_numbers?: unknown }).missing_numbers as unknown[])
                .filter((n) => typeof n === "number")
                .map((n) => n as number)
            : [];
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
        setGenerating(false);
      }
    },
    [activeChapter, chapters, confirm, dirty, form, genForm, preset, requestSelectChapter, saveChapter, toast],
  );

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
        toast.toastError("未在正文中找到该引用片段（可复制后 Ctrl/Cmd+F 搜索）");
        return;
      }

      setContentEditorTab("edit");
      window.requestAnimationFrame(() => {
        const el = contentTextareaRef.current;
        if (!el) return;
        el.focus();
        el.setSelectionRange(index, Math.min(haystack.length, index + needle.length));
      });
    },
    [contentTextareaRef, form, setContentEditorTab, toast],
  );

  const analyzeChapter = useCallback(async () => {
    if (!activeChapter || !form) return;
    if (!preset) {
      toast.toastError("请先在 Prompts 页保存 LLM 配置");
      return;
    }
    if (!(form.content_md ?? "").trim()) {
      toast.toastError("正文为空，无法分析");
      return;
    }

    const headers: Record<string, string> = { "X-LLM-Provider": preset.provider };
    setAnalysisLoading(true);
    try {
      const payload = {
        instruction: analysisFocus,
        context: {
          include_world_setting: genForm.context.include_world_setting,
          include_style_guide: genForm.context.include_style_guide,
          include_constraints: genForm.context.include_constraints,
          include_outline: genForm.context.include_outline,
          include_smart_context: genForm.context.include_smart_context,
          require_sequential: genForm.context.require_sequential,
          character_ids: genForm.context.character_ids,
          previous_chapter: genForm.context.previous_chapter === "none" ? null : genForm.context.previous_chapter,
        },
        draft_title: form.title,
        draft_plan: form.plan,
        draft_summary: form.summary,
        draft_content_md: form.content_md,
      };

      const res = await apiJson<ChapterAnalyzeResult>(`/api/chapters/${activeChapter.id}/analyze`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });
      setAnalysisResult(res.data);
      if (res.data.parse_error?.message) {
        toast.toastError(`分析解析失败：${res.data.parse_error.message}`, res.request_id);
      } else {
        toast.toastSuccess("分析完成", res.request_id);
      }
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setAnalysisLoading(false);
    }
  }, [activeChapter, analysisFocus, form, genForm, preset, toast]);

  const rewriteFromAnalysis = useCallback(async () => {
    if (!activeChapter || !form) return;
    if (!preset) {
      toast.toastError("请先在 Prompts 页保存 LLM 配置");
      return;
    }
    if (!analysisResult?.analysis) {
      toast.toastError("请先完成章节分析");
      return;
    }
    if (!(form.content_md ?? "").trim()) {
      toast.toastError("正文为空，无法重写");
      return;
    }

    const headers: Record<string, string> = { "X-LLM-Provider": preset.provider };
    setRewriteLoading(true);
    try {
      const payload = {
        instruction: rewriteInstruction,
        analysis: analysisResult.analysis,
        draft_content_md: form.content_md,
        context: {
          include_world_setting: genForm.context.include_world_setting,
          include_style_guide: genForm.context.include_style_guide,
          include_constraints: genForm.context.include_constraints,
          include_outline: genForm.context.include_outline,
          include_smart_context: genForm.context.include_smart_context,
          require_sequential: genForm.context.require_sequential,
          character_ids: genForm.context.character_ids,
          previous_chapter: genForm.context.previous_chapter === "none" ? null : genForm.context.previous_chapter,
        },
      };

      const res = await apiJson<ChapterRewriteResult>(`/api/chapters/${activeChapter.id}/rewrite`, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });

      const nextContent = (res.data.content_md ?? "").trim();
      if (!nextContent) {
        const msg = res.data.parse_error?.message ?? "重写解析失败";
        toast.toastError(msg, res.request_id);
        return;
      }

      setForm((prev) => (prev ? { ...prev, content_md: nextContent, status: "drafting" } : prev));
      toast.toastSuccess("已应用重写结果到编辑器（未保存）", res.request_id);
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setRewriteLoading(false);
    }
  }, [activeChapter, analysisResult?.analysis, form, genForm, preset, rewriteInstruction, toast]);

  const startBatchGeneration = useCallback(async () => {
    if (!projectId) return;
    if (!preset) {
      toast.toastError("请先在 Prompts 页保存 LLM 配置");
      return;
    }
    setBatchLoading(true);
    try {
      const headers: Record<string, string> = { "X-LLM-Provider": preset.provider };
      const payload = {
        after_chapter_id: activeChapter?.id ?? null,
        count: batchCount,
        include_existing: batchIncludeExisting,
        instruction: genForm.instruction,
        target_word_count: genForm.target_word_count > 0 ? genForm.target_word_count : null,
        plan_first: genForm.plan_first,
        post_edit: genForm.post_edit,
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
      const missingNumbers =
        err.code === "CHAPTER_PREREQ_MISSING" &&
        err.details &&
        typeof err.details === "object" &&
        "missing_numbers" in err.details &&
        Array.isArray((err.details as { missing_numbers?: unknown }).missing_numbers)
          ? ((err.details as { missing_numbers?: unknown }).missing_numbers as unknown[])
              .filter((n) => typeof n === "number")
              .map((n) => n as number)
          : [];
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
    activeChapter,
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
      setBatchOpen(false);
      await requestSelectChapter(item.chapter_id);
      const next = new URLSearchParams(searchParams);
      next.set("applyRunId", item.generation_run_id);
      setSearchParams(next, { replace: true });
    },
    [requestSelectChapter, searchParams, setSearchParams],
  );

  const saveAndGenerateNext = useCallback(async () => {
    if (!activeChapter) return;

    const ok = await saveChapter();
    if (!ok) return;

    const sorted = [...chapters].sort((a, b) => (a.number ?? 0) - (b.number ?? 0));
    const idx = sorted.findIndex((c) => c.id === activeChapter.id);
    const next =
      idx >= 0
        ? (sorted[idx + 1] ?? null)
        : (sorted.find((c) => (c.number ?? 0) > (activeChapter.number ?? 0)) ?? null);

    if (!next) {
      toast.toastSuccess("已保存，已是最后一章");
      return;
    }

    const nextHasContent = Boolean((next.content_md ?? "").trim() || (next.summary ?? "").trim());
    if (nextHasContent) {
      const replaceOk = await confirm.confirm({
        title: `下一章（第 ${next.number} 章）已有内容，仍要开始生成？`,
        description: "将以“替换”模式生成草稿（生成结果不会自动保存）。",
        confirmText: "继续",
        cancelText: "取消",
        danger: true,
      });
      if (!replaceOk) return;
    }

    autoGenerateNextRef.current = { chapterId: next.id, mode: "replace" };
    setActiveId(next.id);
    setAiOpen(true);
  }, [activeChapter, chapters, confirm, saveChapter, toast]);

  useEffect(() => {
    const pending = autoGenerateNextRef.current;
    if (!pending) return;
    if (!activeChapter || !form) return;
    if (activeChapter.id !== pending.chapterId) return;
    if (generating) return;
    autoGenerateNextRef.current = null;
    void generate(pending.mode);
  }, [activeChapter, form, generate, generating]);

  if (loading) return <div className="text-subtext">加载中...</div>;

  return (
    <div className="grid gap-4">
      <div className="panel p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-subtext">当前大纲</span>
            <select
              className="select w-auto"
              name="active_outline_id"
              value={activeOutlineId}
              onChange={(e) => void switchOutline(e.target.value)}
            >
              {outlines.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.title}
                  {o.has_chapters ? "（已有章节）" : ""}
                </option>
              ))}
            </select>
            <span className="text-xs text-subtext">共 {chapters.length} 章</span>
          </div>

          <div className="flex items-center gap-2">
            <button className="btn btn-secondary lg:hidden" onClick={() => setChapterListOpen(true)} type="button">
              <List size={16} />
              章节列表
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => {
                setBatchOpen(true);
                void refreshBatchTask();
              }}
              type="button"
            >
              批量生成
              {batchTask && (batchTask.status === "queued" || batchTask.status === "running")
                ? `（${batchTask.completed_count}/${batchTask.total_count}）`
                : ""}
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => {
                setHistoryOpen(true);
                void refreshRuns();
              }}
              type="button"
            >
              生成记录
            </button>
            <button className="btn btn-primary" onClick={openCreate} type="button">
              新增章节
            </button>
          </div>
        </div>
      </div>

      <div className="flex gap-4">
        <aside className="hidden w-[240px] shrink-0 lg:block">
          <div className="panel p-2">
            {chapters.length === 0 ? (
              <div className="p-3 text-sm text-subtext">还没有章节，先新建一个吧。</div>
            ) : (
              <div className="flex flex-col gap-1">
                {chapters.map((c) => (
                  <button
                    key={c.id}
                    className={
                      c.id === activeId
                        ? "ui-focus-ring ui-transition-fast rounded-atelier bg-canvas px-3 py-2 text-left text-sm text-ink"
                        : "ui-focus-ring ui-transition-fast rounded-atelier px-3 py-2 text-left text-sm text-subtext hover:bg-canvas hover:text-ink"
                    }
                    onClick={() => void requestSelectChapter(c.id)}
                    type="button"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0 truncate">
                        <span className="mr-2 text-xs text-subtext">#{c.number}</span>
                        <span className="truncate">{c.title ?? "未命名章节"}</span>
                      </div>
                      <span className="shrink-0 text-[11px] text-subtext">{c.status}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </aside>

        <section className="min-w-0 flex-1">
          {!activeChapter || !form ? (
            <div className="panel p-8 text-sm text-subtext">请选择或新建章节开始写作。</div>
          ) : (
            <div className="panel p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-content text-2xl text-ink">
                    第 {activeChapter.number} 章 <span className="text-subtext">{dirty ? "（未保存）" : ""}</span>
                  </div>
                  <div className="mt-1 text-xs text-subtext">updated_at: {activeChapter.updated_at}</div>
                </div>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <button
                    className="btn btn-secondary"
                    disabled={loadingChapter}
                    onClick={() => setAiOpen(true)}
                    type="button"
                  >
                    AI 生成
                  </button>
                  <button
                    className="btn btn-secondary"
                    disabled={loadingChapter || generating}
                    onClick={() => setAnalysisOpen(true)}
                    type="button"
                  >
                    分析
                  </button>
                  <button
                    className="btn btn-ghost text-accent hover:bg-accent/10"
                    disabled={loadingChapter || generating}
                    onClick={() => void deleteChapter()}
                    type="button"
                  >
                    删除
                  </button>
                  <button
                    className="btn btn-primary"
                    disabled={!dirty || loadingChapter || generating}
                    onClick={() => void saveChapter()}
                    type="button"
                  >
                    保存
                  </button>
                </div>
              </div>

              {generating ? (
                <GhostwriterIndicator
                  className="mt-4"
                  label={
                    genForm.stream && genStreamProgress
                      ? `${genStreamProgress.message}（${genStreamProgress.progress}%）`
                      : "墨迹渗入纸张中…生成需要一点时间"
                  }
                />
              ) : null}

              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <label className="grid gap-1 sm:col-span-2">
                  <span className="text-xs text-subtext">标题</span>
                  <input
                    className="input"
                    disabled={generating}
                    name="title"
                    value={form.title}
                    onChange={(e) => setForm((v) => (v ? { ...v, title: e.target.value } : v))}
                  />
                </label>
                <label className="grid gap-1 sm:col-span-1">
                  <span className="text-xs text-subtext">状态</span>
                  <select
                    className="select"
                    disabled={generating}
                    name="status"
                    value={form.status}
                    onChange={(e) => setForm((v) => (v ? { ...v, status: e.target.value as ChapterStatus } : v))}
                  >
                    <option value="planned">planned</option>
                    <option value="drafting">drafting</option>
                    <option value="done">done</option>
                  </select>
                </label>
              </div>

              <div className="mt-4 grid gap-3">
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">本章要点</span>
                  <textarea
                    className="textarea atelier-content"
                    disabled={generating}
                    name="plan"
                    rows={4}
                    value={form.plan}
                    onChange={(e) => setForm((v) => (v ? { ...v, plan: e.target.value } : v))}
                  />
                </label>
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">正文（Markdown）</span>
                  <MarkdownEditor
                    value={form.content_md}
                    onChange={(next) => setForm((v) => (v ? { ...v, content_md: next } : v))}
                    placeholder="开始写作..."
                    minRows={16}
                    name="content_md"
                    readOnly={generating}
                    tab={contentEditorTab}
                    onTabChange={setContentEditorTab}
                    textareaRef={contentTextareaRef}
                  />
                </label>
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">摘要（可选）</span>
                  <textarea
                    className="textarea atelier-content"
                    disabled={generating}
                    name="summary"
                    rows={3}
                    value={form.summary}
                    onChange={(e) => setForm((v) => (v ? { ...v, summary: e.target.value } : v))}
                  />
                </label>
              </div>

              <div className="mt-4 text-xs text-subtext">快捷键：Ctrl/Cmd + S 保存</div>
            </div>
          )}
        </section>
      </div>

      <CreateChapterDialog
        open={createOpen}
        saving={createSaving}
        form={createForm}
        setForm={setCreateForm}
        onClose={() => setCreateOpen(false)}
        onSubmit={() => void createChapter()}
      />

      <Modal
        open={batchOpen}
        onClose={batchLoading ? undefined : () => setBatchOpen(false)}
        panelClassName="surface max-w-2xl p-5"
        ariaLabel="批量生成"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-content text-xl text-ink">批量顺序生成</div>
            <div className="mt-1 text-xs text-subtext">
              批量生成只会写入“生成记录”，不会自动保存到章节；你可以逐章“应用到编辑器”后再保存。
            </div>
          </div>
          <button className="btn btn-secondary" onClick={() => setBatchOpen(false)} disabled={batchLoading} type="button">
            关闭
          </button>
        </div>

        <div className="mt-4 grid gap-3">
          <div className="grid gap-2 rounded-atelier border border-border bg-canvas p-3">
            <div className="text-xs text-subtext">
              起点：{activeChapter ? `第 ${activeChapter.number} 章之后` : "从第 1 章开始"}
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <label className="grid gap-1">
                <span className="text-xs text-subtext">数量（1~20）</span>
                <input
                  className="input w-28"
                  min={1}
                  max={20}
                  type="number"
                  value={batchCount}
                  onChange={(e) => setBatchCount(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
                />
              </label>
              <label className="flex items-center gap-2 pb-2 text-sm text-ink">
                <input
                  className="checkbox"
                  type="checkbox"
                  checked={batchIncludeExisting}
                  disabled={batchLoading}
                  onChange={(e) => setBatchIncludeExisting(e.target.checked)}
                />
                包含已有内容章节
              </label>
              <div className="flex-1" />
              {batchTask && (batchTask.status === "queued" || batchTask.status === "running") ? (
                <button className="btn btn-secondary" disabled={batchLoading} onClick={() => void cancelBatchGeneration()} type="button">
                  {batchLoading ? "取消中..." : "取消任务"}
                </button>
              ) : (
                <button className="btn btn-primary" disabled={batchLoading} onClick={() => void startBatchGeneration()} type="button">
                  {batchLoading ? "启动中..." : "开始批量生成"}
                </button>
              )}
            </div>
          </div>

          {batchTask ? (
            <div className="grid gap-2 rounded-atelier border border-border bg-surface p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm text-ink">
                  任务状态：{batchTask.status}（{batchTask.completed_count}/{batchTask.total_count}）
                </div>
                {batchTask.status === "failed" && batchTask.error_json ? (
                  <div className="text-xs text-subtext">错误：{batchTask.error_json}</div>
                ) : null}
              </div>
              <div className="h-2 w-full rounded bg-border">
                <div
                  className="h-2 rounded bg-accent motion-safe:transition-[width] motion-safe:duration-atelier motion-safe:ease-atelier"
                  style={{
                    width: `${Math.round(
                      (batchTask.total_count > 0 ? batchTask.completed_count / batchTask.total_count : 0) * 100,
                    )}%`,
                  }}
                />
              </div>
              <div className="max-h-64 overflow-auto rounded-atelier border border-border bg-canvas">
                {batchItems.length === 0 ? (
                  <div className="p-3 text-sm text-subtext">暂无任务项</div>
                ) : (
                  <div className="divide-y divide-border">
                    {batchItems.map((it) => (
                      <div key={it.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                        <div className="min-w-0">
                          <div className="text-sm text-ink">第 {it.chapter_number} 章</div>
                          <div className="text-xs text-subtext">
                            {it.status}
                            {it.error_message ? ` · ${it.error_message}` : ""}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {it.status === "succeeded" && it.chapter_id && it.generation_run_id ? (
                            <button
                              className="btn btn-secondary"
                              onClick={() => void applyBatchItemToEditor(it)}
                              disabled={batchLoading}
                              type="button"
                            >
                              应用到编辑器
                            </button>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="text-sm text-subtext">当前没有进行中的任务。</div>
          )}
        </div>
      </Modal>

      <Modal
        open={analysisOpen}
        onClose={analysisLoading || rewriteLoading ? undefined : () => setAnalysisOpen(false)}
        panelClassName="surface max-w-3xl p-5"
        ariaLabel="章节分析"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="font-content text-xl text-ink">章节分析 / 建议</div>
            <div className="mt-1 text-xs text-subtext">分析与重写只会写入“生成记录”，不会自动保存到章节。</div>
          </div>
          <button
            className="btn btn-secondary"
            onClick={() => setAnalysisOpen(false)}
            disabled={analysisLoading || rewriteLoading}
            type="button"
          >
            关闭
          </button>
        </div>

        <div className="mt-4 grid gap-3">
          <label className="grid gap-1">
            <span className="text-xs text-subtext">分析重点（可选）</span>
            <input
              className="input"
              value={analysisFocus}
              onChange={(e) => setAnalysisFocus(e.target.value)}
              disabled={analysisLoading || rewriteLoading}
              placeholder="例如：钩子/伏笔回收、节奏、人物动机、逻辑矛盾…"
            />
          </label>

          <div className="flex flex-wrap items-center gap-2">
            <button className="btn btn-primary" disabled={analysisLoading || rewriteLoading} onClick={() => void analyzeChapter()} type="button">
              {analysisLoading ? "分析中..." : analysisResult ? "重新分析" : "开始分析"}
            </button>
            {analysisResult?.generation_run_id ? (
              <button
                className="btn btn-secondary"
                disabled={analysisLoading || rewriteLoading}
                onClick={() => void navigator.clipboard.writeText(analysisResult.generation_run_id)}
                type="button"
              >
                复制 run_id
              </button>
            ) : null}
          </div>

          {analysisResult ? (
            <div className="grid gap-4">
              {analysisResult.parse_error?.message ? (
                <div className="rounded-atelier border border-border bg-surface p-3 text-sm text-accent">
                  解析失败：{analysisResult.parse_error.message}
                  {analysisResult.parse_error.hint ? (
                    <div className="mt-1 text-xs text-subtext">hint: {analysisResult.parse_error.hint}</div>
                  ) : null}
                </div>
              ) : null}

              {analysisResult.warnings && analysisResult.warnings.length > 0 ? (
                <div className="rounded-atelier border border-border bg-surface p-3 text-xs text-subtext">
                  warnings: {analysisResult.warnings.join(", ")}
                </div>
              ) : null}

              <div className="grid gap-3 rounded-atelier border border-border bg-surface p-3">
                <div className="text-sm text-ink">本章摘要</div>
                <div className="text-sm text-ink">
                  {(analysisResult.analysis?.chapter_summary ?? "").trim() || "（空）"}
                </div>
              </div>

              <div className="grid gap-2 rounded-atelier border border-border bg-surface p-3">
                <div className="text-sm text-ink">Hooks / 钩子</div>
                {(analysisResult.analysis?.hooks ?? []).length === 0 ? (
                  <div className="text-sm text-subtext">（无）</div>
                ) : (
                  <div className="grid gap-2">
                    {(analysisResult.analysis?.hooks ?? []).map((it, idx) => (
                      <div key={idx} className="rounded-atelier border border-border bg-canvas p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-xs text-subtext">{(it.excerpt ?? "").trim() || "（无 excerpt）"}</div>
                          {it.excerpt ? (
                            <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => locateInEditor(it.excerpt ?? "")} type="button">
                              定位
                            </button>
                          ) : null}
                        </div>
                        {it.note ? <div className="mt-2 text-sm text-ink">{it.note}</div> : null}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="grid gap-2 rounded-atelier border border-border bg-surface p-3">
                <div className="text-sm text-ink">Foreshadows / 伏笔</div>
                {(analysisResult.analysis?.foreshadows ?? []).length === 0 ? (
                  <div className="text-sm text-subtext">（无）</div>
                ) : (
                  <div className="grid gap-2">
                    {(analysisResult.analysis?.foreshadows ?? []).map((it, idx) => (
                      <div key={idx} className="rounded-atelier border border-border bg-canvas p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-xs text-subtext">{(it.excerpt ?? "").trim() || "（无 excerpt）"}</div>
                          {it.excerpt ? (
                            <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => locateInEditor(it.excerpt ?? "")} type="button">
                              定位
                            </button>
                          ) : null}
                        </div>
                        {it.note ? <div className="mt-2 text-sm text-ink">{it.note}</div> : null}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="grid gap-2 rounded-atelier border border-border bg-surface p-3">
                <div className="text-sm text-ink">Plot Points / 情节点</div>
                {(analysisResult.analysis?.plot_points ?? []).length === 0 ? (
                  <div className="text-sm text-subtext">（无）</div>
                ) : (
                  <div className="grid gap-2">
                    {(analysisResult.analysis?.plot_points ?? []).map((it, idx) => (
                      <div key={idx} className="rounded-atelier border border-border bg-canvas p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-sm text-ink">{(it.beat ?? "").trim() || "（无 beat）"}</div>
                          {it.excerpt ? (
                            <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => locateInEditor(it.excerpt ?? "")} type="button">
                              定位
                            </button>
                          ) : null}
                        </div>
                        {it.excerpt ? <div className="mt-2 text-xs text-subtext">{it.excerpt}</div> : null}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="grid gap-2 rounded-atelier border border-border bg-surface p-3">
                <div className="text-sm text-ink">Suggestions / 修改建议</div>
                {(analysisResult.analysis?.suggestions ?? []).length === 0 ? (
                  <div className="text-sm text-subtext">（无）</div>
                ) : (
                  <div className="grid gap-2">
                    {(analysisResult.analysis?.suggestions ?? []).map((it, idx) => (
                      <div key={idx} className="rounded-atelier border border-border bg-canvas p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-sm text-ink">
                            {(it.title ?? "").trim() || "建议"}{" "}
                            {(it.priority ?? "").trim() ? <span className="text-xs text-subtext">({it.priority})</span> : null}
                          </div>
                          {it.excerpt ? (
                            <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => locateInEditor(it.excerpt ?? "")} type="button">
                              定位
                            </button>
                          ) : null}
                        </div>
                        {it.excerpt ? <div className="mt-2 text-xs text-subtext">{it.excerpt}</div> : null}
                        {it.issue ? <div className="mt-2 text-sm text-ink">问题：{it.issue}</div> : null}
                        {it.recommendation ? (
                          <div className="mt-2 text-sm text-ink">建议：{it.recommendation}</div>
                        ) : null}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {analysisResult.analysis?.overall_notes ? (
                <div className="grid gap-2 rounded-atelier border border-border bg-surface p-3">
                  <div className="text-sm text-ink">总体备注</div>
                  <div className="text-sm text-ink">{analysisResult.analysis.overall_notes}</div>
                </div>
              ) : null}

              <details>
                <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">raw_output</summary>
                <pre className="mt-2 max-h-56 overflow-auto rounded-atelier border border-border bg-canvas p-3 text-xs text-ink">
                  {analysisResult.raw_output ?? ""}
                </pre>
              </details>
            </div>
          ) : (
            <div className="text-sm text-subtext">暂无分析结果。</div>
          )}

          <div className="grid gap-3 rounded-atelier border border-border bg-surface p-3">
            <div className="text-sm text-ink">按建议重写（覆盖编辑器正文）</div>
            <label className="grid gap-1">
              <span className="text-xs text-subtext">重写指令（可选）</span>
              <input
                className="input"
                value={rewriteInstruction}
                onChange={(e) => setRewriteInstruction(e.target.value)}
                disabled={analysisLoading || rewriteLoading}
              />
            </label>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-xs text-subtext">重写结果不会自动保存，记得 Ctrl/Cmd+S 保存。</div>
              <button
                className="btn btn-primary"
                disabled={!analysisResult || analysisLoading || rewriteLoading}
                onClick={() => void rewriteFromAnalysis()}
                type="button"
              >
                {rewriteLoading ? "重写中..." : "按建议重写并应用"}
              </button>
            </div>
          </div>
        </div>
      </Modal>

      <Drawer
        open={chapterListOpen}
        onClose={() => setChapterListOpen(false)}
        side="left"
        overlayClassName="lg:hidden"
        ariaLabel="章节列表"
        panelClassName="h-full w-[280px] overflow-hidden border-r border-border bg-surface shadow-sm"
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="text-sm text-ink">章节列表</div>
          <button className="btn btn-secondary" onClick={() => setChapterListOpen(false)} type="button">
            关闭
          </button>
        </div>

        <div className="h-full overflow-auto p-2">
          {chapters.length === 0 ? (
            <div className="p-3 text-sm text-subtext">还没有章节，先新建一个吧。</div>
          ) : (
            <div className="flex flex-col gap-1">
              {chapters.map((c) => (
                <button
                  key={c.id}
                  className={
                    c.id === activeId
                      ? "ui-focus-ring ui-transition-fast rounded-atelier bg-canvas px-3 py-2 text-left text-sm text-ink"
                      : "ui-focus-ring ui-transition-fast rounded-atelier px-3 py-2 text-left text-sm text-subtext hover:bg-canvas hover:text-ink"
                  }
                  onClick={() => {
                    setChapterListOpen(false);
                    void requestSelectChapter(c.id);
                  }}
                  type="button"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0 truncate">
                      <span className="mr-2 text-xs text-subtext">#{c.number}</span>
                      <span className="truncate">{c.title ?? "未命名章节"}</span>
                    </div>
                    <span className="shrink-0 text-[11px] text-subtext">{c.status}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </Drawer>

      <AiGenerateDrawer
        open={aiOpen}
        generating={generating}
        preset={preset}
        activeChapter={Boolean(activeChapter)}
        dirty={dirty}
        saving={loadingChapter}
        genForm={genForm}
        setGenForm={setGenForm}
        characters={characters}
        streamProgress={genStreamProgress}
        onClose={() => setAiOpen(false)}
        onSave={() => void saveChapter()}
        onSaveAndGenerateNext={() => void saveAndGenerateNext()}
        onGenerateAppend={() => void generate("append")}
        onGenerateReplace={() => void generate("replace")}
        onCancelGenerate={() => genStreamClientRef.current?.abort()}
      />

      {generating && genForm.stream && !aiOpen ? (
        <div className="fixed inset-x-4 bottom-24 z-40 flex justify-center sm:inset-auto sm:bottom-8 sm:right-8 sm:justify-end">
          <div className="w-full max-w-sm rounded-atelier border border-border bg-surface/90 p-3 shadow-sm backdrop-blur">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-sm text-ink">AI 流式生成中</div>
                <div className="mt-1 truncate text-xs text-subtext">{genStreamProgress?.message ?? "处理中..."}</div>
                {genRequestId ? (
                  <div className="mt-1 truncate text-[11px] text-subtext">request_id: {genRequestId}</div>
                ) : null}
              </div>
              {genStreamProgress ? (
                <div className="shrink-0 text-xs text-subtext">
                  {Math.max(0, Math.min(100, genStreamProgress.progress))}%
                </div>
              ) : null}
            </div>
            <div className="mt-2 h-2 w-full rounded bg-border">
              <div
                className="h-2 rounded bg-accent motion-safe:transition-[width] motion-safe:duration-atelier motion-safe:ease-atelier"
                style={{ width: `${Math.max(0, Math.min(100, genStreamProgress?.progress ?? 0))}%` }}
              />
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <button className="btn btn-secondary" onClick={() => setAiOpen(true)} type="button">
                展开
              </button>
              <button className="btn btn-secondary" onClick={() => genStreamClientRef.current?.abort()} type="button">
                取消
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <GenerationHistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        loading={runsLoading}
        runs={runs}
        selectedRun={selectedRun}
        onSelectRun={(run) => void selectRun(run)}
      />

      <WizardNextBar
        projectId={projectId}
        currentStep="writing"
        progress={wizard.progress}
        loading={wizard.loading}
        dirty={dirty}
        saving={loadingChapter || generating}
        onSave={saveChapter}
      />
    </div>
  );
}
