import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { ChapterAnalyzeResult, ChapterRewriteResult, GenerateForm } from "../../components/writing/types";
import type { ToastApi } from "../../components/ui/toast";
import { UI_COPY } from "../../lib/uiCopy";
import { createRequestSeqGuard } from "../../lib/requestSeqGuard";
import { ApiError, apiJson } from "../../services/apiClient";
import type { Chapter, LLMPreset } from "../../types";
import { getWritingApplyMemorySuccess, WRITING_PAGE_COPY } from "./writingPageCopy";
import type { ChapterForm } from "./writingUtils";

export function useChapterAnalysis(args: {
  activeChapter: Chapter | null;
  preset: LLMPreset | null;
  genForm: GenerateForm;
  form: ChapterForm | null;
  setForm: React.Dispatch<React.SetStateAction<ChapterForm | null>>;
  dirty?: boolean;
  saveChapter?: (opts?: { silent?: boolean }) => Promise<boolean>;
  toast: ToastApi;
}) {
  const { activeChapter, preset, genForm, form, setForm, dirty = false, saveChapter, toast } = args;

  const [open, setOpen] = useState(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<ChapterAnalyzeResult | null>(null);
  const [analysisFocus, setAnalysisFocus] = useState("");
  const [rewriteInstruction, setRewriteInstruction] = useState<string>(WRITING_PAGE_COPY.analyzeInstructionDefault);
  const [rewriteLoading, setRewriteLoading] = useState(false);
  const [applyLoading, setApplyLoading] = useState(false);
  const analyzeGuardRef = useRef(createRequestSeqGuard());
  const rewriteGuardRef = useRef(createRequestSeqGuard());
  const applyGuardRef = useRef(createRequestSeqGuard());
  const dirtyRef = useRef(dirty);
  const navigate = useNavigate();

  useEffect(() => {
    dirtyRef.current = dirty;
  }, [dirty]);

  useEffect(() => {
    const analyzeGuard = analyzeGuardRef.current;
    const rewriteGuard = rewriteGuardRef.current;
    const applyGuard = applyGuardRef.current;
    return () => {
      analyzeGuard.invalidate();
      rewriteGuard.invalidate();
      applyGuard.invalidate();
    };
  }, []);

  useEffect(() => {
    analyzeGuardRef.current.invalidate();
    rewriteGuardRef.current.invalidate();
    applyGuardRef.current.invalidate();
    setOpen(false);
    setAnalysisResult(null);
    setAnalysisLoading(false);
    setRewriteLoading(false);
    setApplyLoading(false);
  }, [activeChapter?.id]);

  const openModal = useCallback(() => setOpen(true), []);
  const closeModal = useCallback(() => setOpen(false), []);

  const analyzeChapter = useCallback(async () => {
    if (!activeChapter || !form) return;
    if (!preset) {
      toast.toastError(WRITING_PAGE_COPY.promptPresetRequired);
      return;
    }
    if (!(form.content_md ?? "").trim()) {
      toast.toastError(WRITING_PAGE_COPY.analyzeEmptyContent);
      return;
    }

    const headers: Record<string, string> = { "X-LLM-Provider": preset.provider };
    const seq = analyzeGuardRef.current.next();
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
      if (!analyzeGuardRef.current.isLatest(seq)) return;
      setAnalysisResult(res.data);
      if (res.data.parse_error?.message) {
        toast.toastError(
          `${WRITING_PAGE_COPY.analyzeParseFailedPrefix}${res.data.parse_error.message}`,
          res.request_id,
        );
      } else {
        toast.toastSuccess(WRITING_PAGE_COPY.analyzeDone, res.request_id);
      }
      const droppedParams = res.data.dropped_params ?? [];
      if (droppedParams.length > 0) {
        toast.toastSuccess(`${UI_COPY.common.droppedParamsPrefix}${droppedParams.join("、")}`, res.request_id);
      }
    } catch (e) {
      if (!analyzeGuardRef.current.isLatest(seq)) return;
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      if (analyzeGuardRef.current.isLatest(seq)) {
        setAnalysisLoading(false);
      }
    }
  }, [activeChapter, analysisFocus, form, genForm, preset, toast]);

  const rewriteFromAnalysis = useCallback(async () => {
    if (!activeChapter || !form) return;
    if (!preset) {
      toast.toastError(WRITING_PAGE_COPY.promptPresetRequired);
      return;
    }
    if (!analysisResult?.analysis) {
      toast.toastError(WRITING_PAGE_COPY.rewriteNeedsAnalysis);
      return;
    }
    if (!(form.content_md ?? "").trim()) {
      toast.toastError(WRITING_PAGE_COPY.rewriteEmptyContent);
      return;
    }

    const headers: Record<string, string> = { "X-LLM-Provider": preset.provider };
    const seq = rewriteGuardRef.current.next();
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
      if (!rewriteGuardRef.current.isLatest(seq)) return;

      const nextContent = (res.data.content_md ?? "").trim();
      if (!nextContent) {
        const msg = res.data.parse_error?.message ?? WRITING_PAGE_COPY.rewriteParseFailed;
        toast.toastError(msg, res.request_id);
        return;
      }

      setForm((prev) => (prev ? { ...prev, content_md: nextContent, status: "drafting" } : prev));
      toast.toastSuccess(WRITING_PAGE_COPY.rewriteAppliedUnsaved, res.request_id);
      const droppedParams = res.data.dropped_params ?? [];
      if (droppedParams.length > 0) {
        toast.toastSuccess(`${UI_COPY.common.droppedParamsPrefix}${droppedParams.join("、")}`, res.request_id);
      }
    } catch (e) {
      if (!rewriteGuardRef.current.isLatest(seq)) return;
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      if (rewriteGuardRef.current.isLatest(seq)) {
        setRewriteLoading(false);
      }
    }
  }, [activeChapter, analysisResult?.analysis, form, genForm, preset, rewriteInstruction, setForm, toast]);

  const applyAnalysisToMemory = useCallback(async () => {
    if (!activeChapter || !form) return;
    if (!analysisResult?.analysis) {
      toast.toastError(WRITING_PAGE_COPY.rewriteNeedsAnalysis);
      return;
    }

    const seq = applyGuardRef.current.next();
    setApplyLoading(true);
    try {
      const res = await apiJson<{
        idempotent: boolean;
        analysis_hash: string;
        plot_analysis_id: string;
        memories: unknown[];
      }>(`/api/chapters/${activeChapter.id}/analysis/apply`, {
        method: "POST",
        body: JSON.stringify({
          analysis: analysisResult.analysis,
          draft_content_md: form.content_md,
        }),
      });
      if (!applyGuardRef.current.isLatest(seq)) return;

      const count = (res.data.memories ?? []).length;
      toast.toastSuccess(getWritingApplyMemorySuccess(count), res.request_id, {
        label: WRITING_PAGE_COPY.openChapterAnalysis,
        onClick: () => {
          void (async () => {
            if (dirtyRef.current && saveChapter) {
              void saveChapter({ silent: true });
              const startedAt = window.performance.now();
              while (dirtyRef.current && window.performance.now() - startedAt < 10_000) {
                await new Promise((resolve) => window.setTimeout(resolve, 100));
              }
            }
            window.requestAnimationFrame(() => {
              navigate(`/projects/${activeChapter.project_id}/chapter-analysis?chapterId=${activeChapter.id}`);
            });
          })();
        },
      });
    } catch (e) {
      if (!applyGuardRef.current.isLatest(seq)) return;
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      if (applyGuardRef.current.isLatest(seq)) {
        setApplyLoading(false);
      }
    }
  }, [activeChapter, analysisResult?.analysis, form, navigate, saveChapter, toast]);

  return {
    open,
    openModal,
    closeModal,
    analysisLoading,
    analysisResult,
    analysisFocus,
    setAnalysisFocus,
    analyzeChapter,
    rewriteInstruction,
    setRewriteInstruction,
    rewriteLoading,
    rewriteFromAnalysis,
    applyLoading,
    applyAnalysisToMemory,
  };
}
