import { useCallback, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { DebugDetails, DebugPageShell } from "../components/atelier/DebugPageShell";
import { useConfirm } from "../components/ui/confirm";
import { useToast } from "../components/ui/toast";
import { copyText } from "../lib/copyText";
import { ApiError, apiJson } from "../services/apiClient";

type GlossarySource = {
  source_type: string;
  source_id: string;
  label: string | null;
};

type GlossaryTerm = {
  id: string;
  project_id: string;
  term: string;
  aliases: string[];
  sources: GlossarySource[];
  origin: string;
  enabled: number;
  created_at: string | null;
  updated_at: string | null;
};

function parseAliasesInput(raw: string): string[] {
  const parts = String(raw || "")
    .split(/[,\n|;]+/g)
    .map((s) => s.trim())
    .filter(Boolean);
  return Array.from(new Set(parts)).slice(0, 50);
}

function sourceLabel(s: GlossarySource): string {
  const label = s.label?.trim();
  if (label) return label;
  return s.source_id;
}

export function GlossaryPage() {
  const { projectId } = useParams();
  const toast = useToast();
  const confirm = useConfirm();

  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);

  const [createTerm, setCreateTerm] = useState("");
  const [createAliases, setCreateAliases] = useState("");
  const [creating, setCreating] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTerm, setEditingTerm] = useState("");
  const [editingAliases, setEditingAliases] = useState("");
  const [savingId, setSavingId] = useState<string | null>(null);

  const [rebuilding, setRebuilding] = useState(false);
  const [exporting, setExporting] = useState(false);

  const byId = useMemo(() => {
    const map: Record<string, GlossaryTerm> = {};
    for (const t of terms) map[t.id] = t;
    return map;
  }, [terms]);

  const rawJson = useMemo(() => JSON.stringify({ terms }, null, 2), [terms]);

  const copyRawJson = useCallback(async () => {
    const ok = await copyText(rawJson, { title: "复制失败：请手动复制 glossary JSON" });
    if (ok) toast.toastSuccess("已复制 glossary JSON");
    else toast.toastWarning("自动复制失败：已打开手动复制弹窗。");
  }, [rawJson, toast]);

  const copyTermId = useCallback(
    async (id: string) => {
      const ok = await copyText(id, { title: "复制失败：请手动复制术语 ID" });
      if (ok) toast.toastSuccess("已复制术语 ID");
      else toast.toastWarning("自动复制失败：已打开手动复制弹窗。");
    },
    [toast],
  );

  const load = useCallback(async () => {
    if (!projectId) return;
    if (loading) return;
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (query.trim()) qs.set("q", query.trim());
      qs.set("include_disabled", "1");
      const res = await apiJson<{ terms: GlossaryTerm[] }>(
        `/api/projects/${projectId}/glossary_terms?${qs.toString()}`,
      );
      setTerms(Array.isArray(res.data.terms) ? res.data.terms : []);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setLoading(false);
    }
  }, [loading, projectId, query, toast]);

  const doCreate = useCallback(async () => {
    if (!projectId) return;
    if (creating) return;
    const term = createTerm.trim();
    if (!term) return;
    const aliases = parseAliasesInput(createAliases);

    setCreating(true);
    try {
      const res = await apiJson<{ term: GlossaryTerm }>(`/api/projects/${projectId}/glossary_terms`, {
        method: "POST",
        body: JSON.stringify({ term, aliases, enabled: 1 }),
      });
      toast.toastSuccess("已创建术语", res.request_id);
      setCreateTerm("");
      setCreateAliases("");
      setTerms((prev) => [res.data.term, ...prev]);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setCreating(false);
    }
  }, [createAliases, createTerm, creating, projectId, toast]);

  const startEdit = useCallback(
    (id: string) => {
      const row = byId[id];
      if (!row) return;
      setEditingId(id);
      setEditingTerm(row.term);
      setEditingAliases((row.aliases ?? []).join(", "));
    },
    [byId],
  );

  const cancelEdit = useCallback(() => {
    setEditingId(null);
    setEditingTerm("");
    setEditingAliases("");
  }, []);

  const saveEdit = useCallback(async () => {
    if (!projectId) return;
    if (!editingId) return;
    if (savingId) return;
    const term = editingTerm.trim();
    if (!term) return;
    const aliases = parseAliasesInput(editingAliases);

    setSavingId(editingId);
    try {
      const res = await apiJson<{ term: GlossaryTerm }>(`/api/projects/${projectId}/glossary_terms/${editingId}`, {
        method: "PUT",
        body: JSON.stringify({ term, aliases }),
      });
      toast.toastSuccess("已保存", res.request_id);
      setTerms((prev) => prev.map((t) => (t.id === editingId ? res.data.term : t)));
      cancelEdit();
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setSavingId(null);
    }
  }, [cancelEdit, editingAliases, editingId, editingTerm, projectId, savingId, toast]);

  const toggleEnabled = useCallback(
    async (row: GlossaryTerm, next: boolean) => {
      if (!projectId) return;
      if (savingId) return;
      setSavingId(row.id);
      try {
        const res = await apiJson<{ term: GlossaryTerm }>(`/api/projects/${projectId}/glossary_terms/${row.id}`, {
          method: "PUT",
          body: JSON.stringify({ enabled: next ? 1 : 0 }),
        });
        setTerms((prev) => prev.map((t) => (t.id === row.id ? res.data.term : t)));
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setSavingId(null);
      }
    },
    [projectId, savingId, toast],
  );

  const deleteTerm = useCallback(
    async (row: GlossaryTerm) => {
      if (!projectId) return;
      const ok = await confirm.confirm({
        title: "删除术语？",
        description: `将删除“${row.term}”。该操作不可撤销。`,
        confirmText: "删除",
        cancelText: "取消",
        danger: true,
      });
      if (!ok) return;
      setSavingId(row.id);
      try {
        const res = await apiJson(`/api/projects/${projectId}/glossary_terms/${row.id}`, { method: "DELETE" });
        toast.toastSuccess("已删除", res.request_id);
        setTerms((prev) => prev.filter((t) => t.id !== row.id));
        if (editingId === row.id) cancelEdit();
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setSavingId(null);
      }
    },
    [cancelEdit, confirm, editingId, projectId, toast],
  );

  const rebuild = useCallback(async () => {
    if (!projectId) return;
    if (rebuilding) return;
    setRebuilding(true);
    try {
      const res = await apiJson(`/api/projects/${projectId}/glossary_terms/rebuild`, {
        method: "POST",
        body: JSON.stringify({ include_chapters: true, include_imports: true, max_terms_per_source: 60 }),
      });
      toast.toastSuccess("已重建 glossary（auto）", res.request_id);
      await load();
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setRebuilding(false);
    }
  }, [load, projectId, rebuilding, toast]);

  const exportAll = useCallback(async () => {
    if (!projectId) return;
    if (exporting) return;
    setExporting(true);
    try {
      const res = await apiJson<{ export: unknown }>(`/api/projects/${projectId}/glossary_terms/export_all`);
      const blob = new Blob([JSON.stringify(res.data.export ?? {}, null, 2)], {
        type: "application/json;charset=utf-8",
      });
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = objectUrl;
      a.download = `glossary-${projectId}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      toast.toastSuccess("已导出 glossary JSON", res.request_id);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setExporting(false);
    }
  }, [exporting, projectId, toast]);

  return (
    <DebugPageShell
      title="术语映射（Glossary）"
      description={
        <div className="grid gap-1">
          <div>维护“术语 → 别名”映射，供 worldbook/graph/rag 进行可选增强（默认关闭）。</div>
          <div className="callout-warning">风险：自动抽取可能产生误召回；建议先重建再人工筛选。</div>
        </div>
      }
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn btn-secondary" aria-label="glossary_refresh" onClick={() => void load()} type="button">
            刷新
          </button>
          <button
            className="btn btn-secondary"
            aria-label="glossary_rebuild"
            disabled={rebuilding}
            onClick={() => void rebuild()}
            type="button"
          >
            {rebuilding ? "重建中…" : "重建（抽取）"}
          </button>
          <button
            className="btn btn-secondary"
            aria-label="glossary_export"
            disabled={exporting}
            onClick={() => void exportAll()}
            type="button"
          >
            {exporting ? "导出中…" : "导出 JSON"}
          </button>
          {projectId ? (
            <>
              <Link className="btn btn-secondary" to={`/projects/${projectId}/search`}>
                返回搜索
              </Link>
              <Link className="btn btn-secondary" to={`/projects/${projectId}/rag`}>
                RAG 配置
              </Link>
            </>
          ) : null}
        </div>
      }
    >
      <section className="grid gap-3">
        <div className="grid gap-2 rounded-atelier border border-border bg-canvas p-4">
          <div className="text-sm font-semibold text-ink">搜索</div>
          <div className="flex flex-wrap items-center gap-2">
            <input
              aria-label="glossary_search"
              className="input w-full max-w-lg"
              placeholder="输入术语或别名（支持模糊匹配）"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button className="btn btn-primary" disabled={loading} onClick={() => void load()} type="button">
              {loading ? "查询中…" : "查询"}
            </button>
          </div>
          <div className="text-[11px] text-subtext">
            提示：启用增强需在后端设置 `GLOSSARY_QUERY_EXPAND_ENABLED=true`（默认关闭）。
          </div>
        </div>

        <div className="grid gap-2 rounded-atelier border border-border bg-canvas p-4">
          <div className="text-sm font-semibold text-ink">新增术语</div>
          <div className="grid gap-2">
            <input
              aria-label="glossary_create_term"
              className="input"
              placeholder="术语（term）"
              value={createTerm}
              onChange={(e) => setCreateTerm(e.target.value)}
            />
            <input
              aria-label="glossary_create_aliases"
              className="input"
              placeholder="别名（aliases），用逗号分隔"
              value={createAliases}
              onChange={(e) => setCreateAliases(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <button
                className="btn btn-primary"
                disabled={!createTerm.trim() || creating}
                onClick={() => void doCreate()}
                type="button"
              >
                {creating ? "创建中…" : "创建"}
              </button>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-3">
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm font-semibold text-ink">术语列表</div>
          <div className="text-xs text-subtext">{terms.length} 条</div>
        </div>

        {terms.length === 0 ? (
          <div className="rounded-atelier border border-border bg-canvas p-4 text-sm text-subtext">
            暂无术语。你可以：
            <ul className="mt-2 list-disc pl-5 text-xs">
              <li>点击“重建（抽取）”从章节/导入文本中生成 auto 术语；</li>
              <li>或在上方“新增术语”手动创建。</li>
            </ul>
          </div>
        ) : null}

        <div className="grid gap-3">
          {terms.map((t) => {
            const isEditing = editingId === t.id;
            const saving = savingId === t.id;
            return (
              <div key={t.id} className="rounded-atelier border border-border bg-canvas p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="truncate text-sm font-semibold text-ink">{t.term}</div>
                      <span className="rounded-atelier border border-border bg-surface px-2 py-0.5 text-[11px] text-subtext">
                        {t.origin === "auto" ? "auto" : "manual"}
                      </span>
                      {t.enabled ? (
                        <span className="rounded-atelier border border-border bg-surface px-2 py-0.5 text-[11px] text-subtext">
                          enabled
                        </span>
                      ) : (
                        <span className="rounded-atelier border border-border bg-surface px-2 py-0.5 text-[11px] text-subtext">
                          disabled
                        </span>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-subtext">
                      别名：{(t.aliases ?? []).length ? (t.aliases ?? []).join("、") : "（无）"}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <label className="flex items-center gap-2 text-xs text-subtext">
                      <input
                        className="checkbox"
                        checked={Boolean(t.enabled)}
                        disabled={saving}
                        onChange={(e) => void toggleEnabled(t, e.target.checked)}
                        type="checkbox"
                      />
                      启用
                    </label>
                    <button className="btn btn-secondary" onClick={() => void copyTermId(t.id)} type="button">
                      复制 ID
                    </button>
                    {isEditing ? (
                      <>
                        <button
                          className="btn btn-primary"
                          disabled={savingId !== null}
                          onClick={() => void saveEdit()}
                          type="button"
                        >
                          保存
                        </button>
                        <button
                          className="btn btn-secondary"
                          disabled={savingId !== null}
                          onClick={cancelEdit}
                          type="button"
                        >
                          取消
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          className="btn btn-secondary"
                          disabled={savingId !== null}
                          onClick={() => startEdit(t.id)}
                          type="button"
                        >
                          编辑
                        </button>
                        <button
                          className="btn btn-danger"
                          disabled={savingId !== null}
                          onClick={() => void deleteTerm(t)}
                          type="button"
                        >
                          删除
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {isEditing ? (
                  <div className="mt-3 grid gap-2 rounded-atelier border border-border bg-surface p-3">
                    <input
                      aria-label="glossary_edit_term"
                      className="input"
                      value={editingTerm}
                      onChange={(e) => setEditingTerm(e.target.value)}
                      placeholder="term"
                    />
                    <input
                      aria-label="glossary_edit_aliases"
                      className="input"
                      value={editingAliases}
                      onChange={(e) => setEditingAliases(e.target.value)}
                      placeholder="aliases（逗号分隔）"
                    />
                    <div className="text-[11px] text-subtext">保存后会立即生效（启用增强仍需后端开关）。</div>
                  </div>
                ) : null}

                {t.sources?.length ? (
                  <div className="mt-3 grid gap-2">
                    <div className="text-xs text-subtext">引用来源</div>
                    <div className="flex flex-wrap gap-2">
                      {t.sources.map((s) => {
                        const st = s.source_type;
                        const sid = s.source_id;
                        const label = sourceLabel(s);
                        const to =
                          st === "chapter" && projectId
                            ? `/projects/${projectId}/writing?chapterId=${encodeURIComponent(sid)}`
                            : st === "import" && projectId
                              ? `/projects/${projectId}/import?docId=${encodeURIComponent(sid)}`
                              : null;
                        return to ? (
                          <Link
                            key={`${st}:${sid}`}
                            className="ui-focus-ring rounded-atelier border border-border bg-surface px-3 py-1 text-xs text-ink hover:bg-surface-hover"
                            to={to}
                          >
                            {st}:{label}
                          </Link>
                        ) : (
                          <span
                            key={`${st}:${sid}`}
                            className="rounded-atelier border border-border bg-surface px-3 py-1 text-xs text-subtext"
                          >
                            {st}:{label}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </section>

      <DebugDetails title="Debug（raw JSON）">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <button className="btn btn-secondary" onClick={() => void copyRawJson()} type="button">
            复制 JSON
          </button>
          <div className="text-xs text-subtext">terms: {terms.length}</div>
        </div>
        <pre className="mt-2 max-h-[28rem] overflow-auto rounded-atelier border border-border bg-surface p-3 text-[11px] text-subtext">
          {rawJson}
        </pre>
      </DebugDetails>
    </DebugPageShell>
  );
}
