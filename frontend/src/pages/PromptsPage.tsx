import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { WizardNextBar } from "../components/atelier/WizardNextBar";
import { LlmPresetPanel } from "../components/prompts/LlmPresetPanel";
import { PromptTemplatesPanel } from "../components/prompts/PromptTemplatesPanel";
import type { LlmForm, PromptForm } from "../components/prompts/types";
import { useConfirm } from "../components/ui/confirm";
import { useToast } from "../components/ui/toast";
import { useSaveHotkey } from "../hooks/useSaveHotkey";
import { useUnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";
import { useWizardProgress } from "../hooks/useWizardProgress";
import { ApiError, apiJson } from "../services/apiClient";
import { markWizardLlmTestOk } from "../services/wizard";
import type { Character, LLMPreset, LLMProfile, Outline, Project, ProjectSettings, PromptTemplate } from "../types";

function parseNumber(value: string): number | null {
  const v = value.trim();
  if (!v) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function parseStopList(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  return trimmed
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function findPlaceholders(text: string): string[] {
  const re = /{{\s*([a-zA-Z0-9_]+)\s*}}/g;
  const found = new Set<string>();
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) found.add(m[1]);
  return [...found];
}

function renderTemplate(template: string, values: Record<string, string>): { text: string; missing: string[] } {
  const missing = new Set<string>();
  const text = template.replace(/{{\s*([a-zA-Z0-9_]+)\s*}}/g, (_, key: string) => {
    if (!(key in values)) {
      missing.add(key);
      return "";
    }
    return values[key] ?? "";
  });
  return { text, missing: [...missing].sort() };
}

function parseTimeoutSecondsForTest(value: string): number {
  const n = parseNumber(value);
  const i = Math.trunc(n ?? 90);
  if (i < 1) return 1;
  if (i > 1800) return 1800;
  return i;
}

function parseTimeoutSecondsForPreset(value: string): number | null {
  const n = parseNumber(value);
  if (n === null) return null;
  const i = Math.trunc(n);
  if (i < 1) return 1;
  if (i > 1800) return 1800;
  return i;
}

export function PromptsPage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirm();
  const wizard = useWizardProgress(projectId);
  const refreshWizard = wizard.refresh;
  const bumpWizardLocal = wizard.bumpLocal;

  const [loading, setLoading] = useState(true);
  const [savingPreset, setSavingPreset] = useState(false);
  const [savingPrompts, setSavingPrompts] = useState(false);
  const [testing, setTesting] = useState(false);

  const [project, setProject] = useState<Project | null>(null);
  const [settings, setSettings] = useState<ProjectSettings | null>(null);
  const [outline, setOutline] = useState<Outline | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [profiles, setProfiles] = useState<LLMProfile[]>([]);
  const [profileName, setProfileName] = useState("");
  const [profileBusy, setProfileBusy] = useState(false);

  const [baselinePreset, setBaselinePreset] = useState<LLMPreset | null>(null);
  const [baselinePrompts, setBaselinePrompts] = useState<PromptForm | null>(null);

  const [apiKey, setApiKey] = useState("");

  const [llmForm, setLlmForm] = useState<LlmForm>({
    provider: "openai",
    base_url: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    temperature: "0.7",
    top_p: "1",
    max_tokens: "32000",
    presence_penalty: "0",
    frequency_penalty: "0",
    top_k: "",
    stop: "",
    timeout_seconds: "90",
    extra: "{}",
  });

  const [promptForm, setPromptForm] = useState<PromptForm>({
    outline_generate: { system_template: "", user_template: "" },
    chapter_generate: { system_template: "", user_template: "" },
  });

  const reloadAll = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [presetRes, promptsRes, pRes, sRes, oRes, cRes, profilesRes] = await Promise.all([
        apiJson<{ llm_preset: LLMPreset }>(`/api/projects/${projectId}/llm_preset`),
        apiJson<{ templates: PromptTemplate[] }>(`/api/projects/${projectId}/prompts`),
        apiJson<{ project: Project }>(`/api/projects/${projectId}`),
        apiJson<{ settings: ProjectSettings }>(`/api/projects/${projectId}/settings`),
        apiJson<{ outline: Outline }>(`/api/projects/${projectId}/outline`),
        apiJson<{ characters: Character[] }>(`/api/projects/${projectId}/characters`),
        apiJson<{ profiles: LLMProfile[] }>(`/api/llm_profiles`),
      ]);

      setProject(pRes.data.project);
      setSettings(sRes.data.settings);
      setOutline(oRes.data.outline);
      setCharacters(cRes.data.characters);
      setProfiles(profilesRes.data.profiles ?? []);
      setProfileName("");

      setBaselinePreset(presetRes.data.llm_preset);
      setLlmForm({
        provider: presetRes.data.llm_preset.provider,
        base_url: presetRes.data.llm_preset.base_url ?? "",
        model: presetRes.data.llm_preset.model ?? "",
        temperature: presetRes.data.llm_preset.temperature?.toString() ?? "",
        top_p: presetRes.data.llm_preset.top_p?.toString() ?? "",
        max_tokens: presetRes.data.llm_preset.max_tokens?.toString() ?? "",
        presence_penalty: presetRes.data.llm_preset.presence_penalty?.toString() ?? "",
        frequency_penalty: presetRes.data.llm_preset.frequency_penalty?.toString() ?? "",
        top_k: presetRes.data.llm_preset.top_k?.toString() ?? "",
        stop: (presetRes.data.llm_preset.stop ?? []).join(", "),
        timeout_seconds: presetRes.data.llm_preset.timeout_seconds?.toString() ?? "",
        extra: JSON.stringify(presetRes.data.llm_preset.extra ?? {}, null, 2),
      });

      const byType = new Map(promptsRes.data.templates.map((t) => [t.type, t]));
      const pf: PromptForm = {
        outline_generate: {
          system_template: byType.get("outline_generate")?.system_template ?? "",
          user_template: byType.get("outline_generate")?.user_template ?? "",
        },
        chapter_generate: {
          system_template: byType.get("chapter_generate")?.system_template ?? "",
          user_template: byType.get("chapter_generate")?.user_template ?? "",
        },
      };
      setPromptForm(pf);
      setBaselinePrompts(pf);

      setApiKey("");
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    void reloadAll();
  }, [reloadAll]);

  useEffect(() => {
    setApiKey("");
  }, [llmForm.provider, project?.llm_profile_id]);

  const presetDirty = useMemo(() => {
    if (!baselinePreset) return false;
    const extraObj = (() => {
      try {
        return JSON.parse(llmForm.extra || "{}");
      } catch {
        return null;
      }
    })();
    if (!extraObj) return true;
    return (
      llmForm.provider !== baselinePreset.provider ||
      (llmForm.base_url || "") !== (baselinePreset.base_url ?? "") ||
      llmForm.model !== baselinePreset.model ||
      parseNumber(llmForm.temperature) !== (baselinePreset.temperature ?? null) ||
      parseNumber(llmForm.top_p) !== (baselinePreset.top_p ?? null) ||
      parseNumber(llmForm.max_tokens) !== (baselinePreset.max_tokens ?? null) ||
      parseNumber(llmForm.presence_penalty) !== (baselinePreset.presence_penalty ?? null) ||
      parseNumber(llmForm.frequency_penalty) !== (baselinePreset.frequency_penalty ?? null) ||
      parseNumber(llmForm.top_k) !== (baselinePreset.top_k ?? null) ||
      JSON.stringify(parseStopList(llmForm.stop)) !== JSON.stringify(baselinePreset.stop ?? []) ||
      parseNumber(llmForm.timeout_seconds) !== (baselinePreset.timeout_seconds ?? null) ||
      JSON.stringify(extraObj) !== JSON.stringify(baselinePreset.extra ?? {})
    );
  }, [baselinePreset, llmForm]);

  const promptsDirty = useMemo(() => {
    if (!baselinePrompts) return false;
    return (
      promptForm.outline_generate.system_template !== baselinePrompts.outline_generate.system_template ||
      promptForm.outline_generate.user_template !== baselinePrompts.outline_generate.user_template ||
      promptForm.chapter_generate.system_template !== baselinePrompts.chapter_generate.system_template ||
      promptForm.chapter_generate.user_template !== baselinePrompts.chapter_generate.user_template
    );
  }, [baselinePrompts, promptForm]);

  const dirty = presetDirty || promptsDirty;
  useUnsavedChangesGuard(dirty);

  const selectedProfileId = project?.llm_profile_id ?? null;
  const selectedProfile = selectedProfileId ? (profiles.find((p) => p.id === selectedProfileId) ?? null) : null;
  const lockConnectionFields = Boolean(selectedProfileId);

  const saveAll = useCallback(async (): Promise<boolean> => {
    if (!projectId) return false;
    if (!dirty) return true;

    const extraObj = (() => {
      try {
        return JSON.parse(llmForm.extra || "{}") as Record<string, unknown>;
      } catch {
        return null;
      }
    })();
    if (!extraObj) {
      toast.toastError("extra 不是合法 JSON");
      return false;
    }

    setSavingPreset(presetDirty);
    setSavingPrompts(promptsDirty);
    try {
      if (presetDirty) {
        const res = await apiJson<{ llm_preset: LLMPreset }>(`/api/projects/${projectId}/llm_preset`, {
          method: "PUT",
          body: JSON.stringify({
            provider: llmForm.provider,
            base_url: llmForm.base_url || null,
            model: llmForm.model,
            temperature: parseNumber(llmForm.temperature),
            top_p: parseNumber(llmForm.top_p),
            max_tokens: parseNumber(llmForm.max_tokens),
            presence_penalty: parseNumber(llmForm.presence_penalty),
            frequency_penalty: parseNumber(llmForm.frequency_penalty),
            top_k: parseNumber(llmForm.top_k),
            stop: parseStopList(llmForm.stop),
            timeout_seconds: parseTimeoutSecondsForPreset(llmForm.timeout_seconds),
            extra: extraObj,
          }),
        });
        setBaselinePreset(res.data.llm_preset);
      }

      if (promptsDirty) {
        const res = await apiJson<{ templates: PromptTemplate[] }>(`/api/projects/${projectId}/prompts`, {
          method: "PUT",
          body: JSON.stringify({
            templates: [
              { type: "outline_generate", ...promptForm.outline_generate },
              { type: "chapter_generate", ...promptForm.chapter_generate },
            ],
          }),
        });
        const byType = new Map(res.data.templates.map((t) => [t.type, t]));
        const pf: PromptForm = {
          outline_generate: {
            system_template:
              byType.get("outline_generate")?.system_template ?? promptForm.outline_generate.system_template,
            user_template: byType.get("outline_generate")?.user_template ?? promptForm.outline_generate.user_template,
          },
          chapter_generate: {
            system_template:
              byType.get("chapter_generate")?.system_template ?? promptForm.chapter_generate.system_template,
            user_template: byType.get("chapter_generate")?.user_template ?? promptForm.chapter_generate.user_template,
          },
        };
        setPromptForm(pf);
        setBaselinePrompts(pf);
      }

      toast.toastSuccess("已保存");
      await refreshWizard();
      return true;
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
      return false;
    } finally {
      setSavingPreset(false);
      setSavingPrompts(false);
    }
  }, [dirty, llmForm, presetDirty, projectId, promptForm, promptsDirty, refreshWizard, toast]);

  useSaveHotkey(() => void saveAll(), dirty);

  const selectProfile = useCallback(
    async (profileId: string | null) => {
      if (!projectId) return;
      if (profileBusy) return;
      if (profileId === selectedProfileId) return;

      if (dirty) {
        const choice = await confirm.choose({
          title: "当前有未保存修改，是否切换配置？",
          description: "切换后会刷新表单；建议先保存。",
          confirmText: "保存并切换",
          secondaryText: "不保存切换",
          cancelText: "取消",
        });
        if (choice === "cancel") return;
        if (choice === "confirm") {
          const ok = await saveAll();
          if (!ok) return;
        }
      }

      setProfileBusy(true);
      try {
        await apiJson<{ project: Project }>(`/api/projects/${projectId}`, {
          method: "PUT",
          body: JSON.stringify({ llm_profile_id: profileId }),
        });
        await reloadAll();
        await refreshWizard();
        toast.toastSuccess("已切换配置");
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setProfileBusy(false);
      }
    },
    [confirm, dirty, profileBusy, projectId, reloadAll, refreshWizard, saveAll, selectedProfileId, toast],
  );

  const createProfile = useCallback(async () => {
    if (!projectId) return;
    if (profileBusy) return;
    const name = profileName.trim();
    if (!name) {
      toast.toastError("请先填写“新建配置名”");
      return;
    }

    setProfileBusy(true);
    try {
      const apiKeyInput = apiKey.trim();
      const res = await apiJson<{ profile: LLMProfile }>(`/api/llm_profiles`, {
        method: "POST",
        body: JSON.stringify({
          name,
          provider: llmForm.provider,
          base_url: llmForm.base_url || null,
          model: llmForm.model,
          api_key: apiKeyInput ? apiKeyInput : undefined,
        }),
      });
      await apiJson<{ project: Project }>(`/api/projects/${projectId}`, {
        method: "PUT",
        body: JSON.stringify({ llm_profile_id: res.data.profile.id }),
      });
      setApiKey("");
      await reloadAll();
      await refreshWizard();
      toast.toastSuccess("已保存为新配置并应用到项目");
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setProfileBusy(false);
    }
  }, [
    apiKey,
    llmForm.base_url,
    llmForm.model,
    llmForm.provider,
    profileBusy,
    profileName,
    projectId,
    reloadAll,
    refreshWizard,
    toast,
  ]);

  const updateProfile = useCallback(async () => {
    if (!projectId) return;
    if (profileBusy) return;
    if (!selectedProfileId) {
      toast.toastError("请先选择一个后端配置");
      return;
    }
    const name = profileName.trim();
    setProfileBusy(true);
    try {
      await apiJson<{ profile: LLMProfile }>(`/api/llm_profiles/${selectedProfileId}`, {
        method: "PUT",
        body: JSON.stringify({
          name: name ? name : undefined,
          provider: llmForm.provider,
          base_url: llmForm.base_url || null,
          model: llmForm.model,
        }),
      });
      await reloadAll();
      toast.toastSuccess("已更新配置");
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setProfileBusy(false);
    }
  }, [
    llmForm.base_url,
    llmForm.model,
    llmForm.provider,
    profileBusy,
    profileName,
    projectId,
    reloadAll,
    selectedProfileId,
    toast,
  ]);

  const deleteProfile = useCallback(async () => {
    if (!selectedProfileId) {
      toast.toastError("请先选择一个后端配置");
      return;
    }
    if (profileBusy) return;

    const ok = await confirm.confirm({
      title: "删除当前后端配置？",
      description: "删除后不可恢复。项目将解除绑定，需要重新选择/新建配置并保存 Key。",
      confirmText: "删除",
      danger: true,
    });
    if (!ok) return;

    setProfileBusy(true);
    try {
      await apiJson<Record<string, never>>(`/api/llm_profiles/${selectedProfileId}`, { method: "DELETE" });
      setApiKey("");
      await reloadAll();
      await refreshWizard();
      toast.toastSuccess("已删除配置");
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setProfileBusy(false);
    }
  }, [confirm, profileBusy, reloadAll, refreshWizard, selectedProfileId, toast]);

  const saveApiKeyToProfile = useCallback(async (): Promise<boolean> => {
    if (!selectedProfileId) {
      toast.toastError("请先选择或新建一个后端配置");
      return false;
    }
    const key = apiKey.trim();
    if (!key) {
      toast.toastError("请先填写 API Key");
      return false;
    }
    if (profileBusy) return false;

    setProfileBusy(true);
    try {
      await apiJson<{ profile: LLMProfile }>(`/api/llm_profiles/${selectedProfileId}`, {
        method: "PUT",
        body: JSON.stringify({ api_key: key }),
      });
      setApiKey("");
      await reloadAll();
      await refreshWizard();
      bumpWizardLocal();
      toast.toastSuccess("已保存 Key");
      return true;
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
      return false;
    } finally {
      setProfileBusy(false);
    }
  }, [apiKey, bumpWizardLocal, profileBusy, refreshWizard, reloadAll, selectedProfileId, toast]);

  const clearApiKeyInProfile = useCallback(async () => {
    if (!selectedProfileId) {
      toast.toastError("请先选择一个后端配置");
      return;
    }
    if (profileBusy) return;

    const ok = await confirm.confirm({
      title: "清除 API Key？",
      description: "清除后将无法生成/测试连接，直到重新保存 Key。",
      confirmText: "清除",
      danger: true,
    });
    if (!ok) return;

    setProfileBusy(true);
    try {
      await apiJson<{ profile: LLMProfile }>(`/api/llm_profiles/${selectedProfileId}`, {
        method: "PUT",
        body: JSON.stringify({ api_key: null }),
      });
      setApiKey("");
      await reloadAll();
      await refreshWizard();
      bumpWizardLocal();
      toast.toastSuccess("已清除 Key");
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setProfileBusy(false);
    }
  }, [bumpWizardLocal, confirm, profileBusy, refreshWizard, reloadAll, selectedProfileId, toast]);

  const testConnection = useCallback(async (): Promise<boolean> => {
    if (!projectId) return false;
    if (!selectedProfileId) {
      toast.toastError("请先选择或新建一个后端配置");
      return false;
    }
    const extraObj = (() => {
      try {
        return JSON.parse(llmForm.extra || "{}") as Record<string, unknown>;
      } catch {
        return null;
      }
    })();
    if (!extraObj) {
      toast.toastError("extra 不是合法 JSON");
      return false;
    }

    if (!selectedProfile?.has_api_key) {
      const okSave = await saveApiKeyToProfile();
      if (!okSave) return false;
    }

    setTesting(true);
    try {
      const res = await apiJson<{ latency_ms: number }>("/api/llm/test", {
        method: "POST",
        headers: {
          "X-LLM-Provider": llmForm.provider,
        },
        body: JSON.stringify({
          project_id: projectId,
          provider: llmForm.provider,
          base_url: llmForm.base_url || null,
          model: llmForm.model,
          timeout_seconds: parseTimeoutSecondsForTest(llmForm.timeout_seconds),
          params: {
            temperature: parseNumber(llmForm.temperature) ?? 0,
            max_tokens: 8,
          },
        }),
      });
      toast.toastSuccess(`连接成功（延迟 ${res.data.latency_ms}ms）`);
      if (projectId) {
        markWizardLlmTestOk(projectId, llmForm.provider, llmForm.model);
        bumpWizardLocal();
      }
      return true;
    } catch (e) {
      const err = e as ApiError;
      const upstreamStatusCode =
        err.details && typeof err.details === "object" && err.details !== null && "status_code" in err.details
          ? (err.details as { status_code?: unknown }).status_code
          : undefined;
      const msg =
        err.code === "LLM_KEY_MISSING"
          ? "请先保存 API Key"
          : err.code === "LLM_AUTH_ERROR"
            ? "API Key 无效或已过期，请检查后重试"
            : err.code === "LLM_TIMEOUT"
              ? "连接超时，请检查网络或 base_url 是否正确"
              : err.code === "LLM_BAD_REQUEST"
                ? "请求参数有误，可能是模型名称拼写错误"
                : err.code === "LLM_UPSTREAM_ERROR"
                  ? `服务暂时不可用，请稍后重试（${
                      typeof upstreamStatusCode === "number" ? upstreamStatusCode : err.status
                    }）`
                  : err.message;
      toast.toastError(msg, err.requestId);
      return false;
    } finally {
      setTesting(false);
    }
  }, [
    bumpWizardLocal,
    llmForm,
    projectId,
    saveApiKeyToProfile,
    selectedProfile?.has_api_key,
    selectedProfileId,
    toast,
  ]);

  const nextAfterLlm = useMemo(() => {
    const idx = wizard.progress.steps.findIndex((s) => s.key === "llm");
    if (idx < 0) return wizard.progress.nextStep;
    for (let i = idx + 1; i < wizard.progress.steps.length; i++) {
      const s = wizard.progress.steps[i];
      if (s.state === "todo") return s;
    }
    return null;
  }, [wizard.progress]);

  const testAndGoNext = useCallback(async (): Promise<boolean> => {
    if (!projectId) return false;

    const saved = await saveAll();
    if (!saved) return false;

    const ok = await testConnection();
    if (!ok) return false;

    if (nextAfterLlm?.href) navigate(nextAfterLlm.href);
    else navigate(`/projects/${projectId}/outline`);
    return true;
  }, [navigate, nextAfterLlm?.href, projectId, saveAll, testConnection]);

  const previewValues = useMemo(() => {
    const charactersText = characters.map((c) => `- ${c.name}${c.role ? `（${c.role}）` : ""}`).join("\\n");
    return {
      project_name: project?.name ?? "",
      genre: project?.genre ?? "",
      logline: project?.logline ?? "",
      world_setting: settings?.world_setting ?? "",
      style_guide: settings?.style_guide ?? "",
      constraints: settings?.constraints ?? "",
      characters: charactersText,
      outline: outline?.content_md ?? "",
      chapter_number: "1",
      chapter_title: "第一章",
      chapter_plan: "（示例要点）",
      requirements: '{\\n  "chapter_count": 12\\n}',
      instruction: "（示例指令）",
      previous_chapter: "（示例上一章摘要）",
    } satisfies Record<string, string>;
  }, [
    characters,
    outline?.content_md,
    project?.genre,
    project?.logline,
    project?.name,
    settings?.constraints,
    settings?.style_guide,
    settings?.world_setting,
  ]);

  const outlinePreview = useMemo(() => {
    const system = renderTemplate(promptForm.outline_generate.system_template, previewValues);
    const user = renderTemplate(promptForm.outline_generate.user_template, previewValues);
    const missing = [...new Set([...system.missing, ...user.missing])];
    return { system: system.text, user: user.text, missing };
  }, [previewValues, promptForm.outline_generate.system_template, promptForm.outline_generate.user_template]);

  const chapterPreview = useMemo(() => {
    const system = renderTemplate(promptForm.chapter_generate.system_template, previewValues);
    const user = renderTemplate(promptForm.chapter_generate.user_template, previewValues);
    const missing = [...new Set([...system.missing, ...user.missing])];
    return { system: system.text, user: user.text, missing };
  }, [previewValues, promptForm.chapter_generate.system_template, promptForm.chapter_generate.user_template]);

  const availablePlaceholdersText = useMemo(() => {
    const placeholders = new Set([
      ...findPlaceholders(promptForm.outline_generate.user_template),
      ...findPlaceholders(promptForm.chapter_generate.user_template),
    ]);
    return [...placeholders].join(", ") || "—";
  }, [promptForm.chapter_generate.user_template, promptForm.outline_generate.user_template]);

  if (loading) return <div className="text-subtext">加载中...</div>;

  return (
    <div className="grid gap-6">
      <LlmPresetPanel
        llmForm={llmForm}
        setLlmForm={setLlmForm}
        presetDirty={presetDirty}
        saving={savingPreset}
        testing={testing}
        onTestConnection={() => void testConnection()}
        onSave={() => void saveAll()}
        profiles={profiles}
        selectedProfileId={selectedProfileId}
        onSelectProfile={(id) => void selectProfile(id)}
        profileName={profileName}
        onChangeProfileName={setProfileName}
        profileBusy={profileBusy || testing || savingPreset || savingPrompts}
        onCreateProfile={() => void createProfile()}
        onUpdateProfile={() => void updateProfile()}
        onDeleteProfile={() => void deleteProfile()}
        lockConnectionFields={lockConnectionFields}
        apiKey={apiKey}
        onChangeApiKey={setApiKey}
        onSaveApiKey={() => void saveApiKeyToProfile()}
        onClearApiKey={() => void clearApiKeyInProfile()}
      />

      <div className="surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">Prompt Studio（beta）</div>
            <div className="text-xs text-subtext">预设 + 块编辑器（预览走后端渲染）。旧模板编辑仍保留。</div>
          </div>
          <button
            className="btn btn-secondary"
            onClick={() => navigate(`/projects/${projectId}/prompt-studio`)}
            type="button"
          >
            打开
          </button>
        </div>
      </div>

      <PromptTemplatesPanel
        promptForm={promptForm}
        setPromptForm={setPromptForm}
        promptsDirty={promptsDirty}
        saving={savingPrompts}
        outlinePreview={outlinePreview}
        chapterPreview={chapterPreview}
        availablePlaceholdersText={availablePlaceholdersText}
        onSave={() => void saveAll()}
      />

      <div className="text-xs text-subtext">快捷键：Ctrl/Cmd + S 保存（保存配置 + 模板）</div>

      <WizardNextBar
        projectId={projectId}
        currentStep="llm"
        progress={wizard.progress}
        loading={wizard.loading}
        dirty={dirty}
        saving={savingPreset || savingPrompts || testing}
        onSave={saveAll}
        primaryAction={
          wizard.progress.nextStep?.key === "llm"
            ? {
                label: `测试连接并下一步：${nextAfterLlm ? nextAfterLlm.title : "继续"}`,
                disabled: Boolean(savingPreset || savingPrompts || testing),
                onClick: testAndGoNext,
              }
            : undefined
        }
      />
    </div>
  );
}
