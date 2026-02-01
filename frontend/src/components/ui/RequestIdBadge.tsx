import clsx from "clsx";

import { copyText } from "../../lib/copyText";
import { UI_COPY } from "../../lib/uiCopy";

export function RequestIdBadge(props: { requestId?: string | null; className?: string }) {
  const requestId = props.requestId;
  if (!requestId) return null;

  return (
    <div
      className={clsx(
        "inline-flex max-w-full min-w-0 items-center gap-2 rounded-atelier border border-border bg-surface px-2 py-1 text-xs",
        props.className,
      )}
    >
      <span className="shrink-0 text-subtext">{UI_COPY.common.requestIdLabel}</span>
      <span className="atelier-mono min-w-0 truncate text-ink" title={requestId}>
        {requestId}
      </span>
      <button
        className="btn btn-ghost btn-sm shrink-0"
        type="button"
        aria-label="copy_request_id"
        onClick={async () => {
          await copyText(requestId);
        }}
      >
        {UI_COPY.common.copy}
      </button>
    </div>
  );
}
