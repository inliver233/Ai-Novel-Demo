import clsx from "clsx";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useConfirm } from "../components/ui/confirm";
import { useToast } from "../components/ui/toast";
import { copyText } from "../lib/copyText";
import { PROMPT_STUDIO_TASKS } from "../lib/promptTaskCatalog";
import { usePersistentOutletIsActive } from "../hooks/usePersistentOutlet";
import { UnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";
import { ApiError, apiJson, sanitizeFilename } from "../services/apiClient";
import type { Character, Outline, Project, ProjectSettings, PromptBlock, PromptPreset, PromptPreview } from "../types";
import { PromptStudioPreviewPanel } from "./promptStudio/PromptStudioPreviewPanel";
import type { PromptStudioTask } from "./promptStudio/types";
import { guessPreviewValues } from "./promptStudio/utils";

const PREVIEW_TASKS: PromptStudioTask[] = PROMPT_STUDIO_TASKS;

const SUPPORTED_PREVIEW_TASK_KEYS = new Set(PREVIEW_TASKS.map((t) => t.key));
const TEMPLATE_VAR_TOKEN_RE = /{{\s*([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)\s*}}/g;
const TEMPLATE_MACRO_NAMES = new Set(["date", "time", "isodate"]);
const SAFE_KEY_RE = /^[A-Za-z0-9_]+$/;

function extractTemplateVars(template: string): string[] {
  const out = new Set<string>();
  for (const match of template.matchAll(TEMPLATE_VAR_TOKEN_RE)) {
    const path = String(match[1] ?? "").trim();
    if (!path || TEMPLATE_MACRO_NAMES.has(path)) continue;
    out.add(path);
  }
  return [...out].sort((a, b) => a.localeCompare(b, "en"));
}

function collectPreviewValuePaths(values: Record<string, unknown>): string[] {
  const out = new Set<string>();

  const visit = (value: unknown, prefix: string, depth: number) => {
    if (!prefix) return;
    if (value === null || value === undefined) {
      out.add(prefix);
      return;
    }
    if (typeof value !== "object" || Array.isArray(value)) {
      out.add(prefix);
      return;
    }

    if (depth >= 3) {
      out.add(prefix);
      return;
    }

    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      if (!key || key.startsWith("_") || !SAFE_KEY_RE.test(key)) continue;
      visit(child, `${prefix}.${key}`, depth + 1);
    }
  };

  for (const [key, value] of Object.entries(values)) {
    if (!key || key.startsWith("_") || !SAFE_KEY_RE.test(key)) continue;
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      for (const [childKey, child] of Object.entries(value as Record<string, unknown>)) {
        if (!childKey || childKey.startsWith("_") || !SAFE_KEY_RE.test(childKey)) continue;
        visit(child, `${key}.${childKey}`, 1);
      }
      continue;
    }
    visit(value, key, 0);
  }

  return [...out].sort((a, b) => a.localeCompare(b, "en"));
}

type PromptPresetResource = {
  key: string;
  name: string;
  category?: string | null;
  scope: string;
  version: number;
  activation_tasks: string[];
  preset_id?: string | null;
  preset_version?: number | null;
  preset_updated_at?: string | null;
};

type PresetDetails = {
  preset: PromptPreset;
  blocks: PromptBlock[];
};

type ImportAllReport = {
  dry_run: boolean;
  created: number;
  updated: number;
  skipped: number;
  conflicts: unknown[];
  actions: unknown[];
};

