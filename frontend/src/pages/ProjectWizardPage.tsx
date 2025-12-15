import clsx from "clsx";
import { CheckCircle2, Circle, CircleSlash2, Wand2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { GhostwriterIndicator } from "../components/atelier/GhostwriterIndicator";
import { useConfirm } from "../components/ui/confirm";
import { useToast } from "../components/ui/toast";
import { useProjects } from "../contexts/projects";
import { useProjectData } from "../hooks/useProjectData";
import { ApiError, apiJson } from "../services/apiClient";
import { getLlmApiKey } from "../services/llmKeyStore";
import { computeWizardProgress, setWizardStepSkipped, type WizardStep, type WizardStepKey } from "../services/wizard";
import type { Chapter, Character, LLMPreset, Outline, ProjectSettings } from "../types";

type OutlineGenChapter = { number: number; title: string; beats: string[] };
type OutlineGenResult = {
  outline_md: string;
  chapters: OutlineGenChapter[];
  raw_output: string;
  parse_error?: { code: string; message: string };
};

type WizardLoaded = {
  settings: ProjectSettings;
  characters: Character[];
  outline: Outline;
  chapters: Chapter[];
  llmPreset: LLMPreset;
};

const EMPTY_CHARACTERS: Character[] = [];
const EMPTY_CHAPTERS: Chapter[] = [];

export function ProjectWizardPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const { projects } = useProjects();

  const project = useMemo(() => projects.find((p) => p.id === projectId) ?? null, [projectId, projects]);

  const [version, setVersion] = useState(0);
  const [autoRunning, setAutoRunning] = useState(false);

  const wizardQuery = useProjectData<WizardLoaded>(projectId, async (id) => {
    const [settingsRes, charsRes, outlineRes, chaptersRes, presetRes] = await Promise.all([
      apiJson<{ settings: ProjectSettings }>(`/api/projects/${id}/settings`),
      apiJson<{ characters: Character[] }>(`/api/projects/${id}/characters`),
      apiJson<{ outline: Outline }>(`/api/projects/${id}/outline`),
      apiJson<{ chapters: Chapter[] }>(`/api/projects/${id}/chapters`),
      apiJson<{ llm_preset: LLMPreset }>(`/api/projects/${id}/llm_preset`),
    ]);
    return {
      settings: settingsRes.data.settings,
      characters: charsRes.data.characters,
      outline: outlineRes.data.outline,
      chapters: chaptersRes.data.chapters,
      llmPreset: presetRes.data.llm_preset,
    };
  });

  const reload = wizardQuery.refresh;
  const settings = wizardQuery.data?.settings ?? null;
  const characters = wizardQuery.data?.characters ?? EMPTY_CHARACTERS;
  const outline = wizardQuery.data?.outline ?? null;
  const chapters = wizardQuery.data?.chapters ?? EMPTY_CHAPTERS;
  const llmPreset = wizardQuery.data?.llmPreset ?? null;

  const progress = useMemo(() => {
    void version;
    return computeWizardProgress({
      project,
      settings,
      characters,
      outline,
      chapters,
      llmPreset,
    });
  }, [project, settings, characters, outline, chapters, llmPreset, version]);

  const goStep = useCallback(
    (step: WizardStep) => {
      if (!step.href) return;
      navigate(step.href);
    },
    [navigate],
  );

  const setSkipped = useCallback(
    (step: WizardStepKey, skipped: boolean) => {
      if (!projectId) return;
      setWizardStepSkipped(projectId, step, skipped);
      setVersion((v) => v + 1);
    },
    [projectId],
  );

  const autoOutlineAndChapters = useCallback(async () => {
    if (!projectId) return;
    if (!llmPreset) {
      toast.toastError("未加载到模型配置，请先在 Prompts 页保存模型预设");
      navigate(`/projects/${projectId}/prompts`);
      return;
    }
    const apiKey = getLlmApiKey(llmPreset.provider).trim();
    if (!apiKey) {
      toast.toastError("请先在 Prompts 页填写 API Key，并测试连接");
      navigate(`/projects/${projectId}/prompts`);
      return;
    }

    const hasAnyChapters = (chapters?.length ?? 0) > 0;
    const ok = await confirm.confirm({
      title: "自动生成大纲并创建章节骨架？",
      description: hasAnyChapters ? "检测到已有章节，可能需要覆盖创建（不可恢复）。" : "将调用 LLM 生成大纲，并创建章节骨架。",
      confirmText: "开始",
      danger: hasAnyChapters,
    });
    if (!ok) return;

    setAutoRunning(true);
    try {
      const outlineGen = await apiJson<OutlineGenResult>(`/api/projects/${projectId}/outline/generate`, {
        method: "POST",
        headers: {
          "X-LLM-Provider": llmPreset.provider,
          "X-LLM-API-Key": apiKey,
        },
        body: JSON.stringify({
          requirements: {
            chapter_count: 12,
            tone: "偏现实，克制但有爆点",
            pacing: "前3章强钩子，中段升级，结尾反转",
          },
          context: {
            include_world_setting: true,
            include_characters: true,
          },
        }),
      });

      const outlineMd = outlineGen.data.outline_md ?? "";
      await apiJson<{ outline: Outline }>(`/api/projects/${projectId}/outline`, {
        method: "PUT",
        body: JSON.stringify({ content_md: outlineMd }),
      });

      const genChapters = outlineGen.data.chapters ?? [];
      if (genChapters.length === 0) {
        toast.toastError("已生成大纲，但未解析出章节结构；请到大纲页手动调整并创建章节。");
        navigate(`/projects/${projectId}/outline`);
        return;
      }

      const payload = {
        chapters: genChapters.map((c) => ({
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
          await apiJson<{ chapters: Chapter[] }>(`/api/projects/${projectId}/chapters/bulk_create?replace=true`, {
            method: "POST",
            body: JSON.stringify(payload),
          });
        } else {
          throw e;
        }
      }

      toast.toastSuccess("已生成大纲并创建章节骨架");
      navigate(`/projects/${projectId}/writing`);
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setAutoRunning(false);
    }
  }, [chapters?.length, confirm, llmPreset, navigate, projectId, toast]);

  if (!projectId) return <div className="text-subtext">缺少 projectId</div>;
  if (wizardQuery.loading) return <div className="text-subtext">加载中...</div>;

  return (
    <div className="grid gap-6">
      <section className="rounded-atelier border border-border bg-surface p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="grid gap-2">
            <div className="font-content text-xl">开工向导</div>
            <div className="text-xs text-subtext">
              {project ? (
                <>
                  当前项目：<span className="text-ink">{project.name}</span>
                </>
              ) : (
                "按步骤跑通闭环：设定 → 角色 → 模型 → 大纲 → 章节 → 写作 → 导出"
              )}
            </div>
          </div>
          <div className="flex gap-2">
            <button
              className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink hover:bg-surface"
              onClick={() => void reload()}
              type="button"
            >
              刷新完成度
            </button>
            <button
              className="rounded-atelier bg-accent px-3 py-2 text-sm text-white hover:opacity-90 disabled:opacity-60"
              disabled={!progress.nextStep}
              onClick={() => {
                if (progress.nextStep) goStep(progress.nextStep);
              }}
              type="button"
            >
              {progress.nextStep ? `继续：${progress.nextStep.title}` : "已完成"}
            </button>
          </div>
        </div>

        <div className="mt-4">
          <div className="h-2 w-full rounded-full bg-border/60">
            <div className="h-2 rounded-full bg-accent transition-[width] duration-300" style={{ width: `${progress.percent}%` }} />
          </div>
          <div className="mt-2 text-xs text-subtext">完成度：{progress.percent}%</div>
        </div>
      </section>

      <section className="rounded-atelier border border-border bg-surface p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="grid gap-2">
            <div className="font-content text-xl">自动模式（MVP）</div>
            <div className="text-xs text-subtext">一键：生成大纲 → 保存 → 创建章节骨架 → 跳转写作页。</div>
          </div>
          <button
            className="rounded-atelier bg-accent px-3 py-2 text-sm text-white hover:opacity-90 disabled:opacity-60"
            disabled={autoRunning}
            onClick={() => void autoOutlineAndChapters()}
            type="button"
          >
            <span className="inline-flex items-center gap-2">
              <Wand2 size={18} />
              {autoRunning ? "运行中..." : "一键开工"}
            </span>
          </button>
        </div>
        {autoRunning ? <GhostwriterIndicator className="mt-4" label="正在调用模型生成大纲与章节结构…" /> : null}
      </section>

      <section className="rounded-atelier border border-border bg-surface p-6">
        <div className="font-content text-xl">步骤清单</div>
        <div className="mt-4 grid gap-3">
          {progress.steps.map((s) => {
            const Icon = s.state === "done" ? CheckCircle2 : s.state === "skipped" ? CircleSlash2 : Circle;
            const badge =
              s.state === "done"
                ? "已完成"
                : s.state === "skipped"
                  ? "已跳过"
                  : progress.nextStep?.key === s.key
                    ? "下一步"
                    : "待完成";
            return (
              <div key={s.key} className="flex flex-wrap items-start justify-between gap-3 rounded-atelier border border-border bg-canvas p-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Icon
                      className={clsx(
                        "shrink-0",
                        s.state === "done" ? "text-success" : s.state === "skipped" ? "text-subtext" : "text-subtext",
                      )}
                      size={18}
                    />
                    <div className="min-w-0 truncate text-sm text-ink">{s.title}</div>
                    <div
                      className={clsx(
                        "shrink-0 rounded-atelier px-2 py-0.5 text-[11px]",
                        s.state === "done"
                          ? "bg-success/15 text-success"
                          : s.state === "skipped"
                            ? "bg-border/60 text-subtext"
                            : progress.nextStep?.key === s.key
                              ? "bg-accent/15 text-accent"
                              : "bg-border/60 text-subtext",
                      )}
                    >
                      {badge}
                    </div>
                  </div>
                  <div className="mt-1 text-xs text-subtext">{s.description}</div>
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <button
                    className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink hover:bg-canvas"
                    onClick={() => goStep(s)}
                    type="button"
                  >
                    打开
                  </button>
                  {s.state === "todo" ? (
                    <button
                      className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-subtext hover:bg-canvas"
                      onClick={() => setSkipped(s.key, true)}
                      type="button"
                    >
                      跳过
                    </button>
                  ) : s.state === "skipped" ? (
                    <button
                      className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-subtext hover:bg-canvas"
                      onClick={() => setSkipped(s.key, false)}
                      type="button"
                    >
                      撤销跳过
                    </button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
