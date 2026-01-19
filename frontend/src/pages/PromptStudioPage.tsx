import clsx from "clsx";
import { LayoutGroup, motion, useReducedMotion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useConfirm } from "../components/ui/confirm";
import { useToast } from "../components/ui/toast";
import { transition } from "../lib/motion";
import { ApiError, apiJson, sanitizeFilename } from "../services/apiClient";
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
  return chars.map((c) => `- ${c.name}${c.role ? `（${c.role}）` : ""}`).join("\n");
}

function guessPreviewValues(args: {
  project: Project | null;
  settings: ProjectSettings | null;
  outline: Outline | null;
  characters: Character[];
}): Record<string, unknown> {
  const projectName = args.project?.name ?? "";
  const genre = args.project?.genre ?? "";
  const logline = args.project?.logline ?? "";
  const worldSetting = args.settings?.world_setting ?? "";
  const styleGuide = args.settings?.style_guide ?? "";
  const constraints = args.settings?.constraints ?? "";
  const charactersText = formatCharacters(args.characters);
  const outlineText = args.outline?.content_md ?? "";

  const chapterNumber = 1;
  const chapterTitle = "第一章";
  const chapterPlan = "（示例要点）";
  const chapterSummary = "（示例摘要）";
  const instruction = "（示例指令）";
  const previousChapter = "（示例上一章摘要）";
  const targetWordCount = 2500;
  const rawContent = "（示例已生成正文，用于 post_edit 预览）";
  const chapterContentMd = "（示例章节正文，用于 chapter_analyze / chapter_rewrite）";
  const planText = "（示例规划，可用于 plan_first 注入）";
  const analysisJson = JSON.stringify(
    {
      chapter_summary: "（示例分析摘要）",
      hooks: [{ excerpt: "（示例 excerpt）", note: "（示例 hook 备注）" }],
      foreshadows: [],
      plot_points: [{ beat: "（示例情节点）", excerpt: "（示例 excerpt）" }],
      suggestions: [
        {
          title: "（示例建议）",
          excerpt: "（示例 excerpt）",
          issue: "（示例问题）",
          recommendation: "（示例建议）",
          priority: "medium",
        },
      ],
      overall_notes: "",
    },
    null,
    2,
  );
  const requirementsObj = { chapter_count: 12 };

  const values: Record<string, unknown> = {
    project_name: projectName,
    genre,
    logline,
    world_setting: worldSetting,
    style_guide: styleGuide,
    constraints,
    characters: charactersText,
    outline: outlineText,
    chapter_number: String(chapterNumber),
    chapter_title: chapterTitle,
    chapter_plan: chapterPlan,
    chapter_summary: chapterSummary,
    chapter_content_md: chapterContentMd,
    analysis_json: analysisJson,
    requirements: JSON.stringify(requirementsObj, null, 2),
    instruction,
    previous_chapter: previousChapter,
    target_word_count: String(targetWordCount),
    raw_content: rawContent,
    story_plan: planText,
    smart_context_recent_summaries: "（示例 smart_context_recent_summaries）",
    smart_context_recent_full: "（示例 smart_context_recent_full）",
    smart_context_story_skeleton: "（示例 smart_context_story_skeleton）",
  };

  values.project = {
    name: projectName,
    genre,
    logline,
    world_setting: worldSetting,
    style_guide: styleGuide,
    constraints,
    characters: charactersText,
  };
  values.story = {
    outline: outlineText,
    chapter_number: chapterNumber,
    chapter_title: chapterTitle,
    chapter_plan: chapterPlan,
    chapter_summary: chapterSummary,
    previous_chapter: previousChapter,
    plan: planText,
    raw_content: rawContent,
    chapter_content_md: chapterContentMd,
    analysis_json: analysisJson,
    smart_context_recent_summaries: "（示例 smart_context_recent_summaries）",
    smart_context_recent_full: "（示例 smart_context_recent_full）",
    smart_context_story_skeleton: "（示例 smart_context_story_skeleton）",
  };
  values.user = { instruction, requirements: requirementsObj };

  return values;
}

