import { getCurrentUserId } from "./currentUser";
import { storageKey } from "./storageKeys";
import type { Chapter, Character, LLMPreset, LLMProfile, Outline, Project, ProjectSettings } from "../types";

export type WizardStepKey =
  | "llm"
  | "settings"
  | "characters"
  | "outline"
  | "chapters"
  | "writing"
  | "preview"
  | "export";
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
  exportedAt: string | null;
  writing: { doneChapters: number; totalChapters: number };
};

export type WizardComputeInput = {
  project: Project | null;
  settings: ProjectSettings | null;
  characters: Character[];
  outline: Outline | null;
  chapters: Chapter[];
  llmPreset: LLMPreset | null;
  llmProfile: LLMProfile | null;
};

export const WIZARD_PROGRESS_INVALIDATED_EVENT = "ainovel:wizard:progress_invalidated";

export type WizardProgressInvalidatedDetail = {
  projectId: string;
  refresh: boolean;
  reason: "project_changed" | "skip_changed" | "llm_test_ok" | "preview_seen" | "exported";
};

function emitWizardProgressInvalidated(detail: WizardProgressInvalidatedDetail): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<WizardProgressInvalidatedDetail>(WIZARD_PROGRESS_INVALIDATED_EVENT, { detail }));
}

export function onWizardProgressInvalidated(handler: (detail: WizardProgressInvalidatedDetail) => void): () => void {
  if (typeof window === "undefined") return () => {};
  const listener = (event: Event) => {
    const custom = event as CustomEvent<WizardProgressInvalidatedDetail>;
    if (!custom.detail?.projectId) return;
    handler(custom.detail);
  };
  window.addEventListener(WIZARD_PROGRESS_INVALIDATED_EVENT, listener);
  return () => window.removeEventListener(WIZARD_PROGRESS_INVALIDATED_EVENT, listener);
}

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

function projectChangedAtKey(projectId: string): string {
  return storageKey("wizard", "changed_at", getCurrentUserId(), projectId);
}

function previewSeenKey(projectId: string): string {
  return storageKey("wizard", "preview_seen", getCurrentUserId(), projectId);
}

export function isWizardStepSkipped(projectId: string, step: WizardStepKey): boolean {
  return localStorage.getItem(skipKey(projectId, step)) === "1";
}

export function setWizardStepSkipped(projectId: string, step: WizardStepKey, skipped: boolean): void {
  const key = skipKey(projectId, step);
  if (skipped) localStorage.setItem(key, "1");
  else localStorage.removeItem(key);
  emitWizardProgressInvalidated({ projectId, refresh: false, reason: "skip_changed" });
}

type LlmTestOkPayload = { provider: string; model: string; at: string };

export function markWizardLlmTestOk(projectId: string, provider: string, model: string): void {
  const payload: LlmTestOkPayload = { provider, model, at: new Date().toISOString() };
  localStorage.setItem(llmTestOkKey(projectId), JSON.stringify(payload));
  emitWizardProgressInvalidated({ projectId, refresh: false, reason: "llm_test_ok" });
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
  emitWizardProgressInvalidated({ projectId, refresh: false, reason: "exported" });
}

export function hasWizardExported(projectId: string): boolean {
  return Boolean(localStorage.getItem(exportedKey(projectId)));
}

export function getWizardExportedAt(projectId: string): string | null {
  return localStorage.getItem(exportedKey(projectId));
}

export function markWizardProjectChanged(projectId: string): void {
  localStorage.setItem(projectChangedAtKey(projectId), new Date().toISOString());
  emitWizardProgressInvalidated({ projectId, refresh: true, reason: "project_changed" });
}

export function getWizardProjectChangedAt(projectId: string): string | null {
  return localStorage.getItem(projectChangedAtKey(projectId));
}

export function markWizardPreviewSeen(projectId: string): void {
  localStorage.setItem(previewSeenKey(projectId), new Date().toISOString());
  emitWizardProgressInvalidated({ projectId, refresh: false, reason: "preview_seen" });
}

export function hasWizardPreviewSeen(projectId: string): boolean {
  return Boolean(localStorage.getItem(previewSeenKey(projectId)));
}

