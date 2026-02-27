import { UI_COPY } from "../../../lib/uiCopy";
import type { MemoryContextPack } from "../types";

type WorldbookLog = {
  note: string | null;
  budget_char_limit: number | null;
  budget_source: string | null;
  token_estimate: number | null;
  triggered_count: number | null;
  truncated: boolean | null;
};

function extractWorldbookLog(logs: unknown[]): WorldbookLog | null {
  const list = Array.isArray(logs) ? logs : [];
  for (const raw of list) {
    if (!raw || typeof raw !== "object") continue;
    const o = raw as Record<string, unknown>;
    if (String(o.section ?? "") !== "worldbook") continue;
    const budgetRaw = o.budget_char_limit;
    const budgetCharLimit = typeof budgetRaw === "number" ? budgetRaw : Number(budgetRaw);
    const tokenRaw = o.token_estimate;
    const tokenEstimate = typeof tokenRaw === "number" ? tokenRaw : Number(tokenRaw);
    const triggeredCountRaw = o.triggered_count;
    const triggeredCount = typeof triggeredCountRaw === "number" ? triggeredCountRaw : Number(triggeredCountRaw);
    return {
      note: typeof o.note === "string" ? o.note : null,
      budget_char_limit: Number.isFinite(budgetCharLimit) ? budgetCharLimit : null,
      budget_source: typeof o.budget_source === "string" ? o.budget_source : null,
      token_estimate: Number.isFinite(tokenEstimate) ? tokenEstimate : null,
      triggered_count: Number.isFinite(triggeredCount) ? triggeredCount : null,
      truncated: typeof o.truncated === "boolean" ? o.truncated : null,
    };
  }
  return null;
}

export function WorldbookPreviewPanel(props: {
  effectivePack: MemoryContextPack;
  worldbookPreview: { triggered: unknown[]; textMd: string; truncated: boolean };
}) {
  const { effectivePack, worldbookPreview } = props;
  const sectionRaw = (effectivePack.worldbook ?? {}) as Record<string, unknown>;
  const enabled = Boolean(sectionRaw.enabled);
  const disabledReason = typeof sectionRaw.disabled_reason === "string" ? sectionRaw.disabled_reason : null;
  const log = extractWorldbookLog(effectivePack.logs);

  return (
    <div className="panel p-4">
      <div className="text-sm text-ink">{UI_COPY.writing.worldbookSectionTitle}</div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-subtext">
        <span>
          {UI_COPY.worldbook.previewTriggeredPrefix}
          {worldbookPreview.triggered.length}
          {UI_COPY.worldbook.previewTriggeredSuffix}
        </span>
        <span className="flex flex-wrap items-center gap-2">
          {enabled ? (
            <span className="inline-flex rounded-atelier bg-success/10 px-2 py-0.5 text-success">enabled</span>
          ) : (
            <span className="inline-flex rounded-atelier bg-warning/10 px-2 py-0.5 text-warning">
              disabled: {disabledReason ?? "unknown"}
            </span>
          )}
          {log?.budget_char_limit != null ? (
            <span>
              budget:{log.budget_char_limit}
              {log.budget_source ? ` (${log.budget_source})` : ""}
            </span>
          ) : null}
          {log?.token_estimate != null ? <span>tokens≈{log.token_estimate}</span> : null}
          {worldbookPreview.truncated ? (
            <span className="inline-flex rounded-atelier bg-warning/10 px-2 py-0.5 text-warning">
              {UI_COPY.worldbook.previewTruncated}
            </span>
          ) : null}
        </span>
      </div>

      {enabled && worldbookPreview.triggered.length === 0 ? (
        <div className="mt-2 text-xs text-subtext">
          未命中：请检查本章计划/指令里的关键词是否包含条目 keywords/aliases，或将条目设为 constant 以强制注入。
        </div>
      ) : null}

      <details className="mt-3">
        <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
          {UI_COPY.worldbook.previewTriggeredList}
        </summary>
        <div className="mt-2 grid gap-2">
          {worldbookPreview.triggered.length === 0 ? (
            <div className="text-sm text-subtext">{UI_COPY.worldbook.previewNoTriggered}</div>
          ) : (
            worldbookPreview.triggered.map((t) => {
              if (!t || typeof t !== "object") return null;
              const o = t as Record<string, unknown>;
              const id = String(o.id ?? "");
              const title = String(o.title ?? "");
              const reason = String(o.reason ?? "");
              const matchSourceRaw = o.match_source;
              const matchSource = typeof matchSourceRaw === "string" ? matchSourceRaw : "";
              const matchValueRaw = o.match_value;
              const matchValue = typeof matchValueRaw === "string" ? matchValueRaw : "";
              const priority = String(o.priority ?? "");
              const displayReason =
                reason || (matchSource ? (matchValue ? `${matchSource}:${matchValue}` : matchSource) : "");
              return (
                <div key={id || title} className="rounded-atelier border border-border bg-surface p-2 text-xs">
                  <div className="truncate text-ink">{title || id}</div>
                  <div className="mt-1 text-subtext">
                    {displayReason}
                    {priority ? ` | priority:${priority}` : ""}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </details>

      <details className="mt-3">
        <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
          {UI_COPY.worldbook.previewText}
        </summary>
        <pre className="mt-2 max-h-64 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
          {worldbookPreview.textMd || UI_COPY.worldbook.previewTextEmpty}
        </pre>
      </details>

      <details className="mt-3">
        <summary className="ui-transition-fast cursor-pointer text-xs text-subtext hover:text-ink">
          {UI_COPY.writing.contextPreviewRawPack}
        </summary>
        <pre className="mt-2 max-h-64 overflow-auto rounded-atelier border border-border bg-surface p-3 text-xs text-ink">
          {JSON.stringify(effectivePack ?? null, null, 2)}
        </pre>
      </details>
    </div>
  );
}
