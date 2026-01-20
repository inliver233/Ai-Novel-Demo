import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { ApiError, apiJson } from "../services/apiClient";
import { useToast } from "../components/ui/toast";

type PromptBlock = {
  identifier: string;
  role: string;
  text_md: string;
};

type FractalV2Info = {
  enabled?: boolean;
  status?: string;
  disabled_reason?: string;
  summary_md?: string;
  provider?: string;
  model?: string;
  run_id?: string;
  finish_reason?: string | null;
  latency_ms?: number;
  dropped_params?: string[];
  warnings?: string[];
  error_code?: string;
  error_type?: string;
  parse_error?: unknown;
};

type FractalContext = {
  enabled: boolean;
  disabled_reason?: string | null;
  config?: Record<string, unknown>;
  v2?: FractalV2Info;
  prompt_block?: PromptBlock;
  prompt_block_v2?: PromptBlock;
  updated_at?: string;
};

export function FractalPage() {
  const { projectId } = useParams();
  const toast = useToast();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<FractalContext | null>(null);

  const loadFractal = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiJson<{ result: FractalContext }>(`/api/projects/${projectId}/fractal`);
      setResult(res.data?.result ?? null);
    } catch (e) {
      const err =
        e instanceof ApiError ? e : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
      setError(err);
      toast.toastError(`${err.message} (${err.code})`, err.requestId);
    } finally {
      setLoading(false);
    }
  }, [projectId, toast]);

  const rebuild = useCallback(
    async (mode: "deterministic" | "llm_v2") => {
      if (!projectId) return;
      setLoading(true);
      setError(null);
      try {
        const reason = mode === "llm_v2" ? "manual_rebuild_v2" : "manual_rebuild";
        const res = await apiJson<{ result: FractalContext }>(`/api/projects/${projectId}/fractal/rebuild`, {
          method: "POST",
          body: JSON.stringify({ reason, mode }),
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
    },
    [projectId, toast],
  );

  useEffect(() => {
    if (!projectId) return;
    void loadFractal();
  }, [loadFractal, projectId]);

  const v2 = result?.v2 ?? null;
  const v2Enabled = Boolean(v2?.enabled);
  const v2StatusText = v2Enabled
    ? "enabled"
    : v2
      ? `disabled (${v2.disabled_reason ?? v2.status ?? "unknown"})`
      : "disabled (missing)";

  return (
    <div className="grid gap-4">
      <div className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="font-content text-2xl text-ink">Fractal</div>
            <div className="mt-1 text-xs text-subtext">FractalMemory（deterministic + 可选 v2 摘要）预览与回放。</div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn btn-secondary" onClick={() => void loadFractal()} disabled={loading} type="button">
              {loading ? "刷新..." : "刷新"}
            </button>
            <button className="btn btn-secondary" onClick={() => void rebuild("deterministic")} disabled={loading} type="button">
              {loading ? "重建中..." : "重建（deterministic）"}
            </button>
            <button className="btn btn-primary" onClick={() => void rebuild("llm_v2")} disabled={loading} type="button">
              {loading ? "重建中..." : "重建（llm v2）"}
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
            <div className="text-sm text-ink">状态</div>
            <div className="mt-1 text-xs text-subtext">
              fractal: {result?.enabled ? "enabled" : `disabled (${result?.disabled_reason ?? "unknown"})`} | v2:{" "}
              {v2StatusText}
              {result?.updated_at ? ` | updated_at: ${result.updated_at}` : ""}
            </div>
            <div className="mt-1 text-xs text-subtext">
              v2_meta: provider={v2?.provider ?? "-"} | model={v2?.model ?? "-"} | latency_ms=
              {typeof v2?.latency_ms === "number" ? String(v2.latency_ms) : "-"} | run_id={v2?.run_id ?? "-"}
            </div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <div className="rounded-atelier border border-border bg-surface p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm text-ink">Deterministic</div>
                <div className="text-xs text-subtext">{result?.prompt_block?.identifier ?? "-"}</div>
              </div>
              <pre className="mt-2 max-h-96 overflow-auto rounded-atelier border border-border bg-canvas p-3 text-xs text-ink">
                {result?.prompt_block?.text_md || "（空）"}
              </pre>
            </div>
            <div className="rounded-atelier border border-border bg-surface p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm text-ink">LLM v2</div>
                <div className="text-xs text-subtext">{result?.prompt_block_v2?.identifier ?? "-"}</div>
              </div>
              {!v2Enabled ? (
                <div className="mt-2 rounded-atelier border border-border bg-canvas p-3 text-xs text-subtext">
                  v2 当前为 fallback/disabled：{v2?.disabled_reason ?? v2?.status ?? "unknown"}
                  {v2?.error_code ? ` | error_code=${v2.error_code}` : ""}
                  {v2?.error_type ? ` | error_type=${v2.error_type}` : ""}
                </div>
              ) : null}
              <pre className="mt-2 max-h-96 overflow-auto rounded-atelier border border-border bg-canvas p-3 text-xs text-ink">
                {result?.prompt_block_v2?.text_md || "（空）"}
              </pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