export function computeWizardProgress(input: WizardComputeInput): WizardProgress {
  const projectId = input.project?.id ?? "";
  const base = projectId ? `/projects/${projectId}` : "";

  const exportedAt = projectId ? getWizardExportedAt(projectId) : null;
  const changedAt = projectId ? getWizardProjectChangedAt(projectId) : null;
  const exportIsFresh = Boolean(exportedAt && (!changedAt || exportedAt >= changedAt));

  const totalChapters = input.chapters?.length ?? 0;
  const doneChapters = (input.chapters ?? []).filter((c) => c.status === "done").length;
  const writingProgress = totalChapters > 0 ? doneChapters / totalChapters : 0;

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
      description: "保存后端配置（含 API Key），点击“测试连接”。",
      href: `${base}/prompts`,
      done: Boolean(
        projectId &&
        input.llmPreset &&
        input.project?.llm_profile_id &&
        input.llmProfile?.has_api_key &&
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
      title: "完成全部章节",
      description: "将所有章节标记为 done（写完一章就设为 done）。",
      href: `${base}/writing`,
      done: totalChapters > 0 && doneChapters >= totalChapters,
    }),
    makeStep({
      key: "preview",
      title: "预览阅读",
      description: "在预览页通读章节内容，并可跳转回写作页快速修改。",
      href: `${base}/preview`,
      done: projectId ? hasWizardPreviewSeen(projectId) : false,
    }),
    makeStep({
      key: "export",
      title: "导出整本 Markdown",
      description: "在导出页选择范围，下载 `.md` 文件。",
      href: `${base}/export`,
      done: Boolean(projectId && exportIsFresh),
    }),
  ];

  const weights: Record<WizardStepKey, number> = {
    settings: 6,
    characters: 6,
    llm: 12,
    outline: 18,
    chapters: 10,
    writing: 36,
    preview: 6,
    export: 6,
  };

  const stepProgress = (key: WizardStepKey, state: WizardStepState): number => {
    if (state === "done" || state === "skipped") return 1;
    if (key === "writing") return writingProgress;
    return 0;
  };

  const percentRaw = steps.reduce((acc, s) => acc + weights[s.key] * stepProgress(s.key, s.state), 0);
  const percent = Math.max(0, Math.min(100, Math.floor(percentRaw)));
  const nextStep = steps.find((s) => s.state === "todo") ?? null;

  return { percent, steps, nextStep, exportedAt, writing: { doneChapters, totalChapters } };
}

export type WizardSummaryComputeInput = {
  project: Project | null;
  settings: ProjectSettings | null;
  characters_count: number;
  outline_content_md: string;
  chapters_total: number;
  chapters_done: number;
  llm_preset: Pick<LLMPreset, "provider" | "model"> | null;
  llm_profile_has_api_key: boolean;
};

export function computeWizardProgressFromSummary(input: WizardSummaryComputeInput): WizardProgress {
  const projectId = input.project?.id ?? "";
  const base = projectId ? `/projects/${projectId}` : "";

  const exportedAt = projectId ? getWizardExportedAt(projectId) : null;
  const changedAt = projectId ? getWizardProjectChangedAt(projectId) : null;
  const exportIsFresh = Boolean(exportedAt && (!changedAt || exportedAt >= changedAt));

  const totalChapters = input.chapters_total ?? 0;
  const doneChapters = input.chapters_done ?? 0;
  const writingProgress = totalChapters > 0 ? doneChapters / totalChapters : 0;

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
      done: (input.characters_count ?? 0) > 0,
    }),
    makeStep({
      key: "llm",
      title: "配置模型并测试连接",
      description: "保存后端配置（含 API Key），点击“测试连接”。",
      href: `${base}/prompts`,
      done: Boolean(
        projectId &&
        input.llm_preset &&
        input.project?.llm_profile_id &&
        input.llm_profile_has_api_key &&
        hasWizardLlmTestOk(projectId, input.llm_preset.provider, input.llm_preset.model),
      ),
    }),
    makeStep({
      key: "outline",
      title: "生成/编辑大纲",
      description: "用 AI 生成大纲后“应用生成结果”，或手动编写并保存。",
      href: `${base}/outline`,
      done: isNonEmpty(input.outline_content_md),
    }),
    makeStep({
      key: "chapters",
      title: "创建章节骨架",
      description: "从大纲一键创建章节骨架，或在写作页手动创建章节。",
      href: `${base}/outline`,
      done: totalChapters > 0,
    }),
    makeStep({
      key: "writing",
      title: "完成全部章节",
      description: "将所有章节标记为 done（写完一章就设为 done）。",
      href: `${base}/writing`,
      done: totalChapters > 0 && doneChapters >= totalChapters,
    }),
    makeStep({
      key: "preview",
      title: "预览阅读",
      description: "在预览页通读章节内容，并可跳转回写作页快速修改。",
      href: `${base}/preview`,
      done: projectId ? hasWizardPreviewSeen(projectId) : false,
    }),
    makeStep({
      key: "export",
      title: "导出整本 Markdown",
      description: "在导出页选择范围，下载 `.md` 文件。",
      href: `${base}/export`,
      done: Boolean(projectId && exportIsFresh),
    }),
  ];

  const weights: Record<WizardStepKey, number> = {
    settings: 6,
    characters: 6,
    llm: 12,
    outline: 18,
    chapters: 10,
    writing: 36,
    preview: 6,
    export: 6,
  };

  const stepProgress = (key: WizardStepKey, state: WizardStepState): number => {
    if (state === "done" || state === "skipped") return 1;
    if (key === "writing") return writingProgress;
    return 0;
  };

  const percentRaw = steps.reduce((acc, s) => acc + weights[s.key] * stepProgress(s.key, s.state), 0);
  const percent = Math.max(0, Math.min(100, Math.floor(percentRaw)));
  const nextStep = steps.find((s) => s.state === "todo") ?? null;

  return { percent, steps, nextStep, exportedAt, writing: { doneChapters, totalChapters } };
}
