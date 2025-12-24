import { createContext, useContext } from "react";

import type { Project } from "../types";

export type ProjectsState = {
  projects: Project[];
  loading: boolean;
  refresh: () => Promise<void>;
};

export const ProjectsContext = createContext<ProjectsState | null>(null);

export function useProjects(): ProjectsState {
  const ctx = useContext(ProjectsContext);
  if (!ctx) throw new Error("useProjects must be used within ProjectsProvider");
  return ctx;
}