function downloadJsonFile(value: unknown, filename: string) {
  const jsonText = JSON.stringify(value, null, 2);
  const blob = new Blob([jsonText], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = sanitizeFilename(filename) || "prompt_templates.json";
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function formatImportAllReport(report: ImportAllReport): string {
  const conflicts = Array.isArray(report.conflicts) ? report.conflicts : [];
  const actions = Array.isArray(report.actions) ? report.actions : [];

  const lines = [
    `dry_run: ${Boolean(report.dry_run)}`,
    `created: ${Number(report.created) || 0}`,
    `updated: ${Number(report.updated) || 0}`,
    `skipped: ${Number(report.skipped) || 0}`,
    `conflicts: ${conflicts.length}`,
    "",
    "conflicts sample:",
    ...(conflicts.slice(0, 10).map((c) => JSON.stringify(c)) || ["(none)"]),
    "",
    "actions sample:",
    ...(actions.slice(0, 20).map((a) => JSON.stringify(a)) || ["(none)"]),
    actions.length > 20 ? `...(${actions.length - 20} more actions)` : "",
  ].filter((v) => typeof v === "string");

  return lines.join("\n").trim();
}

export function PromptTemplatesPage() {
  const { projectId } = useParams();
  const toast = useToast();
  const confirm = useConfirm();

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [project, setProject] = useState<Project | null>(null);
  const [settings, setSettings] = useState<ProjectSettings | null>(null);
  const [outline, setOutline] = useState<Outline | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);

  const [resources, setResources] = useState<PromptPresetResource[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const [preset, setPreset] = useState<PromptPreset | null>(null);
  const [blocks, setBlocks] = useState<PromptBlock[]>([]);

  const [draftTemplates, setDraftTemplates] = useState<Record<string, string>>({});
  const [baselineTemplates, setBaselineTemplates] = useState<Record<string, string>>({});

  const outletActive = usePersistentOutletIsActive();

  const pageDirty = useMemo(
    () => blocks.some((b) => (draftTemplates[b.id] ?? "") !== (baselineTemplates[b.id] ?? "")),
    [baselineTemplates, blocks, draftTemplates],
  );

  const savingBlockIdRef = useRef<string | null>(null);

  const [previewTask, setPreviewTask] = useState<string>("chapter_generate");
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [renderLog, setRenderLog] = useState<unknown | null>(null);
  const [previewRequestId, setPreviewRequestId] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const selectedResource = useMemo(
    () => resources.find((r) => r.key === selectedKey) ?? null,
    [resources, selectedKey],
  );

  const resourceGroups = useMemo(() => {
    const groups = new Map<string, PromptPresetResource[]>();
    for (const r of resources) {
      const key = String(r.category ?? "").trim() || "（未分类）";
      const list = groups.get(key) ?? [];
      list.push(r);
      groups.set(key, list);
    }
    const out = Array.from(groups.entries()).map(([category, items]) => {
      items.sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"));
      return [category, items] as const;
    });
    out.sort((a, b) => a[0].localeCompare(b[0], "zh-Hans-CN"));
    return out;
  }, [resources]);

  const loadResources = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      // Ensure baseline presets exist (idempotent) so the resource list can map to preset_id.
      await apiJson<{ presets: PromptPreset[] }>(`/api/projects/${projectId}/prompt_presets`);

      const res = await apiJson<{ resources: PromptPresetResource[] }>(
        `/api/projects/${projectId}/prompt_preset_resources`,
      );
      const nextResources = res.data.resources ?? [];
      setResources(nextResources);

      setSelectedKey((prev) => {
        if (prev && nextResources.some((r) => r.key === prev)) return prev;
        const firstWithPreset = nextResources.find((r) => typeof r.preset_id === "string" && r.preset_id.length > 0);
        return firstWithPreset?.key ?? nextResources[0]?.key ?? null;
      });
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  const selectKeyWithGuard = useCallback(
    async (nextKey: string) => {
      if (nextKey === selectedKey) return;
      if (!pageDirty) {
        setSelectedKey(nextKey);
        return;
      }

      const ok = await confirm.confirm({
        title: "有未保存修改，确定切换模板？",
        description: "切换后未保存内容会丢失。",
        confirmText: "切换",
        cancelText: "取消",
        danger: true,
      });
      if (!ok) return;
      setSelectedKey(nextKey);
    },
    [confirm, pageDirty, selectedKey],
  );

  const loadPreviewContext = useCallback(async () => {
    if (!projectId) return;
    try {
      const [pRes, sRes, oRes, cRes] = await Promise.all([
        apiJson<{ project: Project }>(`/api/projects/${projectId}`),
        apiJson<{ settings: ProjectSettings }>(`/api/projects/${projectId}/settings`),
        apiJson<{ outline: Outline }>(`/api/projects/${projectId}/outline`),
        apiJson<{ characters: Character[] }>(`/api/projects/${projectId}/characters`),
      ]);
      setProject(pRes.data.project);
      setSettings(sRes.data.settings);
      setOutline(oRes.data.outline);
      setCharacters(cRes.data.characters ?? []);
    } catch {
      // optional: preview can still work with fallback values
    }
  }, [projectId]);

  const loadPreset = useCallback(
    async (presetId: string) => {
      setBusy(true);
      try {
        const res = await apiJson<PresetDetails>(`/api/prompt_presets/${presetId}`);
        setPreset(res.data.preset);
        setBlocks(res.data.blocks ?? []);

        const nextDrafts: Record<string, string> = {};
        const nextBaseline: Record<string, string> = {};
        for (const b of res.data.blocks ?? []) {
          const t = b.template ?? "";
          nextDrafts[b.id] = t;
          nextBaseline[b.id] = t;
        }
        setDraftTemplates(nextDrafts);
        setBaselineTemplates(nextBaseline);
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setBusy(false);
      }
    },
    [toast],
  );

  useEffect(() => {
    void loadResources();
  }, [loadResources]);

  useEffect(() => {
    void loadPreviewContext();
  }, [loadPreviewContext]);

  useEffect(() => {
    const presetId = selectedResource?.preset_id ?? null;
    if (!presetId) {
      setPreset(null);
      setBlocks([]);
      setDraftTemplates({});
      setBaselineTemplates({});
      return;
    }
    void loadPreset(presetId);
  }, [loadPreset, selectedResource?.preset_id]);

  const previewValues = useMemo(
    () => guessPreviewValues({ project, settings, outline, characters }),
    [characters, outline, project, settings],
  );

  const availableValuePaths = useMemo(() => collectPreviewValuePaths(previewValues), [previewValues]);
  const availableVariablesText = useMemo(
    () => availableValuePaths.map((path) => `{{` + path + `}}`).join("\n"),
    [availableValuePaths],
  );

  const previewTasks = useMemo(() => {
    const activationTasks = selectedResource?.activation_tasks ?? [];
    const allowed = new Set(activationTasks.filter((t) => SUPPORTED_PREVIEW_TASK_KEYS.has(t)));
    if (allowed.size > 0) return PREVIEW_TASKS.filter((t) => allowed.has(t.key));
    return PREVIEW_TASKS;
  }, [selectedResource?.activation_tasks]);

  useEffect(() => {
    if (!previewTasks.length) return;
    if (previewTasks.some((t) => t.key === previewTask)) return;
    setPreviewTask(previewTasks[0].key);
  }, [previewTask, previewTasks]);

  const runPreview = useCallback(async () => {
    if (!projectId || !preset) return;
    setPreviewLoading(true);
    setPreviewRequestId(null);
    try {
      const res = await apiJson<{ preview: PromptPreview; render_log?: unknown }>(
        `/api/projects/${projectId}/prompt_preview`,
        {
          method: "POST",
          body: JSON.stringify({ task: previewTask, preset_id: preset.id, values: previewValues }),
        },
      );
      setPreview(res.data.preview);
      setRenderLog(res.data.render_log ?? null);
      setPreviewRequestId(res.request_id ?? null);
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
      setPreviewRequestId(err.requestId ?? null);
    } finally {
      setPreviewLoading(false);
    }
  }, [preset, previewTask, previewValues, projectId, toast]);

  const templateErrors = useMemo(() => {
    const blocks = (renderLog as { blocks?: unknown } | null)?.blocks;
    if (!Array.isArray(blocks)) return [];
    return blocks
      .map((b) => b as { identifier?: unknown; render_error?: unknown })
      .filter((b) => typeof b.render_error === "string" && b.render_error.trim())
      .map((b) => ({ identifier: String(b.identifier ?? ""), error: String(b.render_error ?? "") }))
      .filter((b) => b.identifier && b.error);
  }, [renderLog]);

  const exportAllPresets = useCallback(async () => {
    if (!projectId) return;
    setBusy(true);
    try {
      const res = await apiJson<{ export: unknown }>(`/api/projects/${projectId}/prompt_presets/export_all`);
      const stamp = new Date().toISOString().replaceAll(":", "-").replaceAll(".", "-");
      downloadJsonFile(res.data.export, `prompt_presets_all_${stamp}.json`);
      toast.toastSuccess("已导出整套");
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setBusy(false);
    }
  }, [projectId, toast]);

  const importAllPresets = useCallback(
    async (file: File) => {
      if (!projectId) return;
      setBusy(true);
      try {
        const text = await file.text();
        const obj = JSON.parse(text) as Record<string, unknown>;

        const dryRunRes = await apiJson<ImportAllReport>(`/api/projects/${projectId}/prompt_presets/import_all`, {
          method: "POST",
          body: JSON.stringify({ ...obj, dry_run: true }),
        });

        const report = dryRunRes.data;
        const ok = await confirm.confirm({
          title: "导入整套 PromptPresets（dry_run）",
          description: formatImportAllReport(report),
          confirmText: "应用导入",
          cancelText: "取消",
          danger: Array.isArray(report.conflicts) && report.conflicts.length > 0,
        });
        if (!ok) return;

        const applyRes = await apiJson<ImportAllReport>(`/api/projects/${projectId}/prompt_presets/import_all`, {
          method: "POST",
          body: JSON.stringify({ ...obj, dry_run: false }),
        });

        toast.toastSuccess(
          `已导入整套 created:${applyRes.data.created} updated:${applyRes.data.updated} skipped:${applyRes.data.skipped}`,
        );
        await loadResources();
      } catch (e) {
        if (e instanceof SyntaxError) {
          toast.toastError("导入失败：不是合法 JSON");
          return;
        }
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setBusy(false);
      }
    },
    [confirm, loadResources, projectId, toast],
  );

  const exportSelectedPreset = useCallback(async () => {
    if (!preset) return;
    setBusy(true);
    try {
      const res = await apiJson<{ export: unknown }>(`/api/prompt_presets/${preset.id}/export`);
      downloadJsonFile(res.data.export, `${preset.name || "prompt_preset"}.json`);
      toast.toastSuccess("已导出");
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setBusy(false);
    }
  }, [preset, toast]);

  const resetSelectedPreset = useCallback(async () => {
    if (!preset) return;
    const ok = await confirm.confirm({
      title: "重置为系统默认",
      description: "将该预设的所有模板片段恢复为内置资源版本（不会删除你的其它预设）。",
      confirmText: "重置",
      cancelText: "取消",
      danger: true,
    });
    if (!ok) return;

    setBusy(true);
    try {
      const res = await apiJson<{ preset: PromptPreset; blocks: PromptBlock[] }>(
        `/api/prompt_presets/${preset.id}/reset_to_default`,
        { method: "POST", body: JSON.stringify({}) },
      );
      setPreset(res.data.preset);
      setBlocks(res.data.blocks ?? []);
      const nextDrafts: Record<string, string> = {};
      const nextBaseline: Record<string, string> = {};
      for (const b of res.data.blocks ?? []) {
        const t = b.template ?? "";
        nextDrafts[b.id] = t;
        nextBaseline[b.id] = t;
      }
      setDraftTemplates(nextDrafts);
      setBaselineTemplates(nextBaseline);
      toast.toastSuccess("已重置为系统默认");
      await loadResources();
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setBusy(false);
    }
  }, [confirm, loadResources, preset, toast]);

  const saveBlockTemplate = useCallback(
    async (block: PromptBlock) => {
      const nextTemplate = draftTemplates[block.id] ?? "";
      if (savingBlockIdRef.current) return;
      savingBlockIdRef.current = block.id;
      setBusy(true);
      try {
        const res = await apiJson<{ block: PromptBlock }>(`/api/prompt_blocks/${block.id}`, {
          method: "PUT",
          body: JSON.stringify({ template: nextTemplate }),
        });
        const updated = res.data.block;
        setBlocks((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
        const stableTemplate = updated.template ?? "";
        setDraftTemplates((prev) => ({ ...prev, [updated.id]: stableTemplate }));
        setBaselineTemplates((prev) => ({ ...prev, [updated.id]: stableTemplate }));
        toast.toastSuccess("已保存");
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        savingBlockIdRef.current = null;
        setBusy(false);
      }
    },
    [draftTemplates, toast],
  );

  const resetBlockTemplate = useCallback(
    async (block: PromptBlock) => {
      const ok = await confirm.confirm({
        title: "重置该片段",
        description: "将该模板片段恢复为系统默认版本。",
        confirmText: "重置",
        cancelText: "取消",
        danger: true,
      });
      if (!ok) return;

      setBusy(true);
      try {
        const res = await apiJson<{ block: PromptBlock }>(`/api/prompt_blocks/${block.id}/reset_to_default`, {
          method: "POST",
          body: JSON.stringify({}),
        });
        const updated = res.data.block;
        setBlocks((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
        const stableTemplate = updated.template ?? "";
        setDraftTemplates((prev) => ({ ...prev, [updated.id]: stableTemplate }));
        setBaselineTemplates((prev) => ({ ...prev, [updated.id]: stableTemplate }));
        toast.toastSuccess("已重置");
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setBusy(false);
      }
    },
    [confirm, toast],
  );

  return (
    <div className="grid gap-6">
      {pageDirty && outletActive ? <UnsavedChangesGuard when={pageDirty} /> : null}
      <div className="panel p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="text-lg font-semibold">Prompt 模板（新手）</div>
              {pageDirty ? (
                <span className="rounded-atelier border border-accent/30 bg-accent/10 px-2 py-0.5 text-xs text-accent">
                  未保存
                </span>
              ) : null}
            </div>
            <div className="text-xs text-subtext">
              按任务提供系统默认模板；编辑会直接影响真实渲染。{" "}
              <Link className="underline" to={`/projects/${projectId}/prompt-studio`}>
                高级：提示词工作室
              </Link>
            </div>
          </div>
          <div className="text-xs text-subtext">{loading || busy ? "处理中…" : ""}</div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button className="btn btn-secondary" onClick={() => void exportAllPresets()} disabled={busy} type="button">
            导出整套
          </button>
          <label className={clsx("btn btn-secondary", busy ? "opacity-60" : "cursor-pointer")}>
            导入整套
            <input
              className="hidden"
              type="file"
              accept="application/json"
              disabled={busy}
              onChange={(e) => {
                const file = e.currentTarget.files?.[0];
                e.currentTarget.value = "";
                if (!file) return;
                void importAllPresets(file);
              }}
            />
          </label>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px,1fr]">
        <div className="panel p-3">
          <div className="text-sm font-semibold">系统默认模板</div>
          <div className="mt-1 text-xs text-subtext">按分类分组；点击后在右侧编辑。</div>
          <div className="mt-3 grid gap-3">
            {resourceGroups.map(([category, items]) => (
              <div key={category}>
                <div className="text-xs text-subtext">{category}</div>
                <div className="mt-1 grid gap-1">
                  {items.map((r) => {
                    const selected = r.key === selectedKey;
                    return (
                      <button
                        key={r.key}
                        className={clsx(
                          "ui-transition-fast w-full overflow-hidden rounded-atelier border px-3 py-2 text-left text-sm",
                          selected
                            ? "border-accent/40 bg-accent/10 text-ink"
                            : "border-border bg-canvas text-subtext hover:bg-surface hover:text-ink",
                        )}
                        onClick={() => void selectKeyWithGuard(r.key)}
                        type="button"
                      >
                        <div className="flex min-w-0 items-center justify-between gap-2">
                          <div className="min-w-0 flex-1 truncate">{r.name}</div>
                          <div className="min-w-0 max-w-[120px] shrink-0 truncate text-[11px] text-subtext">
                            {r.activation_tasks?.[0] ?? ""}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-6">
          <div className="panel p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-sm font-semibold">{selectedResource?.name ?? "（未选择）"}</div>
                <div className="text-xs text-subtext">
                  tasks:{" "}
                  {selectedResource?.activation_tasks?.length ? selectedResource.activation_tasks.join(", ") : "—"}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  className="btn btn-secondary"
                  onClick={() => void exportSelectedPreset()}
                  disabled={busy || !preset}
                  type="button"
                >
                  导出当前
                </button>
                <button
                  className="btn btn-ghost text-accent hover:bg-accent/10"
                  onClick={() => void resetSelectedPreset()}
                  disabled={busy || !preset}
                  type="button"
                >
                  重置为系统默认
                </button>
              </div>
            </div>

            {!selectedResource ? <div className="text-sm text-subtext">请选择左侧模板。</div> : null}

            {selectedResource && !selectedResource.preset_id ? (
              <div className="text-sm text-subtext">该模板尚未在项目中初始化，请刷新或先打开提示词工作室。</div>
            ) : null}

            {preset ? (
              <div className="grid gap-3">
                <details className="rounded-atelier border border-border bg-surface/50 p-3">
                  <summary className="ui-transition-fast cursor-pointer text-sm hover:text-ink">
                    模板语法与可用变量（点击复制）
                  </summary>
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-subtext">
                    <div className="grid gap-1">
                      <div>
                        变量：<span className="atelier-mono text-ink">{"{{project_name}}"}</span>{" "}
                        <span className="atelier-mono text-ink">{"{{story.outline}}"}</span>
                      </div>
                      <div>
                        条件：<span className="atelier-mono text-ink">{"{% if chapter_number == '1' %}"}</span>...{" "}
                        <span className="atelier-mono text-ink">{"{% endif %}"}</span>
                      </div>
                      <div>
                        宏：<span className="atelier-mono text-ink">{"{{date}}"}</span>{" "}
                        <span className="atelier-mono text-ink">{"{{time}}"}</span>{" "}
                        <span className="atelier-mono text-ink">{"{{pick::A::B}}"}</span>
                      </div>
                      <div>预览渲染使用“已保存模板”；未保存改动请先点“保存”。</div>
                    </div>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={async () => {
                        await copyText(availableVariablesText, { title: "复制失败：请手动复制变量清单" });
                      }}
                      type="button"
                    >
                      复制变量清单
                    </button>
                  </div>
                  <pre className="mt-2 max-h-[220px] overflow-auto whitespace-pre-wrap break-words rounded-atelier border border-border bg-surface p-3 text-xs">
                    {availableVariablesText || "（变量清单为空）"}
                  </pre>
                </details>

                {blocks.map((b) => {
                  const draft = draftTemplates[b.id] ?? "";
                  const baseline = baselineTemplates[b.id] ?? "";
                  const dirty = draft !== baseline;
                  const usedVars = extractTemplateVars(draft);
                  return (
                    <div key={b.id} className="rounded-atelier border border-border bg-canvas p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium">
                            {b.name} <span className="text-xs text-subtext">({b.role})</span>
                          </div>
                          <div className="truncate text-xs text-subtext">{b.identifier}</div>
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                          {dirty ? <div className="text-xs text-accent">未保存</div> : null}
                          <button
                            className="btn btn-primary"
                            onClick={() => void saveBlockTemplate(b)}
                            disabled={busy || !dirty}
                            type="button"
                          >
                            保存
                          </button>
                          <button
                            className="btn btn-ghost text-accent hover:bg-accent/10"
                            onClick={() => void resetBlockTemplate(b)}
                            disabled={busy}
                            type="button"
                          >
                            重置
                          </button>
                        </div>
                      </div>
                      <div className="mt-2 grid gap-1">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-xs text-subtext">
                            变量（本块）：{usedVars.length ? `${usedVars.length} 个（点击复制）` : "未检测到"}
                          </div>
                          {usedVars.length ? (
                            <button
                              className="btn btn-secondary btn-sm"
                              onClick={async () => {
                                const text = usedVars.map((v) => `{{` + v + `}}`).join("\n");
                                await copyText(text, {
                                  title: "复制失败：请手动复制变量清单",
                                });
                              }}
                              type="button"
                            >
                              复制本块变量
                            </button>
                          ) : null}
                        </div>
                        {usedVars.length ? (
                          <div className="flex flex-wrap gap-1">
                            {usedVars.map((v) => (
                              <button
                                key={v}
                                className="btn btn-ghost btn-sm atelier-mono"
                                onClick={async () => {
                                  const text = `{{` + v + `}}`;
                                  await copyText(text, { title: "复制失败：请手动复制变量" });
                                }}
                                type="button"
                              >
                                {`{{` + v + `}}`}
                              </button>
                            ))}
                          </div>
                        ) : null}
                        <textarea
                          className="textarea atelier-mono min-h-[160px] resize-y py-2 text-xs"
                          value={draft}
                          disabled={busy}
                          onChange={(e) => setDraftTemplates((prev) => ({ ...prev, [b.id]: e.target.value }))}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : null}
          </div>

          <PromptStudioPreviewPanel
            busy={busy}
            selectedPresetId={preset?.id ?? null}
            previewTask={previewTask}
            setPreviewTask={setPreviewTask}
            tasks={previewTasks}
            previewLoading={previewLoading}
            runPreview={runPreview}
            requestId={previewRequestId}
            preview={preview}
            templateErrors={templateErrors}
            renderLog={renderLog}
          />
        </div>
      </div>
    </div>
  );
}
