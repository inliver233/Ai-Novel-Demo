import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { GhostwriterIndicator } from "../components/atelier/GhostwriterIndicator";
import { MarkdownEditor } from "../components/atelier/MarkdownEditor";
import { WizardNextBar } from "../components/atelier/WizardNextBar";
import { Drawer } from "../components/ui/Drawer";
import { AiGenerateDrawer } from "../components/writing/AiGenerateDrawer";
import { BatchGenerationModal } from "../components/writing/BatchGenerationModal";
import { ChapterListPanel } from "../components/writing/ChapterListPanel";
import { CreateChapterDialog } from "../components/writing/CreateChapterDialog";
import { ChapterAnalysisModal } from "../components/writing/ChapterAnalysisModal";
import { GenerationHistoryDrawer } from "../components/writing/GenerationHistoryDrawer";
import { WritingToolbar } from "../components/writing/WritingToolbar";
import { useConfirm } from "../components/ui/confirm";
import { useToast } from "../components/ui/toast";
import { useProjectData } from "../hooks/useProjectData";
import { useWizardProgress } from "../hooks/useWizardProgress";
import { apiJson } from "../services/apiClient";
import { useApplyGenerationRun } from "./writing/useApplyGenerationRun";
import { useBatchGeneration } from "./writing/useBatchGeneration";
import { useChapterAnalysis } from "./writing/useChapterAnalysis";
import { useChapterCrud } from "./writing/useChapterCrud";
import { useChapterEditor } from "./writing/useChapterEditor";
import { useChapterGeneration } from "./writing/useChapterGeneration";
import { useGenerationHistory } from "./writing/useGenerationHistory";
import { useOutlineSwitcher } from "./writing/useOutlineSwitcher";
import type { ChapterStatus, Character, LLMPreset, Outline, OutlineListItem } from "../types";

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
    setChapters,
    refreshChapters,
    activeId,
    setActiveId,
    activeChapter,
    form,
    setForm,
    dirty,
    saveChapter,
    requestSelectChapter: requestSelectChapterBase,
    loadingChapter,
  } = chapterEditor;
  const contentTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [contentEditorTab, setContentEditorTab] = useState<"edit" | "preview">("edit");

  const [aiOpen, setAiOpen] = useState(false);
  const autoGenerateNextRef = useRef<{ chapterId: string; mode: "replace" | "append" } | null>(null);

  useEffect(() => {
    if (!activeChapter) autoGenerateNextRef.current = null;
  }, [activeChapter]);

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
    async (id: string) => {
      autoGenerateNextRef.current = null;
      await requestSelectChapterBase(id);
    },
    [requestSelectChapterBase],
  );

  const chapterCrud = useChapterCrud({
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
  });

  const generation = useChapterGeneration({
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
  const { generating, genRequestId, genStreamProgress, genForm, setGenForm, generate, abortGenerate } = generation;

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

  const analysis = useChapterAnalysis({ activeChapter, preset, genForm, form, setForm, toast });
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
  }, [activeChapter, chapters, confirm, saveChapter, setActiveId, setAiOpen, toast]);

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
      <WritingToolbar
        outlines={outlines}
        activeOutlineId={activeOutlineId}
        chaptersCount={chapters.length}
        batchProgressText={
          batch.batchTask && (batch.batchTask.status === "queued" || batch.batchTask.status === "running")
            ? `（${batch.batchTask.completed_count}/${batch.batchTask.total_count}）`
            : ""
        }
        onSwitchOutline={(outlineId) => void switchOutline(outlineId)}
        onOpenChapterList={() => setChapterListOpen(true)}
        onOpenBatch={batch.openModal}
        onOpenHistory={history.openDrawer}
        onCreateChapter={chapterCrud.openCreate}
      />

      <div className="flex gap-4">
        <aside className="hidden w-[240px] shrink-0 lg:block">
          <ChapterListPanel
            chapters={chapters}
            activeId={activeId}
            onSelectChapter={(chapterId) => void requestSelectChapter(chapterId)}
          />
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
                    onClick={analysis.openModal}
                    type="button"
                  >
                    分析
                  </button>
                  <button
                    className="btn btn-ghost text-accent hover:bg-accent/10"
                    disabled={loadingChapter || generating}
                    onClick={() => void chapterCrud.deleteChapter()}
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
        open={chapterCrud.createOpen}
        saving={chapterCrud.createSaving}
        form={chapterCrud.createForm}
        setForm={chapterCrud.setCreateForm}
        onClose={() => chapterCrud.setCreateOpen(false)}
        onSubmit={() => void chapterCrud.createChapter()}
      />

      <BatchGenerationModal
        open={batch.open}
        batchLoading={batch.batchLoading}
        activeChapterNumber={activeChapter?.number ?? null}
        batchCount={batch.batchCount}
        setBatchCount={batch.setBatchCount}
        batchIncludeExisting={batch.batchIncludeExisting}
        setBatchIncludeExisting={batch.setBatchIncludeExisting}
        batchTask={batch.batchTask}
        batchItems={batch.batchItems}
        onClose={batch.closeModal}
        onCancelTask={() => void batch.cancelBatchGeneration()}
        onStartTask={() => void batch.startBatchGeneration()}
        onApplyItemToEditor={(it) => void batch.applyBatchItemToEditor(it)}
      />

      <ChapterAnalysisModal
        open={analysis.open}
        analysisLoading={analysis.analysisLoading}
        rewriteLoading={analysis.rewriteLoading}
        analysisFocus={analysis.analysisFocus}
        setAnalysisFocus={analysis.setAnalysisFocus}
        analysisResult={analysis.analysisResult}
        rewriteInstruction={analysis.rewriteInstruction}
        setRewriteInstruction={analysis.setRewriteInstruction}
        onClose={analysis.closeModal}
        onAnalyze={() => void analysis.analyzeChapter()}
        onLocateInEditor={locateInEditor}
        onRewriteFromAnalysis={() => void analysis.rewriteFromAnalysis()}
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
          <ChapterListPanel
            chapters={chapters}
            activeId={activeId}
            containerClassName=""
            onSelectChapter={(chapterId) => {
              setChapterListOpen(false);
              void requestSelectChapter(chapterId);
            }}
          />
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
        onCancelGenerate={abortGenerate}
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
              <button className="btn btn-secondary" onClick={abortGenerate} type="button">
                取消
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <GenerationHistoryDrawer
        open={history.open}
        onClose={history.closeDrawer}
        loading={history.runsLoading}
        runs={history.runs}
        selectedRun={history.selectedRun}
        onSelectRun={(run) => void history.selectRun(run)}
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