export function PromptStudioPage() {
  const { projectId } = useParams();
  const toast = useToast();
  const confirm = useConfirm();
  const reduceMotion = useReducedMotion();

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
  const [bulkBusy, setBulkBusy] = useState(false);
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const importAllInputRef = useRef<HTMLInputElement | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<string>("__all__");

  const [previewTask, setPreviewTask] = useState<string>("chapter_generate");
  const [preview, setPreview] = useState<PromptPreview | null>(null);
  const [renderLog, setRenderLog] = useState<unknown | null>(null);
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

  type ImportAllReport = {
    dry_run: boolean;
    created: number;
    updated: number;
    skipped: number;
    conflicts: unknown[];
    actions: unknown[];
  };

  const formatImportAllReport = useCallback((report: ImportAllReport): string => {
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
  }, []);

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
      const safeName = sanitizeFilename(selectedPreset.name) || "prompt_preset";
      a.download = `${safeName}.json`;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.toastSuccess("已导出");
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setBusy(false);
    }
  }, [selectedPreset, selectedPresetId, toast]);

  const exportAllPresets = useCallback(async () => {
    if (!projectId) return;
    setBulkBusy(true);
    try {
      const res = await apiJson<{ export: unknown }>(`/api/projects/${projectId}/prompt_presets/export_all`);
      const jsonText = JSON.stringify(res.data.export, null, 2);
      const blob = new Blob([jsonText], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const safeName = sanitizeFilename(project?.name || "prompt_presets_all") || "prompt_presets_all";
      const stamp = new Date().toISOString().replaceAll(":", "-").replaceAll(".", "-");
      a.download = `${safeName}_${stamp}.json`;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.toastSuccess("已导出整套");
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setBulkBusy(false);
    }
  }, [project?.name, projectId, toast]);

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

  const importAllPresets = useCallback(
    async (file: File) => {
      if (!projectId) return;
      setBulkBusy(true);
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
        await reloadAll();
      } catch (e) {
        if (e instanceof SyntaxError) {
          toast.toastError("导入失败：不是合法 JSON");
          return;
        }
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setBulkBusy(false);
      }
    },
    [confirm, formatImportAllReport, projectId, reloadAll, toast],
  );

  const runPreview = useCallback(async () => {
    if (!projectId || !selectedPresetId) return;
    setPreviewLoading(true);
    try {
      const res = await apiJson<{ preview: PromptPreview; render_log?: unknown }>(
        `/api/projects/${projectId}/prompt_preview`,
        {
          method: "POST",
          body: JSON.stringify({ task: previewTask, preset_id: selectedPresetId, values: previewValues }),
        },
      );
      setPreview(res.data.preview);
      setRenderLog(res.data.render_log ?? null);
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setPreviewLoading(false);
    }
  }, [previewTask, previewValues, projectId, selectedPresetId, toast]);

  const templateErrors = useMemo(() => {
    const blocks = (renderLog as { blocks?: unknown } | null)?.blocks;
    if (!Array.isArray(blocks)) return [];
    return blocks
      .map((b) => b as { identifier?: unknown; render_error?: unknown })
      .filter((b) => typeof b.render_error === "string" && b.render_error.trim())
      .map((b) => ({ identifier: String(b.identifier ?? ""), error: String(b.render_error ?? "") }))
      .filter((b) => b.identifier && b.error);
  }, [renderLog]);

  const tasks = useMemo(
    () => [
      { key: "outline_generate", label: "outline_generate（大纲）" },
      { key: "chapter_generate", label: "chapter_generate（章节）" },
      { key: "plan_chapter", label: "plan_chapter（规划，M3）" },
      { key: "post_edit", label: "post_edit（润色，M3）" },
      { key: "chapter_analyze", label: "chapter_analyze（章节分析，P2）" },
      { key: "chapter_rewrite", label: "chapter_rewrite（章节重写，P2）" },
    ],
    [],
  );

  const presetCategoryGroups = useMemo(() => {
    const groups = new Map<string, PromptPreset[]>();
    for (const p of presets) {
      const key = String(p.category ?? "").trim() || "（未分类）";
      const list = groups.get(key) ?? [];
      list.push(p);
      groups.set(key, list);
    }
    const ordered = [...groups.entries()];
    ordered.sort((a, b) => a[0].localeCompare(b[0]));
    return ordered;
  }, [presets]);

  const visiblePresetCategoryGroups = useMemo(() => {
    if (categoryFilter === "__all__") return presetCategoryGroups;
    return presetCategoryGroups.filter(([key]) => key === categoryFilter);
  }, [categoryFilter, presetCategoryGroups]);

  useEffect(() => {
    if (categoryFilter === "__all__") return;
    if (presetCategoryGroups.some(([key]) => key === categoryFilter)) return;
    setCategoryFilter("__all__");
  }, [categoryFilter, presetCategoryGroups]);

  const showCategoryHeaders = categoryFilter === "__all__";

  if (!projectId) return <div className="text-subtext">缺少 projectId</div>;
  if (loading) return <div className="text-subtext">加载中...</div>;

  return (
    <div className="grid gap-6">
      <div className="panel p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-lg font-semibold">Prompt Studio（beta）</div>
            <div className="text-xs text-subtext">
              预览通过后端渲染接口生成。{" "}
              <Link className="underline" to={`/projects/${projectId}/prompts`}>
                返回模型配置
              </Link>
            </div>
          </div>
          <div className="text-xs text-subtext">{busy || importBusy || bulkBusy ? "处理中…" : ""}</div>
        </div>

        <div className="mt-3 grid gap-1 text-sm text-subtext">
          <div>
            <span className="font-medium text-ink">预设（Preset）</span>：一套“提示蓝图”，通过{" "}
            <span className="font-medium text-ink">active_for</span> 决定哪些任务使用它（大纲/章节/规划/润色）。
          </div>
          <div>
            <span className="font-medium text-ink">提示块（Block）</span>：可排序/启停，支持
            role、triggers（按任务触发）、token 预算与后端统一渲染。
          </div>
          <div>若同一任务被多个预设勾选，系统会优先使用“最近更新”的预设（历史导入的预设通常作为兜底）。</div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            className="btn btn-secondary"
            onClick={() => void enableRecommendedDefaults()}
            disabled={busy || importBusy}
            type="button"
          >
            一键启用推荐预设（大纲/章节）
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px,1fr]">
        <div className="panel p-4">
          <div className="mb-3 text-sm font-semibold">预设</div>
          <div className="grid gap-2">
            <div className="flex gap-2">
              <input
                className="input"
                placeholder="新预设名称"
                value={newPresetName}
                onChange={(e) => setNewPresetName(e.target.value)}
                disabled={busy}
              />
              <button className="btn btn-secondary" onClick={() => void createPreset()} disabled={busy}>
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
              <input
                ref={importAllInputRef}
                type="file"
                accept="application/json"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void importAllPresets(file);
                  if (importAllInputRef.current) importAllInputRef.current.value = "";
                }}
              />
              <button
                className="btn btn-secondary w-full"
                onClick={() => importInputRef.current?.click()}
                disabled={importBusy || busy}
              >
                导入
              </button>
              <button
                className="btn btn-secondary w-full"
                onClick={() => void exportPreset()}
                disabled={busy || !selectedPresetId}
              >
                导出
              </button>
            </div>

            <div className="flex gap-2">
              <button
                className="btn btn-secondary w-full"
                onClick={() => importAllInputRef.current?.click()}
                disabled={bulkBusy || importBusy || busy}
                type="button"
              >
                导入整套
              </button>
              <button className="btn btn-secondary w-full" onClick={() => void exportAllPresets()} disabled={bulkBusy || busy} type="button">
                导出整套
              </button>
            </div>

            <div className="grid gap-1">
              <div className="text-xs text-subtext">分类</div>
              <select
                className="input"
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.currentTarget.value)}
                disabled={busy || bulkBusy}
              >
                <option value="__all__">全部分类</option>
                {presetCategoryGroups.map(([key]) => (
                  <option key={key} value={key}>
                    {key}
                  </option>
                ))}
              </select>
            </div>

            <LayoutGroup id="promptstudio-presets">
              <div className="mt-2 grid gap-3">
                {visiblePresetCategoryGroups.length ? (
                  visiblePresetCategoryGroups.map(([category, items]) => (
                    <div key={category}>
                      {showCategoryHeaders ? <div className="text-xs text-subtext">{category}</div> : null}
                      <div className={clsx("grid gap-1", showCategoryHeaders ? "mt-1" : null)}>
                        {items.map((p) => {
                          const active = p.id === selectedPresetId;
                          return (
                            <button
                              key={p.id}
                              className={clsx(
                                "ui-focus-ring ui-transition-fast group relative w-full overflow-hidden rounded-atelier border px-3 py-2 text-left text-sm motion-safe:active:scale-[0.99]",
                                active
                                  ? "border-accent/40 text-ink"
                                  : "border-border text-subtext hover:bg-canvas hover:text-ink",
                              )}
                              onClick={() => setSelectedPresetId(p.id)}
                              type="button"
                            >
                              {active ? (
                                <motion.span
                                  layoutId="promptstudio-preset-active"
                                  className="absolute inset-0 rounded-atelier bg-canvas"
                                  transition={reduceMotion ? { duration: 0.01 } : transition.fast}
                                />
                              ) : null}
                              <div className="relative z-10 truncate">{p.name}</div>
                              <div className="relative z-10 mt-1 text-xs opacity-80">{(p.active_for ?? []).join(", ") || "—"}</div>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-xs text-subtext">暂无预设</div>
                )}
              </div>
            </LayoutGroup>

            <div className="mt-2 text-xs text-subtext">拖拽块可调整排序；预览走后端渲染。</div>
          </div>
        </div>

        <div className="grid gap-6">
          <div className="panel p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-sm font-semibold">预设设置</div>
              <div className="flex gap-2">
                <button
                  className="btn btn-primary"
                  onClick={() => void savePreset()}
                  disabled={busy || !selectedPresetId}
                  type="button"
                >
                  保存预设
                </button>
                <button
                  className="btn btn-ghost text-accent hover:bg-accent/10"
                  onClick={() => void deletePreset()}
                  disabled={busy || !selectedPresetId}
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
                  className="input"
                  value={presetDraftName}
                  onChange={(e) => setPresetDraftName(e.target.value)}
                  disabled={busy}
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
                        className={clsx(
                          "ui-transition-fast flex items-center gap-2 rounded-atelier border px-3 py-2 text-sm",
                          checked
                            ? "border-accent/40 bg-accent/10 text-ink"
                            : "border-border bg-canvas text-subtext hover:bg-surface hover:text-ink",
                          busy ? "opacity-60" : "cursor-pointer",
                        )}
                      >
                        <input
                          className="checkbox"
                          type="checkbox"
                          checked={checked}
                          disabled={busy}
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

          <div className="panel p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-sm font-semibold">提示块</div>
              <button
                className="btn btn-secondary"
                onClick={() => void addBlock()}
                disabled={busy || !selectedPresetId}
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
                const markerKey = d?.marker_key ?? b.marker_key ?? "";
                const template = d?.template ?? b.template ?? "";

                return (
                  <div
                    key={b.id}
                    className="surface p-3"
                    draggable
                    onDragStart={() => {
                      dragIdRef.current = b.id;
                    }}
                    onDragOver={(e) => {
                      e.preventDefault();
                    }}
                    onDrop={() => {
                      const fromId = dragIdRef.current;
                      dragIdRef.current = null;
                      if (!fromId || fromId === b.id) return;
                      const ids = blocks.map((x) => x.id);
                      const fromIdx = ids.indexOf(fromId);
                      const toIdx = ids.indexOf(b.id);
                      if (fromIdx < 0 || toIdx < 0) return;
                      ids.splice(fromIdx, 1);
                      const insertIdx = fromIdx < toIdx ? toIdx - 1 : toIdx;
                      ids.splice(insertIdx, 0, fromId);
                      void onReorder(ids);
                    }}
                    title="拖拽可调整排序"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="select-none text-subtext">≡</span>
                        <span className="text-xs text-subtext">#{idx + 1}</span>
                        <label className="flex items-center gap-2 text-sm">
                          <input
                            className="checkbox"
                            type="checkbox"
                            checked={enabled}
                            disabled={busy}
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
                          className="btn btn-secondary px-3 py-1 text-sm"
                          onClick={() => void saveBlock(b.id)}
                          disabled={busy}
                          type="button"
                        >
                          保存
                        </button>
                        <button
                          className="btn btn-ghost px-3 py-1 text-sm text-accent hover:bg-accent/10"
                          onClick={() => void deleteBlock(b.id)}
                          disabled={busy}
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
                            className="input"
                            value={identifier}
                            disabled={busy}
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
                            className="select"
                            value={role}
                            disabled={busy}
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
                          className="input"
                          value={name}
                          disabled={busy}
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
                            className="input"
                            value={triggers}
                            disabled={busy}
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
                            className="input"
                            value={markerKey}
                            disabled={busy}
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
                          className="textarea atelier-mono min-h-[140px] resize-y py-2 text-xs"
                          value={template}
                          disabled={busy}
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

          <div className="panel p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div className="text-sm font-semibold">预览（后端渲染）</div>
              <div className="flex gap-2">
                <select
                  className="select w-auto"
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
                  className="btn btn-secondary"
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
                {templateErrors.length ? (
                  <div className="rounded-atelier border border-border bg-surface/50 p-3 text-xs">
                    <div className="font-semibold">模板渲染错误</div>
                    <div className="mt-2 grid gap-1 text-subtext">
                      {templateErrors.map((item) => (
                        <div key={`${item.identifier}:${item.error}`}>
                          <span className="font-mono text-ink">{item.identifier}</span>
                          <span className="text-subtext">：{item.error}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

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

                {renderLog ? (
                  <details className="rounded-atelier border border-border bg-surface/50 p-3">
                    <summary className="ui-transition-fast cursor-pointer text-sm hover:text-ink">
                      查看 render_log（裁剪/原因/错误）
                    </summary>
                    <pre className="mt-2 max-h-[260px] overflow-auto whitespace-pre-wrap break-words rounded-atelier border border-border bg-surface p-3 text-xs">
                      {JSON.stringify(renderLog, null, 2)}
                    </pre>
                  </details>
                ) : null}

                <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                  <div className="grid gap-1">
                    <div className="text-xs text-subtext">system</div>
                    <textarea
                      readOnly
                      className="textarea atelier-mono min-h-[180px] resize-y bg-surface py-2 text-xs"
                      value={preview.system}
                    />
                  </div>
                  <div className="grid gap-1">
                    <div className="text-xs text-subtext">user</div>
                    <textarea
                      readOnly
                      className="textarea atelier-mono min-h-[180px] resize-y bg-surface py-2 text-xs"
                      value={preview.user}
                    />
                  </div>
                </div>

                <details className="rounded-atelier border border-border bg-surface/50 p-3">
                  <summary className="ui-transition-fast cursor-pointer text-sm hover:text-ink">
                    查看分块渲染结果
                  </summary>
                  <div className="mt-3 grid gap-2">
                    {(preview.blocks ?? []).map((pb) => (
                      <div key={pb.id} className="surface p-3">
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
