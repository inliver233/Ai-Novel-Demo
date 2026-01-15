import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

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
import { ApiError, apiJson } from "../services/apiClient";
import { markWizardProjectChanged } from "../services/wizard";
import type { Project, ProjectSettings, QueryPreprocessingConfig } from "../types";

type ProjectForm = { name: string; genre: string; logline: string };
type SettingsForm = {
  world_setting: string;
  style_guide: string;
  constraints: string;
  query_preprocessing_enabled: boolean;
  query_preprocessing_tags: string;
  query_preprocessing_exclusion_rules: string;
  query_preprocessing_index_ref_enhance: boolean;
  vector_embedding_base_url: string;
  vector_embedding_model: string;
};
type SettingsLoaded = { project: Project; settings: ProjectSettings };
type SaveSnapshot = { projectForm: ProjectForm; settingsForm: SettingsForm };
type ProjectMembershipItem = {
  project_id: string;
  user: { id: string; display_name: string | null; is_admin: boolean };
  role: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export function SettingsPage() {
  const { projectId } = useParams();
  const toast = useToast();
  const auth = useAuth();
  const { refresh } = useProjects();
  const outletActive = usePersistentOutletIsActive();
  const wizard = useWizardProgress(projectId);
  const refreshWizard = wizard.refresh;
  const bumpWizardLocal = wizard.bumpLocal;

  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const queuedSaveRef = useRef<null | { silent: boolean; snapshot?: SaveSnapshot }>(null);
  const wizardRefreshTimerRef = useRef<number | null>(null);
  const projectsRefreshTimerRef = useRef<number | null>(null);
  const [baselineProject, setBaselineProject] = useState<Project | null>(null);
  const [baselineSettings, setBaselineSettings] = useState<ProjectSettings | null>(null);

  const [projectForm, setProjectForm] = useState<ProjectForm>({ name: "", genre: "", logline: "" });
  const [settingsForm, setSettingsForm] = useState<SettingsForm>({
    world_setting: "",
    style_guide: "",
    constraints: "",
    query_preprocessing_enabled: false,
    query_preprocessing_tags: "",
    query_preprocessing_exclusion_rules: "",
    query_preprocessing_index_ref_enhance: false,
    vector_embedding_base_url: "",
    vector_embedding_model: "",
  });
  const [vectorApiKeyDraft, setVectorApiKeyDraft] = useState("");
  const [vectorApiKeyClearRequested, setVectorApiKeyClearRequested] = useState(false);

  const settingsQuery = useProjectData<SettingsLoaded>(projectId, async (id) => {
    const [pRes, sRes] = await Promise.all([
      apiJson<{ project: Project }>(`/api/projects/${id}`),
      apiJson<{ settings: ProjectSettings }>(`/api/projects/${id}/settings`),
    ]);
    return { project: pRes.data.project, settings: sRes.data.settings };
  });

  useEffect(() => {
    if (!settingsQuery.data) return;
    const { project, settings } = settingsQuery.data;
    setBaselineProject(project);
    setBaselineSettings(settings);
    setProjectForm({
      name: project.name ?? "",
      genre: project.genre ?? "",
      logline: project.logline ?? "",
    });
    setSettingsForm({
      world_setting: settings.world_setting ?? "",
      style_guide: settings.style_guide ?? "",
      constraints: settings.constraints ?? "",
      query_preprocessing_enabled: Boolean(settings.query_preprocessing_effective?.enabled),
      query_preprocessing_tags: Array.isArray(settings.query_preprocessing_effective?.tags)
        ? settings.query_preprocessing_effective?.tags.join("\n")
        : "",
      query_preprocessing_exclusion_rules: Array.isArray(settings.query_preprocessing_effective?.exclusion_rules)
        ? settings.query_preprocessing_effective?.exclusion_rules.join("\n")
        : "",
      query_preprocessing_index_ref_enhance: Boolean(settings.query_preprocessing_effective?.index_ref_enhance),
      vector_embedding_base_url: settings.vector_embedding_base_url ?? "",
      vector_embedding_model: settings.vector_embedding_model ?? "",
    });
    setVectorApiKeyDraft("");
    setVectorApiKeyClearRequested(false);
  }, [settingsQuery.data]);

  const [membershipsLoading, setMembershipsLoading] = useState(false);
  const [membershipSaving, setMembershipSaving] = useState(false);
  const [memberships, setMemberships] = useState<ProjectMembershipItem[]>([]);
  const [inviteUserId, setInviteUserId] = useState("");
  const [inviteRole, setInviteRole] = useState<"viewer" | "editor">("viewer");

  const [qpPreviewQueryText, setQpPreviewQueryText] = useState("");
  const [qpPreviewLoading, setQpPreviewLoading] = useState(false);
  const [qpPreview, setQpPreview] = useState<null | { normalized: string; obs: unknown; requestId: string }>(null);
  const [qpPreviewError, setQpPreviewError] = useState<string | null>(null);

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
      setQpPreviewError("请输入示例 query_text");
      return;
    }
    setQpPreviewLoading(true);
    setQpPreviewError(null);
    try {
      const res = await apiJson<{
        result: unknown;
        raw_query_text: string;
        normalized_query_text: string;
        preprocess_obs: unknown;
      }>(`/api/projects/${projectId}/graph/query`, {
        method: "POST",
        body: JSON.stringify({ query_text: queryText, enabled: false }),
      });
      setQpPreview({
        normalized: String(res.data.normalized_query_text ?? ""),
        obs: res.data.preprocess_obs ?? null,
        requestId: res.request_id ?? "unknown",
      });
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      setQpPreview(null);
      setQpPreviewError(`${err.message} (${err.code})`);
    } finally {
      setQpPreviewLoading(false);
    }
  }, [projectId, qpPreviewQueryText]);

  const dirty = useMemo(() => {
    if (!baselineProject || !baselineSettings) return false;
    const vectorApiKeyDirty = vectorApiKeyClearRequested || vectorApiKeyDraft.trim().length > 0;
    const qpDirty = !isSameQueryPreprocess(queryPreprocessFromForm(settingsForm), queryPreprocessFromBaseline(baselineSettings));
    return (
      projectForm.name !== baselineProject.name ||
      projectForm.genre !== (baselineProject.genre ?? "") ||
      projectForm.logline !== (baselineProject.logline ?? "") ||
      settingsForm.world_setting !== baselineSettings.world_setting ||
      settingsForm.style_guide !== baselineSettings.style_guide ||
      settingsForm.constraints !== baselineSettings.constraints ||
      qpDirty ||
      settingsForm.vector_embedding_base_url !== baselineSettings.vector_embedding_base_url ||
      settingsForm.vector_embedding_model !== baselineSettings.vector_embedding_model ||
      vectorApiKeyDirty
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
      const qpDirty = !isSameQueryPreprocess(
        queryPreprocessFromForm(nextSettingsForm),
        queryPreprocessFromBaseline(baselineSettings),
      );
      const settingsDirty =
        nextSettingsForm.world_setting !== baselineSettings.world_setting ||
        nextSettingsForm.style_guide !== baselineSettings.style_guide ||
        nextSettingsForm.constraints !== baselineSettings.constraints ||
        qpDirty ||
        nextSettingsForm.vector_embedding_base_url !== baselineSettings.vector_embedding_base_url ||
        nextSettingsForm.vector_embedding_model !== baselineSettings.vector_embedding_model ||
        vectorApiKeyDirty;
      if (!projectDirty && !settingsDirty) return true;

      if (qpDirty) {
        const qpCfg = queryPreprocessFromForm(nextSettingsForm);
        const qpErr = validateQueryPreprocess(qpCfg);
        if (qpErr) {
          if (!silent) toast.toastError(qpErr);
          return false;
        }
      }

      const scheduleWizardRefresh = () => {
        if (wizardRefreshTimerRef.current !== null) window.clearTimeout(wizardRefreshTimerRef.current);
        wizardRefreshTimerRef.current = window.setTimeout(() => void refreshWizard(), 1200);
      };
      const scheduleProjectsRefresh = () => {
        if (projectsRefreshTimerRef.current !== null) window.clearTimeout(projectsRefreshTimerRef.current);
        projectsRefreshTimerRef.current = window.setTimeout(() => void refresh(), 1200);
      };

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
                  ...(qpDirty ? { query_preprocessing: queryPreprocessFromForm(nextSettingsForm) } : {}),
                  vector_embedding_base_url: nextSettingsForm.vector_embedding_base_url,
                  vector_embedding_model: nextSettingsForm.vector_embedding_model,
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
          setVectorApiKeyDraft("");
          setVectorApiKeyClearRequested(false);
        }
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
        return false;
      } finally {
        setSaving(false);
        savingRef.current = false;
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
      vectorApiKeyClearRequested,
      vectorApiKeyDraft,
    ],
  );

  useSaveHotkey(() => void save(), dirty);

  const vectorApiKeyDirty = vectorApiKeyClearRequested || vectorApiKeyDraft.trim().length > 0;
  useAutoSave({
    enabled: Boolean(projectId && baselineProject && baselineSettings && !vectorApiKeyDirty),
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
      settingsForm.query_preprocessing_enabled,
      settingsForm.query_preprocessing_tags,
      settingsForm.query_preprocessing_exclusion_rules,
      settingsForm.query_preprocessing_index_ref_enhance,
      settingsForm.vector_embedding_base_url,
      settingsForm.vector_embedding_model,
    ],
  });

  const loading = settingsQuery.loading;
  if (loading) return <div className="text-subtext">加载中...</div>;
  if (!baselineProject || !baselineSettings) return <div className="text-subtext">项目加载失败</div>;

  return (
    <div className="grid gap-6">
      {dirty && outletActive ? <UnsavedChangesGuard when={dirty} /> : null}
      <section className="panel p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="grid gap-2">
            <div className="font-content text-xl">项目信息</div>
            <div className="text-xs text-subtext">名称 / 类型 / Logline</div>
          </div>
          <button className="btn btn-primary" disabled={!dirty || saving} onClick={() => void save()} type="button">
            保存
          </button>
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
            <span className="text-xs text-subtext">类型</span>
            <input
              className="input"
              name="project_genre"
              value={projectForm.genre}
              onChange={(e) => setProjectForm((v) => ({ ...v, genre: e.target.value }))}
            />
          </label>
          <label className="grid gap-1 sm:col-span-3">
            <span className="text-xs text-subtext">Logline</span>
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
        <div className="font-content text-xl">设定</div>
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
        <div className="font-content text-xl">向量检索（Vector RAG）</div>
        <div className="mt-1 text-xs text-subtext">
          Embedding 配置支持项目级覆盖（API Key 加密存储，仅回显 masked），并可 fallback 到后端 env。
        </div>

        <div className="mt-3 text-xs text-subtext">
          status: {baselineSettings.vector_embedding_effective_disabled_reason ?? "enabled"} | source:{" "}
          {baselineSettings.vector_embedding_effective_source}
        </div>

        <div className="mt-4 grid gap-4">
          <label className="grid gap-1">
            <span className="text-xs text-subtext">Base URL（项目覆盖；留空=env fallback）</span>
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
            <span className="text-xs text-subtext">Model（项目覆盖；留空=env fallback）</span>
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
            <span className="text-xs text-subtext">API Key（项目覆盖；留空不修改）</span>
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
              清除项目 API Key
            </button>
            <button
              className="btn btn-secondary"
              disabled={saving}
              onClick={() => {
                setSettingsForm((v) => ({ ...v, vector_embedding_base_url: "", vector_embedding_model: "" }));
                setVectorApiKeyDraft("");
                setVectorApiKeyClearRequested(true);
              }}
              type="button"
            >
              恢复 env fallback（清除项目覆盖）
            </button>
          </div>
        </div>
      </section>

      <section className="panel p-6">
        <div className="font-content text-xl">Query 预处理（Query Preprocessing）</div>
        <div className="mt-1 text-xs text-subtext">
          用于统一 WorldBook / VectorRAG / Graph / 生成链路的 query_text 处理（默认关闭）。tags 支持从 query_text 中提取
          #tag；exclusion_rules 会从 query_text 中移除。
        </div>

        <div className="mt-3 text-xs text-subtext">
          status: {baselineSettings.query_preprocessing_effective?.enabled ? "enabled" : "disabled"} | source:{" "}
          {baselineSettings.query_preprocessing_effective_source ?? "unknown"}
        </div>

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
                onChange={(e) => setQpPreviewQueryText(e.target.value)}
                placeholder="例如：回顾第1章 #foo REMOVE"
              />
            </label>

            <div className="mt-3 flex flex-wrap gap-2">
              <button className="btn btn-secondary" disabled={qpPreviewLoading || !projectId} onClick={() => void runQpPreview()} type="button">
                {qpPreviewLoading ? "预览中…" : "预览"}
              </button>
              <button
                className="btn btn-secondary"
                disabled={qpPreviewLoading}
                onClick={() => {
                  setQpPreview(null);
                  setQpPreviewError(null);
                }}
                type="button"
              >
                清空结果
              </button>
            </div>

            {qpPreviewError ? <div className="mt-3 text-xs text-amber-600 dark:text-amber-400">{qpPreviewError}</div> : null}

            {qpPreview ? (
              <div className="mt-3 grid gap-3">
                <div className="text-xs text-subtext">request_id: {qpPreview.requestId}</div>
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
        </div>
      </section>

      <section className="panel p-6">
        <div className="font-content text-xl">协作成员（Project Memberships）</div>
        <div className="mt-1 text-xs text-subtext">
          项目 owner 可邀请/改角色/移除成员；非成员访问将被 404（RBAC fail-closed）。
        </div>

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
                  <option value="viewer">viewer</option>
                  <option value="editor">editor</option>
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
                            <span className="text-xs text-subtext">owner</span>
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
                              <option value="viewer">viewer</option>
                              <option value="editor">editor</option>
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
      </section>

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
    </div>
  );
}
