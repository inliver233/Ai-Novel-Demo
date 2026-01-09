import { apiJson } from "./apiClient";

export type WorldBookPriority = "drop_first" | "optional" | "important" | "must";

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
