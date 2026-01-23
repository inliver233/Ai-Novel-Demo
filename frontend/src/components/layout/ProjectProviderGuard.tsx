import { Link, Outlet, useParams } from "react-router-dom";

import { useProjects } from "../../contexts/projects";
import { UI_COPY } from "../../lib/uiCopy";

export function ProjectProviderGuard() {
  const { projectId } = useParams();
  const { projects, loading, error, refresh } = useProjects();

  if (!projectId) return <Outlet />;
  if (loading) {
    return (
      <div className="panel p-6">
        <div className="text-sm text-subtext">加载项目中...</div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="panel p-6">
        <div className="font-content text-xl text-ink">项目加载失败</div>
        <div className="mt-2 text-sm text-subtext">{error.message}</div>
        {error.requestId ? (
          <div className="mt-1 flex items-center gap-2 text-xs text-subtext">
            <span className="truncate">
              {UI_COPY.common.requestIdLabel}: <span className="font-mono">{error.requestId}</span>
            </span>
            <button
              className="btn btn-ghost px-2 py-1 text-xs"
              onClick={async () => {
                await navigator.clipboard.writeText(error.requestId ?? "");
              }}
              type="button"
            >
              {UI_COPY.common.copy}
            </button>
          </div>
        ) : null}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button className="btn btn-secondary" onClick={() => void refresh()} type="button">
            重试
          </button>
          <Link className="btn btn-ghost" to="/" aria-label="返回首页 (project_guard_back_home)">
            {UI_COPY.nav.backToHome}
          </Link>
        </div>
      </div>
    );
  }

  const exists = projects.some((p) => p.id === projectId);
  if (!exists) {
    return (
      <div className="panel p-6">
        <div className="font-content text-xl text-ink">项目不存在或无权限</div>
        <div className="mt-2 text-sm text-subtext">请返回{UI_COPY.nav.home}重新选择项目，或在左侧切换其他项目。</div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Link className="btn btn-secondary" to="/" aria-label="返回首页 (project_guard_back_home)">
            {UI_COPY.nav.backToHome}
          </Link>
          <button className="btn btn-ghost" onClick={() => void refresh()} type="button">
            重新加载项目列表
          </button>
        </div>
      </div>
    );
  }

  return <Outlet />;
}
