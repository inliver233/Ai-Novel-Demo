import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { DebugDetails, DebugPageShell } from "../components/atelier/DebugPageShell";
import { UI_COPY } from "../lib/uiCopy";
import { ApiError, apiJson } from "../services/apiClient";
import { useToast } from "../components/ui/toast";

type GraphNode = {
  id: string;
  entity_type: string;
  name: string;
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
};

type GraphEvidence = {
  id: string;
  source_type: string;
  source_id?: string | null;
  quote_md: string;
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

  const [enabled, setEnabled] = useState(true);
  const [queryText, setQueryText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<GraphQueryResult | null>(null);

  const matchedIds = useMemo(() => new Set(result?.matched?.entity_ids ?? []), [result?.matched?.entity_ids]);

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
        </>
      }
    >
      <DebugDetails title={UI_COPY.help.title}>
        <div className="grid gap-2 text-xs text-subtext">
          <div>{UI_COPY.graph.usageHint}</div>
          <div>{UI_COPY.graph.exampleHint}</div>
          <div className="text-amber-700 dark:text-amber-300">{UI_COPY.graph.riskHint}</div>
        </div>
      </DebugDetails>

      <label className="block">
        <div className="text-xs text-subtext">{UI_COPY.graph.queryTextLabel}</div>
        <input
          className="mt-1 w-full rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink"
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

      {error ? (
        <div className="rounded-atelier border border-border bg-surface p-3 text-xs text-subtext">
          {error.message} ({error.code}) {error.requestId ? `| request_id: ${error.requestId}` : ""}
        </div>
      ) : null}

      <div className="rounded-atelier border border-border bg-surface p-3">
        <div className="text-sm text-ink">{UI_COPY.graph.overviewTitle}</div>
        <div className="mt-1 text-xs text-subtext">
          状态：{statusText} | 节点：{result?.nodes?.length ?? 0} | 关系：{result?.edges?.length ?? 0} | 证据：
          {result?.evidence?.length ?? 0}
        </div>
      </div>

      <DebugDetails title={UI_COPY.graph.injectionPreviewTitle} defaultOpen>
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-[11px] leading-4 text-subtext">
          {result?.prompt_block?.text_md || "（空）"}
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
            {(result?.nodes ?? []).length === 0 ? <div className="text-xs text-subtext">暂无节点</div> : null}
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
        <pre className="max-h-80 overflow-auto whitespace-pre-wrap text-[11px] leading-4 text-subtext">
          {safeJson(result)}
        </pre>
      </DebugDetails>
    </DebugPageShell>
  );
}
