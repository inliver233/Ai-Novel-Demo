import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { DebugDetails, DebugPageShell } from "../components/atelier/DebugPageShell";
import { RequestIdBadge } from "../components/ui/RequestIdBadge";
import { useToast } from "../components/ui/toast";
import { useProjectData } from "../hooks/useProjectData";
import { UI_COPY } from "../lib/uiCopy";
import { ApiError, apiJson } from "../services/apiClient";
import type { ProjectSettings } from "../types";
import { RagAdvancedDebugPanel } from "./rag/RagAdvancedDebugPanel";
import { RagKnowledgeBasePanel } from "./rag/RagKnowledgeBasePanel";
import { RagQueryPanel } from "./rag/RagQueryPanel";
import { RagStatusPanel } from "./rag/RagStatusPanel";
import type { KnowledgeBase, VectorRagResult, VectorSource } from "./rag/types";
import { formatIsoToLocal } from "./rag/utils";

export function RagPage() {
  const { projectId } = useParams();
  const toast = useToast();

  const settingsQuery = useProjectData<ProjectSettings>(projectId, async (id) => {
    const res = await apiJson<{ settings: ProjectSettings }>(`/api/projects/${id}/settings`);
    return res.data.settings;
  });

  const [rerankEnabled, setRerankEnabled] = useState(false);
  const [rerankMethod, setRerankMethod] = useState("auto");
  const [rerankTopK, setRerankTopK] = useState(20);
  const [rerankHybridAlpha, setRerankHybridAlpha] = useState(0);
  const [rerankSaving, setRerankSaving] = useState(false);

  const [sources, setSources] = useState<VectorSource[]>(["worldbook", "outline", "chapter", "story_memory"]);
  const [queryText, setQueryText] = useState("");

  const [superSortMode, setSuperSortMode] = useState<"disabled" | "order" | "weights">("disabled");
  const [superSortOrderText, setSuperSortOrderText] = useState("worldbook,outline,chapter,story_memory");
  const [superSortWeights, setSuperSortWeights] = useState({ worldbook: 1, outline: 1, chapter: 1 });

  const [kbLoading, setKbLoading] = useState(false);
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [selectedKbIds, setSelectedKbIds] = useState<string[]>([]);
  const [kbDraftById, setKbDraftById] = useState<Record<string, Pick<KnowledgeBase, "name" | "enabled" | "weight">>>(
    {},
  );
  const [kbDirtyById, setKbDirtyById] = useState<Record<string, boolean>>({});
  const [kbOrderDirty, setKbOrderDirty] = useState(false);
  const [kbDragId, setKbDragId] = useState<string | null>(null);
  const [kbCreateName, setKbCreateName] = useState("");
  const [kbCreateLoading, setKbCreateLoading] = useState(false);
  const [kbSaveLoadingId, setKbSaveLoadingId] = useState<string | null>(null);
  const [kbDeleteLoadingId, setKbDeleteLoadingId] = useState<string | null>(null);

  const [statusLoading, setStatusLoading] = useState(false);
  const [ingestLoading, setIngestLoading] = useState(false);
  const [rebuildLoading, setRebuildLoading] = useState(false);
  const [queryLoading, setQueryLoading] = useState(false);

  const [status, setStatus] = useState<VectorRagResult | null>(null);
  const [ingestResult, setIngestResult] = useState<unknown>(null);
  const [rebuildResult, setRebuildResult] = useState<unknown>(null);
  const [queryResult, setQueryResult] = useState<VectorRagResult | null>(null);
  const [queryRequestId, setQueryRequestId] = useState<string | null>(null);
  const [rawQueryText, setRawQueryText] = useState<string | null>(null);
  const [normalizedQueryText, setNormalizedQueryText] = useState<string | null>(null);
  const [queryPreprocessObs, setQueryPreprocessObs] = useState<unknown>(null);

  const [debugOpen, setDebugOpen] = useState(false);
  const [lastOpRequestId, setLastOpRequestId] = useState<string | null>(null);
  const [lastOp, setLastOp] = useState<"status" | "ingest" | "rebuild" | null>(null);

  const busy = statusLoading || ingestLoading || rebuildLoading || queryLoading || rerankSaving;

  const vectorIndexDirty = status?.index ? Boolean(status.index.dirty) : null;
  const lastVectorBuildAt = status?.index ? (status.index.last_build_at ?? null) : null;
  const vectorEnabled = status ? Boolean(status.enabled) : null;
  const vectorDisabledReason = status && typeof status.disabled_reason === "string" ? status.disabled_reason : null;

  useEffect(() => {
    if (ingestLoading || rebuildLoading || ingestResult || rebuildResult) setDebugOpen(true);
  }, [ingestLoading, ingestResult, rebuildLoading, rebuildResult]);

  useEffect(() => {
    if (!settingsQuery.data) return;
    setRerankEnabled(Boolean(settingsQuery.data.vector_rerank_effective_enabled));
    setRerankMethod(String(settingsQuery.data.vector_rerank_effective_method ?? "auto") || "auto");
    setRerankTopK(Number(settingsQuery.data.vector_rerank_effective_top_k ?? 20) || 20);
  }, [settingsQuery.data]);

  const applyRerank = useCallback(async () => {
    if (!projectId) return;
    setRerankSaving(true);
    try {
      const method = rerankMethod.trim() || "auto";
      const topK = Math.max(1, Math.min(1000, Math.floor(rerankTopK)));
      const res = await apiJson<{ settings: ProjectSettings }>(`/api/projects/${projectId}/settings`, {
        method: "PUT",
        body: JSON.stringify({
          vector_rerank_enabled: Boolean(rerankEnabled),
          vector_rerank_method: method,
          vector_rerank_top_k: topK,
        }),
      });
      settingsQuery.setData(res.data.settings);
      toast.toastSuccess("已更新 rerank 配置", res.request_id);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setRerankSaving(false);
    }
  }, [projectId, rerankEnabled, rerankMethod, rerankTopK, settingsQuery, toast]);

  const toggleSource = useCallback((src: VectorSource) => {
    setSources((prev) => (prev.includes(src) ? prev.filter((v) => v !== src) : [...prev, src]));
  }, []);

  const sortedSources = useMemo(
    () =>
      (["worldbook", "outline", "chapter", "story_memory"] as const).filter((s) =>
        sources.includes(s),
      ) as VectorSource[],
    [sources],
  );

  const loadKbs = useCallback(async () => {
    if (!projectId) return;
    setKbLoading(true);
    try {
      const res = await apiJson<{ kbs: KnowledgeBase[] }>(`/api/projects/${projectId}/vector/kbs`);
      const list = Array.isArray(res.data?.kbs) ? res.data.kbs : [];
      setKbs(list);
      setKbDraftById((prev) => {
        const next = { ...prev };
        for (const kb of list) {
          if (!next[kb.kb_id]) next[kb.kb_id] = { name: kb.name, enabled: kb.enabled, weight: kb.weight };
        }
        return next;
      });
      setKbDirtyById((prev) => {
        const next = { ...prev };
        for (const kb of list) {
          if (!(kb.kb_id in next)) next[kb.kb_id] = false;
        }
        return next;
      });
      setSelectedKbIds((prev) => {
        const valid = prev.filter((id) => list.some((kb) => kb.kb_id === id));
        if (valid.length) return valid;
        const enabledIds = list.filter((kb) => kb.enabled).map((kb) => kb.kb_id);
        return enabledIds.length ? enabledIds : list.length ? [list[0].kb_id] : [];
      });
      setKbOrderDirty(false);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setKbLoading(false);
    }
  }, [projectId, toast]);

  useEffect(() => {
    if (!projectId) return;
    void loadKbs();
  }, [loadKbs, projectId]);

  const toggleKbSelected = useCallback((kbId: string) => {
    const kid = String(kbId || "").trim();
    if (!kid) return;
    setSelectedKbIds((prev) => (prev.includes(kid) ? prev.filter((v) => v !== kid) : [...prev, kid]));
  }, []);

  const updateKbDraft = useCallback(
    (kbId: string, patch: Partial<Pick<KnowledgeBase, "name" | "enabled" | "weight">>) => {
      const kid = String(kbId || "").trim();
      if (!kid) return;
      setKbDraftById((prev) => ({ ...prev, [kid]: { ...prev[kid], ...patch } }));
      setKbDirtyById((prev) => ({ ...prev, [kid]: true }));
    },
    [],
  );

  const createKb = useCallback(async () => {
    if (!projectId) return;
    const name = kbCreateName.trim();
    if (!name) {
      toast.toastError("KB 名称不能为空");
      return;
    }
    setKbCreateLoading(true);
    try {
      const res = await apiJson<{ kb: KnowledgeBase }>(`/api/projects/${projectId}/vector/kbs`, {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      toast.toastSuccess("已创建 KB", res.request_id);
      setKbCreateName("");
      await loadKbs();
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setKbCreateLoading(false);
    }
  }, [kbCreateName, loadKbs, projectId, toast]);

  const saveKb = useCallback(
    async (kbId: string) => {
      if (!projectId) return;
      const kid = String(kbId || "").trim();
      if (!kid) return;
      const draft = kbDraftById[kid];
      if (!draft) {
        toast.toastError("KB 未加载");
        return;
      }
      setKbSaveLoadingId(kid);
      try {
        const res = await apiJson<{ kb: KnowledgeBase }>(
          `/api/projects/${projectId}/vector/kbs/${encodeURIComponent(kid)}`,
          {
            method: "PUT",
            body: JSON.stringify({ name: draft.name, enabled: draft.enabled, weight: draft.weight }),
          },
        );
        setKbs((prev) => prev.map((kb) => (kb.kb_id === kid ? res.data.kb : kb)));
        setKbDraftById((prev) => ({
          ...prev,
          [kid]: { name: res.data.kb.name, enabled: res.data.kb.enabled, weight: res.data.kb.weight },
        }));
        setKbDirtyById((prev) => ({ ...prev, [kid]: false }));
        toast.toastSuccess("已保存 KB", res.request_id);
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setKbSaveLoadingId(null);
      }
    },
    [kbDraftById, projectId, toast],
  );

  const deleteKb = useCallback(
    async (kbId: string) => {
      if (!projectId) return;
      const kid = String(kbId || "").trim();
      if (!kid) return;
      setKbDeleteLoadingId(kid);
      try {
        const res = await apiJson<{ deleted: boolean }>(
          `/api/projects/${projectId}/vector/kbs/${encodeURIComponent(kid)}`,
          {
            method: "DELETE",
          },
        );
        toast.toastSuccess("已删除 KB", res.request_id);
        await loadKbs();
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setKbDeleteLoadingId(null);
      }
    },
    [loadKbs, projectId, toast],
  );

  const saveKbOrder = useCallback(async () => {
    if (!projectId) return;
    const ids = kbs.map((kb) => kb.kb_id);
    if (!ids.length) return;
    setKbLoading(true);
    try {
      const res = await apiJson<{ kbs: KnowledgeBase[] }>(`/api/projects/${projectId}/vector/kbs/reorder`, {
        method: "POST",
        body: JSON.stringify({ kb_ids: ids }),
      });
      setKbs(res.data.kbs ?? []);
      setKbOrderDirty(false);
      toast.toastSuccess("已保存 KB 排序", res.request_id);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setKbLoading(false);
    }
  }, [kbs, projectId, toast]);

  const moveKb = useCallback((fromKbId: string, toKbId: string) => {
    const from = String(fromKbId || "").trim();
    const to = String(toKbId || "").trim();
    if (!from || !to || from === to) return;
    setKbs((prev) => {
      const items = [...prev];
      const fromIdx = items.findIndex((kb) => kb.kb_id === from);
      const toIdx = items.findIndex((kb) => kb.kb_id === to);
      if (fromIdx < 0 || toIdx < 0) return prev;
      const [item] = items.splice(fromIdx, 1);
      items.splice(toIdx, 0, item);
      return items.map((kb, idx) => ({ ...kb, order: idx }));
    });
    setKbOrderDirty(true);
  }, []);

  const runStatus = useCallback(
    async (opts?: { updateRequestId?: boolean }) => {
      if (!projectId) return;
      if (sortedSources.length === 0) {
        toast.toastError("至少选择一个 source");
        return;
      }
      setStatusLoading(true);
      try {
        const res = await apiJson<{ result: VectorRagResult }>(`/api/projects/${projectId}/vector/status`, {
          method: "POST",
          body: JSON.stringify({ sources: sortedSources }),
        });
        setStatus(res.data?.result ?? null);
        if (opts?.updateRequestId ?? true) {
          setLastOpRequestId(res.request_id ?? null);
          setLastOp("status");
        }
      } catch (e) {
        const err =
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
        toast.toastError(`${err.message} (${err.code})`, err.requestId);
      } finally {
        setStatusLoading(false);
      }
    },
    [projectId, sortedSources, toast],
  );

  useEffect(() => {
    if (!projectId) return;
    if (sortedSources.length === 0) return;
    void runStatus();
  }, [projectId, runStatus, sortedSources]);

  const runIngest = useCallback(async () => {
    if (!projectId) return;
    if (sortedSources.length === 0) {
      toast.toastError("至少选择一个 source");
      return;
    }
    setIngestLoading(true);
    try {
      const res = await apiJson<{ result: unknown }>(`/api/projects/${projectId}/vector/ingest`, {
        method: "POST",
        body: JSON.stringify({ sources: sortedSources, kb_ids: selectedKbIds }),
      });
      setIngestResult(res.data?.result ?? null);
      setLastOpRequestId(res.request_id ?? null);
      setLastOp("ingest");
      toast.toastSuccess("ingest 已触发", res.request_id);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setIngestLoading(false);
    }
  }, [projectId, selectedKbIds, sortedSources, toast]);

  const runRebuild = useCallback(async () => {
    if (!projectId) return;
    if (sortedSources.length === 0) {
      toast.toastError("至少选择一个 source");
      return;
    }
    setRebuildLoading(true);
    try {
      const res = await apiJson<{ result: unknown }>(`/api/projects/${projectId}/vector/rebuild`, {
        method: "POST",
        body: JSON.stringify({ sources: sortedSources, kb_ids: selectedKbIds }),
      });
      const result = res.data?.result ?? null;
      setRebuildResult(result);
      if (result && typeof result === "object") {
        const out = result as Record<string, unknown>;
        const enabled = Boolean(out.enabled);
        const skipped = Boolean(out.skipped);
        const disabledReason = typeof out.disabled_reason === "string" ? out.disabled_reason : null;
        const error = typeof out.error === "string" ? out.error : null;
        if (!enabled || skipped) {
          toast.toastError(`rebuild 未执行：${disabledReason ?? error ?? "unknown"}`, res.request_id);
        } else {
          toast.toastSuccess("rebuild 已触发", res.request_id);
        }
      } else {
        toast.toastSuccess("rebuild 已触发", res.request_id);
      }
      setLastOpRequestId(res.request_id ?? null);
      setLastOp("rebuild");
      await runStatus({ updateRequestId: false });
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setRebuildLoading(false);
    }
  }, [projectId, runStatus, selectedKbIds, sortedSources, toast]);

  const runQuery = useCallback(async () => {
    if (!projectId) return;
    if (sortedSources.length === 0) {
      toast.toastError("至少选择一个 source");
      return;
    }
    setQueryLoading(true);
    try {
      const superSort =
        superSortMode === "order"
          ? {
              enabled: true,
              source_order: superSortOrderText
                .split(/[\\s,|;]+/g)
                .map((s) => s.trim())
                .filter(
                  (s): s is VectorSource =>
                    s === "worldbook" || s === "outline" || s === "chapter" || s === "story_memory",
                ),
            }
          : superSortMode === "weights"
            ? { enabled: true, source_weights: superSortWeights }
            : null;

      const res = await apiJson<{
        result: VectorRagResult;
        raw_query_text?: unknown;
        normalized_query_text?: unknown;
        preprocess_obs?: unknown;
      }>(`/api/projects/${projectId}/vector/query`, {
        method: "POST",
        body: JSON.stringify({
          query_text: queryText,
          sources: sortedSources,
          kb_ids: selectedKbIds,
          rerank_hybrid_alpha: rerankHybridAlpha,
          ...(superSort ? { super_sort: superSort } : {}),
        }),
      });
      setQueryResult(res.data?.result ?? null);
      setQueryRequestId(res.request_id ?? null);
      setRawQueryText(typeof res.data?.raw_query_text === "string" ? res.data.raw_query_text : queryText);
      setNormalizedQueryText(
        typeof res.data?.normalized_query_text === "string" ? res.data.normalized_query_text : null,
      );
      setQueryPreprocessObs(res.data?.preprocess_obs ?? null);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setQueryLoading(false);
    }
  }, [
    projectId,
    queryText,
    selectedKbIds,
    sortedSources,
    rerankHybridAlpha,
    superSortMode,
    superSortOrderText,
    superSortWeights,
    toast,
  ]);

  return (
    <DebugPageShell
      title={UI_COPY.rag.title}
      description={UI_COPY.rag.subtitle}
      actions={
        <>
          <button
            className="btn btn-secondary"
            disabled={statusLoading}
            onClick={() => void runStatus()}
            aria-label="刷新状态 (rag_refresh_status)"
            type="button"
          >
            {statusLoading ? "加载中…" : "刷新状态"}
          </button>
          <button
            className="btn btn-secondary"
            disabled={ingestLoading}
            onClick={() => void runIngest()}
            aria-label={`${UI_COPY.rag.ingest} (rag_ingest)`}
            type="button"
          >
            {ingestLoading ? "执行中…" : UI_COPY.rag.ingest}
          </button>
          <button
            className={vectorIndexDirty ? "btn btn-primary" : "btn btn-secondary"}
            disabled={rebuildLoading}
            onClick={() => void runRebuild()}
            aria-label={`${UI_COPY.rag.rebuild} (rag_rebuild)`}
            type="button"
          >
            {rebuildLoading
              ? "执行中…"
              : vectorIndexDirty && vectorEnabled === false
                ? UI_COPY.rag.rebuildNeedConfig
                : vectorIndexDirty
                  ? UI_COPY.rag.rebuildRecommended
                  : UI_COPY.rag.rebuild}
          </button>
          {projectId ? (
            <Link
              className="btn btn-secondary"
              to={`/projects/${projectId}/prompts#rag-config`}
              aria-label={`${UI_COPY.rag.settings} (rag_settings)`}
            >
              {UI_COPY.rag.settings}
            </Link>
          ) : null}
        </>
      }
    >
      <DebugDetails title={UI_COPY.help.title}>
        <div className="grid gap-2 text-xs text-subtext">
          <div>{UI_COPY.rag.usageHint}</div>
          <div>{UI_COPY.rag.exampleHint}</div>
          <div>
            快速开始：创建/启用 KB → 点击“{UI_COPY.rag.ingest}”导入 → “{UI_COPY.rag.rebuild}”构建索引 → 在下方 Query
            预览命中。
          </div>
          <div>
            验证 rerank 是否生效：启用后在下方 Query 执行查询，结果面板会显示 <span className="font-mono">rerank:</span>{" "}
            概要，并可展开 <span className="font-mono">rerank_obs</span> 查看观测信息（用于排障）。
          </div>
          {projectId ? (
            <div>
              配置入口：到{" "}
              <Link className="underline" to={`/projects/${projectId}/prompts#rag-config`}>
                {UI_COPY.rag.settings}
              </Link>{" "}
              完成 Embedding/Rerank 配置后再重建索引。
            </div>
          ) : null}
          {projectId ? (
            <div>
              导入小说/资料：到{" "}
              <Link className="underline" to={`/projects/${projectId}/import`}>
                导入页
              </Link>{" "}
              上传 txt/md 并应用提案（WorldBook / story_memory）。
            </div>
          ) : null}
          <div className="text-warning">{UI_COPY.rag.riskHint}</div>
        </div>
      </DebugDetails>

      {projectId ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-atelier border border-border bg-canvas p-3">
          <div className="text-xs text-subtext">
            小说/资料导入：上传 txt/md 并应用提案（WorldBook / story_memory）。
          </div>
          <Link className="btn btn-secondary" to={`/projects/${projectId}/import`}>
            打开导入页
          </Link>
        </div>
      ) : null}

      <div className="rounded-atelier border border-border bg-canvas p-3 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="text-subtext">
            索引过期（dirty）: {vectorIndexDirty === null ? "loading…" : String(vectorIndexDirty)} |
            上次构建（last_build_at）: {lastVectorBuildAt ?? "-"}
            {lastVectorBuildAt ? `（${formatIsoToLocal(lastVectorBuildAt)}）` : ""}
          </div>
          {vectorIndexDirty === null ? (
            <div className="text-subtext">索引状态加载中…</div>
          ) : vectorIndexDirty ? (
            vectorEnabled === false ? (
              <div className="text-ink">
                索引已过期，但向量服务未启用（disabled_reason: {vectorDisabledReason ?? "-"}）。请先在{" "}
                {projectId ? (
                  <Link className="underline" to={`/projects/${projectId}/prompts#rag-config`}>
                    {UI_COPY.rag.settings}
                  </Link>
                ) : (
                  UI_COPY.rag.settings
                )}{" "}
                配置向量化（Embedding），再 {UI_COPY.rag.rebuild}。
              </div>
            ) : (
              <div className="text-ink">索引已过期：建议点击右上角 “{UI_COPY.rag.rebuildRecommended}” 重新构建。</div>
            )
          ) : (
            <div className="text-subtext">索引为 clean，无需重建。</div>
          )}
        </div>
        {lastOpRequestId ? (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-subtext">last_op: {lastOp ?? "-"}</span>
            <RequestIdBadge requestId={lastOpRequestId} />
          </div>
        ) : null}
      </div>

      <RagStatusPanel status={status} />

      <RagKnowledgeBasePanel
        projectId={projectId}
        kbLoading={kbLoading}
        kbOrderDirty={kbOrderDirty}
        loadKbs={loadKbs}
        saveKbOrder={saveKbOrder}
        selectedKbIds={selectedKbIds}
        queryResult={queryResult}
        kbs={kbs}
        kbDraftById={kbDraftById}
        kbDirtyById={kbDirtyById}
        kbDragId={kbDragId}
        setKbDragId={setKbDragId}
        moveKb={moveKb}
        toggleKbSelected={toggleKbSelected}
        updateKbDraft={updateKbDraft}
        kbSaveLoadingId={kbSaveLoadingId}
        kbDeleteLoadingId={kbDeleteLoadingId}
        saveKb={saveKb}
        deleteKb={deleteKb}
        kbCreateName={kbCreateName}
        setKbCreateName={setKbCreateName}
        kbCreateLoading={kbCreateLoading}
        createKb={createKb}
      />

      <RagQueryPanel
        busy={busy}
        sources={sources}
        toggleSource={toggleSource}
        queryText={queryText}
        setQueryText={setQueryText}
        queryLoading={queryLoading}
        runQuery={runQuery}
        projectId={projectId}
        sortedSources={sortedSources}
        queryResult={queryResult}
        queryRequestId={queryRequestId}
        rawQueryText={rawQueryText}
        normalizedQueryText={normalizedQueryText}
        queryPreprocessObs={queryPreprocessObs}
      />

      <RagAdvancedDebugPanel
        projectId={projectId}
        debugOpen={debugOpen}
        setDebugOpen={setDebugOpen}
        settingsQuery={settingsQuery}
        busy={busy}
        rerankEnabled={rerankEnabled}
        setRerankEnabled={setRerankEnabled}
        rerankMethod={rerankMethod}
        setRerankMethod={setRerankMethod}
        rerankTopK={rerankTopK}
        setRerankTopK={setRerankTopK}
        rerankHybridAlpha={rerankHybridAlpha}
        setRerankHybridAlpha={setRerankHybridAlpha}
        superSortMode={superSortMode}
        setSuperSortMode={setSuperSortMode}
        superSortOrderText={superSortOrderText}
        setSuperSortOrderText={setSuperSortOrderText}
        superSortWeights={superSortWeights}
        setSuperSortWeights={setSuperSortWeights}
        rerankSaving={rerankSaving}
        applyRerank={applyRerank}
        ingestResult={ingestResult}
        rebuildResult={rebuildResult}
      />
    </DebugPageShell>
  );
}
