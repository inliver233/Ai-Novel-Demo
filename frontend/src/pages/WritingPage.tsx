import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { List } from "lucide-react";
import { useParams, useSearchParams } from "react-router-dom";

import { GhostwriterIndicator } from "../components/atelier/GhostwriterIndicator";
import { MarkdownEditor } from "../components/atelier/MarkdownEditor";
import { WizardNextBar } from "../components/atelier/WizardNextBar";
import { Drawer } from "../components/ui/Drawer";
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
import { SSEError, SSEPostClient } from "../services/sseClient";
import { markWizardProjectChanged } from "../services/wizard";
import type { CreateChapterForm, GenerateForm, GenerationRun } from "../components/writing/types";
import type { Chapter, ChapterStatus, Character, LLMPreset, Outline, OutlineListItem, Project } from "../types";

type ChapterForm = {
  title: string;
  plan: string;
  content_md: string;
  summary: string;
  status: ChapterStatus;
};

function normalizeText(v: string | null | undefined): string {
  return v ?? "";
}

function appendMarkdown(base: string, fragment: string): string {
  const a = (base ?? "").trimEnd();
  const b = (fragment ?? "").trimStart();
  if (!a) return b;
  if (!b) return a;
  return `${a}\n\n${b}`;
}

function nextChapterNumber(chapters: Chapter[]): number {
  const max = chapters.reduce((acc, c) => Math.max(acc, c.number ?? 0), 0);
  return max + 1;
}

function chapterToForm(chapter: Chapter): ChapterForm {
  return {
    title: normalizeText(chapter.title),
    plan: normalizeText(chapter.plan),
    content_md: normalizeText(chapter.content_md),
    summary: normalizeText(chapter.summary),
    status: chapter.status,
  };
}

type WritingLoaded = { outlines: OutlineListItem[]; outline: Outline; preset: LLMPreset; characters: Character[] };

export function WritingPage() {
  const { projectId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedChapterId = searchParams.get("chapterId");
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
    context: {
      include_world_setting: true,
      include_style_guide: true,
      include_constraints: true,
      include_outline: true,
      character_ids: [],
      previous_chapter: "summary",
    },
  });

  const [historyOpen, setHistoryOpen] = useState(false);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runs, setRuns] = useState<GenerationRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<GenerationRun | null>(null);

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
        const payload = {
          mode,
          instruction: genForm.instruction,
          target_word_count: genForm.target_word_count > 0 ? genForm.target_word_count : null,
          context: {
            include_world_setting: genForm.context.include_world_setting,
            include_style_guide: genForm.context.include_style_guide,
            include_constraints: genForm.context.include_constraints,
            include_outline: genForm.context.include_outline,
            character_ids: genForm.context.character_ids,
            previous_chapter: genForm.context.previous_chapter === "none" ? null : genForm.context.previous_chapter,
          },
        };

        const baseContent = form.content_md;
        const baseSummary = form.summary;

        if (genForm.stream) {
          const markerContent = "<<<CONTENT>>>";
          const markerSummary = "<<<SUMMARY>>>";

          let phase: "before" | "content" | "summary" | "raw" = "before";
          let pending = "";
          let parsedContent = "";
          let parsedSummary = "";
          let sawContentMarker = false;
          let rawSeen = 0;
          let requestId: string | undefined;

          const closeTo = (s: string, keep: number) => (s.length > keep ? s.slice(s.length - keep) : s);
          const dropLeadingSpace = (s: string) => s.replace(/^[\s\r\n]+/, "");

          const processChunk = (chunk: string) => {
            rawSeen += chunk.length;
            pending += chunk;

            if (!sawContentMarker && rawSeen > 800) {
              phase = "raw";
            }

            while (pending) {
              if (phase === "before") {
                const idx = pending.indexOf(markerContent);
                if (idx === -1) {
                  pending = closeTo(pending, markerContent.length - 1);
                  return;
                }
                sawContentMarker = true;
                pending = dropLeadingSpace(pending.slice(idx + markerContent.length));
                phase = "content";
                continue;
              }

              if (phase === "content") {
                const idx = pending.indexOf(markerSummary);
                if (idx === -1) {
                  const keep = markerSummary.length - 1;
                  if (pending.length > keep) {
                    parsedContent += pending.slice(0, pending.length - keep);
                    pending = pending.slice(pending.length - keep);
                  }
                  return;
                }
                parsedContent += pending.slice(0, idx);
                pending = dropLeadingSpace(pending.slice(idx + markerSummary.length));
                phase = "summary";
                continue;
              }

              if (phase === "summary") {
                parsedSummary += pending;
                pending = "";
                return;
              }

              if (phase === "raw") {
                parsedContent += pending;
                pending = "";
                return;
              }
            }
          };

          const client = new SSEPostClient(`/api/chapters/${activeChapter.id}/generate-stream`, payload, {
            headers,
            onOpen: ({ requestId: rid }) => {
              requestId = rid;
              setGenRequestId(rid ?? null);
            },
            onProgress: ({ message, progress, status, wordCount }) => {
              setGenStreamProgress({ message, progress, status, wordCount });
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
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setGenerating(false);
      }
    },
    [activeChapter, confirm, dirty, form, genForm, preset, saveChapter, toast],
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
