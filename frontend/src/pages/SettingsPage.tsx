import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { useToast } from "../components/ui/toast";
import { WizardNextBar } from "../components/atelier/WizardNextBar";
import { useProjects } from "../contexts/projects";
import { useAutoSave } from "../hooks/useAutoSave";
import { useProjectData } from "../hooks/useProjectData";
import { useSaveHotkey } from "../hooks/useSaveHotkey";
import { useUnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";
import { useWizardProgress } from "../hooks/useWizardProgress";
import { ApiError, apiJson } from "../services/apiClient";
import { markWizardProjectChanged } from "../services/wizard";
import type { Project, ProjectSettings } from "../types";

type ProjectForm = { name: string; genre: string; logline: string };
type SettingsForm = {
  world_setting: string;
  style_guide: string;
  constraints: string;
  vector_embedding_base_url: string;
  vector_embedding_model: string;
};
type SettingsLoaded = { project: Project; settings: ProjectSettings };
type SaveSnapshot = { projectForm: ProjectForm; settingsForm: SettingsForm };

export function SettingsPage() {
  const { projectId } = useParams();
  const toast = useToast();
  const { refresh } = useProjects();
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
      vector_embedding_base_url: settings.vector_embedding_base_url ?? "",
      vector_embedding_model: settings.vector_embedding_model ?? "",
    });
    setVectorApiKeyDraft("");
    setVectorApiKeyClearRequested(false);
  }, [settingsQuery.data]);

  const dirty = useMemo(() => {
    if (!baselineProject || !baselineSettings) return false;
    const vectorApiKeyDirty = vectorApiKeyClearRequested || vectorApiKeyDraft.trim().length > 0;
    return (
      projectForm.name !== baselineProject.name ||
      projectForm.genre !== (baselineProject.genre ?? "") ||
      projectForm.logline !== (baselineProject.logline ?? "") ||
      settingsForm.world_setting !== baselineSettings.world_setting ||
      settingsForm.style_guide !== baselineSettings.style_guide ||
      settingsForm.constraints !== baselineSettings.constraints ||
      settingsForm.vector_embedding_base_url !== baselineSettings.vector_embedding_base_url ||
      settingsForm.vector_embedding_model !== baselineSettings.vector_embedding_model ||
      vectorApiKeyDirty
    );
  }, [baselineProject, baselineSettings, projectForm, settingsForm, vectorApiKeyClearRequested, vectorApiKeyDraft]);

  useUnsavedChangesGuard(dirty);

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
      const settingsDirty =
        nextSettingsForm.world_setting !== baselineSettings.world_setting ||
        nextSettingsForm.style_guide !== baselineSettings.style_guide ||
        nextSettingsForm.constraints !== baselineSettings.constraints ||
        nextSettingsForm.vector_embedding_base_url !== baselineSettings.vector_embedding_base_url ||
        nextSettingsForm.vector_embedding_model !== baselineSettings.vector_embedding_model ||
        vectorApiKeyDirty;
      if (!projectDirty && !settingsDirty) return true;

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
      projectForm,
      projectId,
      refresh,
      refreshWizard,
      settingsForm,
      toast,
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
      settingsForm.vector_embedding_base_url,
      settingsForm.vector_embedding_model,
    ],
  });

  const loading = settingsQuery.loading;
  if (loading) return <div className="text-subtext">加载中...</div>;
  if (!baselineProject || !baselineSettings) return <div className="text-subtext">项目加载失败</div>;

  return (
    <div className="grid gap-6">
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
              {baselineSettings.vector_embedding_has_api_key ? baselineSettings.vector_embedding_masked_api_key : "（无）"}
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
