import { UI_COPY } from "../../../lib/uiCopy";
import type { MemoryContextPack } from "../types";

export function WorldbookPreviewPanel(props: {
  effectivePack: MemoryContextPack;
  worldbookPreview: { triggered: unknown[]; textMd: string; truncated: boolean };
}) {
  const { effectivePack, worldbookPreview } = props;

  return (
    <div className="panel p-4">
      <div className="text-sm text-ink">{UI_COPY.writing.worldbookSectionTitle}</div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-subtext">
        <span>
          {UI_COPY.worldbook.previewTriggeredPrefix}
          {worldbookPreview.triggered.length}
          {UI_COPY.worldbook.previewTriggeredSuffix}
        </span>
        {worldbookPreview.truncated ? (
          <span className="text-amber-600 dark:text-amber-400">{UI_COPY.worldbook.previewTruncated}</span>
        ) : null}
      </div>

      <details open className="mt-3">
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
              const priority = String(o.priority ?? "");
              return (
                <div key={id || title} className="rounded-atelier border border-border bg-surface p-2 text-xs">
                  <div className="truncate text-ink">{title || id}</div>
                  <div className="mt-1 text-subtext">
                    {reason}
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

