import { type ComponentProps, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { WizardNextBar } from "../../components/atelier/WizardNextBar";
import { useToast } from "../../components/ui/toast";
import { useAuth } from "../../contexts/auth";
import { useProjects } from "../../contexts/projects";
import { useAutoSave } from "../../hooks/useAutoSave";
import { usePersistentOutletIsActive } from "../../hooks/usePersistentOutlet";
import { useProjectData } from "../../hooks/useProjectData";
import { useSaveHotkey } from "../../hooks/useSaveHotkey";
import { useWizardProgress } from "../../hooks/useWizardProgress";
import { UI_COPY } from "../../lib/uiCopy";
import { ApiError, apiJson } from "../../services/apiClient";
import { getCurrentUserId } from "../../services/currentUser";
import { writingMemoryInjectionEnabledStorageKey } from "../../services/uiState";
import { markWizardProjectChanged } from "../../services/wizard";
import type { Project, ProjectSettings } from "../../types";
import {
  createDefaultProjectForm,
  createDefaultSettingsForm,
  mapLoadedSettingsToForms,
  type ProjectForm,
  type ProjectMembershipItem,
  type QpPreviewState,
  type SaveSnapshot,
  type SettingsForm,
  type SettingsLoaded,
  type VectorEmbeddingDryRunResult,
  type VectorRerankDryRunResult,
} from "./models";
import {
  getQueryPreprocessErrorField,
  isSameQueryPreprocess,
  queryPreprocessFromBaseline,
  queryPreprocessFromForm,
  validateQueryPreprocess,
} from "./queryPreprocessing";
import { SettingsCoreSections } from "./SettingsCoreSections";
import { SettingsFeatureDefaultsSection } from "./SettingsFeatureDefaultsSection";
import { SettingsQueryPreprocessingSection } from "./SettingsQueryPreprocessingSection";
import { SettingsVectorRagSection } from "./SettingsVectorRagSection";
import { SETTINGS_COPY } from "./settingsCopy";

const qpPreviewCache = new Map<string, QpPreviewState>();
const qpPreviewQueryTextCache = new Map<string, string>();

type SettingsPageBlockingLoadError = {
  message: string;
  code: string;
  requestId?: string;
};

type SettingsPageState = {
  loading: boolean;
  blockingLoadError: SettingsPageBlockingLoadError | null;
  reloadAll: () => Promise<void>;
  dirty: boolean;
  outletActive: boolean;
  coreSectionsProps: ComponentProps<typeof SettingsCoreSections>;
  vectorRagSectionProps: ComponentProps<typeof SettingsVectorRagSection>;
  queryPreprocessingSectionProps: ComponentProps<typeof SettingsQueryPreprocessingSection>;
  featureDefaultsSectionProps: ComponentProps<typeof SettingsFeatureDefaultsSection>;
  wizardBarProps: ComponentProps<typeof WizardNextBar>;
};

export function useSettingsPageState(): SettingsPageState {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const auth = useAuth();
  const { refresh } = useProjects();
  const outletActive = usePersistentOutletIsActive();
  const wizard = useWizardProgress(projectId);
  const refreshWizard = wizard.refresh;
  const bumpWizardLocal = wizard.bumpLocal;

  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const settingsSavePendingRef = useRef(false);
  const queuedSaveRef = useRef<null | { silent: boolean; snapshot?: SaveSnapshot }>(null);
  const wizardRefreshTimerRef = useRef<number | null>(null);
  const projectsRefreshTimerRef = useRef<number | null>(null);
  const autoUpdateMasterRef = useRef<HTMLInputElement | null>(null);
  const [baselineProject, setBaselineProject] = useState<Project | null>(null);
  const [baselineSettings, setBaselineSettings] = useState<ProjectSettings | null>(null);
  const [loadError, setLoadError] = useState<null | { message: string; code: string; requestId?: string }>(null);

  const [projectForm, setProjectForm] = useState<ProjectForm>(() => createDefaultProjectForm());
  const [settingsForm, setSettingsForm] = useState<SettingsForm>(() => createDefaultSettingsForm());
  const [vectorRerankTopKDraft, setVectorRerankTopKDraft] = useState("20");
  const [vectorRerankTimeoutDraft, setVectorRerankTimeoutDraft] = useState("");
  const [vectorRerankHybridAlphaDraft, setVectorRerankHybridAlphaDraft] = useState("");
  const [rerankApiKeyDraft, setRerankApiKeyDraft] = useState("");
  const [rerankApiKeyClearRequested, setRerankApiKeyClearRequested] = useState(false);
  const [vectorApiKeyDraft, setVectorApiKeyDraft] = useState("");
  const [vectorApiKeyClearRequested, setVectorApiKeyClearRequested] = useState(false);
  const [embeddingDryRunLoading, setEmbeddingDryRunLoading] = useState(false);
  const [embeddingDryRun, setEmbeddingDryRun] = useState<null | {
    requestId: string;
    result: VectorEmbeddingDryRunResult;
  }>(null);
  const [embeddingDryRunError, setEmbeddingDryRunError] = useState<null | {
    message: string;
    code: string;
    requestId?: string;
  }>(null);
  const [rerankDryRunLoading, setRerankDryRunLoading] = useState(false);
  const [rerankDryRun, setRerankDryRun] = useState<null | { requestId: string; result: VectorRerankDryRunResult }>(
    null,
  );
  const [rerankDryRunError, setRerankDryRunError] = useState<null | {
    message: string;
    code: string;
    requestId?: string;
  }>(null);
  const [writingMemoryInjectionEnabled, setWritingMemoryInjectionEnabled] = useState(true);

  useEffect(() => {
    if (!projectId) return;
    const key = writingMemoryInjectionEnabledStorageKey(getCurrentUserId(), projectId);
    const raw = localStorage.getItem(key);
    if (raw === null) {
      setWritingMemoryInjectionEnabled(true);
      return;
    }
    setWritingMemoryInjectionEnabled(raw === "1");
  }, [projectId]);

  const saveWritingMemoryInjectionEnabled = useCallback(
    (enabled: boolean) => {
      if (!projectId) return;
      setWritingMemoryInjectionEnabled(enabled);
      const key = writingMemoryInjectionEnabledStorageKey(getCurrentUserId(), projectId);
      localStorage.setItem(key, enabled ? "1" : "0");
      toast.toastSuccess(enabled ? UI_COPY.featureDefaults.toastEnabled : UI_COPY.featureDefaults.toastDisabled);
    },
    [projectId, toast],
  );

  const resetWritingMemoryInjectionEnabled = useCallback(() => {
    if (!projectId) return;
    setWritingMemoryInjectionEnabled(true);
    const key = writingMemoryInjectionEnabledStorageKey(getCurrentUserId(), projectId);
    localStorage.removeItem(key);
    toast.toastSuccess(UI_COPY.featureDefaults.toastReset);
  }, [projectId, toast]);

  const autoUpdateAllEnabled = useMemo(
    () =>
      settingsForm.auto_update_worldbook_enabled &&
      settingsForm.auto_update_characters_enabled &&
      settingsForm.auto_update_story_memory_enabled &&
      settingsForm.auto_update_graph_enabled &&
      settingsForm.auto_update_vector_enabled &&
      settingsForm.auto_update_search_enabled &&
      settingsForm.auto_update_fractal_enabled &&
      settingsForm.auto_update_tables_enabled,
    [settingsForm],
  );

  const autoUpdateAnyEnabled = useMemo(
    () =>
      settingsForm.auto_update_worldbook_enabled ||
      settingsForm.auto_update_characters_enabled ||
      settingsForm.auto_update_story_memory_enabled ||
      settingsForm.auto_update_graph_enabled ||
      settingsForm.auto_update_vector_enabled ||
      settingsForm.auto_update_search_enabled ||
      settingsForm.auto_update_fractal_enabled ||
      settingsForm.auto_update_tables_enabled,
    [settingsForm],
  );

  useEffect(() => {
    const el = autoUpdateMasterRef.current;
    if (!el) return;
    el.indeterminate = autoUpdateAnyEnabled && !autoUpdateAllEnabled;
  }, [autoUpdateAllEnabled, autoUpdateAnyEnabled]);

  const setAllAutoUpdates = useCallback((enabled: boolean) => {
    setSettingsForm((v) => ({
      ...v,
      auto_update_worldbook_enabled: enabled,
      auto_update_characters_enabled: enabled,
      auto_update_story_memory_enabled: enabled,
      auto_update_graph_enabled: enabled,
      auto_update_vector_enabled: enabled,
      auto_update_search_enabled: enabled,
      auto_update_fractal_enabled: enabled,
      auto_update_tables_enabled: enabled,
    }));
  }, []);

  const settingsQuery = useProjectData<SettingsLoaded>(projectId, async (id) => {
    try {
      const [pRes, sRes] = await Promise.all([
        apiJson<{ project: Project }>(`/api/projects/${id}`),
        apiJson<{ settings: ProjectSettings }>(`/api/projects/${id}/settings`),
      ]);
      setLoadError(null);
      return { project: pRes.data.project, settings: sRes.data.settings };
    } catch (e) {
      if (e instanceof ApiError) {
        setLoadError({ message: e.message, code: e.code, requestId: e.requestId });
      } else {
        setLoadError({ message: "请求失败", code: "UNKNOWN_ERROR" });
      }
      throw e;
    }
  });

  useEffect(() => {
    if (!settingsQuery.data) return;
    const { project, settings } = settingsQuery.data;
    const mapped = mapLoadedSettingsToForms(settingsQuery.data);
    setBaselineProject(project);
    setBaselineSettings(settings);
    setProjectForm(mapped.projectForm);
    setSettingsForm(mapped.settingsForm);
    setVectorRerankTopKDraft(mapped.vectorRerankTopKDraft);
    setVectorRerankTimeoutDraft(mapped.vectorRerankTimeoutDraft);
    setVectorRerankHybridAlphaDraft(mapped.vectorRerankHybridAlphaDraft);
    setRerankApiKeyDraft("");
    setRerankApiKeyClearRequested(false);
    setVectorApiKeyDraft("");
    setVectorApiKeyClearRequested(false);
  }, [settingsQuery.data]);

  const [membershipsLoading, setMembershipsLoading] = useState(false);
  const [membershipSaving, setMembershipSaving] = useState(false);
  const [memberships, setMemberships] = useState<ProjectMembershipItem[]>([]);
  const [inviteUserId, setInviteUserId] = useState("");
  const [inviteRole, setInviteRole] = useState<"viewer" | "editor">("viewer");

  const [qpPanelOpen, setQpPanelOpen] = useState(true);
  const [qpPreviewQueryText, setQpPreviewQueryText] = useState(() => {
    if (!projectId) return "";
    return qpPreviewQueryTextCache.get(projectId) ?? "";
  });
  const [qpPreviewLoading, setQpPreviewLoading] = useState(false);
  const [qpPreview, setQpPreview] = useState<null | QpPreviewState>(() => {
    if (!projectId) return null;
    return qpPreviewCache.get(projectId) ?? null;
  });
  const [qpPreviewError, setQpPreviewError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    setQpPreview(qpPreviewCache.get(projectId) ?? null);
    setQpPreviewQueryText(qpPreviewQueryTextCache.get(projectId) ?? "");
    setQpPreviewError(null);
  }, [projectId]);

  const canManageMemberships = useMemo(() => {
    if (!baselineProject) return false;
    const uid = auth.user?.id ?? "";
    return Boolean(uid) && baselineProject.owner_user_id === uid;
  }, [auth.user?.id, baselineProject]);

  const loadMemberships = useCallback(async () => {
    if (!projectId) return;
    setMembershipsLoading(true);
    try {
      const res = await apiJson<{ memberships: ProjectMembershipItem[] }>(`/api/projects/${projectId}/memberships`);
      const next = Array.isArray(res.data.memberships) ? res.data.memberships : [];
      next.sort((a, b) => String(a.user?.id ?? "").localeCompare(String(b.user?.id ?? "")));
      setMemberships(next);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setMembershipsLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    if (!canManageMemberships) return;
    void loadMemberships();
  }, [canManageMemberships, loadMemberships]);

  const inviteMember = useCallback(async () => {
    if (!projectId) return;
    const targetUserId = inviteUserId.trim();
    if (!targetUserId) {
      toast.toastError("user_id 不能为空");
      return;
    }
    setMembershipSaving(true);
    try {
      await apiJson<{ membership: unknown }>(`/api/projects/${projectId}/memberships`, {
        method: "POST",
        body: JSON.stringify({ user_id: targetUserId, role: inviteRole }),
      });
      setInviteUserId("");
      toast.toastSuccess("已邀请成员");
      await loadMemberships();
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setMembershipSaving(false);
    }
  }, [inviteRole, inviteUserId, loadMemberships, projectId, toast]);

  const updateMemberRole = useCallback(
    async (targetUserId: string, role: "viewer" | "editor") => {
      if (!projectId) return;
      setMembershipSaving(true);
      try {
        await apiJson<{ membership: unknown }>(`/api/projects/${projectId}/memberships/${targetUserId}`, {
          method: "PUT",
          body: JSON.stringify({ role }),
        });
        toast.toastSuccess("已更新角色");
        await loadMemberships();
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setMembershipSaving(false);
      }
    },
    [loadMemberships, projectId, toast],
  );

  const removeMember = useCallback(
    async (targetUserId: string) => {
      if (!projectId) return;
      setMembershipSaving(true);
      try {
        await apiJson<Record<string, never>>(`/api/projects/${projectId}/memberships/${targetUserId}`, {
          method: "DELETE",
        });
        toast.toastSuccess("已移除成员");
        await loadMemberships();
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setMembershipSaving(false);
      }
    },
    [loadMemberships, projectId, toast],
  );

  const runQpPreview = useCallback(async () => {
    if (!projectId) return;
    const queryText = qpPreviewQueryText.trim();
    if (!queryText) {
      setQpPreview(null);
      qpPreviewCache.delete(projectId);
      setQpPreviewError("请输入示例 query_text");
      return;
    }
    setQpPreviewLoading(true);
    setQpPreviewError(null);
    try {
      const deadlineMs = Date.now() + 10_000;
      while (settingsSavePendingRef.current) {
        await new Promise((resolve) => setTimeout(resolve, 50));
        if (Date.now() > deadlineMs) {
          setQpPreview(null);
          qpPreviewCache.delete(projectId);
          setQpPreviewError("配置保存中，暂时无法预览（请稍后重试）");
          return;
        }
      }

      setQpPanelOpen(true);

      const res = await apiJson<{
        result: unknown;
        raw_query_text: string;
        normalized_query_text: string;
        preprocess_obs: unknown;
      }>(`/api/projects/${projectId}/graph/query`, {
        method: "POST",
        body: JSON.stringify({ query_text: queryText, enabled: false }),
      });
      const next: QpPreviewState = {
        normalized: String(res.data.normalized_query_text ?? ""),
        obs: res.data.preprocess_obs ?? null,
        requestId: res.request_id ?? "unknown",
      };
      setQpPreview(next);
      qpPreviewCache.set(projectId, next);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      setQpPreview(null);
      if (projectId) qpPreviewCache.delete(projectId);
      setQpPreviewError(`${err.message} (${err.code})`);
    } finally {
      setQpPreviewLoading(false);
    }
  }, [projectId, qpPreviewQueryText]);

  const dirty = useMemo(() => {
    if (!baselineProject || !baselineSettings) return false;
    const vectorApiKeyDirty = vectorApiKeyClearRequested || vectorApiKeyDraft.trim().length > 0;
    const rerankApiKeyDirty = rerankApiKeyClearRequested || rerankApiKeyDraft.trim().length > 0;
    const qpDirty = !isSameQueryPreprocess(
      queryPreprocessFromForm(settingsForm),
      queryPreprocessFromBaseline(baselineSettings),
    );
    return (
      projectForm.name !== baselineProject.name ||
      projectForm.genre !== (baselineProject.genre ?? "") ||
      projectForm.logline !== (baselineProject.logline ?? "") ||
      settingsForm.world_setting !== baselineSettings.world_setting ||
      settingsForm.style_guide !== baselineSettings.style_guide ||
      settingsForm.constraints !== baselineSettings.constraints ||
      settingsForm.context_optimizer_enabled !== baselineSettings.context_optimizer_enabled ||
      settingsForm.auto_update_worldbook_enabled !== baselineSettings.auto_update_worldbook_enabled ||
      settingsForm.auto_update_characters_enabled !== baselineSettings.auto_update_characters_enabled ||
      settingsForm.auto_update_story_memory_enabled !== baselineSettings.auto_update_story_memory_enabled ||
      settingsForm.auto_update_graph_enabled !== baselineSettings.auto_update_graph_enabled ||
      settingsForm.auto_update_vector_enabled !== baselineSettings.auto_update_vector_enabled ||
      settingsForm.auto_update_search_enabled !== baselineSettings.auto_update_search_enabled ||
      settingsForm.auto_update_fractal_enabled !== baselineSettings.auto_update_fractal_enabled ||
      settingsForm.auto_update_tables_enabled !== baselineSettings.auto_update_tables_enabled ||
      qpDirty ||
      settingsForm.vector_rerank_enabled !== baselineSettings.vector_rerank_effective_enabled ||
      settingsForm.vector_rerank_method.trim() !== baselineSettings.vector_rerank_effective_method ||
      Math.max(1, Math.min(1000, Math.floor(settingsForm.vector_rerank_top_k))) !==
        baselineSettings.vector_rerank_effective_top_k ||
      settingsForm.vector_rerank_provider !== baselineSettings.vector_rerank_provider ||
      settingsForm.vector_rerank_base_url !== baselineSettings.vector_rerank_base_url ||
      settingsForm.vector_rerank_model !== baselineSettings.vector_rerank_model ||
      (settingsForm.vector_rerank_timeout_seconds ?? null) !==
        (baselineSettings.vector_rerank_timeout_seconds ?? null) ||
      (settingsForm.vector_rerank_hybrid_alpha ?? null) !== (baselineSettings.vector_rerank_hybrid_alpha ?? null) ||
      settingsForm.vector_embedding_provider !== baselineSettings.vector_embedding_provider ||
      settingsForm.vector_embedding_base_url !== baselineSettings.vector_embedding_base_url ||
      settingsForm.vector_embedding_model !== baselineSettings.vector_embedding_model ||
      settingsForm.vector_embedding_azure_deployment !== baselineSettings.vector_embedding_azure_deployment ||
      settingsForm.vector_embedding_azure_api_version !== baselineSettings.vector_embedding_azure_api_version ||
      settingsForm.vector_embedding_sentence_transformers_model !==
        baselineSettings.vector_embedding_sentence_transformers_model ||
      vectorApiKeyDirty ||
      rerankApiKeyDirty
    );
  }, [
    baselineProject,
    baselineSettings,
    projectForm,
    settingsForm,
    vectorApiKeyClearRequested,
    vectorApiKeyDraft,
    rerankApiKeyClearRequested,
    rerankApiKeyDraft,
  ]);

  useEffect(() => {
    return () => {
      if (wizardRefreshTimerRef.current !== null) window.clearTimeout(wizardRefreshTimerRef.current);
      if (projectsRefreshTimerRef.current !== null) window.clearTimeout(projectsRefreshTimerRef.current);
    };
  }, []);

  const save = useCallback(
    async (opts?: { silent?: boolean; snapshot?: SaveSnapshot }): Promise<boolean> => {
      if (!projectId) return false;
      if (savingRef.current) {
        queuedSaveRef.current = { silent: Boolean(opts?.silent), snapshot: opts?.snapshot };
        return false;
      }
      const silent = Boolean(opts?.silent);
      const snapshot = opts?.snapshot;
      const nextProjectForm = snapshot?.projectForm ?? projectForm;
      const nextSettingsForm = snapshot?.settingsForm ?? settingsForm;

      if (!baselineProject || !baselineSettings) return false;
      const projectDirty =
        nextProjectForm.name.trim() !== baselineProject.name ||
        nextProjectForm.genre.trim() !== (baselineProject.genre ?? "") ||
        nextProjectForm.logline.trim() !== (baselineProject.logline ?? "");
      const vectorApiKeyDirty = vectorApiKeyClearRequested || vectorApiKeyDraft.trim().length > 0;
      const rerankApiKeyDirty = rerankApiKeyClearRequested || rerankApiKeyDraft.trim().length > 0;
      const qpDirty = !isSameQueryPreprocess(
        queryPreprocessFromForm(nextSettingsForm),
        queryPreprocessFromBaseline(baselineSettings),
      );
      const rerankMethod = nextSettingsForm.vector_rerank_method.trim() || "auto";
      const topKRaw = !snapshot ? vectorRerankTopKDraft.trim() : "";
      const topKFromDraft = topKRaw ? Math.floor(Number(topKRaw)) : null;
      if (topKFromDraft !== null && !Number.isFinite(topKFromDraft)) {
        if (!silent) toast.toastError("rerank top_k 必须为 1-1000 的整数");
        return false;
      }
      const rerankTopK = Math.max(
        1,
        Math.min(
          1000,
          Math.floor(Number(topKFromDraft !== null ? topKFromDraft : nextSettingsForm.vector_rerank_top_k)),
        ),
      );
      if (!snapshot && topKFromDraft !== null) {
        setSettingsForm((v) => ({ ...v, vector_rerank_top_k: rerankTopK }));
        setVectorRerankTopKDraft(String(rerankTopK));
      }

      const timeoutRaw = !snapshot ? vectorRerankTimeoutDraft.trim() : "";
      let rerankTimeoutSeconds: number | null = snapshot ? nextSettingsForm.vector_rerank_timeout_seconds : null;
      if (!snapshot) {
        if (!timeoutRaw) {
          rerankTimeoutSeconds = null;
        } else {
          const next = Math.floor(Number(timeoutRaw));
          if (!Number.isFinite(next)) {
            if (!silent) toast.toastError("rerank timeout_seconds 必须为 1-120 的整数");
            return false;
          }
          rerankTimeoutSeconds = Math.max(1, Math.min(120, next));
        }
      }

      const alphaRaw = !snapshot ? vectorRerankHybridAlphaDraft.trim() : "";
      let rerankHybridAlpha: number | null = snapshot ? nextSettingsForm.vector_rerank_hybrid_alpha : null;
      if (!snapshot) {
        if (!alphaRaw) {
          rerankHybridAlpha = null;
        } else {
          const next = Number(alphaRaw);
          if (!Number.isFinite(next)) {
            if (!silent) toast.toastError("rerank alpha 必须为 0-1 的数字");
            return false;
          }
          rerankHybridAlpha = Math.max(0, Math.min(1, next));
        }
      }

      if (!snapshot) {
        setSettingsForm((v) => ({
          ...v,
          vector_rerank_timeout_seconds: rerankTimeoutSeconds,
          vector_rerank_hybrid_alpha: rerankHybridAlpha,
        }));
        setVectorRerankTimeoutDraft(rerankTimeoutSeconds != null ? String(rerankTimeoutSeconds) : "");
        setVectorRerankHybridAlphaDraft(rerankHybridAlpha != null ? String(rerankHybridAlpha) : "");
      }
      const settingsDirty =
        nextSettingsForm.world_setting !== baselineSettings.world_setting ||
        nextSettingsForm.style_guide !== baselineSettings.style_guide ||
        nextSettingsForm.constraints !== baselineSettings.constraints ||
        nextSettingsForm.context_optimizer_enabled !== baselineSettings.context_optimizer_enabled ||
        nextSettingsForm.auto_update_worldbook_enabled !== baselineSettings.auto_update_worldbook_enabled ||
        nextSettingsForm.auto_update_characters_enabled !== baselineSettings.auto_update_characters_enabled ||
        nextSettingsForm.auto_update_story_memory_enabled !== baselineSettings.auto_update_story_memory_enabled ||
        nextSettingsForm.auto_update_graph_enabled !== baselineSettings.auto_update_graph_enabled ||
        nextSettingsForm.auto_update_vector_enabled !== baselineSettings.auto_update_vector_enabled ||
        nextSettingsForm.auto_update_search_enabled !== baselineSettings.auto_update_search_enabled ||
        nextSettingsForm.auto_update_fractal_enabled !== baselineSettings.auto_update_fractal_enabled ||
        nextSettingsForm.auto_update_tables_enabled !== baselineSettings.auto_update_tables_enabled ||
        qpDirty ||
        Boolean(nextSettingsForm.vector_rerank_enabled) !== Boolean(baselineSettings.vector_rerank_effective_enabled) ||
        rerankMethod !== baselineSettings.vector_rerank_effective_method ||
        rerankTopK !== baselineSettings.vector_rerank_effective_top_k ||
        nextSettingsForm.vector_rerank_provider !== baselineSettings.vector_rerank_provider ||
        nextSettingsForm.vector_rerank_base_url !== baselineSettings.vector_rerank_base_url ||
        nextSettingsForm.vector_rerank_model !== baselineSettings.vector_rerank_model ||
        (rerankTimeoutSeconds ?? null) !== (baselineSettings.vector_rerank_timeout_seconds ?? null) ||
        (rerankHybridAlpha ?? null) !== (baselineSettings.vector_rerank_hybrid_alpha ?? null) ||
        nextSettingsForm.vector_embedding_provider !== baselineSettings.vector_embedding_provider ||
        nextSettingsForm.vector_embedding_base_url !== baselineSettings.vector_embedding_base_url ||
        nextSettingsForm.vector_embedding_model !== baselineSettings.vector_embedding_model ||
        nextSettingsForm.vector_embedding_azure_deployment !== baselineSettings.vector_embedding_azure_deployment ||
        nextSettingsForm.vector_embedding_azure_api_version !== baselineSettings.vector_embedding_azure_api_version ||
        nextSettingsForm.vector_embedding_sentence_transformers_model !==
          baselineSettings.vector_embedding_sentence_transformers_model ||
        vectorApiKeyDirty ||
        rerankApiKeyDirty;
      if (!projectDirty && !settingsDirty) return true;

      if (qpDirty) {
        const qpCfg = queryPreprocessFromForm(nextSettingsForm);
        const qpErr = validateQueryPreprocess(qpCfg);
        if (qpErr) {
          if (!silent) toast.toastError(qpErr);
          return false;
        }
      }

      if (!Number.isFinite(rerankTopK) || rerankTopK < 1 || rerankTopK > 1000) {
        if (!silent) toast.toastError("rerank top_k 必须为 1-1000 的整数");
        return false;
      }

      const scheduleWizardRefresh = () => {
        if (wizardRefreshTimerRef.current !== null) window.clearTimeout(wizardRefreshTimerRef.current);
        wizardRefreshTimerRef.current = window.setTimeout(() => void refreshWizard(), 1200);
      };
      const scheduleProjectsRefresh = () => {
        if (projectsRefreshTimerRef.current !== null) window.clearTimeout(projectsRefreshTimerRef.current);
        projectsRefreshTimerRef.current = window.setTimeout(() => void refresh(), 1200);
      };

      settingsSavePendingRef.current = settingsDirty;
      savingRef.current = true;
      setSaving(true);
      try {
        const [pRes, sRes] = await Promise.all([
          projectDirty
            ? apiJson<{ project: Project }>(`/api/projects/${projectId}`, {
                method: "PUT",
                body: JSON.stringify({
                  name: nextProjectForm.name.trim(),
                  genre: nextProjectForm.genre.trim() || null,
                  logline: nextProjectForm.logline.trim() || null,
                }),
              })
            : null,
          settingsDirty
            ? apiJson<{ settings: ProjectSettings }>(`/api/projects/${projectId}/settings`, {
                method: "PUT",
                body: JSON.stringify({
                  world_setting: nextSettingsForm.world_setting,
                  style_guide: nextSettingsForm.style_guide,
                  constraints: nextSettingsForm.constraints,
                  context_optimizer_enabled: Boolean(nextSettingsForm.context_optimizer_enabled),
                  auto_update_worldbook_enabled: Boolean(nextSettingsForm.auto_update_worldbook_enabled),
                  auto_update_characters_enabled: Boolean(nextSettingsForm.auto_update_characters_enabled),
                  auto_update_story_memory_enabled: Boolean(nextSettingsForm.auto_update_story_memory_enabled),
                  auto_update_graph_enabled: Boolean(nextSettingsForm.auto_update_graph_enabled),
                  auto_update_vector_enabled: Boolean(nextSettingsForm.auto_update_vector_enabled),
                  auto_update_search_enabled: Boolean(nextSettingsForm.auto_update_search_enabled),
                  auto_update_fractal_enabled: Boolean(nextSettingsForm.auto_update_fractal_enabled),
                  auto_update_tables_enabled: Boolean(nextSettingsForm.auto_update_tables_enabled),
                  ...(qpDirty ? { query_preprocessing: queryPreprocessFromForm(nextSettingsForm) } : {}),
                  vector_rerank_enabled: Boolean(nextSettingsForm.vector_rerank_enabled),
                  vector_rerank_method: rerankMethod,
                  vector_rerank_top_k: rerankTopK,
                  vector_rerank_provider: nextSettingsForm.vector_rerank_provider,
                  vector_rerank_base_url: nextSettingsForm.vector_rerank_base_url,
                  vector_rerank_model: nextSettingsForm.vector_rerank_model,
                  vector_rerank_timeout_seconds: rerankTimeoutSeconds,
                  vector_rerank_hybrid_alpha: rerankHybridAlpha,
                  ...(rerankApiKeyDirty
                    ? { vector_rerank_api_key: rerankApiKeyClearRequested ? "" : rerankApiKeyDraft }
                    : {}),
                  vector_embedding_provider: nextSettingsForm.vector_embedding_provider,
                  vector_embedding_base_url: nextSettingsForm.vector_embedding_base_url,
                  vector_embedding_model: nextSettingsForm.vector_embedding_model,
                  vector_embedding_azure_deployment: nextSettingsForm.vector_embedding_azure_deployment,
                  vector_embedding_azure_api_version: nextSettingsForm.vector_embedding_azure_api_version,
                  vector_embedding_sentence_transformers_model:
                    nextSettingsForm.vector_embedding_sentence_transformers_model,
                  ...(vectorApiKeyDirty
                    ? { vector_embedding_api_key: vectorApiKeyClearRequested ? "" : vectorApiKeyDraft }
                    : {}),
                }),
              })
            : null,
        ]);

        if (pRes) setBaselineProject(pRes.data.project);
        if (sRes) {
          setBaselineSettings(sRes.data.settings);
          setRerankApiKeyDraft("");
          setRerankApiKeyClearRequested(false);
          setVectorApiKeyDraft("");
          setVectorApiKeyClearRequested(false);
        }
        settingsSavePendingRef.current = false;
        markWizardProjectChanged(projectId);
        bumpWizardLocal();
        if (silent) {
          scheduleProjectsRefresh();
          scheduleWizardRefresh();
        } else {
          await refresh();
          await refreshWizard();
          toast.toastSuccess("已保存");
        }
        return true;
      } catch (e) {
        const err = e as ApiError;
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
        settingsSavePendingRef.current = false;
        return false;
      } finally {
        setSaving(false);
        savingRef.current = false;
        settingsSavePendingRef.current = false;
        if (queuedSaveRef.current) {
          const queued = queuedSaveRef.current;
          queuedSaveRef.current = null;
          void save({ silent: queued.silent, snapshot: queued.snapshot });
        }
      }
    },
    [
      baselineProject,
      baselineSettings,
      bumpWizardLocal,
      projectForm,
      projectId,
      refresh,
      refreshWizard,
      settingsForm,
      toast,
      rerankApiKeyClearRequested,
      rerankApiKeyDraft,
      vectorApiKeyClearRequested,
      vectorApiKeyDraft,
      vectorRerankTopKDraft,
      vectorRerankTimeoutDraft,
      vectorRerankHybridAlphaDraft,
    ],
  );

  useSaveHotkey(() => void save(), dirty);

  const vectorApiKeyDirty = vectorApiKeyClearRequested || vectorApiKeyDraft.trim().length > 0;
  const rerankApiKeyDirty = rerankApiKeyClearRequested || rerankApiKeyDraft.trim().length > 0;

  const runEmbeddingDryRun = useCallback(async () => {
    if (!projectId) return;
    if (saving || embeddingDryRunLoading || rerankDryRunLoading) return;

    if (dirty) {
      toast.toastError(SETTINGS_COPY.vectorRag.saveBeforeTestToast);
      return;
    }

    setEmbeddingDryRunLoading(true);
    setEmbeddingDryRunError(null);
    try {
      const res = await apiJson<{ result: VectorEmbeddingDryRunResult }>(
        `/api/projects/${projectId}/vector/embeddings/dry-run`,
        {
          method: "POST",
          body: JSON.stringify({ text: "hello world" }),
        },
      );
      setEmbeddingDryRun({ requestId: res.request_id, result: res.data.result });
      toast.toastSuccess("Embedding 测试已完成", res.request_id);
    } catch (e) {
      const err = e as ApiError;
      setEmbeddingDryRunError({ message: err.message, code: err.code, requestId: err.requestId });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setEmbeddingDryRunLoading(false);
    }
  }, [dirty, embeddingDryRunLoading, projectId, rerankDryRunLoading, saving, toast]);

  const runRerankDryRun = useCallback(async () => {
    if (!projectId) return;
    if (saving || embeddingDryRunLoading || rerankDryRunLoading) return;

    if (dirty) {
      toast.toastError(SETTINGS_COPY.vectorRag.saveBeforeTestToast);
      return;
    }

    setRerankDryRunLoading(true);
    setRerankDryRunError(null);
    try {
      const res = await apiJson<{ result: VectorRerankDryRunResult }>(
        `/api/projects/${projectId}/vector/rerank/dry-run`,
        {
          method: "POST",
          body: JSON.stringify({
            query_text: "dragon castle",
            documents: ["apple banana", "dragon castle"],
          }),
        },
      );
      setRerankDryRun({ requestId: res.request_id, result: res.data.result });
      toast.toastSuccess("Rerank 测试已完成", res.request_id);
    } catch (e) {
      const err = e as ApiError;
      setRerankDryRunError({ message: err.message, code: err.code, requestId: err.requestId });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setRerankDryRunLoading(false);
    }
  }, [dirty, embeddingDryRunLoading, projectId, rerankDryRunLoading, saving, toast]);

  useAutoSave({
    enabled: Boolean(projectId && baselineProject && baselineSettings && !vectorApiKeyDirty && !rerankApiKeyDirty),
    dirty,
    delayMs: 1200,
    getSnapshot: () => ({ projectForm: { ...projectForm }, settingsForm: { ...settingsForm } }),
    onSave: async (snapshot) => {
      await save({ silent: true, snapshot });
    },
    deps: [
      projectForm.name,
      projectForm.genre,
      projectForm.logline,
      settingsForm.world_setting,
      settingsForm.style_guide,
      settingsForm.constraints,
      settingsForm.context_optimizer_enabled,
      settingsForm.query_preprocessing_enabled,
      settingsForm.query_preprocessing_tags,
      settingsForm.query_preprocessing_exclusion_rules,
      settingsForm.query_preprocessing_index_ref_enhance,
      settingsForm.vector_rerank_enabled,
      settingsForm.vector_rerank_method,
      settingsForm.vector_rerank_top_k,
      settingsForm.vector_rerank_provider,
      settingsForm.vector_rerank_base_url,
      settingsForm.vector_rerank_model,
      settingsForm.vector_rerank_timeout_seconds,
      settingsForm.vector_rerank_hybrid_alpha,
      settingsForm.vector_embedding_provider,
      settingsForm.vector_embedding_base_url,
      settingsForm.vector_embedding_model,
      settingsForm.vector_embedding_azure_deployment,
      settingsForm.vector_embedding_azure_api_version,
      settingsForm.vector_embedding_sentence_transformers_model,
    ],
  });

  const gotoCharacters = useCallback(async () => {
    if (!projectId) return;
    if (saving) return;
    if (dirty) {
      const ok = await save();
      if (!ok) return;
    }
    navigate(`/projects/${projectId}/characters`);
  }, [dirty, navigate, projectId, save, saving]);

  const loading = settingsQuery.loading;
  const embeddingProviderPreview = (
    settingsForm.vector_embedding_provider.trim() ||
    baselineSettings?.vector_embedding_effective_provider ||
    "openai_compatible"
  ).trim();
  const queryPreprocessCfg = queryPreprocessFromForm(settingsForm);
  const queryPreprocessErr = settingsForm.query_preprocessing_enabled
    ? validateQueryPreprocess(queryPreprocessCfg)
    : null;
  const queryPreprocessErrField = getQueryPreprocessErrorField(queryPreprocessErr);

  return {
    loading,
    blockingLoadError:
      !loading && !baselineProject && !baselineSettings
        ? (loadError ?? { message: "项目加载失败", code: "UNKNOWN_ERROR" })
        : null,
    reloadAll: async () => {
      await settingsQuery.refresh();
    },
    dirty,
    outletActive,
    coreSectionsProps:
      baselineProject && baselineSettings
        ? {
            projectForm,
            setProjectForm,
            settingsForm,
            setSettingsForm,
            dirty,
            saving,
            autoUpdateMasterRef,
            autoUpdateAllEnabled,
            onSetAllAutoUpdates: setAllAutoUpdates,
            onGoToCharacters: () => void gotoCharacters(),
            onSave: () => void save(),
            baselineProject,
            baselineSettings,
            canManageMemberships,
            currentUserId: auth.user?.id ?? "unknown",
            membershipsLoading,
            membershipSaving,
            memberships,
            inviteUserId,
            onChangeInviteUserId: setInviteUserId,
            inviteRole,
            onChangeInviteRole: (role) => setInviteRole(role),
            onInviteMember: () => void inviteMember(),
            onLoadMemberships: () => void loadMemberships(),
            onUpdateMemberRole: (targetUserId, role) => void updateMemberRole(targetUserId, role),
            onRemoveMember: (targetUserId) => void removeMember(targetUserId),
          }
        : (null as never),
    vectorRagSectionProps: baselineSettings
      ? {
          projectId,
          onOpenPromptsConfig: () => {
            if (!projectId) return;
            navigate(`/projects/${projectId}/prompts#rag-config`);
          },
          baselineSettings,
          settingsForm,
          setSettingsForm,
          saving,
          dirty,
          vectorApiKeyDirty,
          rerankApiKeyDirty,
          vectorRerankTopKDraft,
          setVectorRerankTopKDraft,
          vectorRerankTimeoutDraft,
          setVectorRerankTimeoutDraft,
          vectorRerankHybridAlphaDraft,
          setVectorRerankHybridAlphaDraft,
          rerankApiKeyDraft,
          setRerankApiKeyDraft,
          rerankApiKeyClearRequested,
          setRerankApiKeyClearRequested,
          vectorApiKeyDraft,
          setVectorApiKeyDraft,
          vectorApiKeyClearRequested,
          setVectorApiKeyClearRequested,
          embeddingProviderPreview,
          embeddingDryRunLoading,
          embeddingDryRun,
          embeddingDryRunError,
          rerankDryRunLoading,
          rerankDryRun,
          rerankDryRunError,
          onRunEmbeddingDryRun: () => void runEmbeddingDryRun(),
          onRunRerankDryRun: () => void runRerankDryRun(),
        }
      : (null as never),
    queryPreprocessingSectionProps: baselineSettings
      ? {
          baselineSettings,
          settingsForm,
          setSettingsForm,
          qpPanelOpen,
          onTogglePanel: setQpPanelOpen,
          queryPreprocessErr,
          queryPreprocessErrField,
          qpPreviewQueryText,
          onChangePreviewQueryText: (value) => {
            setQpPreviewQueryText(value);
            if (projectId) qpPreviewQueryTextCache.set(projectId, value);
          },
          qpPreviewLoading,
          qpPreview,
          qpPreviewError,
          projectId,
          onRunQpPreview: () => void runQpPreview(),
          onClearQpPreview: () => {
            setQpPreview(null);
            if (projectId) qpPreviewCache.delete(projectId);
            setQpPreviewError(null);
          },
        }
      : (null as never),
    featureDefaultsSectionProps: {
      writingMemoryInjectionEnabled,
      onChangeWritingMemoryInjectionEnabled: (enabled) => saveWritingMemoryInjectionEnabled(enabled),
      onResetWritingMemoryInjectionEnabled: resetWritingMemoryInjectionEnabled,
    },
    wizardBarProps: {
      projectId,
      currentStep: "settings",
      progress: wizard.progress,
      loading: wizard.loading,
      dirty,
      saving,
      onSave: save,
    },
  };
}
