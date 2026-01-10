import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

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
        e instanceof ApiError ? e : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
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

  return (
    <div className="grid gap-4">
      <div className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="font-content text-2xl text-ink">图谱</div>
            <div className="mt-1 text-xs text-subtext">GraphContext（命中实体 + 1-hop 扩散）与回放。</div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-xs text-subtext">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                aria-label="graph_enabled"
              />
              启用
            </label>
            <button className="btn btn-secondary" onClick={() => void runQuery()} disabled={loading} type="button">
              {loading ? "查询..." : "查询"}
            </button>
          </div>
        </div>

        <div className="mt-3 grid gap-3">
          <label className="block">
            <div className="text-xs text-subtext">query_text</div>
            <input
              className="mt-1 w-full rounded-atelier border border-border bg-surface px-3 py-2 text-sm text-ink"
              value={queryText}
              onChange={(e) => setQueryText(e.target.value)}
              placeholder="输入章节文本或关键片段（命中实体名/别名）"
              aria-label="graph_query_text"
            />
          </label>

          {error ? (
            <div className="rounded-atelier border border-border bg-surface p-3 text-xs text-subtext">
              {error.message} ({error.code}) {error.requestId ? `| request_id: ${error.requestId}` : ""}
            </div>
          ) : null}

          <div className="rounded-atelier border border-border bg-surface p-3">
            <div className="text-sm text-ink">GraphContext（注入预览）</div>
            <div className="mt-1 text-xs text-subtext">
              status: {result?.enabled ? "enabled" : `disabled (${result?.disabled_reason ?? "unknown"})`} | nodes:{" "}
              {result?.nodes?.length ?? 0} | edges: {result?.edges?.length ?? 0} | evidence: {result?.evidence?.length ?? 0}
            </div>
            <pre className="mt-2 max-h-64 overflow-auto rounded-atelier border border-border bg-canvas p-3 text-xs text-ink">
              {result?.prompt_block?.text_md || "（空）"}
            </pre>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <div className="rounded-atelier border border-border bg-surface p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm text-ink">Nodes</div>
                <div className="text-xs text-subtext">
                  matched: {(result?.matched?.entity_ids ?? []).length}
                  {result?.truncated?.nodes ? " | truncated" : ""}
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
                {(result?.nodes ?? []).length === 0 ? <div className="text-xs text-subtext">nodes: 0</div> : null}
              </div>
            </div>

            <div className="rounded-atelier border border-border bg-surface p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm text-ink">Edges</div>
                <div className="text-xs text-subtext">{result?.truncated?.edges ? "truncated" : " "}</div>
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
                {(result?.edges ?? []).length === 0 ? <div className="text-xs text-subtext">edges: 0</div> : null}
              </div>
            </div>
          </div>

          <div className="rounded-atelier border border-border bg-surface p-3">
            <div className="text-sm text-ink">Evidence（source_id 命中节点/边）</div>
            <div className="mt-2 grid gap-2">
              {(result?.evidence ?? []).slice(0, 12).map((ev) => (
                <div key={ev.id} className="rounded-atelier border border-border bg-surface p-2 text-xs">
                  <div className="text-ink">
                    {ev.source_type}:{ev.source_id ?? "-"}
                  </div>
                  <div className="mt-1 text-subtext">{ev.quote_md || "（空）"}</div>
                </div>
              ))}
              {(result?.evidence ?? []).length === 0 ? <div className="text-xs text-subtext">evidence: 0</div> : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
