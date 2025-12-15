import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useConfirm } from "../components/ui/confirm";
import { useToast } from "../components/ui/toast";
import { useProjects } from "../contexts/projects";
import { ApiError, apiJson } from "../services/apiClient";
import { computeWizardProgress } from "../services/wizard";
import type { Chapter, Character, LLMPreset, Outline, Project, ProjectSettings } from "../types";

type CreateProjectForm = {
  name: string;
  genre: string;
  logline: string;
};

export function DashboardPage() {
  const { projects, loading, refresh } = useProjects();
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();

  const [creating, setCreating] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<CreateProjectForm>({ name: "", genre: "", logline: "" });

  const sorted = useMemo(() => [...projects].sort((a, b) => b.created_at.localeCompare(a.created_at)), [projects]);

  type WizardSummary = { percent: number; nextTitle: string | null; nextHref: string | null };
  const [wizardByProjectId, setWizardByProjectId] = useState<Record<string, WizardSummary>>({});
  const [wizardLoadingByProjectId, setWizardLoadingByProjectId] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      for (const p of sorted) {
        if (cancelled) return;
        setWizardLoadingByProjectId((prev) => ({ ...prev, [p.id]: true }));
        try {
          const [settingsRes, charsRes, outlineRes, chaptersRes, presetRes] = await Promise.all([
            apiJson<{ settings: ProjectSettings }>(`/api/projects/${p.id}/settings`),
            apiJson<{ characters: Character[] }>(`/api/projects/${p.id}/characters`),
            apiJson<{ outline: Outline }>(`/api/projects/${p.id}/outline`),
            apiJson<{ chapters: Chapter[] }>(`/api/projects/${p.id}/chapters`),
            apiJson<{ llm_preset: LLMPreset }>(`/api/projects/${p.id}/llm_preset`),
          ]);

          const progress = computeWizardProgress({
            project: p,
            settings: settingsRes.data.settings,
            characters: charsRes.data.characters,
            outline: outlineRes.data.outline,
            chapters: chaptersRes.data.chapters,
            llmPreset: presetRes.data.llm_preset,
          });

          if (cancelled) return;
          setWizardByProjectId((prev) => ({
            ...prev,
            [p.id]: {
              percent: progress.percent,
              nextTitle: progress.nextStep?.title ?? null,
              nextHref: progress.nextStep?.href ?? null,
            },
          }));
        } catch {
          if (cancelled) return;
        } finally {
          if (!cancelled) setWizardLoadingByProjectId((prev) => ({ ...prev, [p.id]: false }));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [sorted]);

  const enterProject = useCallback(
    (p: Project) => {
      const w = wizardByProjectId[p.id];
      if (!w) {
        navigate(`/projects/${p.id}/wizard`);
        return;
      }
      navigate(w.percent >= 100 ? `/projects/${p.id}/writing` : `/projects/${p.id}/wizard`);
    },
    [navigate, wizardByProjectId],
  );

  return (
    <div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <button
          className="group rounded-atelier border border-border border-dashed bg-surface p-6 text-left hover:bg-canvas"
          onClick={() => setCreateOpen(true)}
          type="button"
        >
          <div className="font-content text-2xl text-ink">+</div>
          <div className="mt-2 text-sm text-subtext">新建项目</div>
        </button>

        {loading ? (
          <div className="rounded-atelier border border-border bg-surface p-6 text-subtext">加载中...</div>
        ) : null}

        {sorted.map((p) => (
          <div key={p.id} className="rounded-atelier border border-border bg-surface p-6">
            <div className="flex items-start justify-between gap-3">
              <button
                className="min-w-0 text-left"
                onClick={() => enterProject(p)}
                type="button"
              >
                <div className="truncate font-content text-xl text-ink">{p.name}</div>
                <div className="mt-1 text-xs text-subtext">{p.genre ?? "未填写类型"}</div>
              </button>
              <div className="flex shrink-0 gap-2">
                <button
                  className="rounded-atelier border border-border bg-canvas px-3 py-2 text-xs text-ink hover:bg-surface"
                  onClick={() => navigate(`/projects/${p.id}/wizard`)}
                  type="button"
                >
                  向导
                </button>
                <button
                  className="rounded-atelier border border-border bg-canvas px-3 py-2 text-xs text-ink hover:bg-surface"
                  onClick={async () => {
                    const ok = await confirm.confirm({
                      title: "删除项目？",
                      description: "该操作会删除项目及其设定/角色/章节/生成记录，且不可恢复。",
                      confirmText: "删除",
                      danger: true,
                    });
                    if (!ok) return;
                    try {
                      const res = await apiJson<Record<string, never>>(`/api/projects/${p.id}`, { method: "DELETE" });
                      await refresh();
                      toast.toastSuccess("已删除");
                      return res;
                    } catch (e) {
                      const err = e as ApiError;
                      toast.toastError(`${err.message} (${err.code})`, err.requestId);
                    }
                  }}
                  type="button"
                >
                  删除
                </button>
              </div>
            </div>
            {p.logline ? <div className="mt-3 line-clamp-3 text-sm text-subtext">{p.logline}</div> : null}

            {wizardLoadingByProjectId[p.id] ? (
              <div className="mt-4 text-xs text-subtext">计算完成度...</div>
            ) : wizardByProjectId[p.id] ? (
              <div className="mt-4">
                <div className="flex items-center justify-between gap-3 text-xs text-subtext">
                  <div>完成度：{wizardByProjectId[p.id].percent}%</div>
                  <div className="truncate">{wizardByProjectId[p.id].nextTitle ? `下一步：${wizardByProjectId[p.id].nextTitle}` : "已完成"}</div>
                </div>
                <div className="mt-2 h-2 w-full rounded-full bg-border/60">
                  <div className="h-2 rounded-full bg-accent" style={{ width: `${wizardByProjectId[p.id].percent}%` }} />
                </div>
              </div>
            ) : null}
          </div>
        ))}
      </div>

      {createOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-lg rounded-atelier border border-border bg-canvas p-6 shadow-sm">
            <div className="font-content text-2xl text-ink">创建项目</div>
            <div className="mt-4 grid gap-3">
              <label className="grid gap-1">
                <span className="text-xs text-subtext">项目名</span>
                <input
                  className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink outline-none"
                  value={form.name}
                  onChange={(e) => setForm((v) => ({ ...v, name: e.target.value }))}
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs text-subtext">类型（可选）</span>
                <input
                  className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink outline-none"
                  value={form.genre}
                  onChange={(e) => setForm((v) => ({ ...v, genre: e.target.value }))}
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs text-subtext">一句话梗概（可选）</span>
                <textarea
                  className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink outline-none"
                  rows={3}
                  value={form.logline}
                  onChange={(e) => setForm((v) => ({ ...v, logline: e.target.value }))}
                />
              </label>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink hover:bg-canvas"
                onClick={() => setCreateOpen(false)}
                type="button"
              >
                取消
              </button>
              <button
                className="rounded-atelier bg-accent px-3 py-2 text-sm text-white hover:opacity-90 disabled:opacity-60"
                disabled={creating || !form.name.trim()}
                onClick={async () => {
                  setCreating(true);
                  try {
                    const res = await apiJson<{ project: Project }>("/api/projects", {
                      method: "POST",
                      body: JSON.stringify({
                        name: form.name.trim(),
                        genre: form.genre.trim() || undefined,
                        logline: form.logline.trim() || undefined,
                      }),
                    });
                    await refresh();
                    toast.toastSuccess("创建成功");
                    setCreateOpen(false);
                    setForm({ name: "", genre: "", logline: "" });
                    navigate(`/projects/${res.data.project.id}/settings`);
                  } catch (e) {
                    const err = e as ApiError;
                    toast.toastError(`${err.message} (${err.code})`, err.requestId);
                  } finally {
                    setCreating(false);
                  }
                }}
                type="button"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
