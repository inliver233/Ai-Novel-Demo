import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { RequestIdBadge } from "../components/ui/RequestIdBadge";
import { useToast } from "../components/ui/toast";
import { WizardNextBar } from "../components/atelier/WizardNextBar";
import { useAuth } from "../contexts/auth";
import { useProjects } from "../contexts/projects";
import { useAutoSave } from "../hooks/useAutoSave";
import { usePersistentOutletIsActive } from "../hooks/usePersistentOutlet";
import { useProjectData } from "../hooks/useProjectData";
import { useSaveHotkey } from "../hooks/useSaveHotkey";
import { UnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";
import { useWizardProgress } from "../hooks/useWizardProgress";
import { copyText } from "../lib/copyText";
import { humanizeMemberRole } from "../lib/humanize";
import { UI_COPY } from "../lib/uiCopy";
import { ApiError, apiJson } from "../services/apiClient";
import { getCurrentUserId } from "../services/currentUser";
import { writingMemoryInjectionEnabledStorageKey } from "../services/uiState";
import { markWizardProjectChanged } from "../services/wizard";
import type { Project, ProjectSettings, QueryPreprocessingConfig } from "../types";
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
} from "./settings/models";

const qpPreviewCache = new Map<string, QpPreviewState>();
const qpPreviewQueryTextCache = new Map<string, string>();

