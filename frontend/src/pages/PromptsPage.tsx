import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { WizardNextBar } from "../components/atelier/WizardNextBar";
import { LlmPresetPanel } from "../components/prompts/LlmPresetPanel";
import type { LlmForm } from "../components/prompts/types";
import { useConfirm } from "../components/ui/confirm";
import { useToast } from "../components/ui/toast";
import { useAutoSave } from "../hooks/useAutoSave";
import { usePersistentOutletIsActive } from "../hooks/usePersistentOutlet";
import { useSaveHotkey } from "../hooks/useSaveHotkey";
import { UnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";
import { useWizardProgress } from "../hooks/useWizardProgress";
import { copyText } from "../lib/copyText";
import { createRequestSeqGuard } from "../lib/requestSeqGuard";
import { ApiError, apiJson } from "../services/apiClient";
import { markWizardLlmTestOk } from "../services/wizard";
import type { LLMPreset, LLMProfile, Project } from "../types";

type LlmCapabilities = {
  provider: string;
  model: string;
  max_tokens_limit: number | null;
  max_tokens_recommended: number | null;
  context_window_limit: number | null;
};

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
  const outletActive = usePersistentOutletIsActive();
  const wizard = useWizardProgress(projectId);
  const refreshWizard = wizard.refresh;
  const bumpWizardLocal = wizard.bumpLocal;

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<null | { message: string; code: string; requestId?: string }>(null);
  const [savingPreset, setSavingPreset] = useState(false);
  const [testing, setTesting] = useState(false);
  const savingPresetRef = useRef(false);
  const queuedPresetSaveRef = useRef<null | { silent: boolean; snapshot?: LlmForm }>(null);
  const wizardRefreshTimerRef = useRef<number | null>(null);

  const [project, setProject] = useState<Project | null>(null);
  const [profiles, setProfiles] = useState<LLMProfile[]>([]);
  const [profileName, setProfileName] = useState("");
  const [profileBusy, setProfileBusy] = useState(false);

  const [baselinePreset, setBaselinePreset] = useState<LLMPreset | null>(null);
  const [capabilities, setCapabilities] = useState<LlmCapabilities | null>(null);
  const capsGuardRef = useRef(createRequestSeqGuard());

  const [apiKey, setApiKey] = useState("");

  const [llmForm, setLlmForm] = useState<LlmForm>({
    provider: "openai",
    base_url: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    temperature: "0.7",
    top_p: "1",
    max_tokens: "8192",
    presence_penalty: "0",
    frequency_penalty: "0",
    top_k: "",
    stop: "",
    timeout_seconds: "90",
    extra: "{}",
  });

  const reloadAll = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [presetRes, pRes, profilesRes] = await Promise.all([
        apiJson<{ llm_preset: LLMPreset }>(`/api/projects/${projectId}/llm_preset`),
        apiJson<{ project: Project }>(`/api/projects/${projectId}`),
        apiJson<{ profiles: LLMProfile[] }>(`/api/llm_profiles`),
      ]);

      setProject(pRes.data.project);
      setProfiles(profilesRes.data.profiles ?? []);
      setProfileName("");

      setBaselinePreset(presetRes.data.llm_preset);
      setCapabilities({
        provider: presetRes.data.llm_preset.provider,
        model: presetRes.data.llm_preset.model,
        max_tokens_limit: presetRes.data.llm_preset.max_tokens_limit ?? null,
        max_tokens_recommended: presetRes.data.llm_preset.max_tokens_recommended ?? null,
        context_window_limit: presetRes.data.llm_preset.context_window_limit ?? null,
      });
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

      setApiKey("");
      setLoadError(null);
    } catch (e) {
      if (e instanceof ApiError) {
        setLoadError({ message: e.message, code: e.code, requestId: e.requestId });
        toast.toastError(`${e.message} (${e.code})`, e.requestId);
      } else {
        setLoadError({ message: "请求失败", code: "UNKNOWN_ERROR" });
        toast.toastError("请求失败 (UNKNOWN_ERROR)");
      }
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    void reloadAll();
  }, [reloadAll]);

  useEffect(() => {
    return () => {
      if (wizardRefreshTimerRef.current !== null) window.clearTimeout(wizardRefreshTimerRef.current);
    };
  }, []);

  useEffect(() => {
    const guard = capsGuardRef.current;
    return () => {
      guard.invalidate();
    };
  }, []);

  useEffect(() => {
    const provider = llmForm.provider;
    const model = llmForm.model.trim();
    const guard = capsGuardRef.current;
    if (!model) {
      guard.invalidate();
      setCapabilities(null);
      return;
    }
    const seq = guard.next();
    void (async () => {
      try {
        const res = await apiJson<{ capabilities: LlmCapabilities }>(
          `/api/llm_capabilities?provider=${provider}&model=${encodeURIComponent(model)}`,
        );
        if (!guard.isLatest(seq)) return;
        setCapabilities(res.data.capabilities);
      } catch {
        if (!guard.isLatest(seq)) return;
        setCapabilities(null);
      }
    })();
  }, [llmForm.model, llmForm.provider]);

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

  const dirty = presetDirty;

  const selectedProfileId = project?.llm_profile_id ?? null;
  const selectedProfile = selectedProfileId ? (profiles.find((p) => p.id === selectedProfileId) ?? null) : null;
  const llmCtaBlockedReason = useMemo(() => {
    if (!selectedProfileId) return "请先选择或新建一个后端配置";
    if (!selectedProfile?.has_api_key) return "请先保存 API Key";
    return null;
  }, [selectedProfile?.has_api_key, selectedProfileId]);

  const saveAll = useCallback(
    async (opts?: { silent?: boolean; snapshot?: LlmForm }): Promise<boolean> => {
      if (!projectId) return false;
      const silent = Boolean(opts?.silent);
      const snapshot = opts?.snapshot ?? llmForm;
      if (!dirty && !opts?.snapshot) return true;
      if (savingPresetRef.current) {
        queuedPresetSaveRef.current = { silent, snapshot };
        return false;
      }

      const snapshotProvider = snapshot.provider;
      const snapshotModel = snapshot.model.trim();
      const snapshotBaseUrl = snapshot.base_url.trim();
      const extraObj = (() => {
        try {
          return JSON.parse(snapshot.extra || "{}") as Record<string, unknown>;
        } catch {
          return null;
        }
      })();
      if (!extraObj) {
        if (!silent) toast.toastError("extra 不是合法 JSON");
        return false;
      }

      const scheduleWizardRefresh = () => {
        if (wizardRefreshTimerRef.current !== null) window.clearTimeout(wizardRefreshTimerRef.current);
        wizardRefreshTimerRef.current = window.setTimeout(() => void refreshWizard(), 1200);
      };

      savingPresetRef.current = true;
      setSavingPreset(true);
      try {
        if (selectedProfileId) {
          const currentProvider = selectedProfile?.provider ?? null;
          const currentModel = selectedProfile?.model ?? null;
          const currentBaseUrl = (selectedProfile?.base_url ?? "").trim();
          const needsProfileSync =
            currentProvider !== snapshotProvider ||
            currentModel !== snapshotModel ||
            currentBaseUrl !== snapshotBaseUrl;
          if (needsProfileSync) {
            const res = await apiJson<{ profile: LLMProfile }>(`/api/llm_profiles/${selectedProfileId}`, {
              method: "PUT",
              body: JSON.stringify({
                provider: snapshotProvider,
                base_url: snapshotBaseUrl ? snapshotBaseUrl : null,
                model: snapshotModel,
              }),
            });
            setProfiles((prev) => prev.map((p) => (p.id === res.data.profile.id ? res.data.profile : p)));
          }
        }

        if (presetDirty) {
          const res = await apiJson<{ llm_preset: LLMPreset }>(`/api/projects/${projectId}/llm_preset`, {
            method: "PUT",
            body: JSON.stringify({
              provider: snapshotProvider,
              base_url: snapshotBaseUrl ? snapshotBaseUrl : null,
              model: snapshotModel,
              temperature: parseNumber(snapshot.temperature),
              top_p: parseNumber(snapshot.top_p),
              max_tokens: parseNumber(snapshot.max_tokens),
              presence_penalty: parseNumber(snapshot.presence_penalty),
              frequency_penalty: parseNumber(snapshot.frequency_penalty),
              top_k: parseNumber(snapshot.top_k),
              stop: parseStopList(snapshot.stop),
              timeout_seconds: parseTimeoutSecondsForPreset(snapshot.timeout_seconds),
              extra: extraObj,
            }),
          });
          setBaselinePreset(res.data.llm_preset);

          setLlmForm((current) => {
            if (current.provider !== snapshot.provider) return current;
            if (current.base_url !== snapshot.base_url) return current;
            if (current.model !== snapshot.model) return current;
            if (current.temperature !== snapshot.temperature) return current;
            if (current.top_p !== snapshot.top_p) return current;
            if (current.max_tokens !== snapshot.max_tokens) return current;
            if (current.presence_penalty !== snapshot.presence_penalty) return current;
            if (current.frequency_penalty !== snapshot.frequency_penalty) return current;
            if (current.top_k !== snapshot.top_k) return current;
            if (current.stop !== snapshot.stop) return current;
            if (current.timeout_seconds !== snapshot.timeout_seconds) return current;
            if (current.extra !== snapshot.extra) return current;
            return {
              ...current,
              provider: res.data.llm_preset.provider,
              base_url: res.data.llm_preset.base_url ?? "",
              model: res.data.llm_preset.model ?? "",
              max_tokens: res.data.llm_preset.max_tokens?.toString() ?? "",
            };
          });
        }

        bumpWizardLocal();
        if (silent) scheduleWizardRefresh();
        else {
          toast.toastSuccess("已保存");
          await refreshWizard();
        }
        return true;
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
        return false;
      } finally {
        setSavingPreset(false);
        savingPresetRef.current = false;
        if (queuedPresetSaveRef.current) {
          const queued = queuedPresetSaveRef.current;
          queuedPresetSaveRef.current = null;
          void saveAll({ silent: queued.silent, snapshot: queued.snapshot });
        }
      }
    },
    [bumpWizardLocal, dirty, llmForm, presetDirty, projectId, refreshWizard, selectedProfile, selectedProfileId, toast],
  );

  useSaveHotkey(() => void saveAll(), dirty);

  useAutoSave({
    enabled: Boolean(projectId),
    dirty,
    delayMs: 1200,
    getSnapshot: () => ({ ...llmForm }),
    onSave: async (snapshot) => {
      await saveAll({ silent: true, snapshot });
    },
    deps: [
      llmForm.provider,
      llmForm.base_url,
      llmForm.model,
      llmForm.temperature,
      llmForm.top_p,
      llmForm.max_tokens,
      llmForm.presence_penalty,
      llmForm.frequency_penalty,
      llmForm.top_k,
      llmForm.stop,
      llmForm.timeout_seconds,
      llmForm.extra,
      projectId ?? "",
    ],
  });

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
      const model = llmForm.model.trim();
      const baseUrl = llmForm.base_url.trim();
      const res = await apiJson<{ profile: LLMProfile }>(`/api/llm_profiles`, {
        method: "POST",
        body: JSON.stringify({
          name,
          provider: llmForm.provider,
          base_url: baseUrl ? baseUrl : null,
          model,
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
      const model = llmForm.model.trim();
      const baseUrl = llmForm.base_url.trim();
      await apiJson<{ profile: LLMProfile }>(`/api/llm_profiles/${selectedProfileId}`, {
        method: "PUT",
        body: JSON.stringify({
          name: name ? name : undefined,
          provider: llmForm.provider,
          base_url: baseUrl ? baseUrl : null,
          model,
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

    const model = llmForm.model.trim();
    const baseUrl = llmForm.base_url.trim();
    if (!selectedProfile?.has_api_key) {
      toast.toastError("请先保存 API Key");
      return false;
    }

    setTesting(true);
    try {
      const res = await apiJson<{ latency_ms: number; text?: string }>("/api/llm/test", {
        method: "POST",
        headers: {
          "X-LLM-Provider": llmForm.provider,
        },
        body: JSON.stringify({
          project_id: projectId,
          provider: llmForm.provider,
          base_url: baseUrl ? baseUrl : null,
          model,
          timeout_seconds: parseTimeoutSecondsForTest(llmForm.timeout_seconds),
          extra: extraObj,
          params: {
            temperature: parseNumber(llmForm.temperature) ?? 0,
            // Some models may emit "thinking" blocks before final text; keep this > tiny to ensure we get a text preview.
            max_tokens: 64,
          },
        }),
      });
      const preview = (res.data.text ?? "").trim();
      toast.toastSuccess(`连接成功（延迟 ${res.data.latency_ms}ms${preview ? `，输出：${preview}` : ""}）`);
      if (projectId) {
        markWizardLlmTestOk(projectId, llmForm.provider, model);
        bumpWizardLocal();
      }
      return true;
    } catch (e) {
      const err = e as ApiError;
      const details =
        err.details && typeof err.details === "object" && err.details !== null
          ? (err.details as Record<string, unknown>)
          : null;
      const upstreamStatusCode = details && "status_code" in details ? details.status_code : undefined;
      const upstreamErrorRaw = details && "upstream_error" in details ? details.upstream_error : undefined;
      const upstreamError = (() => {
        if (!upstreamErrorRaw) return null;
        if (typeof upstreamErrorRaw === "string") {
          const s = upstreamErrorRaw.trim();
          if (!s) return null;
          try {
            const parsed = JSON.parse(s) as unknown;
            if (parsed && typeof parsed === "object") {
              const obj = parsed as Record<string, unknown>;
              if (typeof obj.detail === "string" && obj.detail.trim()) return obj.detail.trim();
              if (obj.error && typeof obj.error === "object") {
                const errObj = obj.error as Record<string, unknown>;
                if (typeof errObj.message === "string" && errObj.message.trim()) return errObj.message.trim();
              }
            }
          } catch {
            // ignore
          }
          return s.length > 160 ? `${s.slice(0, 160)}…` : s;
        }
        return String(upstreamErrorRaw);
      })();
      const compatAdjustments =
        details && "compat_adjustments" in details && Array.isArray(details.compat_adjustments)
          ? (details.compat_adjustments as unknown[])
              .filter((x) => typeof x === "string" && x)
              .slice(0, 6)
              .join("、")
          : null;
      const msg =
        err.code === "LLM_KEY_MISSING"
          ? "请先保存 API Key"
          : err.code === "LLM_AUTH_ERROR"
            ? "API Key 无效或已过期，请检查后重试"
            : err.code === "LLM_TIMEOUT"
              ? "连接超时，请检查网络或 base_url 是否正确"
              : err.code === "LLM_BAD_REQUEST"
                ? `请求参数有误，可能是模型名称或参数不支持${upstreamError ? `（上游：${upstreamError}）` : ""}${
                    compatAdjustments ? `（兼容：${compatAdjustments}）` : ""
                  }`
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
  }, [bumpWizardLocal, llmForm, projectId, selectedProfile?.has_api_key, selectedProfileId, toast]);

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

  if (loading) {
    return (
      <div className="grid gap-6 pb-24" aria-busy="true" aria-live="polite">
        <span className="sr-only">正在加载模型配置…</span>
        <div className="panel p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="grid gap-2">
              <div className="skeleton h-6 w-44" />
              <div className="skeleton h-4 w-72" />
            </div>
            <div className="skeleton h-9 w-40" />
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="skeleton h-10 w-full" />
            <div className="skeleton h-10 w-full" />
            <div className="skeleton h-28 w-full sm:col-span-2" />
          </div>
        </div>
        <div className="panel p-6">
          <div className="skeleton h-5 w-40" />
          <div className="mt-3 grid gap-2">
            <div className="skeleton h-4 w-80" />
            <div className="skeleton h-4 w-72" />
          </div>
        </div>
      </div>
    );
  }

  if (loadError && !project && !baselinePreset) {
    return (
      <div className="grid gap-6 pb-24">
        <div className="error-card">
          <div className="state-title">加载失败</div>
          <div className="state-desc">{`${loadError.message} (${loadError.code})`}</div>
          {loadError.requestId ? (
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-subtext">
              <span>request_id: {loadError.requestId}</span>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => void copyText(loadError.requestId!, { title: "复制 request_id" })}
                type="button"
              >
                复制 request_id
              </button>
            </div>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <button className="btn btn-primary" onClick={() => void reloadAll()} type="button">
              重试
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-6 pb-24">
      {dirty && outletActive ? <UnsavedChangesGuard when={dirty} /> : null}
      <LlmPresetPanel
        llmForm={llmForm}
        setLlmForm={setLlmForm}
        presetDirty={presetDirty}
        saving={savingPreset}
        testing={testing}
        capabilities={capabilities}
        onTestConnection={() => void testConnection()}
        testConnectionDisabledReason={llmCtaBlockedReason}
        onSave={() => void saveAll()}
        profiles={profiles}
        selectedProfileId={selectedProfileId}
        onSelectProfile={(id) => void selectProfile(id)}
        profileName={profileName}
        onChangeProfileName={setProfileName}
        profileBusy={profileBusy || testing || savingPreset}
        onCreateProfile={() => void createProfile()}
        onUpdateProfile={() => void updateProfile()}
        onDeleteProfile={() => void deleteProfile()}
        apiKey={apiKey}
        onChangeApiKey={setApiKey}
        onSaveApiKey={() => void saveApiKeyToProfile()}
        onClearApiKey={() => void clearApiKeyInProfile()}
      />

      <div className="surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">提示词工作室（beta）</div>
            <div className="text-xs text-subtext">提示词仅在「提示词工作室」中编辑/预览（与实际发送一致）。</div>
          </div>
          <button
            className="btn btn-secondary"
            onClick={() => navigate(`/projects/${projectId}/prompt-studio`)}
            type="button"
          >
            打开提示词工作室
          </button>
        </div>
      </div>

      <div className="text-xs text-subtext">快捷键：Ctrl/Cmd + S 保存（仅保存模型配置）</div>

      <WizardNextBar
        projectId={projectId}
        currentStep="llm"
        progress={wizard.progress}
        loading={wizard.loading}
        dirty={dirty}
        saving={savingPreset || testing}
        onSave={saveAll}
        primaryAction={
          wizard.progress.nextStep?.key === "llm"
            ? {
                label: llmCtaBlockedReason ?? `测试连接并下一步：${nextAfterLlm ? nextAfterLlm.title : "继续"}`,
                disabled: Boolean(savingPreset || testing || llmCtaBlockedReason),
                onClick: testAndGoNext,
              }
            : undefined
        }
      />
    </div>
  );
}
