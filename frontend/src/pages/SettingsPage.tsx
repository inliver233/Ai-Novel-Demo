import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { useToast } from "../components/ui/toast";
import { WizardNextBar } from "../components/atelier/WizardNextBar";
import { useProjects } from "../contexts/projects";
import { useProjectData } from "../hooks/useProjectData";
import { useSaveHotkey } from "../hooks/useSaveHotkey";
import { useUnsavedChangesGuard } from "../hooks/useUnsavedChangesGuard";
import { useWizardProgress } from "../hooks/useWizardProgress";
import { ApiError, apiJson } from "../services/apiClient";
import type { Project, ProjectSettings } from "../types";

type ProjectForm = { name: string; genre: string; logline: string };
type SettingsForm = { world_setting: string; style_guide: string; constraints: string };
type SettingsLoaded = { project: Project; settings: ProjectSettings };

export function SettingsPage() {
  const { projectId } = useParams();
  const toast = useToast();
  const { refresh } = useProjects();
  const wizard = useWizardProgress(projectId);
  const refreshWizard = wizard.refresh;

  const [saving, setSaving] = useState(false);
  const [baselineProject, setBaselineProject] = useState<Project | null>(null);
  const [baselineSettings, setBaselineSettings] = useState<ProjectSettings | null>(null);

  const [projectForm, setProjectForm] = useState<ProjectForm>({ name: "", genre: "", logline: "" });
  const [settingsForm, setSettingsForm] = useState<SettingsForm>({
    world_setting: "",
    style_guide: "",
    constraints: "",
  });

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
    });
  }, [settingsQuery.data]);

  const dirty = useMemo(() => {
    if (!baselineProject || !baselineSettings) return false;
    return (
      projectForm.name !== baselineProject.name ||
      projectForm.genre !== (baselineProject.genre ?? "") ||
      projectForm.logline !== (baselineProject.logline ?? "") ||
      settingsForm.world_setting !== baselineSettings.world_setting ||
      settingsForm.style_guide !== baselineSettings.style_guide ||
      settingsForm.constraints !== baselineSettings.constraints
    );
  }, [baselineProject, baselineSettings, projectForm, settingsForm]);

  useUnsavedChangesGuard(dirty);

  const save = useCallback(async (): Promise<boolean> => {
    if (!projectId) return false;
    if (!dirty) return true;
    setSaving(true);
    try {
      const [pRes, sRes] = await Promise.all([
        apiJson<{ project: Project }>(`/api/projects/${projectId}`, {
          method: "PUT",
          body: JSON.stringify({
            name: projectForm.name.trim(),
            genre: projectForm.genre.trim() || null,
            logline: projectForm.logline.trim() || null,
          }),
        }),
        apiJson<{ settings: ProjectSettings }>(`/api/projects/${projectId}/settings`, {
          method: "PUT",
          body: JSON.stringify({
            world_setting: settingsForm.world_setting,
            style_guide: settingsForm.style_guide,
            constraints: settingsForm.constraints,
          }),
        }),
      ]);

      setBaselineProject(pRes.data.project);
      setBaselineSettings(sRes.data.settings);
      await refresh();
      await refreshWizard();
      toast.toastSuccess("已保存");
      return true;
    } catch (e) {
      const err = e as ApiError;
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
      return false;
    } finally {
      setSaving(false);
    }
  }, [dirty, projectForm, projectId, refresh, refreshWizard, settingsForm, toast]);

  useSaveHotkey(() => void save(), dirty);

  const loading = settingsQuery.loading;
  if (loading) return <div className="text-subtext">加载中...</div>;
  if (!baselineProject) return <div className="text-subtext">项目加载失败</div>;

  return (
    <div className="grid gap-6">
      <section className="rounded-atelier border border-border bg-surface p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="grid gap-2">
            <div className="font-content text-xl">项目信息</div>
            <div className="text-xs text-subtext">名称 / 类型 / Logline</div>
          </div>
          <button
            className="rounded-atelier bg-accent px-3 py-2 text-sm text-white hover:opacity-90 disabled:opacity-60"
            disabled={!dirty || saving}
            onClick={() => void save()}
            type="button"
          >
            保存
          </button>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <label className="grid gap-1 sm:col-span-1">
            <span className="text-xs text-subtext">项目名</span>
            <input
              className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none"
              value={projectForm.name}
              onChange={(e) => setProjectForm((v) => ({ ...v, name: e.target.value }))}
            />
          </label>
          <label className="grid gap-1 sm:col-span-1">
            <span className="text-xs text-subtext">类型</span>
            <input
              className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none"
              value={projectForm.genre}
              onChange={(e) => setProjectForm((v) => ({ ...v, genre: e.target.value }))}
            />
          </label>
          <label className="grid gap-1 sm:col-span-3">
            <span className="text-xs text-subtext">Logline</span>
            <textarea
              className="rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink outline-none"
              rows={2}
              value={projectForm.logline}
              onChange={(e) => setProjectForm((v) => ({ ...v, logline: e.target.value }))}
            />
          </label>
        </div>
      </section>

      <section className="rounded-atelier border border-border bg-surface p-6">
        <div className="font-content text-xl">设定</div>
        <div className="mt-4 grid gap-4">
          <label className="grid gap-1">
            <span className="text-xs text-subtext">世界观</span>
            <textarea
              className="atelier-content w-full rounded-atelier border border-border bg-canvas px-3 py-3 text-ink outline-none"
              rows={6}
              value={settingsForm.world_setting}
              onChange={(e) => setSettingsForm((v) => ({ ...v, world_setting: e.target.value }))}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-subtext">风格</span>
            <textarea
              className="atelier-content w-full rounded-atelier border border-border bg-canvas px-3 py-3 text-ink outline-none"
              rows={6}
              value={settingsForm.style_guide}
              onChange={(e) => setSettingsForm((v) => ({ ...v, style_guide: e.target.value }))}
            />
          </label>
          <label className="grid gap-1">
            <span className="text-xs text-subtext">约束</span>
            <textarea
              className="atelier-content w-full rounded-atelier border border-border bg-canvas px-3 py-3 text-ink outline-none"
              rows={6}
              value={settingsForm.constraints}
              onChange={(e) => setSettingsForm((v) => ({ ...v, constraints: e.target.value }))}
            />
          </label>
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
