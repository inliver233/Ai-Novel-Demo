import { useCallback, useEffect, useState } from "react";

import type { ChapterAnalyzeResult, ChapterRewriteResult, GenerateForm } from "../../components/writing/types";
import { ApiError, apiJson } from "../../services/apiClient";
import type { Chapter, LLMPreset } from "../../types";
import type { ChapterForm } from "./writingUtils";

export function useChapterAnalysis(args: {
  activeChapter: Chapter | null;
  preset: LLMPreset | null;
  genForm: GenerateForm;
  form: ChapterForm | null;
  setForm: React.Dispatch<React.SetStateAction<ChapterForm | null>>;
  toast: { toastError: (message: string, requestId?: string) => void; toastSuccess: (message: string, requestId?: string) => void };
}) {
  const { activeChapter, preset, genForm, form, setForm, toast } = args;

  const [open, setOpen] = useState(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<ChapterAnalyzeResult | null>(null);
  const [analysisFocus, setAnalysisFocus] = useState("");
  const [rewriteInstruction, setRewriteInstruction] = useState("按分析建议重写，减少重复，保持叙事连续。");
  const [rewriteLoading, setRewriteLoading] = useState(false);

  useEffect(() => {
    setOpen(false);
    setAnalysisResult(null);
    setAnalysisLoading(false);
    setRewriteLoading(false);
  }, [activeChapter?.id]);

  const openModal = useCallback(() => setOpen(true), []);
  const closeModal = useCallback(() => setOpen(false), []);

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
  }, [activeChapter, analysisResult?.analysis, form, genForm, preset, rewriteInstruction, setForm, toast]);

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
  };
}

