import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { MarkdownEditor } from "../components/atelier/MarkdownEditor";
import { WizardNextBar } from "../components/atelier/WizardNextBar";
import { useConfirm } from "../components/ui/confirm";
import { useToast } from "../components/ui/toast";
import { useProjectData } from "../hooks/useProjectData";
import { useSaveHotkey } from "../hooks/useSaveHotkey";
import { useUnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";
import { useWizardProgress } from "../hooks/useWizardProgress";
import { ApiError, apiJson } from "../services/apiClient";
import { getLlmApiKey } from "../services/llmKeyStore";
import type { Chapter, LLMPreset, Outline } from "../types";

type OutlineGenChapter = { number: number; title: string; beats: string[] };
type OutlineGenResult = {
  outline_md: string;
  chapters: OutlineGenChapter[];
  raw_output: string;
  parse_error?: { code: string; message: string };
};

type OutlineGenForm = {
  chapter_count: number;
  tone: string;
  pacing: string;
  include_world_setting: boolean;
  include_characters: boolean;
};

type OutlineLoaded = { outline: Outline; preset: LLMPreset };

export function OutlinePage() {
  const { projectId } = useParams();
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const wizard = useWizardProgress(projectId);
  const refreshWizard = wizard.refresh;

  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);

  const [preset, setPreset] = useState<LLMPreset | null>(null);
  const [baseline, setBaseline] = useState<string>("");
  const [content, setContent] = useState<string>("");

  const [genModalOpen, setGenModalOpen] = useState(false);
  const [genPreview, setGenPreview] = useState<OutlineGenResult | null>(null);
  const [genForm, setGenForm] = useState<OutlineGenForm>({
    chapter_count: 12,
    tone: "偏现实，克制但有爆点",
    pacing: "前3章强钩子，中段升级，结尾反转",
    include_world_setting: true,
    include_characters: true,
  });

  const outlineQuery = useProjectData<OutlineLoaded>(projectId, async (id) => {
    const [oRes, presetRes] = await Promise.all([
      apiJson<{ outline: Outline }>(`/api/projects/${id}/outline`),
      apiJson<{ llm_preset: LLMPreset }>(`/api/projects/${id}/llm_preset`),
    ]);
    return { outline: oRes.data.outline, preset: presetRes.data.llm_preset };
  });
  const loading = outlineQuery.loading;

  useEffect(() => {
    if (!outlineQuery.data) return;
    setPreset(outlineQuery.data.preset);
    const next = outlineQuery.data.outline.content_md ?? "";
    setBaseline(next);
    setContent(next);
  }, [outlineQuery.data]);

  const dirty = content !== baseline;
  useUnsavedChangesGuard(dirty);

  const save = useCallback(
    async (nextContent?: string): Promise<boolean> => {
      if (!projectId) return false;
      const toSave = nextContent ?? content;
      if (nextContent === undefined && toSave === baseline) return true;
      setSaving(true);
      try {
        const res = await apiJson<{ outline: Outline }>(`/api/projects/${projectId}/outline`, {
          method: "PUT",
          body: JSON.stringify({ content_md: toSave }),
        });
        setBaseline(res.data.outline.content_md ?? "");
        setContent(res.data.outline.content_md ?? "");
        await refreshWizard();
        toast.toastSuccess("已保存");
        return true;
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
        return false;
      } finally {
        setSaving(false);
      }
    },
    [baseline, content, projectId, refreshWizard, toast],
  );

  useSaveHotkey(() => void save(), dirty);

  const canCreateChapters = (genPreview?.chapters?.length ?? 0) > 0;

  const createChaptersFromOutline = useCallback(async () => {
    if (!projectId) return;
    if (!genPreview || genPreview.chapters.length === 0) return;

    const ok = await confirm.confirm({
      title: "从大纲创建章节骨架？",
      description: `将根据大纲创建 ${genPreview.chapters.length} 个章节。`,
      confirmText: "创建",
    });
    if (!ok) return;

    const payload = {
      chapters: genPreview.chapters.map((c) => ({
        number: c.number,
        title: c.title,
        plan: (c.beats ?? []).join("；"),
      })),
    };

    try {
      await apiJson<{ chapters: Chapter[] }>(`/api/projects/${projectId}/chapters/bulk_create`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      toast.toastSuccess(`已创建 ${genPreview.chapters.length} 个章节`);
      navigate(`/projects/${projectId}/writing`);
    } catch (e) {
      const err = e as ApiError;
      if (err.code === "CONFLICT" && err.status === 409) {
        const replaceOk = await confirm.confirm({
          title: "检测到已有章节，是否覆盖？",
          description: "覆盖创建将删除该项目所有章节（含正文/摘要），不可恢复。",
          confirmText: "覆盖创建",
          danger: true,
        });
        if (!replaceOk) return;
        try {
          await apiJson<{ chapters: Chapter[] }>(`/api/projects/${projectId}/chapters/bulk_create?replace=true`, {
            method: "POST",
            body: JSON.stringify(payload),
          });
          toast.toastSuccess(`已覆盖创建 ${genPreview.chapters.length} 个章节`);
          navigate(`/projects/${projectId}/writing`);
        } catch (e2) {
          const err2 = e2 as ApiError;
          toast.toastError(`${err2.message} (${err2.code})`, err2.requestId);
        }
        return;
      }
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    }
  }, [confirm, genPreview, navigate, projectId, toast]);

  if (loading) return <div className="text-subtext">加载中...</div>;

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            className="rounded-atelier bg-accent px-3 py-2 text-sm text-white hover:opacity-90 disabled:opacity-60"
            disabled={!canCreateChapters}
            onClick={() => void createChaptersFromOutline()}
            title={canCreateChapters ? undefined : "请先生成包含章节结构的大纲"}
            type="button"
          >
            从大纲创建章节骨架
          </button>
          <button
            className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink hover:bg-canvas"
            onClick={() => setGenModalOpen(true)}
            type="button"
          >
            AI 生成大纲
          </button>
        </div>
        <button
          className="rounded-atelier bg-accent px-3 py-2 text-sm text-white hover:opacity-90 disabled:opacity-60"
          disabled={!dirty || saving}
          onClick={() => void save()}
          type="button"
        >
          保存大纲
        </button>
      </div>

      <MarkdownEditor value={content} onChange={setContent} placeholder="在这里编写大纲（Markdown）..." minRows={16} />

      <div className="text-xs text-subtext">快捷键：Ctrl/Cmd + S 保存</div>

      {genModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-2xl rounded-atelier border border-border bg-canvas p-6 shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="font-content text-2xl">AI 生成大纲</div>
                <div className="mt-1 text-xs text-subtext">生成结果会先预览，需手动应用。</div>
              </div>
              <button
                className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink hover:bg-canvas"
                onClick={() => setGenModalOpen(false)}
                type="button"
              >
                关闭
              </button>
            </div>

            <div className="mt-4 grid gap-4 sm:grid-cols-3">
              <label className="grid gap-1">
                <span className="text-xs text-subtext">章节数</span>
                <input
                  className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink outline-none"
                  type="number"
                  min={1}
                  value={genForm.chapter_count}
                  onChange={(e) => setGenForm((v) => ({ ...v, chapter_count: Number(e.target.value) }))}
                />
              </label>
              <label className="grid gap-1 sm:col-span-2">
                <span className="text-xs text-subtext">基调</span>
                <input
                  className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink outline-none"
                  value={genForm.tone}
                  onChange={(e) => setGenForm((v) => ({ ...v, tone: e.target.value }))}
                />
              </label>
              <label className="grid gap-1 sm:col-span-3">
                <span className="text-xs text-subtext">节奏</span>
                <input
                  className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink outline-none"
                  value={genForm.pacing}
                  onChange={(e) => setGenForm((v) => ({ ...v, pacing: e.target.value }))}
                />
              </label>
              <label className="flex items-center gap-2 text-sm text-ink">
                <input
                  checked={genForm.include_world_setting}
                  onChange={(e) => setGenForm((v) => ({ ...v, include_world_setting: e.target.checked }))}
                  type="checkbox"
                />
                注入世界观
              </label>
              <label className="flex items-center gap-2 text-sm text-ink">
                <input
                  checked={genForm.include_characters}
                  onChange={(e) => setGenForm((v) => ({ ...v, include_characters: e.target.checked }))}
                  type="checkbox"
                />
                注入角色卡
              </label>
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <button
                className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink hover:bg-canvas"
                onClick={() => setGenModalOpen(false)}
                type="button"
              >
                取消
              </button>
              <button
                className="rounded-atelier bg-accent px-3 py-2 text-sm text-white hover:opacity-90 disabled:opacity-60"
                disabled={generating}
                onClick={async () => {
                  if (!projectId || !preset) return;
                  const apiKey = getLlmApiKey(preset.provider);
                  if (!apiKey) {
                    toast.toastError("请先在 Prompts 页填写 API Key");
                    return;
                  }
                  setGenerating(true);
                  try {
                    const res = await apiJson<OutlineGenResult>(`/api/projects/${projectId}/outline/generate`, {
                      method: "POST",
                      headers: {
                        "X-LLM-Provider": preset.provider,
                        "X-LLM-API-Key": apiKey,
                      },
                      body: JSON.stringify({
                        requirements: {
                          chapter_count: genForm.chapter_count,
                          tone: genForm.tone,
                          pacing: genForm.pacing,
                        },
                        context: {
                          include_world_setting: genForm.include_world_setting,
                          include_characters: genForm.include_characters,
                        },
                      }),
                    });
                    setGenPreview(res.data);
                    toast.toastSuccess("生成完成");
                  } catch (e) {
                    const err = e as ApiError;
                    toast.toastError(`${err.message} (${err.code})`, err.requestId);
                  } finally {
                    setGenerating(false);
                  }
                }}
                type="button"
              >
                {generating ? "生成中..." : "生成"}
              </button>
            </div>

            {genPreview ? (
              <div className="mt-6 rounded-atelier border border-border bg-surface p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm text-ink">生成结果预览</div>
                    <div className="mt-1 text-xs text-subtext">
                      解析章节：{genPreview.chapters.length} {genPreview.parse_error ? `（${genPreview.parse_error.message}）` : ""}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink hover:bg-surface"
                      onClick={() => setGenPreview(null)}
                      type="button"
                    >
                      取消
                    </button>
                    <button
                      className="rounded-atelier bg-accent px-3 py-2 text-sm text-white hover:opacity-90"
                      onClick={async () => {
                        const ok = !dirty
                          ? true
                          : await confirm.confirm({
                              title: "覆盖当前未保存的大纲？",
                              description: "应用后将以生成结果替换编辑器内容，并立即保存。",
                              confirmText: "应用并保存",
                              danger: true,
                            });
                         if (!ok) return;
                         setGenModalOpen(false);
                         await save(genPreview.outline_md);
                       }}
                       type="button"
                     >
                       应用并下一步
                    </button>
                  </div>
                </div>
                <div className="mt-3">
                  <MarkdownEditor value={genPreview.outline_md} onChange={() => {}} minRows={10} />
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      <WizardNextBar
        projectId={projectId}
        currentStep="outline"
        progress={wizard.progress}
        loading={wizard.loading}
        dirty={dirty}
        saving={saving || generating}
        onSave={() => save()}
        primaryAction={
          wizard.progress.nextStep?.key === "chapters"
            ? canCreateChapters
              ? { label: "下一步：创建章节骨架", disabled: generating || saving, onClick: createChaptersFromOutline }
              : { label: "下一步：先 AI 生成大纲", disabled: generating || saving, onClick: () => setGenModalOpen(true) }
            : undefined
        }
      />
    </div>
  );
}
