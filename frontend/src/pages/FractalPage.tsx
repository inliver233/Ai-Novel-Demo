import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { ApiError, apiJson } from "../services/apiClient";
import { useToast } from "../components/ui/toast";
import { UI_COPY } from "../lib/uiCopy";

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
        e instanceof ApiError
          ? e
          : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
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
          e instanceof ApiError
            ? e
            : new ApiError({ code: "UNKNOWN", message: String(e), requestId: "unknown", status: 0 });
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
  const fractalEnabled = Boolean(result?.enabled);
  const fractalStatusText = result
    ? fractalEnabled
      ? "已启用"
      : `未启用（${result.disabled_reason ?? "unknown"}）`
    : "未加载";
  const v2StatusText = result
    ? v2Enabled
      ? "已启用"
      : v2
        ? `未启用（${v2.disabled_reason ?? v2.status ?? "unknown"}）`
        : "未启用（missing）"
    : "未加载";
  const conclusionText = result
    ? !fractalEnabled
      ? "结论：分形记忆当前不可用（未构建或被禁用）。"
      : v2Enabled
        ? "结论：当前注入将优先使用 LLM 摘要（v2）。"
        : "结论：当前注入将使用确定性结果（deterministic）。"
    : "结论：尚未加载分形记忆结果。";

  return (
    <div className="grid gap-4">
      <div className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="font-content text-2xl text-ink">{UI_COPY.fractal.title}</div>
            <div className="mt-1 text-xs text-subtext">
              <span className="font-mono">{UI_COPY.fractal.tag}</span>
              <span className="ml-2">{UI_COPY.fractal.subtitle}</span>
            </div>
            <div className="mt-3 rounded-atelier border border-border bg-canvas p-3 text-xs text-subtext">
              <div>{UI_COPY.fractal.usageHint}</div>
              <div className="mt-1">{UI_COPY.fractal.riskHint}</div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn btn-secondary" onClick={() => void loadFractal()} disabled={loading} type="button">
              {loading ? "刷新..." : "刷新"}
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => void rebuild("deterministic")}
              disabled={loading}
              type="button"
            >
              {loading ? "重建中..." : "重建（确定性）"}
            </button>
            <button className="btn btn-primary" onClick={() => void rebuild("llm_v2")} disabled={loading} type="button">
              {loading ? "重建中..." : "重建（LLM 摘要）"}
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
            <div className="text-sm text-ink">状态与结论</div>
            <div className="mt-1 text-xs text-subtext">
              分形记忆：{fractalStatusText} | LLM 摘要：{v2StatusText}
              {result?.updated_at ? ` | updated_at: ${result.updated_at}` : ""}
            </div>
            <div className="mt-1 text-xs text-subtext">{conclusionText}</div>
          </div>

          <div className="rounded-atelier border border-border bg-surface p-3">
            <div className="text-sm text-ink">生成结果预览</div>
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              <div className="rounded-atelier border border-border bg-canvas p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm text-ink">确定性（deterministic）</div>
                  <div className="text-xs text-subtext">{result?.prompt_block?.identifier ?? "-"}</div>
                </div>
                <pre className="mt-2 max-h-96 overflow-auto text-xs text-ink">
                  {result?.prompt_block?.text_md || "（空）"}
                </pre>
              </div>

              <div className="rounded-atelier border border-border bg-canvas p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm text-ink">LLM 摘要（v2）</div>
                  <div className="text-xs text-subtext">{result?.prompt_block_v2?.identifier ?? "-"}</div>
                </div>
                {!v2Enabled ? (
                  <div className="mt-2 rounded-atelier border border-border bg-surface p-3 text-xs text-subtext">
                    LLM 摘要当前未启用，将回退至确定性结果。原因：{v2?.disabled_reason ?? v2?.status ?? "unknown"}
                    {v2?.error_code ? ` | error_code=${v2.error_code}` : ""}
                    {v2?.error_type ? ` | error_type=${v2.error_type}` : ""}
                  </div>
                ) : null}
                <pre className="mt-2 max-h-96 overflow-auto text-xs text-ink">
                  {result?.prompt_block_v2?.text_md || "（空）"}
                </pre>
              </div>
            </div>
          </div>

          <details className="rounded-atelier border border-border bg-surface p-3">
            <summary className="cursor-pointer select-none text-sm text-ink">高级调试信息</summary>
            <div className="mt-2 grid gap-2 text-xs text-subtext">
              <div>
                v2_meta: provider={v2?.provider ?? "-"} | model={v2?.model ?? "-"} | latency_ms=
                {typeof v2?.latency_ms === "number" ? String(v2.latency_ms) : "-"} | run_id={v2?.run_id ?? "-"}
              </div>
              {v2?.finish_reason ? <div>v2_finish_reason: {String(v2.finish_reason)}</div> : null}
              {v2?.warnings?.length ? <div>v2_warnings: {v2.warnings.join(" | ")}</div> : null}
              {v2?.dropped_params?.length ? <div>v2_dropped_params: {v2.dropped_params.join(" | ")}</div> : null}
              {v2?.parse_error ? (
                <pre className="max-h-64 overflow-auto rounded-atelier border border-border bg-canvas p-3 text-xs text-ink">
                  {JSON.stringify(v2.parse_error, null, 2)}
                </pre>
              ) : null}
              <pre className="max-h-64 overflow-auto rounded-atelier border border-border bg-canvas p-3 text-xs text-ink">
                {JSON.stringify(result?.config ?? {}, null, 2)}
              </pre>
            </div>
          </details>
        </div>
      </div>
    </div>
  );
}
