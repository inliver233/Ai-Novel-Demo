import { Outlet, useParams } from "react-router-dom";

import { useProjects } from "../../contexts/projects";

export function ProjectProviderGuard() {
  const { projectId } = useParams();
  const { projects, loading } = useProjects();

  if (!projectId) return <Outlet />;
  if (loading) return <div className="text-subtext">加载项目中...</div>;

  const exists = projects.some((p) => p.id === projectId);
  if (!exists) {
    return (
      <div className="rounded-atelier border border-border bg-surface p-6">
        <div className="font-content text-xl">项目不存在或无权限</div>
        <div className="mt-2 text-sm text-subtext">请返回 Dashboard 重新选择项目。</div>
      </div>
    );
  }

  return <Outlet />;
}
