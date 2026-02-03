import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { DebugDetails, DebugPageShell } from "../components/atelier/DebugPageShell";
import { RequestIdBadge } from "../components/ui/RequestIdBadge";
import { copyText } from "../lib/copyText";
import { UI_COPY } from "../lib/uiCopy";
import { ApiError, apiJson } from "../services/apiClient";
import { useToast } from "../components/ui/toast";

type GraphNode = {
  id: string;
  entity_type: string;
  name: string;
  summary_md?: string | null;
  attributes?: Record<string, unknown>;
  matched?: boolean;
};

type GraphEdge = {
  id: string;
  from_entity_id: string;
  to_entity_id: string;
  from_name?: string;
  to_name?: string;
  relation_type: string;
  description_md?: string | null;
  attributes?: Record<string, unknown>;
};

type GraphEvidence = {
  id: string;
  source_type: string;
  source_id?: string | null;
  quote_md: string;
  attributes?: Record<string, unknown>;
  created_at?: string;
};

type GraphQueryResult = {
  enabled: boolean;
  disabled_reason?: string | null;
  error?: string;
  query_text: string;
  matched?: { entity_ids: string[]; entity_names: string[] };
  nodes: GraphNode[];
  edges: GraphEdge[];
  evidence: GraphEvidence[];
  truncated?: { nodes?: boolean; edges?: boolean };
  prompt_block?: { identifier: string; role: string; text_md: string };
  timings_ms?: Record<string, number>;
};

