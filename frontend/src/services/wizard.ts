import { getCurrentUserId } from "./currentUser";
import { getLlmApiKey } from "./llmKeyStore";
import { storageKey } from "./storageKeys";
import type { Chapter, Character, LLMPreset, Outline, Project, ProjectSettings } from "../types";

export type WizardStepKey = "llm" | "settings" | "characters" | "outline" | "chapters" | "writing" | "export";
export type WizardStepState = "todo" | "done" | "skipped";

export type WizardStep = {
  key: WizardStepKey;
  title: string;
  description: string;
  href: string;
  state: WizardStepState;
};

export type WizardProgress = {
  percent: number;
  steps: WizardStep[];
  nextStep: WizardStep | null;
};

export type WizardComputeInput = {
  project: Project | null;
  settings: ProjectSettings | null;
  characters: Character[];
  outline: Outline | null;
  chapters: Chapter[];
  llmPreset: LLMPreset | null;
};

function isNonEmpty(text?: string | null): boolean {
  return Boolean(text && text.trim().length > 0);
}

function skipKey(projectId: string, step: WizardStepKey): string {
  return storageKey("wizard", "skip", getCurrentUserId(), projectId, step);
}

function llmTestOkKey(projectId: string): string {
  return storageKey("wizard", "llm_test_ok", getCurrentUserId(), projectId);
}

function exportedKey(projectId: string): string {
  return storageKey("wizard", "exported", getCurrentUserId(), projectId);
}

export function isWizardStepSkipped(projectId: string, step: WizardStepKey): boolean {
  return localStorage.getItem(skipKey(projectId, step)) === "1";
}

export function setWizardStepSkipped(projectId: string, step: WizardStepKey, skipped: boolean): void {
  const key = skipKey(projectId, step);
  if (skipped) localStorage.setItem(key, "1");
  else localStorage.removeItem(key);
}

type LlmTestOkPayload = { provider: string; model: string; at: string };

export function markWizardLlmTestOk(projectId: string, provider: string, model: string): void {
  const payload: LlmTestOkPayload = { provider, model, at: new Date().toISOString() };
  localStorage.setItem(llmTestOkKey(projectId), JSON.stringify(payload));
}

export function hasWizardLlmTestOk(projectId: string, provider: string, model: string): boolean {
  const raw = localStorage.getItem(llmTestOkKey(projectId));
  if (!raw) return false;
  try {
    const parsed = JSON.parse(raw) as LlmTestOkPayload;
    return parsed.provider === provider && parsed.model === model;
  } catch {
    return false;
  }
}

export function markWizardExported(projectId: string): void {
  localStorage.setItem(exportedKey(projectId), new Date().toISOString());
}

export function hasWizardExported(projectId: string): boolean {
  return Boolean(localStorage.getItem(exportedKey(projectId)));
}

export function computeWizardProgress(input: WizardComputeInput): WizardProgress {
  const projectId = input.project?.id ?? "";
  const base = projectId ? `/projects/${projectId}` : "";

  const makeStep = (step: Omit<WizardStep, "state"> & { done: boolean }): WizardStep => {
    if (!projectId) return { ...step, state: "todo" };
    if (isWizardStepSkipped(projectId, step.key)) return { ...step, state: "skipped" };
    return { ...step, state: step.done ? "done" : "todo" };
  };

  const steps: WizardStep[] = [
    makeStep({
      key: "settings",
      title: "补齐设定",
      description: "填写世界观/风格/约束（越具体越好）。",
      href: `${base}/settings`,
      done: Boolean(
        isNonEmpty(input.settings?.world_setting) ||
          isNonEmpty(input.settings?.style_guide) ||
          isNonEmpty(input.settings?.constraints) ||
          isNonEmpty(input.project?.genre) ||
          isNonEmpty(input.project?.logline),
      ),
    }),
    makeStep({
      key: "characters",
      title: "添加角色卡",
      description: "至少创建 1 个核心角色，后续生成会注入角色信息。",
      href: `${base}/characters`,
      done: (input.characters?.length ?? 0) > 0,
    }),
    makeStep({
      key: "llm",
      title: "配置模型并测试连接",
      description: "填写 API Key，选择 provider/model，点击“测试连接”。",
      href: `${base}/prompts`,
      done: Boolean(
        projectId &&
          input.llmPreset &&
          getLlmApiKey(input.llmPreset.provider).trim() &&
          hasWizardLlmTestOk(projectId, input.llmPreset.provider, input.llmPreset.model),
      ),
    }),
    makeStep({
      key: "outline",
      title: "生成/编辑大纲",
      description: "用 AI 生成大纲后“应用生成结果”，或手动编写并保存。",
      href: `${base}/outline`,
      done: isNonEmpty(input.outline?.content_md),
    }),
    makeStep({
      key: "chapters",
      title: "创建章节骨架",
      description: "从大纲一键创建章节骨架，或在写作页手动创建章节。",
      href: `${base}/outline`,
      done: (input.chapters?.length ?? 0) > 0,
    }),
    makeStep({
      key: "writing",
      title: "开始写作",
      description: "进入写作页，生成第 1 章草稿并编辑保存。",
      href: `${base}/writing`,
      done: (input.chapters ?? []).some((c) => isNonEmpty(c.content_md) || c.status !== "planned"),
    }),
    makeStep({
      key: "export",
      title: "导出整本 Markdown",
      description: "在导出页选择范围，下载 `.md` 文件。",
      href: `${base}/export`,
      done: projectId ? hasWizardExported(projectId) : false,
    }),
  ];

  const completedCount = steps.filter((s) => s.state === "done" || s.state === "skipped").length;
  const percent = steps.length ? Math.round((completedCount / steps.length) * 100) : 0;
  const nextStep = steps.find((s) => s.state === "todo") ?? null;

  return { percent, steps, nextStep };
}
