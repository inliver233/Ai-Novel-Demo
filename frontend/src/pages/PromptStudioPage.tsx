import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useConfirm } from "../components/ui/confirm";
import { useToast } from "../components/ui/toast";
import { ApiError, apiJson } from "../services/apiClient";
import type { Character, Outline, Project, ProjectSettings, PromptBlock, PromptPreset, PromptPreview } from "../types";

type PresetDetails = { preset: PromptPreset; blocks: PromptBlock[] };

type BlockDraft = {
  identifier: string;
  name: string;
  role: string;
  enabled: boolean;
  template: string;
  marker_key: string;
  triggers: string;
};

const RECOMMENDED_OUTLINE_PRESET_NAME = "默认·大纲生成 v3（推荐）";
const RECOMMENDED_CHAPTER_PRESET_NAME = "默认·章节生成 v3（推荐）";

function formatTriggers(value: string[]): string {
  return (value ?? []).join(", ");
}

function parseTriggers(value: string): string[] {
  const trimmed = value.trim();
  if (!trimmed) return [];
  return trimmed
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function formatCharacters(chars: Character[]): string {
  return chars
    .map((c) => `- ${c.name}${c.role ? `（${c.role}）` : ""}`)
    .join("\\n");
}

function guessPreviewValues(args: {
  project: Project | null;
  settings: ProjectSettings | null;
  outline: Outline | null;
  characters: Character[];
}): Record<string, string> {
  return {
    project_name: args.project?.name ?? "",
    genre: args.project?.genre ?? "",
    logline: args.project?.logline ?? "",
    world_setting: args.settings?.world_setting ?? "",
    style_guide: args.settings?.style_guide ?? "",
    constraints: args.settings?.constraints ?? "",
    characters: formatCharacters(args.characters),
    outline: args.outline?.content_md ?? "",
    chapter_number: "1",
    chapter_title: "第一章",
    chapter_plan: "（示例要点）",
    requirements: "{\\n  \"chapter_count\": 12\\n}",
    instruction: "（示例指令）",
    previous_chapter: "（示例上一章摘要）",
    target_word_count: "2500",
    raw_content: "（示例已生成正文，用于 post_edit 预览）",
  };
}

function isMigratedPreset(preset: PromptPreset | null): boolean {
  return (preset?.name ?? "") === "[Migrated] prompt_templates";
}

export function PromptStudioPage() {
  const { projectId } = useParams();
  const toast = useToast();
  const confirm = useConfirm();

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [project, setProject] = useState<Project | null>(null);
  const [settings, setSettings] = useState<ProjectSettings | null>(null);
  const [outline, setOutline] = useState<Outline | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);

  const [presets, setPresets] = useState<PromptPreset[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null);
  const [selectedPreset, setSelectedPreset] = useState<PromptPreset | null>(null);
  const [blocks, setBlocks] = useState<PromptBlock[]>([]);
  const [drafts, setDrafts] = useState<Record<string, BlockDraft>>({});

  const [presetDraftName, setPresetDraftName] = useState("");
  const [presetDraftActiveFor, setPresetDraftActiveFor] = useState<string[]>([]);

  const [newPresetName, setNewPresetName] = useState("");
  const [importBusy, setImportBusy] = useState(false);
  const importInputRef = useRef<HTMLInputElement | null>(null);

  const [previewTask, setPreviewTask] = useState<string>("chapter_generate");
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const previewValues = useMemo(
    () => guessPreviewValues({ project, settings, outline, characters }),
    [characters, outline, project, settings],
  );

  const reloadAll = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [pRes, sRes, oRes, cRes, presetsRes] = await Promise.all([
        apiJson<{ project: Project }>(`/api/projects/${projectId}`),
        apiJson<{ settings: ProjectSettings }>(`/api/projects/${projectId}/settings`),
        apiJson<{ outline: Outline }>(`/api/projects/${projectId}/outline`),
        apiJson<{ characters: Character[] }>(`/api/projects/${projectId}/characters`),
        apiJson<{ presets: PromptPreset[] }>(`/api/projects/${projectId}/prompt_presets`),
      ]);

      setProject(pRes.data.project);
      setSettings(sRes.data.settings);
      setOutline(oRes.data.outline);
      setCharacters(cRes.data.characters);
      setPresets(presetsRes.data.presets ?? []);

      const nextPresetId =
        selectedPresetId && (presetsRes.data.presets ?? []).some((p) => p.id === selectedPresetId)
          ? selectedPresetId
          : (presetsRes.data.presets?.[0]?.id ?? null);
      setSelectedPresetId(nextPresetId);
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setLoading(false);
    }
  }, [projectId, selectedPresetId, toast]);

  useEffect(() => {
    void reloadAll();
  }, [reloadAll]);

  const loadPreset = useCallback(
    async (presetId: string) => {
      setBusy(true);
      try {
        const res = await apiJson<PresetDetails>(`/api/prompt_presets/${presetId}`);
        setSelectedPreset(res.data.preset);
        setBlocks(res.data.blocks ?? []);
        setPresetDraftName(res.data.preset.name ?? "");
        setPresetDraftActiveFor(res.data.preset.active_for ?? []);
        const nextDrafts: Record<string, BlockDraft> = {};
        for (const b of res.data.blocks ?? []) {
          nextDrafts[b.id] = {
            identifier: b.identifier,
            name: b.name,
            role: b.role,
            enabled: b.enabled,
            template: b.template ?? "",
            marker_key: b.marker_key ?? "",
            triggers: formatTriggers(b.triggers ?? []),
          };
        }
        setDrafts(nextDrafts);
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
    if (!selectedPresetId) return;
    void loadPreset(selectedPresetId);
  }, [loadPreset, selectedPresetId]);

  const createPreset = useCallback(async () => {
    if (!projectId) return;
    const name = newPresetName.trim();
    if (!name) {
      toast.toastError("请输入预设名称");
      return;
    }
    setBusy(true);
    try {
      const res = await apiJson<{ preset: PromptPreset }>(`/api/projects/${projectId}/prompt_presets`, {
        method: "POST",
        body: JSON.stringify({ name, scope: "project", version: 1, active_for: [] }),
      });
      setNewPresetName("");
      await reloadAll();
      setSelectedPresetId(res.data.preset.id);
      toast.toastSuccess("已创建预设");
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setBusy(false);
    }
  }, [newPresetName, projectId, reloadAll, toast]);

  const deletePreset = useCallback(async () => {
    if (!selectedPresetId || !selectedPreset) return;
    const ok = await confirm.confirm({
      title: "删除预设？",
      description: `将删除预设“${selectedPreset.name}”及其所有块。该操作不可撤销。`,
      confirmText: "删除",
      danger: true,
    });
    if (!ok) return;

    setBusy(true);
    try {
      await apiJson<Record<string, never>>(`/api/prompt_presets/${selectedPresetId}`, { method: "DELETE" });
      toast.toastSuccess("已删除预设");
      setSelectedPreset(null);
      setBlocks([]);
      setDrafts({});
      setSelectedPresetId(null);
      await reloadAll();
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setBusy(false);
    }
  }, [confirm, reloadAll, selectedPreset, selectedPresetId, toast]);

  const enableRecommendedDefaults = useCallback(async () => {
    if (!projectId) return;
    const outline = presets.find((p) => p.name === RECOMMENDED_OUTLINE_PRESET_NAME);
    const chapter = presets.find((p) => p.name === RECOMMENDED_CHAPTER_PRESET_NAME);
    if (!outline || !chapter) {
      toast.toastError("未找到推荐预设，请刷新后重试");
      return;
    }

    setBusy(true);
    try {
      const outlineActive = new Set(outline.active_for ?? []);
      outlineActive.add("outline_generate");
      await apiJson<{ preset: PromptPreset }>(`/api/prompt_presets/${outline.id}`, {
        method: "PUT",
        body: JSON.stringify({ name: null, active_for: [...outlineActive] }),
      });

      const chapterActive = new Set(chapter.active_for ?? []);
      chapterActive.add("chapter_generate");
      await apiJson<{ preset: PromptPreset }>(`/api/prompt_presets/${chapter.id}`, {
        method: "PUT",
        body: JSON.stringify({ name: null, active_for: [...chapterActive] }),
      });

      toast.toastSuccess("已启用推荐预设：大纲/章节");
      await reloadAll();
      setSelectedPresetId(chapter.id);
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setBusy(false);
    }
  }, [presets, projectId, reloadAll, toast]);

  const savePreset = useCallback(async () => {
    if (!selectedPresetId) return;
    setBusy(true);
    try {
      const res = await apiJson<{ preset: PromptPreset }>(`/api/prompt_presets/${selectedPresetId}`, {
        method: "PUT",
        body: JSON.stringify({
          name: presetDraftName.trim() || null,
          active_for: presetDraftActiveFor,
        }),
      });
      setSelectedPreset(res.data.preset);
      await reloadAll();
      toast.toastSuccess("已保存预设");
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setBusy(false);
    }
  }, [presetDraftActiveFor, presetDraftName, reloadAll, selectedPresetId, toast]);

  const addBlock = useCallback(async () => {
    if (!selectedPresetId) return;
    setBusy(true);
    try {
      const idx = blocks.length + 1;
      const identifier = `block.${Date.now()}.${idx}`;
      const res = await apiJson<{ block: PromptBlock }>(`/api/prompt_presets/${selectedPresetId}/blocks`, {
        method: "POST",
        body: JSON.stringify({
          identifier,
          name: `New block ${idx}`,
          role: "system",
          enabled: true,
          template: "",
          marker_key: null,
          injection_position: "relative",
          injection_depth: null,
          injection_order: blocks.length,
          triggers: [],
          forbid_overrides: false,
          budget: {},
          cache: {},
        }),
      });
      const next = [...blocks, res.data.block];
      setBlocks(next);
      setDrafts((prev) => ({
        ...prev,
        [res.data.block.id]: {
          identifier: res.data.block.identifier,
          name: res.data.block.name,
          role: res.data.block.role,
          enabled: res.data.block.enabled,
          template: res.data.block.template ?? "",
          marker_key: res.data.block.marker_key ?? "",
          triggers: formatTriggers(res.data.block.triggers ?? []),
        },
      }));
      toast.toastSuccess("已添加块");
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setBusy(false);
    }
  }, [blocks, selectedPresetId, toast]);

  const saveBlock = useCallback(
    async (blockId: string) => {
      const draft = drafts[blockId];
      if (!draft) return;
      setBusy(true);
      try {
        const res = await apiJson<{ block: PromptBlock }>(`/api/prompt_blocks/${blockId}`, {
          method: "PUT",
          body: JSON.stringify({
            identifier: draft.identifier.trim() || null,
            name: draft.name.trim() || null,
            role: draft.role,
            enabled: draft.enabled,
            template: draft.template,
            marker_key: draft.marker_key.trim() || null,
            triggers: parseTriggers(draft.triggers),
          }),
        });
        setBlocks((prev) => prev.map((b) => (b.id === blockId ? res.data.block : b)));
        setDrafts((prev) => ({
          ...prev,
          [blockId]: {
            identifier: res.data.block.identifier,
            name: res.data.block.name,
            role: res.data.block.role,
            enabled: res.data.block.enabled,
            template: res.data.block.template ?? "",
            marker_key: res.data.block.marker_key ?? "",
            triggers: formatTriggers(res.data.block.triggers ?? []),
          },
        }));
        toast.toastSuccess("已保存块");
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setBusy(false);
      }
    },
    [drafts, toast],
  );

  const deleteBlock = useCallback(
    async (blockId: string) => {
      const b = blocks.find((x) => x.id === blockId);
      const ok = await confirm.confirm({
        title: "删除块？",
        description: b ? `将删除提示块“${b.name}”。该操作不可撤销。` : "将删除该提示块。",
        confirmText: "删除",
        danger: true,
      });
      if (!ok) return;

      setBusy(true);
      try {
        await apiJson<Record<string, never>>(`/api/prompt_blocks/${blockId}`, { method: "DELETE" });
        setBlocks((prev) => prev.filter((x) => x.id !== blockId));
        setDrafts((prev) => {
          const next = { ...prev };
          delete next[blockId];
          return next;
        });
        toast.toastSuccess("已删除块");
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setBusy(false);
      }
    },
    [blocks, confirm, toast],
  );

  const onReorder = useCallback(
    async (orderedIds: string[]) => {
      if (!selectedPresetId) return;
      setBusy(true);
      try {
        const res = await apiJson<{ blocks: PromptBlock[] }>(`/api/prompt_presets/${selectedPresetId}/blocks/reorder`, {
          method: "POST",
          body: JSON.stringify({ ordered_block_ids: orderedIds }),
        });
        setBlocks(res.data.blocks ?? []);
        toast.toastSuccess("已更新排序");
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setBusy(false);
      }
    },
    [selectedPresetId, toast],
  );

  const dragIdRef = useRef<string | null>(null);

  const exportPreset = useCallback(async () => {
    if (!selectedPresetId || !selectedPreset) return;
    setBusy(true);
    try {
      const res = await apiJson<{ export: unknown }>(`/api/prompt_presets/${selectedPresetId}/export`);
      const jsonText = JSON.stringify(res.data.export, null, 2);
      const blob = new Blob([jsonText], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${selectedPreset.name}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.toastSuccess("已导出");
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setBusy(false);
    }
  }, [selectedPreset, selectedPresetId, toast]);

  const importPreset = useCallback(
    async (file: File) => {
      if (!projectId) return;
      setImportBusy(true);
      try {
        const text = await file.text();
        const obj = JSON.parse(text) as unknown;
        await apiJson<{ preset: PromptPreset }>(`/api/projects/${projectId}/prompt_presets/import`, {
          method: "POST",
          body: JSON.stringify(obj),
        });
        toast.toastSuccess("已导入");
        await reloadAll();
      } catch (e) {
        if (e instanceof SyntaxError) {
          toast.toastError("导入失败：不是合法 JSON");
          return;
        }
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setImportBusy(false);
      }
    },
    [projectId, reloadAll, toast],
  );

  const runPreview = useCallback(async () => {
    if (!projectId || !selectedPresetId) return;
    setPreviewLoading(true);
    try {
      const res = await apiJson<{ preview: PromptPreview }>(`/api/projects/${projectId}/prompt_preview`, {
        method: "POST",
        body: JSON.stringify({ task: previewTask, preset_id: selectedPresetId, values: previewValues }),
      });
      setPreview(res.data.preview);
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setPreviewLoading(false);
    }
  }, [previewTask, previewValues, projectId, selectedPresetId, toast]);

  const tasks = useMemo(
    () => [
      { key: "outline_generate", label: "outline_generate（大纲）" },
      { key: "chapter_generate", label: "chapter_generate（章节）" },
      { key: "plan_chapter", label: "plan_chapter（规划，M3）" },
      { key: "post_edit", label: "post_edit（润色，M3）" },
    ],
    [],
  );

  if (!projectId) return <div className="text-subtext">缺少 projectId</div>;
  if (loading) return <div className="text-subtext">加载中...</div>;

  const migrated = isMigratedPreset(selectedPreset);

  return (
    <div className="grid gap-6">
      <div className="rounded-atelier border border-border bg-canvas p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-lg font-semibold">Prompt Studio（beta）</div>
            <div className="text-xs text-subtext">
              预览通过后端渲染接口生成。{" "}
              <Link className="underline" to={`/projects/${projectId}/prompts`}>
                返回旧 Prompts 页
              </Link>
            </div>
          </div>
          <div className="text-xs text-subtext">{busy || importBusy ? "处理中…" : ""}</div>
        </div>

        <div className="mt-3 grid gap-1 text-sm text-subtext">
          <div>
            <span className="font-medium text-ink">预设（Preset）</span>：一套“提示蓝图”，通过{" "}
            <span className="font-medium text-ink">active_for</span> 决定哪些任务使用它（大纲/章节/规划/润色）。
          </div>
          <div>
            <span className="font-medium text-ink">提示块（Block）</span>：可排序/启停，支持 role、triggers（按任务触发）、token 预算与后端统一渲染。
          </div>
          <div>
            若同一任务被多个预设勾选，系统会优先使用“最近更新”的非迁移预设；{" "}
            <span className="font-medium text-ink">[Migrated] prompt_templates</span> 是旧 Prompts 页兼容用（不建议作为新项目主力）。
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm hover:bg-surface/60 disabled:opacity-50"
            onClick={() => void enableRecommendedDefaults()}
            disabled={busy || importBusy}
            type="button"
          >
            一键启用推荐预设（大纲/章节）
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px,1fr]">
        <div className="rounded-atelier border border-border bg-canvas p-4 shadow-sm">
          <div className="mb-3 text-sm font-semibold">预设</div>
          <div className="grid gap-2">
            <div className="flex gap-2">
              <input
                className="w-full rounded-atelier border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-ink/50"
                placeholder="新预设名称"
                value={newPresetName}
                onChange={(e) => setNewPresetName(e.target.value)}
                disabled={busy}
              />
              <button
                className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm hover:bg-surface/60 disabled:opacity-50"
                onClick={() => void createPreset()}
                disabled={busy}
              >
                新建
              </button>
            </div>

            <div className="flex gap-2">
              <input
                ref={importInputRef}
                type="file"
                accept="application/json"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void importPreset(file);
                  if (importInputRef.current) importInputRef.current.value = "";
                }}
              />
              <button
                className="w-full rounded-atelier border border-border bg-surface px-3 py-2 text-sm hover:bg-surface/60 disabled:opacity-50"
                onClick={() => importInputRef.current?.click()}
                disabled={importBusy || busy}
              >
                导入
              </button>
              <button
                className="w-full rounded-atelier border border-border bg-surface px-3 py-2 text-sm hover:bg-surface/60 disabled:opacity-50"
                onClick={() => void exportPreset()}
                disabled={busy || !selectedPresetId}
              >
                导出
              </button>
            </div>

            <div className="mt-2 grid gap-1">
              {presets.map((p) => {
                const active = p.id === selectedPresetId;
                return (
                  <button
                    key={p.id}
                    className={`w-full rounded-atelier border px-3 py-2 text-left text-sm ${
                      active
                        ? "border-ink/40 bg-surface text-ink"
                        : "border-border bg-surface/50 text-subtext hover:bg-surface"
                    }`}
                    onClick={() => setSelectedPresetId(p.id)}
                    type="button"
                  >
                    <div className="truncate">{p.name}</div>
                    <div className="mt-1 text-xs opacity-80">{(p.active_for ?? []).join(", ") || "—"}</div>
                  </button>
                );
              })}
            </div>

            <div className="mt-2 text-xs text-subtext">
              {migrated ? "当前选中迁移预设：只读（保证旧 Prompts 无感兼容）。" : "拖拽块可调整排序；预览走后端渲染。"}
            </div>
          </div>
        </div>

        <div className="grid gap-6">
          <div className="rounded-atelier border border-border bg-canvas p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-sm font-semibold">预设设置</div>
              <div className="flex gap-2">
                <button
                  className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm hover:bg-surface/60 disabled:opacity-50"
                  onClick={() => void savePreset()}
                  disabled={busy || !selectedPresetId || migrated}
                  type="button"
                >
                  保存预设
                </button>
                <button
                  className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm hover:bg-surface/60 disabled:opacity-50"
                  onClick={() => void deletePreset()}
                  disabled={busy || !selectedPresetId || migrated}
                  title={migrated ? "迁移预设在 M0/M1 阶段不允许删除" : undefined}
                  type="button"
                >
                  删除预设
                </button>
              </div>
            </div>

            <div className="grid gap-4">
              <div className="grid gap-2">
                <div className="text-xs text-subtext">名称</div>
                <input
                  className="w-full rounded-atelier border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-ink/50 disabled:opacity-60"
                  value={presetDraftName}
                  onChange={(e) => setPresetDraftName(e.target.value)}
                  disabled={busy || migrated}
                />
              </div>

              <div className="grid gap-2">
                <div className="text-xs text-subtext">active_for（哪些任务使用该预设）</div>
                <div className="flex flex-wrap gap-2">
                  {tasks.map((t) => {
                    const checked = presetDraftActiveFor.includes(t.key);
                    return (
                      <label
                        key={t.key}
                        className="flex items-center gap-2 rounded-atelier border border-border bg-surface px-3 py-2 text-sm"
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={busy || migrated}
                          onChange={(e) => {
                            const next = new Set(presetDraftActiveFor);
                            if (e.target.checked) next.add(t.key);
                            else next.delete(t.key);
                            setPresetDraftActiveFor([...next]);
                          }}
                        />
                        <span>{t.label}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-atelier border border-border bg-canvas p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-sm font-semibold">提示块</div>
              <button
                className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm hover:bg-surface/60 disabled:opacity-50"
                onClick={() => void addBlock()}
                disabled={busy || !selectedPresetId || migrated}
                title={migrated ? "迁移预设只读" : undefined}
                type="button"
              >
                添加块
              </button>
            </div>

            <div className="grid gap-3">
              {blocks.length === 0 ? <div className="text-sm text-subtext">暂无块</div> : null}
              {blocks.map((b, idx) => {
                const d = drafts[b.id];
                const enabled = d?.enabled ?? b.enabled;
                const role = d?.role ?? b.role;
                const identifier = d?.identifier ?? b.identifier;
                const name = d?.name ?? b.name;
                const triggers = d?.triggers ?? formatTriggers(b.triggers ?? []);
                const markerKey = d?.marker_key ?? (b.marker_key ?? "");
                const template = d?.template ?? (b.template ?? "");

                return (
                  <div
                    key={b.id}
                    className="rounded-atelier border border-border bg-surface p-3"
                    draggable={!migrated}
                    onDragStart={() => {
                      dragIdRef.current = b.id;
                    }}
                    onDragOver={(e) => {
                      if (migrated) return;
                      e.preventDefault();
                    }}
                    onDrop={() => {
                      if (migrated) return;
                      const fromId = dragIdRef.current;
                      dragIdRef.current = null;
                      if (!fromId || fromId === b.id) return;
                      const ids = blocks.map((x) => x.id);
                      const fromIdx = ids.indexOf(fromId);
                      const toIdx = ids.indexOf(b.id);
                      if (fromIdx < 0 || toIdx < 0) return;
                      ids.splice(fromIdx, 1);
                      ids.splice(toIdx, 0, fromId);
                      void onReorder(ids);
                    }}
                    title={migrated ? undefined : "拖拽可调整排序"}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="select-none text-subtext">{migrated ? "#" : "≡"}</span>
                        <span className="text-xs text-subtext">#{idx + 1}</span>
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            type="checkbox"
                            checked={enabled}
                            disabled={busy || migrated}
                            onChange={(e) =>
                              setDrafts((prev) => ({
                                ...prev,
                                [b.id]: {
                                  identifier,
                                  name,
                                  role,
                                  enabled: e.target.checked,
                                  template,
                                  marker_key: markerKey,
                                  triggers,
                                },
                              }))
                            }
                          />
                          <span className="font-semibold">{name}</span>
                        </label>
                      </div>
                      <div className="flex gap-2">
                        <button
                          className="rounded-atelier border border-border bg-canvas px-3 py-1 text-sm hover:bg-canvas/60 disabled:opacity-50"
                          onClick={() => void saveBlock(b.id)}
                          disabled={busy || migrated}
                          type="button"
                        >
                          保存
                        </button>
                        <button
                          className="rounded-atelier border border-border bg-canvas px-3 py-1 text-sm hover:bg-canvas/60 disabled:opacity-50"
                          onClick={() => void deleteBlock(b.id)}
                          disabled={busy || migrated}
                          type="button"
                        >
                          删除
                        </button>
                      </div>
                    </div>

                    <div className="mt-3 grid gap-3">
                      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                        <div className="grid gap-1">
                          <div className="text-xs text-subtext">identifier</div>
                          <input
                            className="w-full rounded-atelier border border-border bg-canvas px-3 py-2 text-sm outline-none focus:border-ink/50 disabled:opacity-60"
                            value={identifier}
                            disabled={busy || migrated}
                            onChange={(e) =>
                              setDrafts((prev) => ({
                                ...prev,
                                [b.id]: {
                                  identifier: e.target.value,
                                  name,
                                  role,
                                  enabled,
                                  template,
                                  marker_key: markerKey,
                                  triggers,
                                },
                              }))
                            }
                          />
                        </div>
                        <div className="grid gap-1">
                          <div className="text-xs text-subtext">role</div>
                          <select
                            className="w-full rounded-atelier border border-border bg-canvas px-3 py-2 text-sm outline-none focus:border-ink/50 disabled:opacity-60"
                            value={role}
                            disabled={busy || migrated}
                            onChange={(e) =>
                              setDrafts((prev) => ({
                                ...prev,
                                [b.id]: {
                                  identifier,
                                  name,
                                  role: e.target.value,
                                  enabled,
                                  template,
                                  marker_key: markerKey,
                                  triggers,
                                },
                              }))
                            }
                          >
                            <option value="system">system</option>
                            <option value="user">user</option>
                            <option value="assistant">assistant</option>
                            <option value="tool">tool</option>
                          </select>
                        </div>
                      </div>

                      <div className="grid gap-1">
                        <div className="text-xs text-subtext">name</div>
                        <input
                          className="w-full rounded-atelier border border-border bg-canvas px-3 py-2 text-sm outline-none focus:border-ink/50 disabled:opacity-60"
                          value={name}
                          disabled={busy || migrated}
                          onChange={(e) =>
                            setDrafts((prev) => ({
                              ...prev,
                              [b.id]: {
                                identifier,
                                name: e.target.value,
                                role,
                                enabled,
                                template,
                                marker_key: markerKey,
                                triggers,
                              },
                            }))
                          }
                        />
                      </div>

                      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                        <div className="grid gap-1">
                          <div className="text-xs text-subtext">triggers（逗号分隔，可空）</div>
                          <input
                            className="w-full rounded-atelier border border-border bg-canvas px-3 py-2 text-sm outline-none focus:border-ink/50 disabled:opacity-60"
                            value={triggers}
                            disabled={busy || migrated}
                            onChange={(e) =>
                              setDrafts((prev) => ({
                                ...prev,
                                [b.id]: {
                                  identifier,
                                  name,
                                  role,
                                  enabled,
                                  template,
                                  marker_key: markerKey,
                                  triggers: e.target.value,
                                },
                              }))
                            }
                            placeholder="chapter_generate, outline_generate"
                          />
                        </div>
                        <div className="grid gap-1">
                          <div className="text-xs text-subtext">marker_key（可空）</div>
                          <input
                            className="w-full rounded-atelier border border-border bg-canvas px-3 py-2 text-sm outline-none focus:border-ink/50 disabled:opacity-60"
                            value={markerKey}
                            disabled={busy || migrated}
                            onChange={(e) =>
                              setDrafts((prev) => ({
                                ...prev,
                                [b.id]: {
                                  identifier,
                                  name,
                                  role,
                                  enabled,
                                  template,
                                  marker_key: e.target.value,
                                  triggers,
                                },
                              }))
                            }
                            placeholder="story.outline / user.instruction / ..."
                          />
                        </div>
                      </div>

                      <div className="grid gap-1">
                        <div className="text-xs text-subtext">template</div>
                        <textarea
                          className="min-h-[140px] w-full resize-y rounded-atelier border border-border bg-canvas px-3 py-2 font-mono text-xs outline-none focus:border-ink/50 disabled:opacity-60"
                          value={template}
                          disabled={busy || migrated}
                          onChange={(e) =>
                            setDrafts((prev) => ({
                              ...prev,
                              [b.id]: {
                                identifier,
                                name,
                                role,
                                enabled,
                                template: e.target.value,
                                marker_key: markerKey,
                                triggers,
                              },
                            }))
                          }
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="rounded-atelier border border-border bg-canvas p-4 shadow-sm">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div className="text-sm font-semibold">预览（后端渲染）</div>
              <div className="flex gap-2">
                <select
                  className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm outline-none focus:border-ink/50"
                  value={previewTask}
                  onChange={(e) => setPreviewTask(e.target.value)}
                  disabled={busy}
                >
                  {tasks.map((t) => (
                    <option key={t.key} value={t.key}>
                      {t.key}
                    </option>
                  ))}
                </select>
                <button
                  className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm hover:bg-surface/60 disabled:opacity-50"
                  onClick={() => void runPreview()}
                  disabled={previewLoading || busy || !selectedPresetId}
                  type="button"
                >
                  {previewLoading ? "渲染中…" : "渲染预览"}
                </button>
              </div>
            </div>

            {preview ? (
              <div className="grid gap-3">
                {preview.missing?.length ? (
                  <div className="rounded-atelier border border-border bg-surface/50 p-3 text-xs">
                    <div className="font-semibold">缺失变量</div>
                    <div className="mt-1 text-subtext">{preview.missing.join(", ")}</div>
                  </div>
                ) : null}

                <div className="rounded-atelier border border-border bg-surface/50 p-3 text-xs">
                  <div className="font-semibold">Token 估算</div>
                  <div className="mt-1 text-subtext">
                    总计：{preview.prompt_tokens_estimate ?? 0}
                    {preview.prompt_budget_tokens ? ` / 预算：${preview.prompt_budget_tokens}` : ""}
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  <div className="grid gap-1">
                    <div className="text-xs text-subtext">system</div>
                    <textarea
                      readOnly
                      className="min-h-[180px] w-full resize-y rounded-atelier border border-border bg-surface px-3 py-2 font-mono text-xs"
                      value={preview.system}
                    />
                  </div>
                  <div className="grid gap-1">
                    <div className="text-xs text-subtext">user</div>
                    <textarea
                      readOnly
                      className="min-h-[180px] w-full resize-y rounded-atelier border border-border bg-surface px-3 py-2 font-mono text-xs"
                      value={preview.user}
                    />
                  </div>
                </div>

                <details className="rounded-atelier border border-border bg-surface/50 p-3">
                  <summary className="cursor-pointer text-sm">查看分块渲染结果</summary>
                  <div className="mt-3 grid gap-2">
                    {(preview.blocks ?? []).map((pb) => (
                      <div key={pb.id} className="rounded-atelier border border-border bg-canvas p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="text-sm font-semibold">
                            {pb.identifier} <span className="text-xs text-subtext">({pb.role})</span>
                          </div>
                          <div className="text-xs text-subtext">
                            tokens≈{pb.token_estimate ?? 0}
                            {pb.missing?.length ? ` · missing: ${pb.missing.join(", ")}` : ""}
                          </div>
                        </div>
                        <pre className="mt-2 max-h-[260px] overflow-auto whitespace-pre-wrap break-words rounded-atelier border border-border bg-surface p-3 text-xs">
                          {pb.text}
                        </pre>
                      </div>
                    ))}
                  </div>
                </details>
              </div>
            ) : (
              <div className="text-sm text-subtext">选择任务并点击“渲染预览”。</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
