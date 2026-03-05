import { isRouteErrorResponse, useRouteError } from "react-router-dom";

import { isChunkLoadError } from "../lib/lazyImportRetry";

function summarizeError(error: unknown): string {
  if (isRouteErrorResponse(error)) {
    const detail = typeof error.data === "string" ? error.data : "";
    return [String(error.status), error.statusText, detail].filter(Boolean).join(" ");
  }
  if (error instanceof Error) return error.message;
  return String(error ?? "");
}

export function RouteErrorPage() {
  const error = useRouteError();
  const chunkError = isChunkLoadError(error);
  const detail = summarizeError(error);

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <div className="mx-auto flex min-h-screen max-w-screen-md items-center px-4 py-12">
        <div className="surface w-full p-6 sm:p-8">
          <div className="font-content text-2xl text-ink">
            {chunkError ? "页面资源已更新，请刷新重试" : "页面加载失败"}
          </div>
          <div className="mt-2 text-sm text-subtext">
            {chunkError
              ? "检测到前端资源版本切换导致分包加载失败。已尝试自动恢复；如仍失败，请刷新后重试。"
              : "应用遇到异常。你可以刷新页面，或返回首页继续操作。"}
          </div>

          {detail ? (
            <div className="mt-4 rounded-atelier border border-border bg-surface px-3 py-2 text-xs text-subtext">
              {detail}
            </div>
          ) : null}

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <button className="btn btn-primary" onClick={() => window.location.reload()} type="button">
              刷新页面
            </button>
            <button className="btn btn-secondary" onClick={() => window.location.assign("/")} type="button">
              返回首页
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
