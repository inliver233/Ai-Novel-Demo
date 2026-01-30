import { apiJson } from "./apiClient";

export type StoryMemory = {
  id: string;
  project_id: string;
  chapter_id?: string | null;
  memory_type: string;
  title?: string | null;
  content: string;
  full_context_md?: string | null;
  importance_score: number;
  tags: string[];
  story_timeline: number;
  text_position: number;
  text_length: number;
  is_foreshadow: boolean;
  resolved_at_chapter_id?: string | null;
  done: boolean;
  created_at?: string | null;
  updated_at?: string | null;
};

export async function createStoryMemory(
  projectId: string,
  body: {
    chapter_id?: string | null;
    memory_type: string;
    title?: string | null;
    content: string;
    full_context_md?: string | null;
    importance_score?: number;
    tags?: string[];
    story_timeline?: number;
    text_position?: number;
    text_length?: number;
    is_foreshadow?: boolean;
  },
): Promise<StoryMemory> {
  const res = await apiJson<{ story_memory: StoryMemory }>(`/api/projects/${projectId}/story_memories`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return res.data.story_memory;
}

export async function updateStoryMemory(
  projectId: string,
  storyMemoryId: string,
  body: Partial<{
    chapter_id: string | null;
    memory_type: string;
    title: string | null;
    content: string;
    full_context_md: string | null;
    importance_score: number;
    tags: string[];
    story_timeline: number;
    text_position: number;
    text_length: number;
    is_foreshadow: boolean;
  }>,
): Promise<StoryMemory> {
  const res = await apiJson<{ story_memory: StoryMemory }>(
    `/api/projects/${projectId}/story_memories/${encodeURIComponent(storyMemoryId)}`,
    {
      method: "PUT",
      body: JSON.stringify(body),
    },
  );
  return res.data.story_memory;
}

export async function deleteStoryMemory(projectId: string, storyMemoryId: string): Promise<string> {
  const res = await apiJson<{ deleted_id: string }>(
    `/api/projects/${projectId}/story_memories/${encodeURIComponent(storyMemoryId)}`,
    {
      method: "DELETE",
    },
  );
  return res.data.deleted_id;
}

export async function mergeStoryMemories(projectId: string, args: { targetId: string; sourceIds: string[] }) {
  return apiJson<{ story_memory: StoryMemory; deleted_ids: string[] }>(
    `/api/projects/${projectId}/story_memories/merge`,
    {
      method: "POST",
      body: JSON.stringify({ target_id: args.targetId, source_ids: args.sourceIds }),
    },
  );
}

export async function markStoryMemoryDone(
  projectId: string,
  storyMemoryId: string,
  done: boolean,
): Promise<StoryMemory> {
  const res = await apiJson<{ story_memory: StoryMemory }>(
    `/api/projects/${projectId}/story_memories/${encodeURIComponent(storyMemoryId)}/mark_done`,
    {
      method: "POST",
      body: JSON.stringify({ done }),
    },
  );
  return res.data.story_memory;
}
