import { apiJson } from "./apiClient";
import type {
  BulkCreateChapterInput,
  ChapterDetail,
  ChapterListItem,
  ChapterMetaPage,
  CreateChapterInput,
  UpdateChapterInput,
} from "../types";

type FetchChapterMetaOptions = {
  outlineId?: string | null;
  cursor?: number | null;
  limit?: number;
};

function buildMetaQuery(options: FetchChapterMetaOptions): string {
  const params = new URLSearchParams();
  if (typeof options.limit === "number" && Number.isFinite(options.limit) && options.limit > 0) {
    params.set("limit", String(Math.floor(options.limit)));
  }
  if (typeof options.cursor === "number" && Number.isFinite(options.cursor) && options.cursor >= 0) {
    params.set("cursor", String(Math.floor(options.cursor)));
  }
  if (options.outlineId) params.set("outline_id", options.outlineId);
  const query = params.toString();
  return query ? `?${query}` : "";
}

function hasText(value: string | null | undefined): boolean {
  return Boolean(value && value.trim());
}

export function chapterDetailToListItem(chapter: ChapterDetail): ChapterListItem {
  return {
    ...chapter,
    has_plan: hasText(chapter.plan),
    has_summary: hasText(chapter.summary),
    has_content: hasText(chapter.content_md),
  };
}

export async function fetchChapterMetaPage(
  projectId: string,
  options: FetchChapterMetaOptions = {},
): Promise<ChapterMetaPage> {
  const res = await apiJson<ChapterMetaPage>(`/api/projects/${projectId}/chapters/meta${buildMetaQuery(options)}`);
  return res.data;
}

export async function fetchAllChapterMeta(
  projectId: string,
  options: Omit<FetchChapterMetaOptions, "cursor"> = {},
): Promise<ChapterListItem[]> {
  const chapters: ChapterListItem[] = [];
  let cursor: number | null = null;
  let pageCount = 0;

  while (pageCount < 50) {
    const page = await fetchChapterMetaPage(projectId, { ...options, cursor });
    chapters.push(...(page.chapters ?? []));
    if (!page.has_more || !page.next_cursor) break;
    cursor = page.next_cursor;
    pageCount += 1;
  }

  return chapters.sort((a, b) => (a.number ?? 0) - (b.number ?? 0));
}

export async function fetchChapterDetail(chapterId: string): Promise<ChapterDetail> {
  const res = await apiJson<{ chapter: ChapterDetail }>(`/api/chapters/${chapterId}`);
  return res.data.chapter;
}

export async function createChapter(projectId: string, payload: CreateChapterInput): Promise<ChapterDetail> {
  const res = await apiJson<{ chapter: ChapterDetail }>(`/api/projects/${projectId}/chapters`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return res.data.chapter;
}

export async function updateChapter(chapterId: string, payload: UpdateChapterInput): Promise<ChapterDetail> {
  const res = await apiJson<{ chapter: ChapterDetail }>(`/api/chapters/${chapterId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return res.data.chapter;
}

export async function deleteChapter(chapterId: string): Promise<void> {
  await apiJson<Record<string, never>>(`/api/chapters/${chapterId}`, { method: "DELETE" });
}

export async function bulkCreateChapters(
  projectId: string,
  payload: BulkCreateChapterInput,
  options: { replace?: boolean } = {},
): Promise<ChapterDetail[]> {
  const params = new URLSearchParams();
  if (options.replace) params.set("replace", "true");
  const query = params.toString();
  const res = await apiJson<{ chapters: ChapterDetail[] }>(
    `/api/projects/${projectId}/chapters/bulk_create${query ? `?${query}` : ""}`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
  return res.data.chapters ?? [];
}