function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function GraphPage() {
  const { projectId } = useParams();
  const toast = useToast();
  const [searchParams] = useSearchParams();

  const chapterId = String(searchParams.get("chapterId") || "").trim() || null;

  const [enabled, setEnabled] = useState(true);
  const [queryText, setQueryText] = useState("");
  const [loading, setLoading] = useState(false);
  const [requestId, setRequestId] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<GraphQueryResult | null>(null);

  const [autoUpdateFocus, setAutoUpdateFocus] = useState("");
  const [autoUpdateLoading, setAutoUpdateLoading] = useState(false);
  const [lastAutoUpdateTaskId, setLastAutoUpdateTaskId] = useState<string | null>(null);

  const injectionPreviewText = useMemo(
    () => (result?.prompt_block?.text_md ?? "").trim(),
    [result?.prompt_block?.text_md],
  );
  const advancedDebugText = useMemo(() => safeJson(result), [result]);

  const copyPreviewBlock = useCallback(
    async (text: string, opts: { emptyMessage: string; successMessage: string; dialogTitle: string }) => {
      if (!text.trim()) {
        toast.toastError(opts.emptyMessage, requestId ?? undefined);
        return;
      }
      const ok = await copyText(text, { title: opts.dialogTitle });
      if (ok) toast.toastSuccess(opts.successMessage, requestId ?? undefined);
      else toast.toastWarning("自动复制失败：已打开手动复制弹窗。", requestId ?? undefined);
    },
    [requestId, toast],
  );

  const matchedIds = useMemo(() => new Set(result?.matched?.entity_ids ?? []), [result?.matched?.entity_ids]);

  const characterRelationsHref = useMemo(() => {
    if (!projectId) return "";
    const params = new URLSearchParams();
    params.set("view", "character-relations");
    if (chapterId) params.set("chapterId", chapterId);
    return `/projects/${projectId}/structured-memory?${params.toString()}`;
  }, [chapterId, projectId]);

  const taskCenterHref = useMemo(() => {
    if (!projectId) return "";
    if (!lastAutoUpdateTaskId) return `/projects/${projectId}/tasks`;
    const params = new URLSearchParams();
    params.set("project_task_id", lastAutoUpdateTaskId);
    return `/projects/${projectId}/tasks?${params.toString()}`;
  }, [lastAutoUpdateTaskId, projectId]);

  const triggerGraphAutoUpdate = useCallback(async () => {
    if (!projectId) return;
    if (!chapterId) {
      toast.toastError(UI_COPY.graph.autoUpdateMissingChapterId);
      return;
    }

    setAutoUpdateLoading(true);
    try {
      const res = await apiJson<{ task_id: string }>(`/api/projects/${projectId}/graph/auto_update`, {
        method: "POST",
        body: JSON.stringify({
          chapter_id: chapterId,
          focus: autoUpdateFocus.trim() ? autoUpdateFocus.trim() : null,
        }),
      });
      const taskId = String(res.data?.task_id ?? "").trim();
      if (taskId) setLastAutoUpdateTaskId(taskId);
      toast.toastSuccess(UI_COPY.graph.autoUpdateCreatedToast, res.request_id);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setAutoUpdateLoading(false);
    }
  }, [autoUpdateFocus, chapterId, projectId, toast]);

  const runQuery = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiJson<{ result: GraphQueryResult }>(`/api/projects/${projectId}/graph/query`, {
        method: "POST",
        body: JSON.stringify({
          query_text: queryText,
          enabled,
          hop: 1,
          max_nodes: 40,
          max_edges: 120,
        }),
      });
      setResult(res.data?.result ?? null);
      setRequestId(res.request_id ?? null);
    } catch (e) {
      const err =
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      setError(err);
      setRequestId(err.requestId ?? null);
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setLoading(false);
    }
  }, [enabled, projectId, queryText, toast]);

  useEffect(() => {
    if (!projectId) return;
    void runQuery();
  }, [projectId, runQuery]);

  const statusText = result
    ? result.enabled
      ? "已启用"
      : `未启用（${result.disabled_reason ?? "未知原因"}）`
    : "未查询";

  return (
    <DebugPageShell
      title={UI_COPY.graph.title}
      description={UI_COPY.graph.subtitle}
      actions={
        <>
          <label className="flex items-center gap-2 text-xs text-subtext">
            <input
              className="checkbox"
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              aria-label="graph_enabled"
            />
            {UI_COPY.graph.enabledToggle}
          </label>
          <button className="btn btn-secondary" onClick={() => void runQuery()} disabled={loading} type="button">
            {loading ? "查询..." : UI_COPY.graph.queryRun}
          </button>
          {projectId ? (
            <Link className="btn btn-secondary" to={characterRelationsHref} aria-label="graph_open_character_relations">
              人物关系编辑
            </Link>
          ) : null}
        </>
      }
    >
      <DebugDetails title={UI_COPY.help.title}>
        <div className="grid gap-2 text-xs text-subtext">
          <div>{UI_COPY.graph.usageHint}</div>
          <div>{UI_COPY.graph.exampleHint}</div>
          <div className="text-warning">{UI_COPY.graph.riskHint}</div>
        </div>
      </DebugDetails>

      <label className="block">
        <div className="text-xs text-subtext">{UI_COPY.graph.queryTextLabel}</div>
        <input
          className="input mt-1"
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
          placeholder={UI_COPY.graph.queryTextPlaceholder}
          aria-label="graph_query_text"
        />
      </label>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-subtext">
        <span>示例：</span>
        <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => setQueryText("Alice")} type="button">
          Alice
        </button>
        <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => setQueryText("Bob")} type="button">
          Bob
        </button>
      </div>

      <div className="rounded-atelier border border-border bg-surface p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm text-ink">{UI_COPY.graph.autoUpdateTitle}</div>
          <button
            className="btn btn-secondary"
            disabled={autoUpdateLoading || !projectId || !chapterId}
            onClick={() => void triggerGraphAutoUpdate()}
            type="button"
          >
            {autoUpdateLoading ? "创建中..." : UI_COPY.graph.autoUpdateCreateButton}
          </button>
        </div>
        <div className="mt-1 text-xs text-subtext">
          chapter_id: {chapterId ?? "（缺少）"}
          {!chapterId ? <span className="ml-2 text-warning">{UI_COPY.graph.autoUpdateMissingChapterId}</span> : null}
        </div>
        <label className="mt-3 grid gap-1">
          <span className="text-xs text-subtext">{UI_COPY.graph.autoUpdateFocusLabel}</span>
          <input
            className="input"
            value={autoUpdateFocus}
            disabled={autoUpdateLoading}
            onChange={(e) => setAutoUpdateFocus(e.target.value)}
            placeholder={UI_COPY.graph.autoUpdateFocusPlaceholder}
            aria-label="graph_auto_update_focus"
          />
        </label>
        {lastAutoUpdateTaskId ? (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="min-w-0 text-subtext">
              {UI_COPY.graph.autoUpdateLastTaskIdLabel}:{" "}
              <span className="font-mono text-ink">{lastAutoUpdateTaskId}</span>
            </div>
            <div className="flex items-center gap-2">
              <Link className="btn btn-secondary" to={taskCenterHref} aria-label="graph_open_task_center">
                {UI_COPY.graph.autoUpdateOpenTaskCenter}
              </Link>
              <button
                className="btn btn-secondary"
                onClick={() =>
                  void copyPreviewBlock(lastAutoUpdateTaskId, {
                    emptyMessage: "没有可复制的 task_id",
                    successMessage: "已复制 task_id",
                    dialogTitle: "复制失败：请手动复制 task_id",
                  })
                }
                type="button"
              >
                {UI_COPY.graph.autoUpdateCopyTaskId}
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {error ? (
        <div className="rounded-atelier border border-border bg-surface p-3 text-xs text-subtext">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              {error.message} ({error.code})
            </div>
            <RequestIdBadge requestId={error.requestId} />
          </div>
        </div>
      ) : null}

      <div className="rounded-atelier border border-border bg-surface p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm text-ink">{UI_COPY.graph.overviewTitle}</div>
          <RequestIdBadge requestId={requestId} />
        </div>
        <div className="mt-1 text-xs text-subtext">
          状态：{statusText} | 节点：{result?.nodes?.length ?? 0} | 关系：{result?.edges?.length ?? 0} | 证据：
          {result?.evidence?.length ?? 0}
        </div>
      </div>

      <DebugDetails title={UI_COPY.graph.injectionPreviewTitle} defaultOpen>
        <div className="flex items-center justify-end">
          <button
            className="btn btn-secondary btn-sm"
            disabled={!injectionPreviewText}
            onClick={() =>
              void copyPreviewBlock(injectionPreviewText, {
                emptyMessage: "没有可复制的注入预览",
                successMessage: "已复制注入预览",
                dialogTitle: "复制失败：请手动复制注入预览",
              })
            }
            type="button"
          >
            {UI_COPY.common.copy}
          </button>
        </div>
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-[11px] leading-4 text-subtext">
          {injectionPreviewText || "（空）"}
        </pre>
      </DebugDetails>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-atelier border border-border bg-surface p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm text-ink">{UI_COPY.graph.nodesTitle}</div>
            <div className="text-xs text-subtext">
              {UI_COPY.graph.matchedLabel}: {(result?.matched?.entity_ids ?? []).length}
              {result?.truncated?.nodes ? " | 已截断（truncated）" : ""}
            </div>
          </div>
          <div className="mt-2 grid gap-2">
            {(result?.nodes ?? []).map((n) => (
              <div
                key={n.id}
                className={
                  "rounded-atelier border border-border p-2 text-xs " +
                  (matchedIds.has(n.id) ? "bg-accent/10 text-ink" : "bg-surface text-subtext")
                }
              >
                <div className="text-ink">
                  [{n.entity_type}] {n.name}
                </div>
                <div className="mt-0.5 text-[11px] text-subtext">{n.id}</div>
              </div>
            ))}
            {(result?.nodes ?? []).length === 0 ? (
              <div className="grid gap-2 text-xs text-subtext">
                <div>暂无节点</div>
                <button
                  className="btn btn-secondary btn-sm w-fit"
                  aria-label="graph_empty_state_run"
                  onClick={() => void runQuery()}
                  disabled={loading}
                  type="button"
                >
                  {loading ? "查询..." : UI_COPY.graph.queryRun}
                </button>
              </div>
            ) : null}
          </div>
        </div>

        <div className="rounded-atelier border border-border bg-surface p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm text-ink">{UI_COPY.graph.relationsTitle}</div>
            <div className="text-xs text-subtext">{result?.truncated?.edges ? "已截断（truncated）" : ""}</div>
          </div>
          <div className="mt-2 grid gap-2">
            {(result?.edges ?? []).map((e) => (
              <div key={e.id} className="rounded-atelier border border-border bg-surface p-2 text-xs">
                <div className="text-ink">
                  {e.from_name || e.from_entity_id} --({e.relation_type})→ {e.to_name || e.to_entity_id}
                </div>
                {e.description_md ? <div className="mt-1 text-subtext">{e.description_md}</div> : null}
                {typeof e.attributes?.context_md === "string" && e.attributes.context_md.trim() ? (
                  <div className="mt-1 whitespace-pre-wrap text-subtext">语境：{e.attributes.context_md}</div>
                ) : null}
                <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
                  <div className="text-[11px] text-subtext">id: {e.id}</div>
                  {projectId ? (
                    <Link
                      className="btn btn-secondary btn-sm"
                      to={`/projects/${projectId}/structured-memory?${(() => {
                        const params = new URLSearchParams();
                        params.set("view", "character-relations");
                        params.set("relationId", String(e.id));
                        if (chapterId) params.set("chapterId", chapterId);
                        return params.toString();
                      })()}`}
                      aria-label={`graph_open_relation_editor_${e.id}`}
                    >
                      打开编辑/证据
                    </Link>
                  ) : null}
                </div>
              </div>
            ))}
            {(result?.edges ?? []).length === 0 ? <div className="text-xs text-subtext">暂无关系</div> : null}
          </div>
        </div>
      </div>

      <div className="rounded-atelier border border-border bg-surface p-3">
        <div className="text-sm text-ink">{UI_COPY.graph.evidenceTitle}</div>
        <div className="mt-2 grid gap-2">
          {(result?.evidence ?? []).slice(0, 12).map((ev) => (
            <div key={ev.id} className="rounded-atelier border border-border bg-surface p-2 text-xs">
              <div className="text-ink">
                来源：{ev.source_type}:{ev.source_id ?? "-"}
              </div>
              <div className="mt-1 text-subtext">{ev.quote_md || "（空）"}</div>
            </div>
          ))}
          {(result?.evidence ?? []).length === 0 ? <div className="text-xs text-subtext">暂无证据</div> : null}
        </div>
      </div>

      <DebugDetails title={UI_COPY.graph.advancedDebugTitle}>
        <div className="flex items-center justify-end">
          <button
            className="btn btn-secondary btn-sm"
            disabled={!result}
            onClick={() =>
              void copyPreviewBlock(advancedDebugText, {
                emptyMessage: "还没有可复制的 Debug JSON",
                successMessage: "已复制 Debug JSON",
                dialogTitle: "复制失败：请手动复制 Debug JSON",
              })
            }
            type="button"
          >
            {UI_COPY.common.copy}
          </button>
        </div>
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap text-[11px] leading-4 text-subtext">
          {advancedDebugText}
        </pre>
      </DebugDetails>
    </DebugPageShell>
  );
}
