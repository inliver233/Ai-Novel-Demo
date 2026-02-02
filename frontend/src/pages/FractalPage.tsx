import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { DebugDetails, DebugPageShell } from "../components/atelier/DebugPageShell";
import { RequestIdBadge } from "../components/ui/RequestIdBadge";
import { ApiError, apiJson } from "../services/apiClient";
import { useToast } from "../components/ui/toast";
import { copyText } from "../lib/copyText";
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
  const [requestId, setRequestId] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<FractalContext | null>(null);

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

  const loadFractal = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiJson<{ result: FractalContext }>(`/api/projects/${projectId}/fractal`);
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
    <DebugPageShell
      title={UI_COPY.fractal.title}
      description={
        <>
          <span className="font-mono">{UI_COPY.fractal.tag}</span>
          <span className="ml-2">{UI_COPY.fractal.subtitle}</span>
        </>
      }
      actions={
        <>
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
        </>
      }
    >
      <DebugDetails title={UI_COPY.help.title}>
        <div className="grid gap-2 text-xs text-subtext">
          <div>{UI_COPY.fractal.usageHint}</div>
          <div className="text-warning">{UI_COPY.fractal.riskHint}</div>
        </div>
      </DebugDetails>

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
          <div className="text-sm text-ink">状态与结论</div>
          <RequestIdBadge requestId={requestId} />
        </div>
        <div className="mt-1 text-xs text-subtext">
          分形记忆：{fractalStatusText} | LLM 摘要：{v2StatusText}
          {result?.updated_at ? ` | 更新时间：${result.updated_at}` : ""}
        </div>
        <div className="mt-1 text-xs text-subtext">{conclusionText}</div>
      </div>

      <div className="rounded-atelier border border-border bg-surface p-3">
        <div className="text-sm text-ink">生成结果预览</div>
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <div className="rounded-atelier border border-border bg-canvas p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm text-ink">确定性（deterministic）</div>
              <div className="flex items-center gap-2 text-xs text-subtext">
                <span className="truncate">{result?.prompt_block?.identifier ?? "-"}</span>
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={!result?.prompt_block?.text_md}
                  onClick={() =>
                    void copyPreviewBlock(result?.prompt_block?.text_md ?? "", {
                      emptyMessage: "没有可复制的确定性预览",
                      successMessage: "已复制确定性预览",
                      dialogTitle: "复制失败：请手动复制确定性预览",
                    })
                  }
                  type="button"
                >
                  {UI_COPY.common.copy}
                </button>
              </div>
            </div>
            <pre className="mt-2 whitespace-pre-wrap break-words text-xs text-ink">
              {result?.prompt_block?.text_md || "（空）"}
            </pre>
          </div>

          <div className="rounded-atelier border border-border bg-canvas p-3">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm text-ink">LLM 摘要（v2）</div>
              <div className="flex items-center gap-2 text-xs text-subtext">
                <span className="truncate">{result?.prompt_block_v2?.identifier ?? "-"}</span>
                <button
                  className="btn btn-ghost btn-sm"
                  disabled={!result?.prompt_block_v2?.text_md}
                  onClick={() =>
                    void copyPreviewBlock(result?.prompt_block_v2?.text_md ?? "", {
                      emptyMessage: "没有可复制的 v2 预览",
                      successMessage: "已复制 v2 预览",
                      dialogTitle: "复制失败：请手动复制 v2 预览",
                    })
                  }
                  type="button"
                >
                  {UI_COPY.common.copy}
                </button>
              </div>
            </div>
            {!v2Enabled ? (
              <div className="mt-2 rounded-atelier border border-border bg-surface p-3 text-xs text-subtext">
                LLM 摘要当前未启用，将回退至确定性结果。原因：{v2?.disabled_reason ?? v2?.status ?? "未知原因"}
                {v2?.error_code ? ` | error_code=${v2.error_code}` : ""}
                {v2?.error_type ? ` | error_type=${v2.error_type}` : ""}
              </div>
            ) : null}
            <pre className="mt-2 whitespace-pre-wrap break-words text-xs text-ink">
              {result?.prompt_block_v2?.text_md || "（空）"}
            </pre>
          </div>
        </div>
      </div>

      <DebugDetails title="高级调试信息">
        <div className="grid gap-2 text-xs text-subtext">
          <div>
            v2_meta: provider={v2?.provider ?? "-"} | model={v2?.model ?? "-"} | latency_ms=
            {typeof v2?.latency_ms === "number" ? String(v2.latency_ms) : "-"} | run_id={v2?.run_id ?? "-"}
          </div>
          {v2?.finish_reason ? <div>v2_finish_reason: {String(v2.finish_reason)}</div> : null}
          {v2?.warnings?.length ? <div>v2_warnings: {v2.warnings.join(" | ")}</div> : null}
          {v2?.dropped_params?.length ? <div>v2_dropped_params: {v2.dropped_params.join(" | ")}</div> : null}
          {v2?.parse_error ? (
            <div className="rounded-atelier border border-border bg-canvas p-3">
              <div className="flex items-center justify-end">
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() =>
                    void copyPreviewBlock(JSON.stringify(v2.parse_error, null, 2), {
                      emptyMessage: "还没有可复制的 parse_error",
                      successMessage: "已复制 parse_error",
                      dialogTitle: "复制失败：请手动复制 parse_error",
                    })
                  }
                  type="button"
                >
                  {UI_COPY.common.copy}
                </button>
              </div>
              <pre className="mt-2 whitespace-pre-wrap break-words text-xs text-ink">
                {JSON.stringify(v2.parse_error, null, 2)}
              </pre>
            </div>
          ) : null}
          <div className="rounded-atelier border border-border bg-canvas p-3">
            <div className="flex items-center justify-end">
              <button
                className="btn btn-secondary btn-sm"
                disabled={!result?.config}
                onClick={() =>
                  void copyPreviewBlock(JSON.stringify(result?.config ?? {}, null, 2), {
                    emptyMessage: "还没有可复制的 config JSON",
                    successMessage: "已复制 config JSON",
                    dialogTitle: "复制失败：请手动复制 config JSON",
                  })
                }
                type="button"
              >
                {UI_COPY.common.copy}
              </button>
            </div>
            <pre className="mt-2 whitespace-pre-wrap break-words text-xs text-ink">
              {JSON.stringify(result?.config ?? {}, null, 2)}
            </pre>
          </div>
        </div>
      </DebugDetails>
    </DebugPageShell>
  );
}
