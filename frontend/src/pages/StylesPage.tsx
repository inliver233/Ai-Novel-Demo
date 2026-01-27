import { Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { Badge } from "../components/ui/Badge";
import { Drawer } from "../components/ui/Drawer";
import { useConfirm } from "../components/ui/confirm";
import { useToast } from "../components/ui/toast";
import { ApiError, apiJson } from "../services/apiClient";

type WritingStyle = {
  id: string;
  owner_user_id?: string | null;
  name: string;
  description?: string | null;
  prompt_content: string;
  is_preset: boolean;
  created_at?: string;
  updated_at?: string;
};

type ProjectDefaultStyle = {
  project_id: string;
  style_id?: string | null;
  updated_at?: string | null;
};

function resolveStyleLabel(style: WritingStyle): string {
  const name = style.name?.trim() || "（未命名）";
  return style.is_preset ? `${name}（预设）` : name;
}

export function StylesPage() {
  const { projectId } = useParams();
  const toast = useToast();
  const confirm = useConfirm();

  const [presets, setPresets] = useState<WritingStyle[]>([]);
  const [userStyles, setUserStyles] = useState<WritingStyle[]>([]);
  const [defaultStyleId, setDefaultStyleId] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<"create" | "edit">("create");
  const [editingStyleId, setEditingStyleId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");
  const [draftDescription, setDraftDescription] = useState("");
  const [draftPromptContent, setDraftPromptContent] = useState("");
  const [saving, setSaving] = useState(false);

  const allStyles = useMemo(() => [...presets, ...userStyles], [presets, userStyles]);
  const defaultStyle = useMemo(
    () => allStyles.find((s) => s.id === defaultStyleId) ?? null,
    [allStyles, defaultStyleId],
  );

  const refresh = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [presetRes, userRes, defaultRes] = await Promise.all([
        apiJson<{ styles: WritingStyle[] }>("/api/writing_styles/presets"),
        apiJson<{ styles: WritingStyle[] }>("/api/writing_styles"),
        apiJson<{ default: ProjectDefaultStyle }>(`/api/projects/${projectId}/writing_style_default`),
      ]);
      setPresets(presetRes.data.styles ?? []);
      setUserStyles(userRes.data.styles ?? []);
      setDefaultStyleId(defaultRes.data.default?.style_id ?? null);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      setError(err);
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const openCreate = () => {
    setModalMode("create");
    setEditingStyleId(null);
    setDraftName("");
    setDraftDescription("");
    setDraftPromptContent("");
    setModalOpen(true);
  };

  const openEdit = (style: WritingStyle) => {
    setModalMode("edit");
    setEditingStyleId(style.id);
    setDraftName(style.name ?? "");
    setDraftDescription(style.description ?? "");
    setDraftPromptContent(style.prompt_content ?? "");
    setModalOpen(true);
  };

  const saveDraft = useCallback(async () => {
    if (saving) return;
    setSaving(true);
    try {
      const payload = {
        name: draftName,
        description: draftDescription || null,
        prompt_content: draftPromptContent,
      };

      if (modalMode === "create") {
        await apiJson<{ style: WritingStyle }>("/api/writing_styles", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        toast.toastSuccess("已创建风格");
      } else if (editingStyleId) {
        await apiJson<{ style: WritingStyle }>(`/api/writing_styles/${editingStyleId}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        toast.toastSuccess("已保存修改");
      }

      setModalOpen(false);
      await refresh();
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setSaving(false);
    }
  }, [draftDescription, draftName, draftPromptContent, editingStyleId, modalMode, refresh, saving, toast]);

  const deleteStyle = useCallback(
    async (style: WritingStyle) => {
      const ok = await confirm.confirm({
        title: "删除风格？",
        description: `将删除「${style.name}」。若该风格为项目默认，会自动清空默认。`,
        confirmText: "删除",
        cancelText: "取消",
        danger: true,
      });
      if (!ok) return;

      try {
        await apiJson(`/api/writing_styles/${style.id}`, { method: "DELETE" });
        toast.toastSuccess("已删除");
        await refresh();
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      }
    },
    [confirm, refresh, toast],
  );

  const setDefault = useCallback(
    async (styleId: string | null) => {
      if (!projectId) return;
      try {
        const res = await apiJson<{ default: ProjectDefaultStyle }>(
          `/api/projects/${projectId}/writing_style_default`,
          {
            method: "PUT",
            body: JSON.stringify({ style_id: styleId }),
          },
        );
        setDefaultStyleId(res.data.default?.style_id ?? null);
        toast.toastSuccess(styleId ? "已设为项目默认" : "已清空项目默认");
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      }
    },
    [projectId, toast],
  );

  return (
    <div className="grid gap-4">
      <div className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="font-content text-2xl text-ink">风格</div>
            <div className="mt-1 text-xs text-subtext">
              写作风格：一段会在生成时注入的“写作要求”。可设为项目默认，也可在「AI 生成」里按章节临时选择。
            </div>
            <div className="mt-1 text-[11px] text-subtext">
              提示：高级参数的「润色 / 去味」会对生成结果做二次处理，可与风格叠加使用。
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn btn-secondary" onClick={() => void refresh()} disabled={loading} type="button">
              {loading ? "刷新中..." : "刷新"}
            </button>
            <button className="btn btn-primary btn-icon" onClick={openCreate} type="button" aria-label="新建风格">
              <Plus size={18} />
            </button>
          </div>
        </div>

        {error ? (
          <div className="mt-3 rounded-atelier border border-border bg-surface p-3 text-xs text-subtext">
            {error.message} ({error.code}) {error.requestId ? `| request_id: ${error.requestId}` : ""}
          </div>
        ) : null}

        <div className="mt-4 grid gap-3">
          <div className="rounded-atelier border border-border bg-surface p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm text-ink">项目默认</div>
                <div className="mt-1 text-xs text-subtext" aria-label="project_default_style">
                  {defaultStyle ? resolveStyleLabel(defaultStyle) : "（未设置）"}
                </div>
                <div className="mt-1 text-[11px] text-subtext">
                  未在「AI 生成」中手动选择风格时，会自动使用项目默认。
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="btn btn-secondary"
                  onClick={() => void setDefault(null)}
                  disabled={!defaultStyleId}
                  type="button"
                >
                  取消默认
                </button>
              </div>
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <div className="rounded-atelier border border-border bg-surface p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm text-ink">系统预设</div>
                <div className="text-xs text-subtext">只读</div>
              </div>
              <div className="mt-3 grid gap-2">
                {presets.map((s) => (
                  <div key={s.id} className="rounded-atelier border border-border bg-surface p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="text-sm text-ink">{s.name}</div>
                          <Badge tone="neutral">预设</Badge>
                          {defaultStyleId === s.id ? <Badge tone="accent">默认</Badge> : null}
                        </div>
                        {s.description ? <div className="mt-1 text-xs text-subtext">{s.description}</div> : null}
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <button
                          className="btn btn-secondary"
                          onClick={() => void setDefault(s.id)}
                          disabled={defaultStyleId === s.id}
                          type="button"
                          aria-label={`设为默认:${s.name}`}
                        >
                          设为默认
                        </button>
                      </div>
                    </div>
                    <pre className="mt-3 max-h-40 overflow-auto rounded-atelier border border-border bg-canvas p-2 text-xs text-ink">
                      {s.prompt_content || "（空）"}
                    </pre>
                  </div>
                ))}
                {presets.length === 0 ? <div className="text-xs text-subtext">（无预设）</div> : null}
              </div>
            </div>

            <div className="rounded-atelier border border-border bg-surface p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm text-ink">我的风格</div>
                <div className="text-xs text-subtext">可编辑</div>
              </div>
              <div className="mt-3 grid gap-2">
                {userStyles.map((s) => (
                  <div key={s.id} className="rounded-atelier border border-border bg-surface p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="text-sm text-ink">{s.name}</div>
                          <Badge tone="neutral">我的</Badge>
                          {defaultStyleId === s.id ? <Badge tone="accent">默认</Badge> : null}
                        </div>
                        {s.description ? <div className="mt-1 text-xs text-subtext">{s.description}</div> : null}
                      </div>
                      <div className="flex shrink-0 flex-wrap items-center gap-2">
                        <button
                          className="btn btn-secondary"
                          onClick={() => void setDefault(s.id)}
                          disabled={defaultStyleId === s.id}
                          type="button"
                          aria-label={`设为默认:${s.name}`}
                        >
                          设为默认
                        </button>
                        <button className="btn btn-secondary" onClick={() => openEdit(s)} type="button">
                          编辑
                        </button>
                        <button
                          className="btn btn-secondary btn-icon"
                          onClick={() => void deleteStyle(s)}
                          type="button"
                          aria-label={`删除:${s.name}`}
                          title="删除"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                    <pre className="mt-3 max-h-40 overflow-auto rounded-atelier border border-border bg-canvas p-2 text-xs text-ink">
                      {s.prompt_content || "（空）"}
                    </pre>
                  </div>
                ))}
                {userStyles.length === 0 ? <div className="text-xs text-subtext">（暂无自定义风格）</div> : null}
              </div>
            </div>
          </div>
        </div>
      </div>

      <Drawer
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        ariaLabel={modalMode === "create" ? "新建风格" : "编辑风格"}
        panelClassName="h-[92vh] w-full overflow-y-auto border-l border-border bg-canvas p-6 shadow-sm sm:h-full sm:max-w-3xl sm:p-8"
      >
        <div className="panel w-full p-5">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="font-content text-xl text-ink">{modalMode === "create" ? "新建风格" : "编辑风格"}</div>
              <div className="mt-1 text-xs text-subtext">风格提示词（prompt_content）会在生成时按优先级注入。</div>
            </div>
            <button className="btn btn-secondary" onClick={() => setModalOpen(false)} type="button">
              关闭
            </button>
          </div>

          <div className="mt-4 grid gap-3">
            <label className="block">
              <div className="text-xs text-subtext">名称</div>
              <input
                className="input mt-1"
                value={draftName}
                onChange={(e) => setDraftName(e.target.value)}
                placeholder="例如：克制现实主义"
                aria-label="style_name"
              />
            </label>
            <label className="block">
              <div className="text-xs text-subtext">描述（可选）</div>
              <input
                className="input mt-1"
                value={draftDescription}
                onChange={(e) => setDraftDescription(e.target.value)}
                placeholder="给自己一个提示，便于筛选"
                aria-label="style_description"
              />
            </label>
            <label className="block">
              <div className="text-xs text-subtext">风格提示词（prompt_content）</div>
              <textarea
                className="textarea mt-1 min-h-[320px] font-mono text-xs sm:min-h-[520px]"
                value={draftPromptContent}
                onChange={(e) => setDraftPromptContent(e.target.value)}
                placeholder="写作要求：..."
                aria-label="style_prompt_content"
              />
              <div className="mt-1 text-xs text-subtext">建议：用条目列出风格约束，避免冗长。</div>
            </label>
            <details className="rounded-atelier border border-border bg-canvas px-3 py-2 text-xs text-subtext">
              <summary className="cursor-pointer select-none">示例（点击展开）</summary>
              <pre className="mt-2 whitespace-pre-wrap font-mono text-[11px] text-ink">{`写作要求：
- 叙述视角：第三人称
- 语气：克制、现实主义
- 节奏：短句为主，少用感叹号
- 禁止：出现“作为一个AI”之类自我表述`}</pre>
            </details>

            <div className="flex items-center justify-end gap-2">
              <button className="btn btn-secondary" onClick={() => setModalOpen(false)} type="button">
                取消
              </button>
              <button className="btn btn-primary" onClick={() => void saveDraft()} disabled={saving} type="button">
                {saving ? "保存中..." : "保存"}
              </button>
            </div>
          </div>
        </div>
      </Drawer>
    </div>
  );
}