export function SettingsPage() {
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

  const parseLineList = useCallback((raw: string) => {
    return (raw || "")
      .split(/\r?\n/)
      .map((v) => v.trim())
      .filter((v) => Boolean(v));
  }, []);

  const queryPreprocessFromForm = useCallback(
    (form: SettingsForm): QueryPreprocessingConfig => {
      return {
        enabled: Boolean(form.query_preprocessing_enabled),
        tags: parseLineList(form.query_preprocessing_tags),
        exclusion_rules: parseLineList(form.query_preprocessing_exclusion_rules),
        index_ref_enhance: Boolean(form.query_preprocessing_index_ref_enhance),
      };
    },
    [parseLineList],
  );

  const queryPreprocessFromBaseline = useCallback((settings: ProjectSettings): QueryPreprocessingConfig => {
    const cfg = settings.query_preprocessing_effective;
    return {
      enabled: Boolean(cfg?.enabled),
      tags: Array.isArray(cfg?.tags) ? cfg.tags.map((v) => String(v)) : [],
      exclusion_rules: Array.isArray(cfg?.exclusion_rules) ? cfg.exclusion_rules.map((v) => String(v)) : [],
      index_ref_enhance: Boolean(cfg?.index_ref_enhance),
    };
  }, []);

  const isSameStringList = useCallback((a: string[], b: string[]) => {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) {
      if (a[i] !== b[i]) return false;
    }
    return true;
  }, []);

  const isSameQueryPreprocess = useCallback(
    (a: QueryPreprocessingConfig, b: QueryPreprocessingConfig) => {
      return (
        Boolean(a.enabled) === Boolean(b.enabled) &&
        Boolean(a.index_ref_enhance) === Boolean(b.index_ref_enhance) &&
        isSameStringList(a.tags ?? [], b.tags ?? []) &&
        isSameStringList(a.exclusion_rules ?? [], b.exclusion_rules ?? [])
      );
    },
    [isSameStringList],
  );

  const validateQueryPreprocess = useCallback((cfg: QueryPreprocessingConfig) => {
    if ((cfg.tags ?? []).length > 50) return "tags 最多 50 条（每行一条）";
    for (const tag of cfg.tags ?? []) {
      if (!tag.trim()) return "tags 不能包含空行";
      if (tag.length > 64) return "tag 过长（最多 64 字符）";
    }
    if ((cfg.exclusion_rules ?? []).length > 50) return "exclusion_rules 最多 50 条（每行一条）";
    for (const rule of cfg.exclusion_rules ?? []) {
      if (!rule.trim()) return "exclusion_rules 不能包含空行";
      if (rule.length > 256) return "exclusion_rule 过长（最多 256 字符）";
    }
    return null;
  }, []);

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
    isSameQueryPreprocess,
    projectForm,
    queryPreprocessFromBaseline,
    queryPreprocessFromForm,
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
      isSameQueryPreprocess,
      projectForm,
      projectId,
      queryPreprocessFromBaseline,
      queryPreprocessFromForm,
      refresh,
      refreshWizard,
      settingsForm,
      toast,
      validateQueryPreprocess,
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
      toast.toastError("请先保存设置后再测试（测试使用已保存配置）");
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
      toast.toastError("请先保存设置后再测试（测试使用已保存配置）");
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
  if (loading) {
    return (
      <div className="grid gap-6 pb-24" aria-busy="true" aria-live="polite">
        <span className="sr-only">正在加载设置…</span>
        <section className="panel p-6">
          <div className="flex items-start justify-between gap-4">
            <div className="grid gap-2">
              <div className="skeleton h-6 w-32" />
              <div className="skeleton h-4 w-56" />
            </div>
            <div className="skeleton h-9 w-40" />
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <div className="grid gap-1 sm:col-span-1">
              <div className="skeleton h-4 w-16" />
              <div className="skeleton h-10 w-full" />
            </div>
            <div className="grid gap-1 sm:col-span-1">
              <div className="skeleton h-4 w-16" />
              <div className="skeleton h-10 w-full" />
            </div>
            <div className="grid gap-1 sm:col-span-3">
              <div className="skeleton h-4 w-40" />
              <div className="skeleton h-16 w-full" />
            </div>
          </div>
        </section>

        <section className="panel p-6">
          <div className="grid gap-2">
            <div className="skeleton h-6 w-44" />
            <div className="skeleton h-4 w-72" />
          </div>
          <div className="mt-4 grid gap-4">
            <div className="skeleton h-28 w-full" />
            <div className="skeleton h-28 w-full" />
            <div className="skeleton h-28 w-full" />
          </div>
        </section>

        <section className="panel p-6">
          <div className="grid gap-2">
            <div className="skeleton h-6 w-48" />
            <div className="skeleton h-4 w-full max-w-2xl" />
            <div className="skeleton h-4 w-full max-w-xl" />
          </div>
        </section>

        <section className="panel p-6">
          <div className="grid gap-2">
            <div className="skeleton h-6 w-56" />
            <div className="skeleton h-4 w-full max-w-2xl" />
            <div className="skeleton h-4 w-full max-w-xl" />
          </div>
        </section>

        <section className="panel p-6">
          <div className="grid gap-2">
            <div className="skeleton h-6 w-56" />
            <div className="skeleton h-4 w-full max-w-2xl" />
            <div className="skeleton h-4 w-full max-w-xl" />
          </div>
        </section>

        <section className="panel p-6">
          <div className="grid gap-2">
            <div className="skeleton h-6 w-60" />
            <div className="skeleton h-4 w-full max-w-2xl" />
            <div className="skeleton h-4 w-full max-w-xl" />
          </div>
        </section>
      </div>
    );
  }

  if (!baselineProject || !baselineSettings) {
    return (
      <div className="grid gap-6 pb-24">
        <div className="error-card">
          <div className="state-title">加载失败</div>
          <div className="state-desc">{loadError ? `${loadError.message} (${loadError.code})` : "项目加载失败"}</div>
          {loadError?.requestId ? (
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
            <button className="btn btn-primary" onClick={() => void settingsQuery.refresh()} type="button">
              重试
            </button>
          </div>
        </div>
      </div>
    );
  }

  const embeddingProviderPreview = (
    settingsForm.vector_embedding_provider.trim() ||
    baselineSettings.vector_embedding_effective_provider ||
    "openai_compatible"
  ).trim();
  const queryPreprocessCfg = queryPreprocessFromForm(settingsForm);
  const queryPreprocessErr = settingsForm.query_preprocessing_enabled
    ? validateQueryPreprocess(queryPreprocessCfg)
    : null;
  const queryPreprocessErrField = queryPreprocessErr
    ? queryPreprocessErr.startsWith("tags") || queryPreprocessErr.startsWith("tag")
      ? "tags"
      : queryPreprocessErr.startsWith("exclusion_rule") || queryPreprocessErr.startsWith("exclusion_rules")
        ? "exclusion_rules"
        : null
    : null;

  return (
    <div className="grid gap-6 pb-24">
      {dirty && outletActive ? <UnsavedChangesGuard when={dirty} /> : null}
      <section className="panel p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="grid gap-2">
            <div className="font-content text-xl">项目信息</div>
            <div className="text-xs text-subtext">名称 / 题材 / 一句话梗概（logline）</div>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <button className="btn btn-secondary" disabled={saving} onClick={() => void gotoCharacters()} type="button">
              {dirty ? "保存并下一步：角色卡" : "下一步：角色卡"}
            </button>
            <button className="btn btn-primary" disabled={!dirty || saving} onClick={() => void save()} type="button">
              保存
            </button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <label className="grid gap-1 sm:col-span-1">
            <span className="text-xs text-subtext">项目名</span>
            <input
              className="input"
              name="project_name"
              value={projectForm.name}
              onChange={(e) => setProjectForm((v) => ({ ...v, name: e.target.value }))}
            />
          </label>
          <label className="grid gap-1 sm:col-span-1">
            <span className="text-xs text-subtext">题材</span>
            <input
              className="input"
              name="project_genre"
              value={projectForm.genre}
              onChange={(e) => setProjectForm((v) => ({ ...v, genre: e.target.value }))}
            />
          </label>
          <label className="grid gap-1 sm:col-span-3">
            <span className="text-xs text-subtext">一句话梗概（logline）</span>
            <textarea
              className="textarea"
              name="project_logline"
              rows={2}
              value={projectForm.logline}
              onChange={(e) => setProjectForm((v) => ({ ...v, logline: e.target.value }))}
            />
          </label>
        </div>
      </section>

      <section className="panel p-6">
        <div className="grid gap-1">
          <div className="font-content text-xl">创作设定（必填）</div>
          <div className="text-xs text-subtext">写作/大纲生成会引用这里的内容；建议尽量具体。</div>
        </div>
        <div className="mt-4 grid gap-4">
          <label className="grid gap-1">
            <span className="text-xs text-subtext">世界观</span>
            <textarea
              className="textarea atelier-content"
              name="world_setting"
              rows={6}
              value={settingsForm.world_setting}
              onChange={(e) => setSettingsForm((v) => ({ ...v, world_setting: e.target.value }))}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-subtext">风格</span>
            <textarea
              className="textarea atelier-content"
              name="style_guide"
              rows={6}
              value={settingsForm.style_guide}
              onChange={(e) => setSettingsForm((v) => ({ ...v, style_guide: e.target.value }))}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-subtext">约束</span>
            <textarea
              className="textarea atelier-content"
              name="constraints"
              rows={6}
              value={settingsForm.constraints}
              onChange={(e) => setSettingsForm((v) => ({ ...v, constraints: e.target.value }))}
            />
          </label>
        </div>
      </section>

      <section className="panel p-6">
        <div className="grid gap-1">
          <div className="font-content text-xl">自动更新（推荐）</div>
          <div className="text-xs text-subtext">章节定稿（done）后自动触发后台更新任务；普通用户建议保持开启。</div>
        </div>

        <div className="mt-4 grid gap-2">
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              ref={autoUpdateMasterRef}
              className="checkbox"
              checked={autoUpdateAllEnabled}
              onChange={(e) => setAllAutoUpdates(e.target.checked)}
              type="checkbox"
            />
            一键开关：自动更新（章节定稿后触发）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_worldbook_enabled}
              onChange={(e) => setSettingsForm((v) => ({ ...v, auto_update_worldbook_enabled: e.target.checked }))}
              type="checkbox"
            />
            世界书：自动更新条目（worldbook_auto_update）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_characters_enabled}
              onChange={(e) => setSettingsForm((v) => ({ ...v, auto_update_characters_enabled: e.target.checked }))}
              type="checkbox"
            />
            角色卡：自动更新（characters_auto_update）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_story_memory_enabled}
              onChange={(e) => setSettingsForm((v) => ({ ...v, auto_update_story_memory_enabled: e.target.checked }))}
              type="checkbox"
            />
            剧情记忆：自动分析并写入（plot_auto_update）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_graph_enabled}
              onChange={(e) => setSettingsForm((v) => ({ ...v, auto_update_graph_enabled: e.target.checked }))}
              type="checkbox"
            />
            图谱：自动更新（graph_auto_update）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_vector_enabled}
              onChange={(e) => setSettingsForm((v) => ({ ...v, auto_update_vector_enabled: e.target.checked }))}
              type="checkbox"
            />
            向量索引：自动重建（vector_rebuild）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_search_enabled}
              onChange={(e) => setSettingsForm((v) => ({ ...v, auto_update_search_enabled: e.target.checked }))}
              type="checkbox"
            />
            搜索索引：自动重建（search_rebuild）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_fractal_enabled}
              onChange={(e) => setSettingsForm((v) => ({ ...v, auto_update_fractal_enabled: e.target.checked }))}
              type="checkbox"
            />
            分形记忆：自动重建（fractal_rebuild）
          </label>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              className="checkbox"
              checked={settingsForm.auto_update_tables_enabled}
              onChange={(e) => setSettingsForm((v) => ({ ...v, auto_update_tables_enabled: e.target.checked }))}
              type="checkbox"
            />
            数值表格：自动更新（table_ai_update）
          </label>
        </div>

        <div className="mt-2 text-xs text-subtext">
          提示：关闭后不会在「章节定稿」时自动排队；仍可在对应页面/任务中心手动触发。
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            className="btn btn-secondary btn-sm"
            disabled={saving}
            onClick={() =>
              setSettingsForm((v) => ({
                ...v,
                auto_update_worldbook_enabled: true,
                auto_update_characters_enabled: true,
                auto_update_story_memory_enabled: true,
                auto_update_graph_enabled: true,
                auto_update_vector_enabled: true,
                auto_update_search_enabled: true,
                auto_update_fractal_enabled: true,
                auto_update_tables_enabled: true,
              }))
            }
            type="button"
          >
            全部开启（推荐）
          </button>
        </div>
      </section>

      <details className="panel" aria-label="向量检索（Vector RAG）">
        <summary className="ui-focus-ring ui-transition-fast cursor-pointer select-none p-6">
          <div className="grid gap-1">
            <div className="font-content text-xl text-ink">{UI_COPY.vectorRag.title}</div>
            <div className="text-xs text-subtext">{UI_COPY.vectorRag.subtitle}</div>
            <div className="text-xs text-subtext">{UI_COPY.vectorRag.apiKeyHint}</div>
          </div>
        </summary>

        <div className="px-6 pb-6 pt-0">
          <div className="mt-4 grid gap-4">
            {projectId ? (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-atelier border border-border bg-canvas p-4 text-xs text-subtext">
                <div className="min-w-0">
                  配置入口已迁移到「模型配置」页（向量检索）。建议在那边完成 Embedding/Rerank
                  配置后再回到这里查看生效状态。
                </div>
                <button
                  className="btn btn-secondary"
                  onClick={() => navigate(`/projects/${projectId}/prompts#rag-config`)}
                  type="button"
                >
                  打开模型配置
                </button>
              </div>
            ) : null}

            <div className="rounded-atelier border border-border bg-canvas p-4 text-xs text-subtext">
              <div className="font-medium text-ink">配置说明（Embedding vs Rerank）</div>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                <li>
                  <span className="font-mono">Embedding</span> 用于向量化（索引/召回）；
                  <span className="font-mono">Rerank</span>{" "}
                  用于对候选片段做二次排序。两者可分别配置（provider/base_url/model/api_key 可不同）。
                </li>
                <li>
                  保存后可用上方 “测试 embedding / 测试 rerank” 做 <span className="font-mono">dry-run</span>{" "}
                  自检（会返回 request_id，便于看后端日志排障）。
                </li>
                <li>
                  验证是否生效：到项目内「RAG」页运行 Query；结果面板会显示 <span className="font-mono">rerank:</span>{" "}
                  概要，并可展开 <span className="font-mono">rerank_obs</span> 查看详情。
                </li>
              </ul>
            </div>

            <div className="rounded-atelier border border-border bg-canvas p-4 text-xs text-subtext">
              <div>
                当前生效：Embedding 提供方（provider）=
                {baselineSettings.vector_embedding_effective_provider || "openai_compatible"}
                （状态: {baselineSettings.vector_embedding_effective_disabled_reason ?? "enabled"}；来源:{" "}
                {baselineSettings.vector_embedding_effective_source}）
              </div>
              <div className="mt-1">
                Rerank：{baselineSettings.vector_rerank_effective_enabled ? "enabled" : "disabled"}（method:{" "}
                {baselineSettings.vector_rerank_effective_method}；provider:{" "}
                {baselineSettings.vector_rerank_effective_provider || "（空）"}；model:{" "}
                {baselineSettings.vector_rerank_effective_model || "（空）"}；top_k:{" "}
                {baselineSettings.vector_rerank_effective_top_k}；alpha:{" "}
                {baselineSettings.vector_rerank_effective_hybrid_alpha ?? 0}
                ；来源: {baselineSettings.vector_rerank_effective_source}；配置:{" "}
                {baselineSettings.vector_rerank_effective_config_source}）
              </div>
            </div>

            <div className="rounded-atelier border border-border bg-canvas p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="text-sm text-ink">测试配置（dry-run）</div>
                <div className="flex flex-wrap gap-2">
                  <button
                    className="btn btn-secondary"
                    disabled={
                      saving ||
                      dirty ||
                      embeddingDryRunLoading ||
                      rerankDryRunLoading ||
                      vectorApiKeyDirty ||
                      rerankApiKeyDirty
                    }
                    onClick={() => void runEmbeddingDryRun()}
                    type="button"
                  >
                    {embeddingDryRunLoading ? "测试 embedding…" : "测试 embedding"}
                  </button>
                  <button
                    className="btn btn-secondary"
                    disabled={
                      saving ||
                      dirty ||
                      embeddingDryRunLoading ||
                      rerankDryRunLoading ||
                      vectorApiKeyDirty ||
                      rerankApiKeyDirty
                    }
                    onClick={() => void runRerankDryRun()}
                    type="button"
                  >
                    {rerankDryRunLoading ? "测试 rerank…" : "测试 rerank"}
                  </button>
                </div>
              </div>
              {dirty || vectorApiKeyDirty || rerankApiKeyDirty ? (
                <div className="mt-1 text-[11px] text-subtext">提示：测试使用已保存配置；请先保存当前设置。</div>
              ) : null}

              {embeddingDryRunError ? (
                <div className="mt-3 rounded-atelier border border-border bg-surface p-3">
                  <div className="text-xs text-red-600 dark:text-red-300">
                    Embedding 测试失败：{embeddingDryRunError.message} ({embeddingDryRunError.code})
                  </div>
                  <RequestIdBadge requestId={embeddingDryRunError.requestId} className="mt-2" />
                  <div className="mt-1 text-[11px] text-subtext">
                    排障：检查 embedding base_url/model/api_key；打开后端日志并搜索 request_id。
                  </div>
                </div>
              ) : null}

              {embeddingDryRun ? (
                <div className="mt-3 rounded-atelier border border-border bg-surface p-3">
                  <div className="text-xs text-subtext">
                    Embedding：{embeddingDryRun.result.enabled ? "enabled" : "disabled"}；dims:
                    {embeddingDryRun.result.dims ?? "（未知）"}；耗时:
                    {embeddingDryRun.result.timings_ms?.total ?? "（未知）"}ms
                    {embeddingDryRun.result.error ? `；error: ${embeddingDryRun.result.error}` : ""}
                  </div>
                  <RequestIdBadge requestId={embeddingDryRun.requestId} className="mt-2" />
                </div>
              ) : null}

              {rerankDryRunError ? (
                <div className="mt-3 rounded-atelier border border-border bg-surface p-3">
                  <div className="text-xs text-red-600 dark:text-red-300">
                    Rerank 测试失败：{rerankDryRunError.message} ({rerankDryRunError.code})
                  </div>
                  <RequestIdBadge requestId={rerankDryRunError.requestId} className="mt-2" />
                  <div className="mt-1 text-[11px] text-subtext">
                    排障：检查 rerank base_url/model/api_key；若使用 external_rerank_api，确认 /v1/rerank 可访问。
                  </div>
                </div>
              ) : null}

              {rerankDryRun ? (
                <div className="mt-3 rounded-atelier border border-border bg-surface p-3">
                  <div className="text-xs text-subtext">
                    Rerank：{rerankDryRun.result.enabled ? "enabled" : "disabled"}；method:
                    {rerankDryRun.result.method ?? "（未知）"}
                    ；provider:
                    {(rerankDryRun.result.rerank as { provider?: string } | undefined)?.provider ?? "（未知）"}
                    ；耗时:{rerankDryRun.result.timings_ms?.total ?? "（未知）"}ms；order:
                    {(rerankDryRun.result.order ?? []).join(" → ") || "（空）"}
                  </div>
                  <RequestIdBadge requestId={rerankDryRun.requestId} className="mt-2" />
                </div>
              ) : null}
            </div>

            <div className="grid gap-2">
              <div className="text-sm text-ink">{UI_COPY.vectorRag.rerankTitle}</div>
              <div className="grid gap-4 sm:grid-cols-3">
                <label className="flex items-center gap-2 text-sm text-ink sm:col-span-3">
                  <input
                    className="checkbox"
                    checked={settingsForm.vector_rerank_enabled}
                    onChange={(e) => setSettingsForm((v) => ({ ...v, vector_rerank_enabled: e.target.checked }))}
                    type="checkbox"
                  />
                  启用 rerank（对候选片段做相关性重排）
                </label>
                <label className="grid gap-1 sm:col-span-2">
                  <span className="text-xs text-subtext">重排算法（rerank method）</span>
                  <select
                    className="select"
                    id="settings_vector_rerank_method"
                    name="vector_rerank_method"
                    aria-label="settings_vector_rerank_method"
                    value={settingsForm.vector_rerank_method}
                    onChange={(e) => setSettingsForm((v) => ({ ...v, vector_rerank_method: e.target.value }))}
                  >
                    <option value="auto">auto</option>
                    <option value="rapidfuzz_token_set_ratio">rapidfuzz_token_set_ratio</option>
                    <option value="token_overlap">token_overlap</option>
                  </select>
                </label>
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">候选数量（top_k）</span>
                  <input
                    className="input"
                    id="settings_vector_rerank_top_k"
                    name="vector_rerank_top_k"
                    aria-label="settings_vector_rerank_top_k"
                    type="number"
                    min={1}
                    max={1000}
                    value={vectorRerankTopKDraft}
                    onBlur={() => {
                      const raw = vectorRerankTopKDraft.trim();
                      if (!raw) {
                        setVectorRerankTopKDraft(String(settingsForm.vector_rerank_top_k));
                        return;
                      }
                      const next = Math.floor(Number(raw));
                      if (!Number.isFinite(next)) {
                        setVectorRerankTopKDraft(String(settingsForm.vector_rerank_top_k));
                        return;
                      }
                      const clamped = Math.max(1, Math.min(1000, next));
                      setSettingsForm((v) => ({ ...v, vector_rerank_top_k: clamped }));
                      setVectorRerankTopKDraft(String(clamped));
                    }}
                    onChange={(e) => setVectorRerankTopKDraft(e.target.value)}
                  />
                </label>
              </div>
              <div className="text-[11px] text-subtext">
                提示：启用后会对候选结果做二次排序，通常命中更好，但可能增加耗时/成本。
              </div>

              <details className="rounded-atelier border border-border bg-canvas p-4" aria-label="Rerank 提供方配置">
                <summary className="ui-transition-fast cursor-pointer select-none text-sm text-ink hover:text-ink">
                  {UI_COPY.vectorRag.rerankConfigDetailsTitle}
                </summary>
                <div className="mt-4 grid gap-4">
                  <div className="text-xs text-subtext">不确定怎么配时，可保持留空让后端从环境变量读取。</div>

                  <label className="grid gap-1">
                    <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankProviderLabel}</span>
                    <select
                      className="select"
                      id="settings_vector_rerank_provider"
                      name="vector_rerank_provider"
                      aria-label="settings_vector_rerank_provider"
                      value={settingsForm.vector_rerank_provider}
                      onChange={(e) => setSettingsForm((v) => ({ ...v, vector_rerank_provider: e.target.value }))}
                    >
                      <option value="">（使用后端环境变量）</option>
                      <option value="external_rerank_api">external_rerank_api</option>
                    </select>
                    <div className="text-[11px] text-subtext">
                      当前有效：{baselineSettings.vector_rerank_effective_provider || "（空）"}
                    </div>
                  </label>

                  <label className="grid gap-1">
                    <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankBaseUrlLabel}</span>
                    <input
                      className="input"
                      id="settings_vector_rerank_base_url"
                      name="vector_rerank_base_url"
                      aria-label="settings_vector_rerank_base_url"
                      value={settingsForm.vector_rerank_base_url}
                      onChange={(e) => {
                        const next = e.target.value;
                        setSettingsForm((v) => {
                          const shouldAutoSetProvider = !v.vector_rerank_provider.trim() && next.trim().length > 0;
                          return {
                            ...v,
                            vector_rerank_base_url: next,
                            ...(shouldAutoSetProvider ? { vector_rerank_provider: "external_rerank_api" } : {}),
                          };
                        });
                      }}
                    />
                    <div className="text-[11px] text-subtext">
                      当前有效：{baselineSettings.vector_rerank_effective_base_url || "（空）"}
                    </div>
                  </label>

                  <label className="grid gap-1">
                    <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankModelLabel}</span>
                    <input
                      className="input"
                      id="settings_vector_rerank_model"
                      name="vector_rerank_model"
                      aria-label="settings_vector_rerank_model"
                      value={settingsForm.vector_rerank_model}
                      onChange={(e) => setSettingsForm((v) => ({ ...v, vector_rerank_model: e.target.value }))}
                    />
                    <div className="text-[11px] text-subtext">
                      当前有效：{baselineSettings.vector_rerank_effective_model || "（空）"}
                    </div>
                  </label>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="grid gap-1">
                      <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankTimeoutLabel}</span>
                      <input
                        className="input"
                        id="settings_vector_rerank_timeout_seconds"
                        name="vector_rerank_timeout_seconds"
                        aria-label="settings_vector_rerank_timeout_seconds"
                        type="number"
                        min={1}
                        max={120}
                        value={vectorRerankTimeoutDraft}
                        onBlur={() => {
                          const raw = vectorRerankTimeoutDraft.trim();
                          if (!raw) {
                            setSettingsForm((v) => ({ ...v, vector_rerank_timeout_seconds: null }));
                            setVectorRerankTimeoutDraft("");
                            return;
                          }
                          const next = Math.floor(Number(raw));
                          if (!Number.isFinite(next)) {
                            setVectorRerankTimeoutDraft(
                              settingsForm.vector_rerank_timeout_seconds != null
                                ? String(settingsForm.vector_rerank_timeout_seconds)
                                : "",
                            );
                            return;
                          }
                          const clamped = Math.max(1, Math.min(120, next));
                          setSettingsForm((v) => ({ ...v, vector_rerank_timeout_seconds: clamped }));
                          setVectorRerankTimeoutDraft(String(clamped));
                        }}
                        onChange={(e) => setVectorRerankTimeoutDraft(e.target.value)}
                      />
                      <div className="text-[11px] text-subtext">
                        当前有效：{baselineSettings.vector_rerank_effective_timeout_seconds ?? 15}
                      </div>
                    </label>

                    <label className="grid gap-1">
                      <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankHybridAlphaLabel}</span>
                      <input
                        className="input"
                        id="settings_vector_rerank_hybrid_alpha"
                        name="vector_rerank_hybrid_alpha"
                        aria-label="settings_vector_rerank_hybrid_alpha"
                        type="number"
                        min={0}
                        max={1}
                        step={0.05}
                        value={vectorRerankHybridAlphaDraft}
                        onBlur={() => {
                          const raw = vectorRerankHybridAlphaDraft.trim();
                          if (!raw) {
                            setSettingsForm((v) => ({ ...v, vector_rerank_hybrid_alpha: null }));
                            setVectorRerankHybridAlphaDraft("");
                            return;
                          }
                          const next = Number(raw);
                          if (!Number.isFinite(next)) {
                            setVectorRerankHybridAlphaDraft(
                              settingsForm.vector_rerank_hybrid_alpha != null
                                ? String(settingsForm.vector_rerank_hybrid_alpha)
                                : "",
                            );
                            return;
                          }
                          const clamped = Math.max(0, Math.min(1, next));
                          setSettingsForm((v) => ({ ...v, vector_rerank_hybrid_alpha: clamped }));
                          setVectorRerankHybridAlphaDraft(String(clamped));
                        }}
                        onChange={(e) => setVectorRerankHybridAlphaDraft(e.target.value)}
                      />
                      <div className="text-[11px] text-subtext">
                        当前有效：{baselineSettings.vector_rerank_effective_hybrid_alpha ?? 0}
                      </div>
                    </label>
                  </div>

                  <label className="grid gap-1">
                    <span className="text-xs text-subtext">{UI_COPY.vectorRag.rerankApiKeyLabel}</span>
                    <input
                      className="input"
                      id="settings_vector_rerank_api_key"
                      name="vector_rerank_api_key"
                      aria-label="settings_vector_rerank_api_key"
                      type="password"
                      autoComplete="off"
                      value={rerankApiKeyDraft}
                      onChange={(e) => {
                        setRerankApiKeyDraft(e.target.value);
                        setRerankApiKeyClearRequested(false);
                      }}
                    />
                    <div className="text-[11px] text-subtext">
                      已保存（项目覆盖）：
                      {baselineSettings.vector_rerank_has_api_key
                        ? baselineSettings.vector_rerank_masked_api_key
                        : "（无）"}
                      {baselineSettings.vector_rerank_effective_has_api_key
                        ? ` | 当前有效：${baselineSettings.vector_rerank_effective_masked_api_key}`
                        : " | 当前有效：（无）"}
                      {rerankApiKeyClearRequested ? " | 将在保存时清除" : ""}
                    </div>
                  </label>

                  <div className="flex flex-wrap gap-2">
                    <button
                      className="btn btn-secondary"
                      aria-label="settings_vector_rerank_api_key_clear"
                      disabled={saving || !baselineSettings.vector_rerank_has_api_key}
                      onClick={() => {
                        setRerankApiKeyDraft("");
                        setRerankApiKeyClearRequested(true);
                      }}
                      type="button"
                    >
                      {UI_COPY.vectorRag.rerankClearApiKey}
                    </button>
                    <button
                      className="btn btn-secondary"
                      aria-label="settings_vector_rerank_reset_overrides"
                      disabled={saving}
                      onClick={() => {
                        setSettingsForm((v) => ({
                          ...v,
                          vector_rerank_provider: "",
                          vector_rerank_base_url: "",
                          vector_rerank_model: "",
                          vector_rerank_timeout_seconds: null,
                          vector_rerank_hybrid_alpha: null,
                        }));
                        setVectorRerankTimeoutDraft("");
                        setVectorRerankHybridAlphaDraft("");
                        setRerankApiKeyDraft("");
                        setRerankApiKeyClearRequested(true);
                      }}
                      type="button"
                    >
                      {UI_COPY.vectorRag.rerankResetOverrides}
                    </button>
                  </div>
                </div>
              </details>
            </div>

            <details className="rounded-atelier border border-border bg-canvas p-4">
              <summary className="ui-transition-fast cursor-pointer select-none text-sm text-ink hover:text-ink">
                {UI_COPY.vectorRag.embeddingTitle}
              </summary>
              <div className="mt-4 grid gap-4">
                <div className="text-xs text-subtext">不确定怎么配时，可保持留空让后端从环境变量读取。</div>

                <label className="grid gap-1">
                  <span className="text-xs text-subtext">
                    Embedding 提供方（provider；项目覆盖；留空=使用后端环境变量）
                  </span>
                  <select
                    className="select"
                    value={settingsForm.vector_embedding_provider}
                    onChange={(e) => setSettingsForm((v) => ({ ...v, vector_embedding_provider: e.target.value }))}
                  >
                    <option value="">（使用后端环境变量）</option>
                    <option value="openai_compatible">openai_compatible</option>
                    <option value="azure_openai">azure_openai</option>
                    <option value="google">google</option>
                    <option value="custom">custom</option>
                    <option value="local_proxy">local_proxy</option>
                    <option value="sentence_transformers">sentence_transformers</option>
                  </select>
                  <div className="text-[11px] text-subtext">
                    当前有效：{baselineSettings.vector_embedding_effective_provider || "openai_compatible"}
                  </div>
                </label>

                {embeddingProviderPreview === "azure_openai" ? (
                  <div className="grid gap-4 sm:grid-cols-2">
                    <label className="grid gap-1">
                      <span className="text-xs text-subtext">
                        Azure 部署名（deployment；项目覆盖；留空=使用后端环境变量）
                      </span>
                      <input
                        className="input"
                        value={settingsForm.vector_embedding_azure_deployment}
                        onChange={(e) =>
                          setSettingsForm((v) => ({ ...v, vector_embedding_azure_deployment: e.target.value }))
                        }
                      />
                      <div className="text-[11px] text-subtext">
                        当前有效：{baselineSettings.vector_embedding_effective_azure_deployment || "（空）"}
                      </div>
                    </label>
                    <label className="grid gap-1">
                      <span className="text-xs text-subtext">
                        Azure API 版本（api_version；项目覆盖；留空=使用后端环境变量）
                      </span>
                      <input
                        className="input"
                        value={settingsForm.vector_embedding_azure_api_version}
                        onChange={(e) =>
                          setSettingsForm((v) => ({ ...v, vector_embedding_azure_api_version: e.target.value }))
                        }
                      />
                      <div className="text-[11px] text-subtext">
                        当前有效：{baselineSettings.vector_embedding_effective_azure_api_version || "（空）"}
                      </div>
                    </label>
                  </div>
                ) : null}

                {embeddingProviderPreview === "sentence_transformers" ? (
                  <label className="grid gap-1">
                    <span className="text-xs text-subtext">
                      SentenceTransformers 模型（项目覆盖；留空=使用后端环境变量）
                    </span>
                    <input
                      className="input"
                      value={settingsForm.vector_embedding_sentence_transformers_model}
                      onChange={(e) =>
                        setSettingsForm((v) => ({ ...v, vector_embedding_sentence_transformers_model: e.target.value }))
                      }
                    />
                    <div className="text-[11px] text-subtext">
                      当前有效：{baselineSettings.vector_embedding_effective_sentence_transformers_model || "（空）"}
                    </div>
                  </label>
                ) : null}

                <label className="grid gap-1">
                  <span className="text-xs text-subtext">
                    Embedding 基础地址（base_url；项目覆盖；留空=使用后端环境变量）
                  </span>
                  <input
                    className="input"
                    id="vector_embedding_base_url"
                    name="vector_embedding_base_url"
                    value={settingsForm.vector_embedding_base_url}
                    onChange={(e) => setSettingsForm((v) => ({ ...v, vector_embedding_base_url: e.target.value }))}
                  />
                  <div className="text-[11px] text-subtext">
                    当前有效：{baselineSettings.vector_embedding_effective_base_url || "（空）"}
                  </div>
                </label>

                <label className="grid gap-1">
                  <span className="text-xs text-subtext">Embedding 模型（model；项目覆盖；留空=使用后端环境变量）</span>
                  <input
                    className="input"
                    id="vector_embedding_model"
                    name="vector_embedding_model"
                    value={settingsForm.vector_embedding_model}
                    onChange={(e) => setSettingsForm((v) => ({ ...v, vector_embedding_model: e.target.value }))}
                  />
                  <div className="text-[11px] text-subtext">
                    当前有效：{baselineSettings.vector_embedding_effective_model || "（空）"}
                  </div>
                </label>

                <label className="grid gap-1">
                  <span className="text-xs text-subtext">API Key（api_key；项目覆盖；留空不修改）</span>
                  <input
                    className="input"
                    id="vector_embedding_api_key"
                    name="vector_embedding_api_key"
                    type="password"
                    autoComplete="off"
                    value={vectorApiKeyDraft}
                    onChange={(e) => {
                      setVectorApiKeyDraft(e.target.value);
                      setVectorApiKeyClearRequested(false);
                    }}
                  />
                  <div className="text-[11px] text-subtext">
                    已保存（项目覆盖）：
                    {baselineSettings.vector_embedding_has_api_key
                      ? baselineSettings.vector_embedding_masked_api_key
                      : "（无）"}
                    {baselineSettings.vector_embedding_effective_has_api_key
                      ? ` | 当前有效：${baselineSettings.vector_embedding_effective_masked_api_key}`
                      : " | 当前有效：（无）"}
                    {vectorApiKeyClearRequested ? " | 将在保存时清除" : ""}
                  </div>
                </label>

                <div className="flex flex-wrap gap-2">
                  <button
                    className="btn btn-secondary"
                    disabled={saving || !baselineSettings.vector_embedding_has_api_key}
                    onClick={() => {
                      setVectorApiKeyDraft("");
                      setVectorApiKeyClearRequested(true);
                    }}
                    type="button"
                  >
                    清除项目级 API Key
                  </button>
                  <button
                    className="btn btn-secondary"
                    disabled={saving}
                    onClick={() => {
                      setSettingsForm((v) => ({
                        ...v,
                        vector_embedding_provider: "",
                        vector_embedding_base_url: "",
                        vector_embedding_model: "",
                        vector_embedding_azure_deployment: "",
                        vector_embedding_azure_api_version: "",
                        vector_embedding_sentence_transformers_model: "",
                      }));
                      setVectorApiKeyDraft("");
                      setVectorApiKeyClearRequested(true);
                    }}
                    type="button"
                  >
                    恢复使用后端环境变量（清除项目覆盖）
                  </button>
                </div>
              </div>
            </details>
          </div>
        </div>
      </details>

      <details
        className="panel"
        aria-label="Query 预处理（Query Preprocessing）"
        open={qpPanelOpen}
        onToggle={(e) => setQpPanelOpen((e.currentTarget as HTMLDetailsElement).open)}
      >
        <summary className="ui-focus-ring ui-transition-fast cursor-pointer select-none p-6">
          <div className="grid gap-1">
            <div className="font-content text-xl text-ink">Query 预处理（Query Preprocessing）</div>
            <div className="text-xs text-subtext">
              用于把 query_text 先“标准化/去噪”，让 WorldBook / Vector RAG / Graph 的检索更稳定（默认关闭）。
            </div>
            <div className="text-xs text-subtext">
              功能：提取 #tag、移除 exclusion_rules、可选识别章节引用（index_ref_enhance）。
            </div>
          </div>
        </summary>

        <div className="px-6 pb-6 pt-0">
          <div className="mt-4 grid gap-4">
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                className="checkbox"
                checked={settingsForm.query_preprocessing_enabled}
                onChange={(e) => setSettingsForm((v) => ({ ...v, query_preprocessing_enabled: e.target.checked }))}
                type="checkbox"
              />
              启用 query_preprocessing（默认关闭）
            </label>

            <div className="text-[11px] text-subtext">
              当前生效：{baselineSettings.query_preprocessing_effective?.enabled ? "enabled" : "disabled"}；来源：
              {baselineSettings.query_preprocessing_effective_source ?? "unknown"}
            </div>

            {settingsForm.query_preprocessing_enabled ? (
              <>
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="grid gap-1">
                    <span className="text-xs text-subtext">tags（每行一条；匹配 #tag；留空=提取所有 tag）</span>
                    <textarea
                      className="textarea"
                      name="query_preprocessing_tags"
                      rows={5}
                      value={settingsForm.query_preprocessing_tags}
                      onChange={(e) => setSettingsForm((v) => ({ ...v, query_preprocessing_tags: e.target.value }))}
                      placeholder={"例如：\nfoo\nbar"}
                    />
                    <div className="text-[11px] text-subtext">最大 50 条；每条最多 64 字符。</div>
                    {queryPreprocessErr && queryPreprocessErrField === "tags" ? (
                      <div className="text-xs text-warning">{queryPreprocessErr}</div>
                    ) : null}
                  </label>

                  <label className="grid gap-1">
                    <span className="text-xs text-subtext">exclusion_rules（每行一条；出现则移除）</span>
                    <textarea
                      className="textarea"
                      name="query_preprocessing_exclusion_rules"
                      rows={5}
                      value={settingsForm.query_preprocessing_exclusion_rules}
                      onChange={(e) =>
                        setSettingsForm((v) => ({ ...v, query_preprocessing_exclusion_rules: e.target.value }))
                      }
                      placeholder={"例如：\n忽略这段\nREMOVE"}
                    />
                    <div className="text-[11px] text-subtext">最大 50 条；每条最多 256 字符。</div>
                    {queryPreprocessErr && queryPreprocessErrField === "exclusion_rules" ? (
                      <div className="text-xs text-warning">{queryPreprocessErr}</div>
                    ) : null}
                  </label>
                </div>

                <label className="flex items-center gap-2 text-sm text-ink">
                  <input
                    className="checkbox"
                    checked={settingsForm.query_preprocessing_index_ref_enhance}
                    onChange={(e) =>
                      setSettingsForm((v) => ({ ...v, query_preprocessing_index_ref_enhance: e.target.checked }))
                    }
                    type="checkbox"
                  />
                  index_ref_enhance（识别“第N章 / chapter N”并追加引用 token）
                </label>

                <div className="rounded-atelier border border-border bg-canvas p-4">
                  <div className="text-sm text-ink">示例 normalize（基于已保存的 effective 配置）</div>
                  <div className="mt-1 text-xs text-subtext">修改配置后请先保存，再点击预览。</div>

                  <label className="mt-3 grid gap-1 text-xs text-subtext">
                    query_text
                    <textarea
                      className="textarea mt-1 min-h-20 w-full"
                      value={qpPreviewQueryText}
                      onChange={(e) => {
                        const next = e.target.value;
                        setQpPreviewQueryText(next);
                        if (projectId) qpPreviewQueryTextCache.set(projectId, next);
                      }}
                      placeholder="例如：回顾第1章 #foo REMOVE"
                    />
                  </label>

                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      className="btn btn-secondary"
                      disabled={qpPreviewLoading || !projectId}
                      onClick={() => void runQpPreview()}
                      type="button"
                    >
                      {qpPreviewLoading ? "预览中…" : "预览"}
                    </button>
                    <button
                      className="btn btn-secondary"
                      disabled={qpPreviewLoading}
                      onClick={() => {
                        setQpPreview(null);
                        if (projectId) qpPreviewCache.delete(projectId);
                        setQpPreviewError(null);
                      }}
                      type="button"
                    >
                      清空结果
                    </button>
                  </div>

                  {qpPreviewError ? <div className="mt-3 text-xs text-warning">{qpPreviewError}</div> : null}

                  {qpPreview ? (
                    <div className="mt-3 grid gap-3">
                      <RequestIdBadge requestId={qpPreview.requestId} />
                      <div>
                        <div className="text-xs text-subtext">normalized_query_text</div>
                        <pre className="mt-1 max-h-40 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                          {qpPreview.normalized}
                        </pre>
                      </div>
                      <details>
                        <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
                          preprocess_obs
                        </summary>
                        <pre className="mt-2 max-h-64 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
                          {JSON.stringify(qpPreview.obs ?? null, null, 2)}
                        </pre>
                      </details>
                    </div>
                  ) : null}
                </div>
              </>
            ) : (
              <div className="rounded-atelier border border-border bg-canvas p-4 text-xs text-subtext">
                启用后可配置 tags / exclusion_rules，并可在下方预览 normalized_query_text（保存后生效）。
              </div>
            )}
          </div>
        </div>
      </details>

      <details className="panel" aria-label="上下文优化（Context Optimizer）">
        <summary className="ui-focus-ring ui-transition-fast cursor-pointer select-none p-6">
          <div className="grid gap-1">
            <div className="font-content text-xl text-ink">上下文优化（Context Optimizer）</div>
            <div className="text-xs text-subtext">
              对 StructuredMemory / WORLD_BOOK 注入做去重、排序、表格化合并，用于节省 tokens 并提升可读性（默认关闭）。
            </div>
            <div className="text-xs text-subtext">
              status: {baselineSettings.context_optimizer_enabled ? "enabled" : "disabled"}
            </div>
          </div>
        </summary>

        <div className="px-6 pb-6 pt-0">
          <div className="mt-4 grid gap-2">
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                className="checkbox"
                checked={settingsForm.context_optimizer_enabled}
                onChange={(e) => setSettingsForm((v) => ({ ...v, context_optimizer_enabled: e.target.checked }))}
                type="checkbox"
              />
              启用 ContextOptimizer（影响 Prompt 预览与生成）
            </label>
            <div className="text-[11px] text-subtext">提示：写作页「上下文预览」会显示优化摘要与 diff。</div>
          </div>
        </div>
      </details>

      <details className="panel" aria-label="协作成员（Project Memberships）">
        <summary className="ui-focus-ring ui-transition-fast cursor-pointer select-none p-6">
          <div className="grid gap-1">
            <div className="font-content text-xl text-ink">协作成员（Project Memberships）</div>
            <div className="text-xs text-subtext">
              项目 owner 可邀请/改角色/移除成员；非成员访问将被 404（RBAC fail-closed）。
            </div>
            <div className="text-xs text-subtext">owner: {baselineProject.owner_user_id}</div>
          </div>
        </summary>

        <div className="px-6 pb-6 pt-0">
          {canManageMemberships ? (
            <div className="mt-4 grid gap-4">
              <div className="flex flex-wrap items-end gap-3">
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">邀请 user_id</span>
                  <input
                    className="input"
                    id="invite_user_id"
                    name="invite_user_id"
                    value={inviteUserId}
                    onChange={(e) => setInviteUserId(e.target.value)}
                    placeholder="admin"
                  />
                </label>
                <label className="grid gap-1">
                  <span className="text-xs text-subtext">角色</span>
                  <select
                    className="select"
                    id="invite_role"
                    name="invite_role"
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value === "editor" ? "editor" : "viewer")}
                  >
                    <option value="viewer">{humanizeMemberRole("viewer")}</option>
                    <option value="editor">{humanizeMemberRole("editor")}</option>
                  </select>
                </label>
                <div className="flex gap-2">
                  <button
                    className="btn btn-secondary"
                    disabled={membershipSaving || membershipsLoading}
                    onClick={() => void inviteMember()}
                    type="button"
                  >
                    邀请
                  </button>
                  <button
                    className="btn btn-secondary"
                    disabled={membershipSaving || membershipsLoading}
                    onClick={() => void loadMemberships()}
                    type="button"
                  >
                    {membershipsLoading ? "刷新中…" : "刷新"}
                  </button>
                </div>
              </div>

              <div className="overflow-auto rounded-atelier border border-border bg-canvas">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="text-xs text-subtext">
                    <tr>
                      <th className="px-3 py-2">user_id</th>
                      <th className="px-3 py-2">display_name</th>
                      <th className="px-3 py-2">role</th>
                      <th className="px-3 py-2">actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {memberships.map((m) => {
                      const memberUserId = m.user?.id ?? "";
                      const isOwnerRow = memberUserId === baselineProject.owner_user_id || m.role === "owner";
                      return (
                        <tr key={memberUserId} className="border-t border-border">
                          <td className="px-3 py-2 font-mono text-xs">{memberUserId}</td>
                          <td className="px-3 py-2">{m.user?.display_name ?? "-"}</td>
                          <td className="px-3 py-2">
                            {isOwnerRow ? (
                              <span className="text-xs text-subtext">{humanizeMemberRole("owner")}</span>
                            ) : (
                              <select
                                className="select"
                                name="member_role"
                                value={m.role === "editor" ? "editor" : "viewer"}
                                disabled={membershipSaving || membershipsLoading}
                                onChange={(e) =>
                                  void updateMemberRole(memberUserId, e.target.value === "editor" ? "editor" : "viewer")
                                }
                              >
                                <option value="viewer">{humanizeMemberRole("viewer")}</option>
                                <option value="editor">{humanizeMemberRole("editor")}</option>
                              </select>
                            )}
                          </td>
                          <td className="px-3 py-2">
                            {isOwnerRow ? (
                              <span className="text-xs text-subtext">-</span>
                            ) : (
                              <button
                                className="btn btn-secondary"
                                disabled={membershipSaving || membershipsLoading}
                                onClick={() => void removeMember(memberUserId)}
                                type="button"
                              >
                                移除
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                    {memberships.length === 0 ? (
                      <tr>
                        <td className="px-3 py-3 text-xs text-subtext" colSpan={4}>
                          暂无成员数据
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="mt-4 text-xs text-subtext">
              仅项目 owner（{baselineProject.owner_user_id}）可管理成员；当前用户：{auth.user?.id ?? "unknown"}。
            </div>
          )}
        </div>
      </details>

      <div className="text-xs text-subtext">快捷键：Ctrl/Cmd + S 保存</div>

      <WizardNextBar
        projectId={projectId}
        currentStep="settings"
        progress={wizard.progress}
        loading={wizard.loading}
        dirty={dirty}
        saving={saving}
        onSave={save}
      />

      <details className="panel" aria-label={UI_COPY.featureDefaults.ariaLabel}>
        <summary className="ui-focus-ring ui-transition-fast cursor-pointer select-none p-6">
          <div className="grid gap-1">
            <div className="font-content text-xl text-ink">{UI_COPY.featureDefaults.title}</div>
            <div className="text-xs text-subtext">{UI_COPY.featureDefaults.subtitle}</div>
            <div className="text-xs text-subtext">
              status: memory_injection_default={writingMemoryInjectionEnabled ? "enabled" : "disabled"} (localStorage)
            </div>
          </div>
        </summary>

        <div className="px-6 pb-6 pt-0">
          <div className="mt-4 grid gap-2">
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                className="checkbox"
                id="settings_writing_memory_injection_default"
                name="writing_memory_injection_default"
                checked={writingMemoryInjectionEnabled}
                onChange={(e) => saveWritingMemoryInjectionEnabled(e.target.checked)}
                aria-label="settings_writing_memory_injection_default"
                type="checkbox"
              />
              {UI_COPY.featureDefaults.memoryInjectionLabel}
            </label>
            <div className="text-[11px] text-subtext">{UI_COPY.featureDefaults.memoryInjectionHint}</div>

            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button className="btn btn-secondary btn-sm" onClick={resetWritingMemoryInjectionEnabled} type="button">
                {UI_COPY.featureDefaults.reset}
              </button>
              <div className="text-[11px] text-subtext">{UI_COPY.featureDefaults.resetHint}</div>
            </div>

            <div className="mt-3 rounded-atelier border border-border bg-canvas p-3 text-[11px] text-subtext">
              {UI_COPY.featureDefaults.autoUpdateHint}
            </div>
          </div>
        </div>
      </details>
    </div>
  );
}
