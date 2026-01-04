import { createContext, useContext } from "react";

import type { Project } from "../types";

export type ProjectsError = {
  code: string;
  message: string;
  requestId: string;
};

export type ProjectsState = {
  projects: Project[];
  loading: boolean;
  error: ProjectsError | null;
  refresh: () => Promise<void>;
};

export const ProjectsContext = createContext<ProjectsState | null>(null);

export function useProjects(): ProjectsState {
  const ctx = useContext(ProjectsContext);
  if (!ctx) throw new Error("useProjects must be used within ProjectsProvider");
  return ctx;
}
