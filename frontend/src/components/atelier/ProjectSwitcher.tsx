import { useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useProjects } from "../../contexts/projects";

export function ProjectSwitcher() {
  const { projects, loading } = useProjects();
  const { projectId } = useParams();
  const navigate = useNavigate();

  const selected = useMemo(() => {
    if (projectId) return projectId;
    return "";
  }, [projectId]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="text-xs text-subtext">当前项目</div>
        <Link className="text-xs text-accent hover:underline" to="/">
          Dashboard
        </Link>
      </div>
      <select
        className="w-full rounded-atelier border border-border bg-canvas px-3 py-2 text-sm text-ink"
        disabled={loading || projects.length === 0}
        name="project_switcher"
        value={selected}
        onChange={(e) => {
          const id = e.target.value;
          if (!id) return;
          navigate(`/projects/${id}/writing`);
        }}
      >
        <option value="" disabled>
          {projects.length === 0 ? "暂无项目" : "请选择项目"}
        </option>
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
    </div>
  );
}
