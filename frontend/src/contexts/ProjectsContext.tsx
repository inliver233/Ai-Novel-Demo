import React, { useCallback, useEffect, useMemo, useState } from "react";

import { apiJson } from "../services/apiClient";
import type { Project } from "../types";
import { ProjectsContext } from "./projects";
import type { ProjectsState } from "./projects";

export function ProjectsProvider(props: { children: React.ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiJson<{ projects: Project[] }>("/api/projects");
      setProjects(res.data.projects);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo<ProjectsState>(() => ({ projects, loading, refresh }), [projects, loading, refresh]);
  return <ProjectsContext.Provider value={value}>{props.children}</ProjectsContext.Provider>;
}
