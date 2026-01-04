import { Outlet, useParams } from "react-router-dom";

import { useProjects } from "../../contexts/projects";

export function ProjectProviderGuard() {
  const { projectId } = useParams();
  const { projects, loading, error, refresh } = useProjects();

  if (!projectId) return <Outlet />;
  if (loading) return <div className="text-subtext">加载项目中...</div>;
  if (error) {
    return (
      <div className="panel p-6">
        <div className="font-content text-xl text-ink">项目加载失败</div>
        <div className="mt-2 text-sm text-subtext">{error.message}</div>
        <div className="mt-1 text-xs text-subtext">request_id: {error.requestId}</div>
        <button className="btn btn-secondary mt-4" onClick={() => void refresh()} type="button">
          重试
        </button>
      </div>
    );
  }

  const exists = projects.some((p) => p.id === projectId);
  if (!exists) {
    return (
      <div className="panel p-6">
        <div className="font-content text-xl">项目不存在或无权限</div>
        <div className="mt-2 text-sm text-subtext">请返回 Dashboard 重新选择项目。</div>
      </div>
    );
  }

  return <Outlet />;
}
