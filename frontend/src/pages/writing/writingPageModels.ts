export type ChapterAutoUpdatesTriggerResult = {
  tasks: Record<string, string | null>;
  chapter_token: string | null;
};

export const CHAPTER_LIST_SIDEBAR_WIDTH_CLASS = "w-[260px]" as const;

export function pickFirstProjectTaskId(tasks: Record<string, string | null> | null | undefined): string | null {
  if (!tasks) return null;
  for (const value of Object.values(tasks)) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

export function buildWritingTaskCenterHref(projectId: string, chapterId?: string | null): string {
  const params = new URLSearchParams();
  if (chapterId) params.set("chapterId", chapterId);
  return `/projects/${projectId}/tasks${params.toString() ? `?${params.toString()}` : ""}`;
}

export function buildProjectTaskCenterHref(projectId?: string, projectTaskId?: string | null): string | null {
  if (!projectId || !projectTaskId) return null;
  return `/projects/${projectId}/tasks?project_task_id=${encodeURIComponent(projectTaskId)}`;
}

export function buildBatchTaskCenterHref(projectId?: string, projectTaskId?: string | null): string | null {
  return buildProjectTaskCenterHref(projectId, projectTaskId);
}
