import React, { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, apiJson } from "../services/apiClient";
import type { Project } from "../types";
import { ProjectsContext } from "./projects";
import type { ProjectsError } from "./projects";
import type { ProjectsState } from "./projects";

export function ProjectsProvider(props: { children: React.ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ProjectsError | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiJson<{ projects: Project[] }>("/api/projects", { timeoutMs: 15_000 });
      setProjects(res.data.projects ?? []);
    } catch (e) {
      const err = e instanceof ApiError ? e : null;
      setError({
        code: err?.code ?? "UNKNOWN_ERROR",
        message: err?.message ?? "加载项目失败，请稍后重试",
        requestId: err?.requestId ?? "unknown",
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo<ProjectsState>(
    () => ({ projects, loading, error, refresh }),
    [projects, loading, error, refresh],
  );
  return <ProjectsContext.Provider value={value}>{props.children}</ProjectsContext.Provider>;
}
