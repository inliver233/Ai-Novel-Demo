import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { WizardNextBar } from "../components/atelier/WizardNextBar";
import { LlmPresetPanel } from "../components/prompts/LlmPresetPanel";
import { PromptTemplatesPanel } from "../components/prompts/PromptTemplatesPanel";
import type { LlmForm, PromptForm } from "../components/prompts/types";
import { useToast } from "../components/ui/toast";
import { useSaveHotkey } from "../hooks/useSaveHotkey";
import { useUnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";
import { useWizardProgress } from "../hooks/useWizardProgress";
import { ApiError, apiJson } from "../services/apiClient";
import { clearLlmApiKey, getLlmApiKey, setLlmApiKey } from "../services/llmKeyStore";
import { markWizardLlmTestOk } from "../services/wizard";
import type { Character, LLMPreset, Outline, Project, ProjectSettings, PromptTemplate } from "../types";

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

  const [baselinePreset, setBaselinePreset] = useState<LLMPreset | null>(null);
  const [baselinePrompts, setBaselinePrompts] = useState<PromptForm | null>(null);

  const [apiKeyVisible, setApiKeyVisible] = useState(false);
  const [apiKey, setApiKey] = useState("");

  const [llmForm, setLlmForm] = useState<LlmForm>({
    provider: "openai",
    base_url: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    temperature: "0.7",
    top_p: "1",
    max_tokens: "1500",
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

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);
    void (async () => {
      try {
        const [presetRes, promptsRes, pRes, sRes, oRes, cRes] = await Promise.all([
          apiJson<{ llm_preset: LLMPreset }>(`/api/projects/${projectId}/llm_preset`),
          apiJson<{ templates: PromptTemplate[] }>(`/api/projects/${projectId}/prompts`),
          apiJson<{ project: Project }>(`/api/projects/${projectId}`),
          apiJson<{ settings: ProjectSettings }>(`/api/projects/${projectId}/settings`),
          apiJson<{ outline: Outline }>(`/api/projects/${projectId}/outline`),
          apiJson<{ characters: Character[] }>(`/api/projects/${projectId}/characters`),
        ]);

        setProject(pRes.data.project);
        setSettings(sRes.data.settings);
        setOutline(oRes.data.outline);
        setCharacters(cRes.data.characters);

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

        const storedKey = getLlmApiKey(presetRes.data.llm_preset.provider);
        setApiKey(storedKey);
        setApiKeyVisible(false);
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId, toast]);

  useEffect(() => {
    setApiKey(getLlmApiKey(llmForm.provider));
    setApiKeyVisible(false);
  }, [llmForm.provider]);

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

  const toggleApiKeyVisible = useCallback(() => {
    setApiKeyVisible((v) => !v);
  }, []);

  const clearApiKey = useCallback(() => {
    clearLlmApiKey(llmForm.provider);
    setApiKey("");
    bumpWizardLocal();
    toast.toastSuccess("已清除");
  }, [bumpWizardLocal, llmForm.provider, toast]);

  const saveApiKeyLocal = useCallback(() => {
    setLlmApiKey(llmForm.provider, apiKey);
    bumpWizardLocal();
    toast.toastSuccess("已保存到本机");
  }, [apiKey, bumpWizardLocal, llmForm.provider, toast]);

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
            system_template: byType.get("outline_generate")?.system_template ?? promptForm.outline_generate.system_template,
            user_template: byType.get("outline_generate")?.user_template ?? promptForm.outline_generate.user_template,
          },
          chapter_generate: {
            system_template: byType.get("chapter_generate")?.system_template ?? promptForm.chapter_generate.system_template,
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

  const testConnection = useCallback(async (): Promise<boolean> => {
    const key = apiKey.trim();
    if (!key) {
      toast.toastError("请先填写 API Key");
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

    setTesting(true);
    try {
      const res = await apiJson<{ latency_ms: number }>("/api/llm/test", {
        method: "POST",
        headers: {
          "X-LLM-Provider": llmForm.provider,
          "X-LLM-API-Key": key,
        },
        body: JSON.stringify({
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
          ? "请先填写 API Key"
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
  }, [apiKey, bumpWizardLocal, llmForm, projectId, toast]);

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
    const key = apiKey.trim();
    if (!key) {
      toast.toastError("请先填写 API Key");
      return false;
    }

    setLlmApiKey(llmForm.provider, key);
    bumpWizardLocal();

    const saved = await saveAll();
    if (!saved) return false;

    const ok = await testConnection();
    if (!ok) return false;

    if (nextAfterLlm?.href) navigate(nextAfterLlm.href);
    else navigate(`/projects/${projectId}/outline`);
    return true;
  }, [apiKey, bumpWizardLocal, llmForm.provider, navigate, nextAfterLlm?.href, projectId, saveAll, testConnection, toast]);

  const previewValues = useMemo(() => {
    const charactersText = characters
      .map((c) => `- ${c.name}${c.role ? `（${c.role}）` : ""}`)
      .join("\\n");
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
      requirements: "{\\n  \"chapter_count\": 12\\n}",
      instruction: "（示例指令）",
      previous_chapter: "（示例上一章摘要）",
    } satisfies Record<string, string>;
  }, [characters, outline?.content_md, project?.genre, project?.logline, project?.name, settings?.constraints, settings?.style_guide, settings?.world_setting]);

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
        apiKeyVisible={apiKeyVisible}
        onToggleApiKeyVisible={toggleApiKeyVisible}
        apiKey={apiKey}
        onChangeApiKey={setApiKey}
        onSaveApiKey={saveApiKeyLocal}
        onClearApiKey={clearApiKey}
      />

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
