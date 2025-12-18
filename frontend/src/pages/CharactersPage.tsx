import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { WizardNextBar } from "../components/atelier/WizardNextBar";
import { useConfirm } from "../components/ui/confirm";
import { useToast } from "../components/ui/toast";
import { useProjectData } from "../hooks/useProjectData";
import { useWizardProgress } from "../hooks/useWizardProgress";
import { ApiError, apiJson } from "../services/apiClient";
import type { Character } from "../types";

type CharacterForm = {
  name: string;
  role: string;
  profile: string;
  notes: string;
};

export function CharactersPage() {
  const { projectId } = useParams();
  const toast = useToast();
  const confirm = useConfirm();
  const wizard = useWizardProgress(projectId);
  const refreshWizard = wizard.refresh;

  const charactersQuery = useProjectData<Character[]>(projectId, async (id) => {
    const res = await apiJson<{ characters: Character[] }>(`/api/projects/${id}/characters`);
    return res.data.characters;
  });
  const characters = charactersQuery.data ?? [];
  const loading = charactersQuery.loading;

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<Character | null>(null);
  const [saving, setSaving] = useState(false);
  const [baseline, setBaseline] = useState<CharacterForm | null>(null);
  const [form, setForm] = useState<CharacterForm>({ name: "", role: "", profile: "", notes: "" });

  const dirty = useMemo(() => {
    if (!baseline) return false;
    return (
      form.name !== baseline.name ||
      form.role !== baseline.role ||
      form.profile !== baseline.profile ||
      form.notes !== baseline.notes
    );
  }, [baseline, form]);

  const load = charactersQuery.refresh;

  const openNew = () => {
    setEditing(null);
    const next = { name: "", role: "", profile: "", notes: "" };
    setForm(next);
    setBaseline(next);
    setDrawerOpen(true);
  };

  const openEdit = (c: Character) => {
    setEditing(c);
    const next = {
      name: c.name ?? "",
      role: c.role ?? "",
      profile: c.profile ?? "",
      notes: c.notes ?? "",
    };
    setForm(next);
    setBaseline(next);
    setDrawerOpen(true);
  };

  const closeDrawer = async () => {
    if (dirty) {
      const ok = await confirm.confirm({
        title: "放弃未保存修改？",
        description: "关闭后未保存内容会丢失。",
        confirmText: "放弃",
        cancelText: "取消",
        danger: true,
      });
      if (!ok) return;
    }
    setDrawerOpen(false);
  };

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-subtext">共 {characters.length} 位角色</div>
        <button
          className="rounded-atelier bg-accent px-3 py-2 text-sm text-white hover:opacity-90"
          onClick={openNew}
          type="button"
        >
          新增角色
        </button>
      </div>

      {loading ? <div className="text-subtext">加载中...</div> : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {characters.map((c) => (
          <div
            key={c.id}
            className="rounded-atelier cursor-pointer border border-border bg-surface p-5 text-left hover:bg-canvas"
            onClick={() => openEdit(c)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                openEdit(c);
              }
            }}
            role="button"
            tabIndex={0}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate font-content text-xl text-ink">{c.name}</div>
                <div className="mt-1 text-xs text-subtext">{c.role ?? "未填写角色定位"}</div>
              </div>
              <button
                className="rounded-atelier border border-border bg-canvas px-3 py-2 text-xs text-ink hover:bg-surface"
                onClick={async (e) => {
                  e.stopPropagation();
                  const ok = await confirm.confirm({
                    title: "删除角色？",
                    description: "该角色将从项目中移除。",
                    confirmText: "删除",
                    danger: true,
                  });
                  if (!ok) return;
                  try {
                    await apiJson<Record<string, never>>(`/api/characters/${c.id}`, { method: "DELETE" });
                    toast.toastSuccess("已删除");
                    await load();
                    await refreshWizard();
                  } catch (err) {
                    const apiErr = err as ApiError;
                    toast.toastError(`${apiErr.message} (${apiErr.code})`, apiErr.requestId);
                  }
                }}
                type="button"
              >
                删除
              </button>
            </div>
            {c.profile ? <div className="mt-3 line-clamp-4 text-sm text-subtext">{c.profile}</div> : null}
          </div>
        ))}
      </div>

      {drawerOpen ? (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/30">
          <div className="h-full w-full max-w-xl border-l border-border bg-canvas p-6">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-content text-2xl">{editing ? "编辑角色" : "新增角色"}</div>
                <div className="mt-1 text-xs text-subtext">{dirty ? "未保存" : "已同步"}</div>
              </div>
              <div className="flex gap-2">
                <button
                  className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink hover:bg-canvas"
                  onClick={() => void closeDrawer()}
                  type="button"
                >
                  关闭
                </button>
                <button
                  className="rounded-atelier bg-accent px-3 py-2 text-sm text-white hover:opacity-90 disabled:opacity-60"
                  disabled={saving || !form.name.trim()}
                  onClick={async () => {
                    if (!projectId) return;
                    setSaving(true);
                    try {
                      if (!editing) {
                        await apiJson<{ character: Character }>(`/api/projects/${projectId}/characters`, {
                          method: "POST",
                          body: JSON.stringify({
                            name: form.name.trim(),
                            role: form.role.trim() || null,
                            profile: form.profile || null,
                            notes: form.notes || null,
                          }),
                        });
                      } else {
                        await apiJson<{ character: Character }>(`/api/characters/${editing.id}`, {
                          method: "PUT",
                          body: JSON.stringify({
                            name: form.name.trim(),
                            role: form.role.trim() || null,
                            profile: form.profile || null,
                            notes: form.notes || null,
                          }),
                        });
                      }
                      toast.toastSuccess("已保存");
                      await load();
                      await refreshWizard();
                      setBaseline(form);
                      setDrawerOpen(false);
                    } catch (err) {
                      const apiErr = err as ApiError;
                      toast.toastError(`${apiErr.message} (${apiErr.code})`, apiErr.requestId);
                    } finally {
                      setSaving(false);
                    }
                  }}
                  type="button"
                >
                  保存
                </button>
              </div>
            </div>

            <div className="mt-5 grid gap-4">
              <label className="grid gap-1">
                <span className="text-xs text-subtext">姓名</span>
                <input
                  className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink outline-none"
                  name="name"
                  value={form.name}
                  onChange={(e) => setForm((v) => ({ ...v, name: e.target.value }))}
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs text-subtext">角色定位</span>
                <input
                  className="rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink outline-none"
                  name="role"
                  value={form.role}
                  onChange={(e) => setForm((v) => ({ ...v, role: e.target.value }))}
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs text-subtext">人物档案</span>
                <textarea
                  className="atelier-content rounded-atelier border border-border bg-surface px-3 py-3 text-ink outline-none"
                  name="profile"
                  rows={8}
                  value={form.profile}
                  onChange={(e) => setForm((v) => ({ ...v, profile: e.target.value }))}
                />
              </label>
              <label className="grid gap-1">
                <span className="text-xs text-subtext">备注</span>
                <textarea
                  className="atelier-content rounded-atelier border border-border bg-surface px-3 py-3 text-ink outline-none"
                  name="notes"
                  rows={6}
                  value={form.notes}
                  onChange={(e) => setForm((v) => ({ ...v, notes: e.target.value }))}
                />
              </label>
            </div>
          </div>
        </div>
      ) : null}

      <WizardNextBar
        projectId={projectId}
        currentStep="characters"
        progress={wizard.progress}
        loading={wizard.loading}
        primaryAction={
          wizard.progress.nextStep?.key === "characters"
            ? { label: "本页：新增角色", onClick: openNew }
            : undefined
        }
      />
    </div>
  );
}
