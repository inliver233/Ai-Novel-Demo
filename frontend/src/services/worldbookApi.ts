import { apiJson } from "./apiClient";

export type WorldBookPriority = "drop_first" | "optional" | "important" | "must";

export type ProjectTask = {
  id: string;
  project_id: string;
  actor_user_id?: string | null;
  kind: string;
  status: string;
  idempotency_key?: string | null;
  error_type?: string | null;
  error_message?: string | null;
  timings?: Record<string, unknown>;
  params?: unknown;
  result?: unknown;
  error?: unknown;
};

type PagedResult<T> = { items: T[]; next_before?: string | null };

export type WorldBookEntry = {
  id: string;
  project_id: string;
  title: string;
  content_md: string;
  enabled: boolean;
  constant: boolean;
  keywords: string[];
  exclude_recursion: boolean;
  prevent_recursion: boolean;
  char_limit: number;
  priority: WorldBookPriority;
  updated_at: string;
};

export type WorldBookTriggeredEntry = { id: string; title: string; reason: string; priority: WorldBookPriority };

export type WorldBookPreviewTriggerRequest = {
  query_text: string;
  include_constant: boolean;
  enable_recursion: boolean;
  char_limit: number;
};

export type WorldBookPreviewTriggerResult = {
  triggered: WorldBookTriggeredEntry[];
  text_md: string;
  truncated: boolean;
};

export type WorldBookExportEntryV1 = {
  title: string;
  content_md: string;
  enabled: boolean;
  constant: boolean;
  keywords: string[];
  exclude_recursion: boolean;
  prevent_recursion: boolean;
  char_limit: number;
  priority: WorldBookPriority;
};

export type WorldBookExportAllV1 = {
  schema_version: string;
  entries: WorldBookExportEntryV1[];
};

export type WorldBookImportMode = "merge" | "overwrite";

export type WorldBookImportAllReport = {
  dry_run: boolean;
  mode: WorldBookImportMode;
  created: number;
  updated: number;
  deleted: number;
  skipped: number;
  conflicts: Array<Record<string, unknown>>;
  actions: Array<Record<string, unknown>>;
};

export async function listWorldBookEntries(projectId: string): Promise<WorldBookEntry[]> {
  const res = await apiJson<{ worldbook_entries: WorldBookEntry[] }>(`/api/projects/${projectId}/worldbook_entries`);
  return res.data.worldbook_entries ?? [];
}

export async function createWorldBookEntry(
  projectId: string,
  body: {
    title: string;
    content_md: string;
    enabled: boolean;
    constant: boolean;
    keywords: string[];
    exclude_recursion: boolean;
    prevent_recursion: boolean;
    char_limit: number;
    priority: WorldBookPriority;
  },
): Promise<WorldBookEntry> {
  const res = await apiJson<{ worldbook_entry: WorldBookEntry }>(`/api/projects/${projectId}/worldbook_entries`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return res.data.worldbook_entry;
}

export async function updateWorldBookEntry(
  entryId: string,
  body: Partial<{
    title: string;
    content_md: string;
    enabled: boolean;
    constant: boolean;
    keywords: string[];
    exclude_recursion: boolean;
    prevent_recursion: boolean;
    char_limit: number;
    priority: WorldBookPriority;
  }>,
): Promise<WorldBookEntry> {
  const res = await apiJson<{ worldbook_entry: WorldBookEntry }>(`/api/worldbook_entries/${entryId}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  return res.data.worldbook_entry;
}

export async function deleteWorldBookEntry(entryId: string): Promise<void> {
  await apiJson(`/api/worldbook_entries/${entryId}`, { method: "DELETE" });
}

export async function previewWorldBookTrigger(projectId: string, body: WorldBookPreviewTriggerRequest) {
  return apiJson<WorldBookPreviewTriggerResult>(`/api/projects/${projectId}/worldbook_entries/preview_trigger`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function bulkUpdateWorldBookEntries(
  projectId: string,
  body: {
    entry_ids: string[];
    enabled?: boolean;
    constant?: boolean;
    exclude_recursion?: boolean;
    prevent_recursion?: boolean;
    char_limit?: number;
    priority?: WorldBookPriority;
  },
): Promise<WorldBookEntry[]> {
  const res = await apiJson<{ worldbook_entries: WorldBookEntry[] }>(
    `/api/projects/${projectId}/worldbook_entries/bulk_update`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
  return res.data.worldbook_entries ?? [];
}

export async function bulkDeleteWorldBookEntries(projectId: string, entryIds: string[]): Promise<string[]> {
  const res = await apiJson<{ deleted_ids: string[] }>(`/api/projects/${projectId}/worldbook_entries/bulk_delete`, {
    method: "POST",
    body: JSON.stringify({ entry_ids: entryIds }),
  });
  return res.data.deleted_ids ?? [];
}

export async function duplicateWorldBookEntries(projectId: string, entryIds: string[]): Promise<WorldBookEntry[]> {
  const res = await apiJson<{ worldbook_entries: WorldBookEntry[] }>(
    `/api/projects/${projectId}/worldbook_entries/duplicate`,
    {
      method: "POST",
      body: JSON.stringify({ entry_ids: entryIds }),
    },
  );
  return res.data.worldbook_entries ?? [];
}

export async function exportAllWorldBookEntries(projectId: string): Promise<WorldBookExportAllV1> {
  const res = await apiJson<{ export: WorldBookExportAllV1 }>(
    `/api/projects/${projectId}/worldbook_entries/export_all`,
  );
  return res.data.export;
}

export async function importAllWorldBookEntries(
  projectId: string,
  body: {
    schema_version: string;
    dry_run: boolean;
    mode: WorldBookImportMode;
    entries: WorldBookExportEntryV1[];
  },
): Promise<WorldBookImportAllReport> {
  const res = await apiJson<WorldBookImportAllReport>(`/api/projects/${projectId}/worldbook_entries/import_all`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return res.data;
}

export async function triggerWorldBookAutoUpdate(
  projectId: string,
  chapterId?: string,
): Promise<{ task_id: string; chapter_id?: string | null }> {
  const params = new URLSearchParams();
  if (chapterId) params.set("chapter_id", chapterId);
  const qs = params.toString();
  const res = await apiJson<{ task_id: string; chapter_id?: string | null }>(
    `/api/projects/${projectId}/worldbook_entries/auto_update${qs ? `?${qs}` : ""}`,
    {
      method: "POST",
    },
  );
  return res.data;
}

export async function getLatestWorldBookAutoUpdateTask(projectId: string): Promise<ProjectTask | null> {
  const params = new URLSearchParams();
  params.set("kind", "worldbook_auto_update");
  params.set("limit", "1");
  const res = await apiJson<PagedResult<ProjectTask>>(`/api/projects/${projectId}/tasks?${params.toString()}`);
  const first = res.data.items?.[0];
  if (!first) return null;
  const detail = await apiJson<ProjectTask>(`/api/tasks/${encodeURIComponent(first.id)}`);
  return detail.data;
}

export async function retryProjectTask(taskId: string): Promise<ProjectTask> {
  const res = await apiJson<ProjectTask>(`/api/tasks/${encodeURIComponent(taskId)}/retry`, { method: "POST" });
  return res.data;
}
